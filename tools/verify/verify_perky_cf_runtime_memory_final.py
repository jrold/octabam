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
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky")]
from remix import arena  # noqa:E402
import perky_cf_assets  # noqa:E402

PERKY = ROOT / "modules/perky"
CONTROL_BYTES_32 = 24
TRACKS = 4


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

    # Historical hand arithmetic is retained below only to explain its error.
    # Actual m68k layout uses two-byte member alignment. Do not infer a target
    # sizeof or a stack ceiling from the host ABI.
    # One engine object per Algo/Mode
    # (fold1, fold2, karplus, nt_m1, nt_shared, res_snare, res_bass, res_nt),
    # thirteen pk4_control blocks per track, two RNG u32s and three trailing
    # bytes; max member alignment is 4. The resonant family keeps one object
    # per panel mode, and its bass object is the 0x1d4 family size.
    state = fold1 + fold2 + karplus + 2 * nt + 2 * res + nt + nh + sd + cd + slap + wt
    # 13 pk4_control blocks, two RNG u32s, the uint16 initialised-engine mask
    # and the active algo/mode bytes.
    track = align4(align4(state) + 13 * CONTROL_BYTES_32 + 8 + 2 + 1 + 1)
    # const pk4_assets *assets, then the uint16 noise-hat hold pair.
    engine = align4(TRACKS * track + 4 + 4)
    assets_struct = 4 * 4 + 4 * (4 + 4) + 4 + 4 + 4 + 4 + 4 + 4
    asset_bytes = sum(size for _label, _address, size, _sha in perky_cf_assets.ASSETS)
    reserve = arena.PLATFORM_PAGES * arena.PAGE

    if (fold1, fold2, karplus, nt, res, nh, sd, cd, slap, wt) != (0xF4, 0x134, 0x10E0, 0x120, 0x1D4, 0x2DF8, 0x120, 0x140, 0x2670, 0x150):
        raise AssertionError(
            f"final state-size drift: fold1={fold1:#x} fold2={fold2:#x} "
            f"karplus={karplus:#x} nt={nt:#x} res={res:#x} nh={nh:#x} sd={sd:#x} cd={cd:#x} slap={slap:#x}"
        )
    sys.path.insert(0, str(PERKY))
    from generate_cf_final import FLAGS
    with tempfile.TemporaryDirectory(prefix='perky-layout-') as directory:
        source, obj = Path(directory)/'layout.c', Path(directory)/'layout.o'
        source.write_text('#include "cf_perky4.h"\n'
                          'unsigned char measured_track[sizeof(pk4_track)];\n'
                          'unsigned char measured_engine[sizeof(pk4_engine)];\n'
                          'unsigned char measured_assets[sizeof(pk4_assets)];\n')
        subprocess.run(['m68k-elf-gcc', *FLAGS, '-I', str(PERKY), '-c', str(source), '-o', str(obj)], check=True)
        symbols = subprocess.check_output(['m68k-elf-nm', '-S', str(obj)], text=True)
    sizes = {name:int(size,16) for size,name in re.findall(r'\b[0-9a-f]+\s+([0-9a-f]+)\s+\w\s+(measured_\w+)', symbols)}
    track, engine, assets_struct = (sizes['measured_'+n] for n in ('track','engine','assets'))
    persistent_known = engine + assets_struct + asset_bytes
    if persistent_known >= reserve:
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
        "static uint32_t pk_final_pcm_cookie = PK_FINAL_PCM_COLD;",
        "pk_final_pcm_cookie != PK_FINAL_PCM_READY",
        "pk_cf_rice_unpack_le(pk_asset_pcm_rice,",
        "pk_final_pcm_cookie = PK_FINAL_PCM_READY;",
    )
    for needle in required:
        if needle not in source:
            raise AssertionError(f"runtime-init contract drifted: missing {needle!r}")

    margin = reserve - persistent_known
    print(
        "PERKY CF runtime memory: PASS "
        f"(32-bit track={track:,} B; engine={engine:,} B; "
        f"firmware assets={asset_bytes:,} B; asset view={assets_struct} B; "
        f"stack requires separate target measurement; "
        f"known data subtotal={persistent_known:,}/{reserve:,} B; "
        f"reserve minus data={margin:,} B, not available machine RAM; deterministic .data init cookies required)"
    )


if __name__ == "__main__":
    main()
