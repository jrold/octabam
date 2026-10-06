#!/usr/bin/env python3
"""Gate PERKY's minimal audio-arena reservation and generic preboot layout.

No assembler, stock image or PĒRKONS data is needed.  This proves the 242-page
bottom reservation contains all four 256 KiB DSP preboot windows in both cached
and uncached aliases, that one fewer page cannot, and that platform_build's
separate preboot-reserve path rejects overlap/out-of-range entries.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/remix")]

from remix import arena, platform_build  # noqa:E402

PAGES = 242
BASE = arena.BASE
SIZE = PAGES * arena.PAGE
END = BASE + SIZE
WINDOW = 0x40000
UNCACHED = platform_build.UNCACHED

# Cached addresses used by perky_image.py. Each is the start of a 256 KiB
# slot; the two dst slots hold raw uploads and the two stage slots hold packed
# upload blobs.
STARTS = (0x40B00000, 0x40B40000, 0x40B80000, 0x40BC0000)


def entry(name: str, dst: int, stage: int, rawlen: int = WINDOW - 4,
          bloblen: int = WINDOW - 4):
    return dict(
        name=name,
        dst=dst + UNCACHED,
        stage=stage + UNCACHED,
        rawlen=rawlen,
        blob=b"x" * bloblen,
    )


def expect_fail(fn, text: str) -> None:
    try:
        fn()
    except ValueError as exc:
        if text not in str(exc):
            raise AssertionError(f"failure {exc!s} does not contain {text!r}") from exc
    else:
        raise AssertionError(f"expected failure containing {text!r}")


def main() -> None:
    if END != 0x40C005E0:
        raise AssertionError(f"242-page reserve ends at {END:#x}, expected 0x40c005e0")
    if SIZE != 1_486_848:
        raise AssertionError(f"242-page reserve is {SIZE} bytes, expected 1,486,848")

    # All four complete 256 KiB slots fit. The last one is the tight edge.
    for start in STARTS:
        if not BASE <= start < start + WINDOW <= END:
            raise AssertionError(f"slot {start:#x}..{start+WINDOW:#x} escapes reserve")
    smaller_end = BASE + (PAGES - 1) * arena.PAGE
    if 0x40BC0000 + WINDOW <= smaller_end:
        raise AssertionError("241 pages unexpectedly fit the final stage slot")

    # The generic platform helper accepts a preboot-only layout with the
    # separately declared reservation. Cached and uncached aliases normalize
    # to the same interval.
    entries = [
        entry("A", 0x40B00000, 0x40B80000),
        entry("B", 0x40B40000, 0x40BC0000),
    ]
    laid = platform_build.preboot_layout({}, entries, (BASE, SIZE))
    if len(laid) != 4:
        raise AssertionError(f"preboot layout produced {len(laid)} extents, expected 4")
    for item in laid:
        if not BASE <= item["start"] < item["end"] <= END:
            raise AssertionError(f"{item['name']} escaped reserve")

    # One byte beyond the reservation is rejected.
    expect_fail(
        lambda: platform_build.preboot_layout(
            {}, [entry("bad", 0x40B00000, END - WINDOW + 5)], (BASE, SIZE)
        ),
        "outside its arena reserve",
    )

    # Overlapping preboot roles are rejected even though both are in reserve.
    overlap = entry("overlap", 0x40B00000, 0x40B00080, rawlen=0x200, bloblen=0x200)
    expect_fail(
        lambda: platform_build.preboot_layout({}, [overlap], (BASE, SIZE)),
        "overlaps",
    )

    # A runtime may live elsewhere and the dedicated preboot reserve remains
    # legal. This is the composition case with another DRAM module.
    runtime_layout = dict(
        base=0x42000000,
        runtime_end=0x42010000,
        stage=0x42010000,
        stage_end=0x42018000,
        ceiling=0x42100000,
    )
    composed = platform_build.preboot_layout(runtime_layout, entries, (BASE, SIZE))
    if composed != laid:
        raise AssertionError("separate preboot reserve changed when a runtime was present")

    print(
        "PERKY preboot reserve: PASS "
        "(242 x 6144 B = 1.418 MiB; 241 pages insufficient; "
        "preboot-only/composed layout and overlap refusal verified)"
    )


if __name__ == "__main__":
    main()
