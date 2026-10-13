"""Stock-preserving DSP memory contract for final Perky Machines.

Addresses here are only regions already proved compatible with retaining both
stock FX slots. This module intentionally knows nothing about the old HW4
reduced-FX donor layout.

The shared 0x30000..0x3ffff window aliases P/X/Y. Stock effect guard/census
work shows an FX2 instance does not write beyond base+0x3da2. The tails below
therefore remain candidates for executable P while stock FX are active. Core-1
mailbox 0x37f00..0x37f0f is excluded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

LOW_Y_SPAN = (0x07A5, 0x1000)
FX_ARENA_SPAN = (0x1000, 0xC000)
STOCK_MAILBOX_SPAN = (0x37F00, 0x37F10)

# Half-open [lo, hi) ORDINARY-LOCAL-P ranges freed by the two effects this milestone is
# approved to sacrifice. Unlike the shared tails these are not in the aliased window, so a
# shard placed in one lives in a DIFFERENT ADDRESS SPACE from a shard in a tail. That is
# fine -- the DSP executes from both -- but it must be recorded, because the two spaces
# have different absolute bases and any emitter that treats them as one range is wrong.
SAFE_LOCAL_P_SPANS: tuple[tuple[int, int], ...] = (
    (0x1000, 0x1252),   # PLATE REV (594 words) -- approved sacrifice
    (0x1AA4, 0x1B58),   # COMPRESSOR (180 words) -- approved sacrifice
)


# Half-open [lo, hi) shared-memory ranges that may be considered for P code.
SAFE_SHARED_P_SPANS: tuple[tuple[int, int], ...] = (
    (0x33DA3, 0x34000),
    (0x37DA3, 0x37F00),
    (0x37F10, 0x38000),
    (0x3BDA3, 0x3C000),
    (0x3FDA3, 0x40000),
)


@dataclass(frozen=True)
class ProgramShard:
    name: str
    words: int
    alignment: int = 1


@dataclass(frozen=True)
class ProgramPlacement:
    name: str
    start: int
    words: int

    @property
    def end(self) -> int:
        return self.start + self.words


def span_words(span: tuple[int, int]) -> int:
    return span[1] - span[0]


def shared_p_capacity() -> int:
    return sum(span_words(span) for span in SAFE_SHARED_P_SPANS)


def largest_shared_p_span() -> int:
    return max(span_words(span) for span in SAFE_SHARED_P_SPANS)


def all_p_spans() -> tuple[tuple[int, int], ...]:
    """Every span a Perky shard may occupy, across BOTH address spaces."""
    return SAFE_LOCAL_P_SPANS + SAFE_SHARED_P_SPANS


def total_p_capacity() -> int:
    return sum(span_words(span) for span in all_p_spans())


def largest_p_span() -> int:
    return max(span_words(span) for span in all_p_spans())


def low_y_capacity() -> int:
    return span_words(LOW_Y_SPAN)


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def validate() -> None:
    if shared_p_capacity() != 2404:
        raise ValueError(f"shared-P capacity drift: {shared_p_capacity()} != 2404")
    if largest_shared_p_span() != 605:
        raise ValueError(
            f"largest shared-P span drift: {largest_shared_p_span()} != 605"
        )
    if low_y_capacity() != 2139:
        raise ValueError(f"low-Y capacity drift: {low_y_capacity()} != 2139")
    if overlaps(LOW_Y_SPAN, FX_ARENA_SPAN):
        raise ValueError("all-FX low-Y span overlaps stock FX arena")

    previous_end = None
    for lo, hi in SAFE_SHARED_P_SPANS:
        if not (0x30000 <= lo < hi <= 0x40000):
            raise ValueError(f"shared-P span outside shared window: {lo:#x}..{hi:#x}")
        if overlaps((lo, hi), STOCK_MAILBOX_SPAN):
            raise ValueError(f"shared-P span overlaps stock mailbox: {lo:#x}..{hi:#x}")
        if previous_end is not None and lo < previous_end:
            raise ValueError("shared-P spans overlap or are unsorted")
        previous_end = hi


def place_program_shards_two_space(shards: Sequence[ProgramShard],
                                   spans: Sequence[tuple[int, int]] | None = None,
                                   ) -> list[ProgramPlacement]:
    """First-fit-DECREASING across both address spaces.

    Why decreasing rather than the given order the shared-only placer uses: the packing is
    tight (measured 127 words free across both spaces for the current program), and
    decreasing order is what was actually proved to fit. A given-order first-fit can fail
    on an input a decreasing one packs, which would look like "it does not fit" when it does.

    Each shard is INDIVISIBLE and must fit inside one span: code may contain local branches
    and data adjacency, so it may only cross a hole after a builder has explicitly split it
    at a relocation-safe boundary. A span in SAFE_LOCAL_P_SPANS and one in
    SAFE_SHARED_P_SPANS are different address spaces; the caller gets whichever fits and is
    responsible for emitting that shard against the right base.
    """
    validate()
    use = tuple(spans) if spans is not None else all_p_spans()
    cursors = [lo for lo, _ in use]
    placements: list[ProgramPlacement] = []
    names: set[str] = set()

    for shard in sorted(shards, key=lambda s: -s.words):
        if not shard.name or shard.name in names:
            raise ValueError(f"program shard name must be unique and nonempty: {shard.name!r}")
        if shard.words <= 0:
            raise ValueError(f"program shard {shard.name!r} has invalid size {shard.words}")
        names.add(shard.name)

        placed = None
        for index, (_, hi) in enumerate(use):
            start = _align(cursors[index], shard.alignment)
            if start + shard.words <= hi:
                placed = ProgramPlacement(shard.name, start, shard.words)
                cursors[index] = placed.end
                break
        if placed is None:
            free = sum(hi - cur for cur, (_, hi) in zip(cursors, use))
            raise ValueError(
                f"program shard {shard.name!r} ({shard.words} words, align {shard.alignment}) "
                f"does not fit across {len(use)} spans; total free {free} words, largest "
                f"original span {max(span_words(s) for s in use)}")
        placements.append(placed)
    return placements


def _align(value: int, alignment: int) -> int:
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError(f"alignment must be a positive power of two, got {alignment}")
    return (value + alignment - 1) & ~(alignment - 1)


def place_program_shards(shards: Sequence[ProgramShard]) -> list[ProgramPlacement]:
    """First-fit explicit, indivisible program shards into the safe P tails.

    A shard is never split across holes. That is deliberate: code may contain
    local branches/data adjacency and may only cross a hole after a builder has
    explicitly split it at a relocation-safe boundary.
    """
    validate()
    cursors = [lo for lo, _ in SAFE_SHARED_P_SPANS]
    placements: list[ProgramPlacement] = []
    names: set[str] = set()

    for shard in shards:
        if not shard.name or shard.name in names:
            raise ValueError(f"program shard name must be unique and nonempty: {shard.name!r}")
        if shard.words <= 0:
            raise ValueError(f"program shard {shard.name!r} has invalid size {shard.words}")
        names.add(shard.name)

        placed = None
        for index, (_, hi) in enumerate(SAFE_SHARED_P_SPANS):
            start = _align(cursors[index], shard.alignment)
            if start + shard.words <= hi:
                placed = ProgramPlacement(shard.name, start, shard.words)
                cursors[index] = placed.end
                break
        if placed is None:
            raise ValueError(
                f"program shard {shard.name!r} ({shard.words} words, align {shard.alignment}) "
                f"does not fit all-FX-safe shared P tails; total free tail capacity is "
                f"{sum(hi - cur for cur, (_, hi) in zip(cursors, SAFE_SHARED_P_SPANS))} words, "
                f"largest original span {largest_shared_p_span()}"
            )
        placements.append(placed)

    validate_placements(placements)
    return placements


def validate_placements(placements: Iterable[ProgramPlacement]) -> None:
    used: list[tuple[int, int, str]] = []
    for item in placements:
        extent = (item.start, item.end)
        if item.words <= 0:
            raise ValueError(f"placement {item.name!r} has invalid size")
        if not any(lo <= item.start and item.end <= hi for lo, hi in SAFE_SHARED_P_SPANS):
            raise ValueError(
                f"placement {item.name!r} ${item.start:05x}..${item.end - 1:05x} "
                "escapes all-FX-safe shared P tails"
            )
        if overlaps(extent, STOCK_MAILBOX_SPAN):
            raise ValueError(f"placement {item.name!r} overlaps stock mailbox")
        for lo, hi, other in used:
            if overlaps(extent, (lo, hi)):
                raise ValueError(f"placement {item.name!r} overlaps {other!r}")
        used.append((item.start, item.end, item.name))
