#!/usr/bin/env python3
"""Gate stock-preserving DSP memory facts for the final Perky Machines layout.

Starts from the pristine Octatrack 1.40C MAIN OS. Proves the stock allocator
geometry on both DSP payloads, rejects the tempting 16K-P/40K-Y memory switch
because it truncates a stock FX2 slot, and accounts only measured-safe tails of
the four shared-window FX2 slots as possible extra executable storage.

This does not claim those tails are sufficient for every Perky engine. It turns
the all-FX requirement into hard placement limits so later builders cannot
silently borrow an FX arena.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/build"))
import dsp_modmap as modmap  # noqa:E402

STOCK = ROOT / "out/raw/section_3_MAIN_OS.bin"
EXPECTED_MAIN_SIZE = 1_112_560

DEFAULT_Y_END = 0xC000
SWITCH_16K_P_Y_END = 0xA000
FX_ARENA_START = 0x1000
FX1_WORDS = 0x0C00
FX1_SLOTS = 4
FX2_WORDS = 0x4000
LOCAL_FX2_SLOTS = 2

EXPECTED_BASES = {
    "A": (0x01000, 0x04000, 0x01C00, 0x08000, 0x02800, 0x30000, 0x03400, 0x34000),
    "B": (0x01000, 0x04000, 0x01C00, 0x08000, 0x02800, 0x38000, 0x03400, 0x3C000),
}

# Hardware/port guard census documented in docs/firmware/CHIP.md: no stock
# effect writes beyond base + 0x3da2 in an FX2 allocation.
STOCK_FX2_MAX_WRITTEN_OFFSET = 0x3DA2
SHARED_SLOT_BASES = (0x30000, 0x34000, 0x38000, 0x3C000)
SHARED_SLOT_END_DELTA = 0x4000
STOCK_MAILBOX = (0x37F00, 0x37F10)


def loaded_words(img: bytes, tag: str, space: int) -> dict[int, int]:
    va, ln = next((va, ln) for t, va, ln in modmap.PAYLOADS if t == tag)
    mods, blob = modmap.modules(img, va, ln)
    out: dict[int, int] = {}
    for sp, addr, count, data in mods:
        if sp != space:
            continue
        for i in range(count):
            out[addr + i] = modmap.w24(blob, data + 3 * i)
    return out


def p_top(img: bytes, tag: str) -> int:
    va, ln = next((va, ln) for t, va, ln in modmap.PAYLOADS if t == tag)
    mods, _ = modmap.modules(img, va, ln)
    return max(addr + count for sp, addr, count, _ in mods
               if sp == 0 and addr < 0x30000)


def subtract(span: tuple[int, int], cut: tuple[int, int]) -> list[tuple[int, int]]:
    lo, hi = span
    a, b = cut
    if b <= lo or hi <= a:
        return [span]
    out = []
    if lo < a:
        out.append((lo, a))
    if b < hi:
        out.append((b, hi))
    return out


def main() -> None:
    if not STOCK.is_file():
        raise SystemExit(
            f"verify-perky-all-fx-memory: missing {STOCK}; decode pristine "
            "OCTATRACK_OS1.40C.bin first"
        )
    img = STOCK.read_bytes()
    if len(img) != EXPECTED_MAIN_SIZE:
        raise AssertionError(
            f"MAIN OS is {len(img):,} bytes, expected {EXPECTED_MAIN_SIZE:,}"
        )

    tops = {}
    for tag in ("A", "B"):
        x = loaded_words(img, tag, 1)
        got = tuple(x[0x255 + i] for i in range(8))
        if got != EXPECTED_BASES[tag]:
            raise AssertionError(
                f"payload {tag} FX allocator base table drift: "
                f"{tuple(hex(v) for v in got)}"
            )
        tops[tag] = p_top(img, tag)

    if tops != {"A": 0x1FDF, "B": 0x1D9F}:
        raise AssertionError(f"stock P high-water drift: {tops!r}")

    stock_local_fx_words = FX1_SLOTS * FX1_WORDS + LOCAL_FX2_SLOTS * FX2_WORDS
    default_available = DEFAULT_Y_END - FX_ARENA_START
    switched_available = SWITCH_16K_P_Y_END - FX_ARENA_START
    if stock_local_fx_words != default_available:
        raise AssertionError(
            "stock allocator geometry no longer fills default local Y exactly"
        )
    switch_shortfall = stock_local_fx_words - switched_available
    if switch_shortfall != 0x2000:
        raise AssertionError(f"16K-P switch shortfall drift: {switch_shortfall}")

    tail0 = STOCK_FX2_MAX_WRITTEN_OFFSET + 1
    safe: list[tuple[int, int]] = []
    for base in SHARED_SLOT_BASES:
        safe.extend(
            span for span in subtract(
                (base + tail0, base + SHARED_SLOT_END_DELTA), STOCK_MAILBOX
            ) if span[0] < span[1]
        )
    tail_words = sum(hi - lo for lo, hi in safe)
    if tail_words != 2404:
        raise AssertionError(f"shared executable-tail budget drift: {tail_words}")

    common_low_y_begin = max(
        max(loaded_words(img, tag, 2), default=-1) + 1 for tag in ("A", "B")
    )
    if common_low_y_begin != 0x07A5:
        raise AssertionError(f"common low-Y free start drift: {common_low_y_begin:#x}")
    low_y_words = 0x1000 - common_low_y_begin
    if low_y_words != 2139:
        raise AssertionError(f"common low-Y budget drift: {low_y_words}")

    print("PERKY all-stock-FX memory ledger: PASS")
    print(f"  stock P high-water : A=${tops['A']:04x} B=${tops['B']:04x}")
    print(
        f"  stock local FX Y   : {stock_local_fx_words} words "
        f"(${FX_ARENA_START:04x}..${DEFAULT_Y_END - 1:04x})"
    )
    print(
        f"  16K-P/40K-Y map    : REJECTED — loses {switch_shortfall} words "
        "from the stock local-FX allocator"
    )
    print(
        f"  all-FX-safe low Y  : {low_y_words} words "
        f"(${common_low_y_begin:04x}..$0fff)"
    )
    print(f"  all-FX-safe shared P tails: {tail_words} words total")
    for lo, hi in safe:
        print(f"    ${lo:05x}..${hi - 1:05x}  {hi - lo} words")
    print("  verdict             : keep default memory split; do not harvest either FX arena")


if __name__ == "__main__":
    main()
