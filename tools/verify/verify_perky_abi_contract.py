#!/usr/bin/env python3
"""Freeze the PERKY Noise/Tone shipping-state/table ABI in one gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "tools"),
    str(ROOT / "tools/perky"),
    str(ROOT / "modules/perky"),
]

import noise_tone_compact as compact  # noqa:E402
import noise_tone_envelope_cache as cachemod  # noqa:E402
import build_noise_tone_payload as payload  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


manifest_mod = load_module("perky_abi_manifest", ROOT / "modules/perky/manifest.py")
fab = load_module(
    "perky_abi_fixture_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    # Live X-state ABI.
    expect(compact.WORDS_PER_VOICE == 41, "compact voice must remain 41 words")
    expect(cachemod.CACHE_WORDS_PER_VOICE == 17, "envelope cache must remain 17 words")
    expect(cachemod.CURVE_SHIFT == 7, "cache key must use bit 7 as curve selector")
    expect(cachemod.BLOCK_MASK == 0x7F, "cache key must retain 7-bit block id")
    expect(payload.X_BASE == 0x3800, "packed state X base drifted")
    expect(payload.VOICES == 4, "one DSP core must own four PERKY voices")
    expect(payload.CACHE_WORDS == 17, "payload cache stride drifted")
    expect(payload.RNG_WORDS == 4, "shared RNG must remain four 16-bit limbs")
    expect(payload.STATE_INIT_WORDS == 236, "shipping X state must remain 236 words")

    # Manifest ownership.
    module = manifest_mod.MODULE
    # Upstream removed the module-level ArenaReserve.  The probe is ROM-only,
    # so its four 256 KiB preboot upload windows are reserved by
    # tools/build/build_perky_tables.py (install_reservation) rather than by a
    # manifest declaration; all this gate still fixes on the manifest is that
    # it claims no module DRAM region of its own.
    expect(not getattr(module, "dram_regions", ()),
           "PERKY's probe must claim no module DRAM region")

    ranges = {(r.space, r.start, r.length, r.what) for r in module.claims.dsp_ranges}
    expect(
        ("x", 0x3800, 236, "PERKY compact voice state + envelope caches + RNG") in ranges,
        "manifest lost the 236-word X-state claim",
    )
    expect(
        ("x", 0x38EC, 2, "PERKY source event-offset and admission staging") in ranges,
        "manifest lost the source event staging claim",
    )
    expect(
        ("x", 0x3900, 0x64, "PERKY shared sparse source-render scratch") in ranges,
        "manifest lost the 100-word sparse scratch claim",
    )
    expect(
        ("y", 0x07a5, 0x1000 - 0x07a5, "PERKY packed Noise/Tone tables") in ranges,
        "manifest lost the private-Y table claim",
    )

    # Build the exact development payload.
    with tempfile.TemporaryDirectory(prefix="perky-abi.") as td:
        td = Path(td)
        raw = td / "raw"
        packed = td / "packed"
        fab.emit_tables(raw)
        layout = payload.build(raw, packed)
        state_words = [int(x, 16) for x in (packed / "state_init.words").read_text().split()]

    expect(layout["synthetic"] is True, "ABI gate must use explicit synthetic fixture")
    expect(layout["total_words"] == 1975, "synthetic Y payload must remain 1975 words")
    expect(layout["waves"]["offset_words"] == 0, "wave stream must lead the Y payload")
    expect(layout["waves"]["words"] == 683, "packed waves must remain 683 Y words")

    envs = layout["envelopes"]
    expect(len(envs) == 2, "Noise/Tone must expose two packed envelope curves")
    expect(
        (envs[0]["offset_words"], envs[0]["words"], envs[0]["delta_bits"]) == (683, 646, 7),
        "synthetic envelope 1 layout drifted",
    )
    expect(
        (envs[1]["offset_words"], envs[1]["words"], envs[1]["delta_bits"]) == (1329, 646, 7),
        "synthetic envelope 2 layout drifted",
    )

    ybase = 0x07a5
    expect(ybase + 683 == 0x0A50, "env1 absolute Y base must be $0A50")
    expect(ybase + 1329 == 0x0CD6, "env2 absolute Y base must be $0CD6")
    expect(ybase + layout["total_words"] - 1 == 0x0F5B, "synthetic table payload must end at $0F5B")

    xi = layout["x_init"]
    expect(xi["base_word"] == 0x3800, "state-init metadata X base drifted")
    expect(xi["words"] == 236, "state-init metadata size drifted")
    expect(xi["voices"] == 4 and xi["voice_words"] == 41, "state-init voice geometry drifted")
    expect(xi["cache_words_per_voice"] == 17, "state-init cache geometry drifted")
    expect(xi["rng_words"] == 4, "state-init RNG geometry drifted")
    expect(len(state_words) == 236, "state_init.words length drifted")

    stride = compact.WORDS_PER_VOICE + cachemod.CACHE_WORDS_PER_VOICE
    for voice in range(4):
        key_index = voice * stride + compact.WORDS_PER_VOICE
        expect(state_words[key_index] == 0xFFFF, f"voice {voice} cache key must boot invalid")
        expect(
            state_words[key_index + 1:key_index + 17] == [0] * 16,
            f"voice {voice} cache values must boot zeroed",
        )

    rng_index = 4 * stride
    expect(state_words[rng_index:rng_index + 4] == [1, 0, 0, 0], "shared RNG init drifted")

    print(
        "PERKY ABI contract: PASS "
        "(4 x (41 voice + 17 cache) + 4 RNG = 236 X words at $3800; "
        "event $38EC; sparse scratch $3900..$3963; "
        "1975 packed Y words at $07a5..$0F5B; env bases $0A50/$0CD6)"
    )


if __name__ == "__main__":
    main()
