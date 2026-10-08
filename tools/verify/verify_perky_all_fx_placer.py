#!/usr/bin/env python3
"""Exercise the stock-preserving Perky shared-P placement contract."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))
import all_fx_layout as layout  # noqa:E402


def must_fail(fn, needle: str) -> None:
    try:
        fn()
    except ValueError as exc:
        if needle not in str(exc):
            raise AssertionError(f"wrong failure: {exc}") from exc
    else:
        raise AssertionError(f"expected failure containing {needle!r}")


def main() -> None:
    layout.validate()
    assert layout.shared_p_capacity() == 2404
    assert layout.low_y_capacity() == 2139
    assert layout.largest_shared_p_span() == 605

    shards = [
        layout.ProgramShard("tail-a", 605),
        layout.ProgramShard("tail-b0", 349),
        layout.ProgramShard("tail-b1", 240),
        layout.ProgramShard("tail-c", 605),
        layout.ProgramShard("tail-d", 605),
    ]
    placed = layout.place_program_shards(shards)
    assert sum(p.words for p in placed) == 2404
    assert [(p.start, p.end) for p in placed] == list(layout.SAFE_SHARED_P_SPANS)

    # A routine is indivisible unless a builder explicitly establishes a safe
    # relocation boundary, so total free capacity cannot hide a too-large shard.
    must_fail(
        lambda: layout.place_program_shards([layout.ProgramShard("too-large", 606)]),
        "does not fit",
    )
    must_fail(
        lambda: layout.place_program_shards([
            layout.ProgramShard("a", 605),
            layout.ProgramShard("b", 349),
            layout.ProgramShard("c", 240),
            layout.ProgramShard("d", 605),
            layout.ProgramShard("e", 605),
            layout.ProgramShard("overflow", 1),
        ]),
        "does not fit",
    )
    must_fail(
        lambda: layout.validate_placements([
            layout.ProgramPlacement("mailbox", 0x37F00, 1)
        ]),
        "escapes all-FX-safe",
    )

    print("PERKY all-stock-FX program placer: PASS")
    print(f"  shared executable capacity: {layout.shared_p_capacity()} words")
    print(f"  largest contiguous shard   : {layout.largest_shared_p_span()} words")
    print(f"  private low-Y capacity     : {layout.low_y_capacity()} words")
    for item in placed:
        print(f"  {item.name:8s} -> P:${item.start:05x}..${item.end - 1:05x} ({item.words})")


if __name__ == "__main__":
    main()
