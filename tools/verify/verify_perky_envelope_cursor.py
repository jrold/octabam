#!/usr/bin/env python3
"""Gate the assembler-shaped generic packed-envelope cursor."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
sys.path.insert(0, str(PERKY))

import noise_tone_tables as packed  # noqa:E402
import noise_tone_envelope_cursor as cursor  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_cursor_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")


def generic_get(words, bitpos, width):
    # Independent tiny reference, deliberately not importing packed._get_bits.
    stream = 0
    for i, word in enumerate(words):
        stream |= (int(word) & 0xFFFFFF) << (24 * i)
    return (stream >> bitpos) & ((1 << width) - 1)


def main() -> None:
    r = random.Random(0x504B5942)

    # Exhaust every starting bit and field width over many random adjacent
    # words; fields may cross exactly one 24-bit boundary.
    for case in range(256):
        words = [r.getrandbits(24) for _ in range(4)]
        for start_word in (0, 1):
            for bit in range(24):
                for width in range(1, 18):
                    c = cursor.Cursor(start_word, bit)
                    got, nxt = cursor.read_bits(words, c, width)
                    absolute = start_word * 24 + bit
                    want = generic_get(words, absolute, width)
                    if got != want:
                        raise AssertionError(
                            f"case {case} word {start_word} bit {bit} width {width}: "
                            f"{got:x} != {want:x}"
                        )
                    expected_abs = absolute + width
                    expected = cursor.Cursor(expected_abs // 24, expected_abs % 24)
                    if nxt != expected:
                        raise AssertionError(f"cursor advance {nxt} != {expected}")

    # Every legal curve width and block id must map to the exact mathematical
    # bit position. This is the multiply/divide geometry the assembly will use.
    for width in range(1, 18):
        bits = cursor.block_bits(width)
        for block in range(128):
            got = cursor.block_cursor(block, width)
            absolute = block * bits
            want = cursor.Cursor(absolute // 24, absolute % 24)
            if got != want:
                raise AssertionError(
                    f"width {width} block {block}: {got} != {want}"
                )

    # Real decoder semantics over all blocks of both synthetic curves.
    for which, values in enumerate((fab.envelope_linear(), fab.envelope_ease()), 1):
        table = packed.pack_envelope(values)
        reconstructed = []
        for block in range(128):
            reconstructed.extend(cursor.decode_block(table, block))
        reconstructed = reconstructed[:len(values)]
        if reconstructed != values:
            at = next(i for i, (a, b) in enumerate(zip(reconstructed, values)) if a != b)
            raise AssertionError(
                f"curve {which} index {at}: cursor {reconstructed[at]} != {values[at]}"
            )

    print(
        "PERKY envelope cursor: PASS "
        "(256 random streams x 2 word starts x 24 bit offsets x 17 widths; "
        "all widths/block starts; 256 synthetic blocks exact)"
    )


if __name__ == "__main__":
    main()
