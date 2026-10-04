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
        raise AssertionError("four voices + one cache each + RNG must use 236 X words")

    curves = (fab.envelope_linear(), fab.envelope_ease())
    tables = [packed.pack_envelope(values) for values in curves]

    for which, (values, table) in enumerate(zip(curves, tables)):
        # Sequential traversal should decode exactly 128 blocks, once each.
        c = cachemod.EnvelopeCache()
        got = [cachemod.envelope_at_cached(table, i, c, curve_id=which)
               for i in range(len(values))]
        if got != values:
            at = next(i for i, (a, b) in enumerate(zip(got, values)) if a != b)
            raise AssertionError(f"curve {which} sequential index {at}: {got[at]} != {values[at]}")
        if c.decode_count != 128:
            raise AssertionError(f"curve {which}: sequential decode count {c.decode_count} != 128")

        # Repeated hits within one curve/block must not cause another decode.
        c = cachemod.EnvelopeCache()
        for _ in range(100):
            for i in (64, 79, 65, 70, 78, 64):
                if cachemod.envelope_at_cached(table, i, c, curve_id=which) != values[i]:
                    raise AssertionError("same-block lookup mismatch")
        if c.decode_count != 1:
            raise AssertionError(f"curve {which}: same-block sequence decoded {c.decode_count} times")

        # Random accesses: exact values, and decode count exactly equals the
        # number of curve/block key changes in the sequence.
        r = random.Random(0x504B5945 + which)
        indices = [r.randrange(len(values)) for _ in range(5000)]
        c = cachemod.EnvelopeCache()
        expected_decodes = 0
        last = None
        for i in indices:
            key = cachemod.cache_key(which, i // 16)
            if key != last:
                expected_decodes += 1
                last = key
            got = cachemod.envelope_at_cached(table, i, c, curve_id=which)
            if got != values[i]:
                raise AssertionError(f"curve {which} random index {i}: {got} != {values[i]}")
        if c.decode_count != expected_decodes:
            raise AssertionError(
                f"curve {which}: random decode count {c.decode_count} != {expected_decodes}"
            )

    # Critical footprint test: SAME block number on the other curve must
    # refill the SAME cache, then switching back must refill again. If curve
    # identity were omitted from the key this would silently return stale data.
    c = cachemod.EnvelopeCache()
    block_index = 5 * 16 + 7
    a = cachemod.envelope_at_cached(tables[0], block_index, c, curve_id=0)
    if a != curves[0][block_index] or c.decode_count != 1:
        raise AssertionError("curve 0 initial fill failed")
    b = cachemod.envelope_at_cached(tables[1], block_index, c, curve_id=1)
    if b != curves[1][block_index] or c.decode_count != 2:
        raise AssertionError("curve switch did not invalidate/refill single cache")
    a2 = cachemod.envelope_at_cached(tables[0], block_index, c, curve_id=0)
    if a2 != a or c.decode_count != 3:
        raise AssertionError("curve switch-back did not refill single cache")

    print(
        "PERKY envelope cache: PASS "
        "(one curve-aware 17-word cache/voice; four voices + caches + RNG = 236 X words; "
        "exact sequential/same-block/random/cross-curve access)"
    )


if __name__ == "__main__":
    main()
