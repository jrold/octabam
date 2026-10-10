#!/usr/bin/env python3
"""Gate final Perky ColdFire persistent RAM and deterministic runtime init.

The platform loader reserves a fixed DRAM slice for all ``dram=True`` linked
units. It loads .text/.rodata/.data but intentionally does not clear .bss, so
BSS-resident state must be explicitly initialized before first use. This gate
prices the 32-bit MCF54455 C layout, pins the firmware-asset footprint, and
requires a loaded non-zero .data cookie to force the first pk4_init().
"""
from __future__ import annotations

import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky")]
from remix import arena  # noqa:E402
import perky_cf_assets  # noqa:E402

PERKY = ROOT / "modules/perky"
CONTROL_BYTES_32 = 24
TRACKS = 4
STACK_SCRATCH_MAX = 256


def macro(path: Path, name: str) -> int:
    text = path.read_text()
    m = re.search(rf"^#define\s+{re.escape(name)}\s+(0x[0-9a-fA-F]+|\d+)u?\b", text, re.M)
    if not m:
        raise AssertionError(f"missing {name} in {path}")
    return int(m.group(1), 0)


def align4(n: int) -> int:
    return (n + 3) & ~3


def main() -> None:
    fold1 = macro(PERKY / "cf_fold.h", "PK_CF_FOLD1_STATE_BYTES")
    fold2 = macro(PERKY / "cf_fold.h", "PK_CF_FOLD2_STATE_BYTES")
    karplus = macro(PERKY / "cf_karplus.h", "PK_CF_KARPLUS_STATE_BYTES")
    nt = macro(PERKY / "cf_noise_tone.h", "PK_CF_NT_STATE_BYTES")
    res = macro(PERKY / "cf_resonant.h", "PK_CF_RES_SNARE_STATE_BYTES")
    nh = macro(PERKY / "cf_noise_hat.h", "PK_CF_NH_WRAPPER_BYTES")
    sd = macro(PERKY / "cf_simple_drum.h", "PK_CF_SD_STATE_BYTES")
    cd = macro(PERKY / "cf_complex_drum.h", "PK_CF_CD_STATE_BYTES")
    slap = macro(PERKY / "cf_slap.h", "PK_CF_SLAP_STATE_BYTES")
    wt = macro(PERKY / "cf_wavetable.h", "PK_CF_WT_STATE_BYTES")

    # Frozen 32-bit MCF54455 layout: one engine object per Algo/Mode
    # (fold1, fold2, karplus, nt_m1, nt_shared, res_snare, res_bass, res_nt),
    # eight pk4_control blocks per track, two RNG u32s and three trailing
    # bytes; max member alignment is 4. The resonant family keeps one object
    # per panel mode, and its bass object is the 0x1d4 family size.
    state = fold1 + fold2 + karplus + 2 * nt + 2 * res + nt + nh + sd + cd + slap + wt
    track = align4(align4(state) + 12 * CONTROL_BYTES_32 + 8 + 3)
    engine = align4(TRACKS * track + 4)  # const pk4_assets *assets
    assets_struct = 4 * 4 + 4 * (4 + 4) + 4 + 4 + 4 + 4 + 4 + 4
    asset_bytes = sum(size for _label, _address, size, _sha in perky_cf_assets.ASSETS)
    persistent_known = engine + assets_struct + asset_bytes
    reserve = arena.PLATFORM_PAGES * arena.PAGE

    if (fold1, fold2, karplus, nt, res, nh, sd, cd, slap, wt) != (0xF4, 0x134, 0x10E0, 0x120, 0x1D4, 0x2DF8, 0x120, 0x140, 0x2670, 0x150):
        raise AssertionError(
            f"final state-size drift: fold1={fold1:#x} fold2={fold2:#x} "
            f"karplus={karplus:#x} nt={nt:#x} res={res:#x} nh={nh:#x} sd={sd:#x} cd={cd:#x} slap={slap:#x}"
        )
    if (track, engine, assets_struct, asset_bytes) != (29524, 118100, 72, 224284):
        raise AssertionError(
            f"final CF layout drift: track={track} engine={engine} "
            f"assets_struct={assets_struct} asset_bytes={asset_bytes}"
        )
    if persistent_known + STACK_SCRATCH_MAX >= reserve:
        raise AssertionError("Perky persistent data no longer fits platform reserve")

    source = (PERKY / "control_cf_final.c").read_text()
    required = (
        "static pk4_engine pk_final_engine;",
        "#define PK_FINAL_RUNTIME_COLD 0x504b434fu",
        "#define PK_FINAL_RUNTIME_READY 0x504b5244u",
        "static uint32_t pk_final_runtime_cookie = PK_FINAL_RUNTIME_COLD;",
        "pk_final_runtime_cookie != PK_FINAL_RUNTIME_READY",
        "pk4_init(&pk_final_engine, &pk_final_assets);",
        "pk_final_runtime_cookie = PK_FINAL_RUNTIME_READY;",
    )
    for needle in required:
        if needle not in source:
            raise AssertionError(f"runtime-init contract drifted: missing {needle!r}")

    margin = reserve - persistent_known - STACK_SCRATCH_MAX
    print(
        "PERKY CF runtime memory: PASS "
        f"(32-bit track={track:,} B; engine={engine:,} B; "
        f"firmware assets={asset_bytes:,} B; asset view={assets_struct} B; "
        f"callback scratch<={STACK_SCRATCH_MAX} B; "
        f"known total<={persistent_known + STACK_SCRATCH_MAX:,}/{reserve:,} B; "
        f"known margin={margin:,} B; deterministic .data init cookie required)"
    )


if __name__ == "__main__":
    main()
