#!/usr/bin/env python3
"""Gate the cached packed-envelope runtime model."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
sys.path.insert(0, str(PERKY))

import noise_tone_tables as packed  # noqa:E402
import noise_tone_envelope_cache as cachemod  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_cache_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")


def main() -> None:
    if cachemod.CACHE_WORDS_PER_VOICE != 17:
        raise AssertionError("envelope cache footprint drifted")
    if 4 * (41 + cachemod.CACHE_WORDS_PER_VOICE) + 4 != 236:
        raise AssertionError("four voices + envelope caches + RNG must use 236 X words")

    for which, values in enumerate((fab.envelope_linear(), fab.envelope_ease()), 1):
        table = packed.pack_envelope(values)

        # Sequential traversal should decode exactly 128 blocks, once each.
        c = cachemod.EnvelopeCache()
        got = [cachemod.envelope_at_cached(table, i, c) for i in range(len(values))]
        if got != values:
            at = next(i for i, (a, b) in enumerate(zip(got, values)) if a != b)
            raise AssertionError(f"curve {which} sequential index {at}: {got[at]} != {values[at]}")
        if c.decode_count != 128:
            raise AssertionError(f"curve {which}: sequential decode count {c.decode_count} != 128")

        # Repeated hits within one block must not cause another decode.
        c = cachemod.EnvelopeCache()
        for _ in range(100):
            for i in (64, 79, 65, 70, 78, 64):
                if cachemod.envelope_at_cached(table, i, c) != values[i]:
                    raise AssertionError("same-block lookup mismatch")
        if c.decode_count != 1:
            raise AssertionError(f"curve {which}: same-block sequence decoded {c.decode_count} times")

        # Random accesses: exact values, and decode count exactly equals the
        # number of block changes in the sequence.
        r = random.Random(0x504B5945 + which)
        indices = [r.randrange(len(values)) for _ in range(5000)]
        c = cachemod.EnvelopeCache()
        expected_decodes = 0
        last = None
        for i in indices:
            block = i // 16
            if block != last:
                expected_decodes += 1
                last = block
            got = cachemod.envelope_at_cached(table, i, c)
            if got != values[i]:
                raise AssertionError(f"curve {which} random index {i}: {got} != {values[i]}")
        if c.decode_count != expected_decodes:
            raise AssertionError(
                f"curve {which}: random decode count {c.decode_count} != {expected_decodes}"
            )

    print(
        "PERKY envelope cache: PASS "
        "(17 words/voice; four voices + caches + RNG = 236 X words; "
        "exact sequential/same-block/random access)"
    )


if __name__ == "__main__":
    main()
