"""Exact packed-table runtime ABI for the PERKY Noise/Tone DSP port.

DSP56300 data words are 24 bits.  The raw PĒRKONS renderer consumes 16-bit
wave/envelope entries, so storing one entry per DSP word wastes a third of the
available data memory.  This module defines the bitstream the shipping decoder
will consume and provides random-access oracle functions for it.

Wave stream
===========
All unique 256-entry signed-16 waves are concatenated as one u16 stream, then
packed LSB-first: three 16-bit samples occupy two 24-bit DSP words.  Lookup is
O(1) and needs at most two word reads.

Envelope stream
===============
Each 2048-entry u16 curve is split into 16-sample blocks.  A block stores one
16-bit absolute anchor followed by fifteen signed fixed-width first deltas.
The width is chosen per curve.  Lookup reads the anchor and accumulates at most
15 deltas, which is the realtime policy used by the memory planner.

No firmware-owned tables live here.  Callers provide values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DSP_BITS = 24
DSP_MASK = (1 << DSP_BITS) - 1
WAVE_SAMPLES = 256
ENVELOPE_SAMPLES = 2048
ENVELOPE_BLOCK = 16
MAX_ENVELOPE_ADDS = ENVELOPE_BLOCK - 1


def words_for_bits(bits: int) -> int:
    if bits < 0:
        raise ValueError("bit count must be non-negative")
    return (bits + DSP_BITS - 1) // DSP_BITS


def _put_bits(words: list[int], bitpos: int, value: int, width: int) -> None:
    if not 1 <= width <= DSP_BITS:
        raise ValueError("field width must be 1..24")
    value &= (1 << width) - 1
    remaining = width
    shift = 0
    while remaining:
        wi, off = divmod(bitpos, DSP_BITS)
        take = min(remaining, DSP_BITS - off)
        mask = (1 << take) - 1
        words[wi] |= ((value >> shift) & mask) << off
        words[wi] &= DSP_MASK
        bitpos += take
        shift += take
        remaining -= take


def _get_bits(words: list[int], bitpos: int, width: int) -> int:
    if not 1 <= width <= DSP_BITS:
        raise ValueError("field width must be 1..24")
    result = 0
    shift = 0
    remaining = width
    while remaining:
        wi, off = divmod(bitpos, DSP_BITS)
        if wi >= len(words):
            raise IndexError("packed-table read past end")
        take = min(remaining, DSP_BITS - off)
        mask = (1 << take) - 1
        result |= ((words[wi] >> off) & mask) << shift
        bitpos += take
        shift += take
        remaining -= take
    return result


def signed_width(values: Iterable[int]) -> int:
    vals = list(values)
    if not vals:
        return 1
    for width in range(1, 18):
        lo = -(1 << (width - 1))
        hi = (1 << (width - 1)) - 1
        if all(lo <= v <= hi for v in vals):
            return width
    raise ValueError("u16 first differences require more than 17 signed bits")


def _signed_encode(value: int, width: int) -> int:
    lo = -(1 << (width - 1))
    hi = (1 << (width - 1)) - 1
    if not lo <= value <= hi:
        raise ValueError(f"signed value {value} does not fit {width} bits")
    return value & ((1 << width) - 1)


def _signed_decode(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def pack_u16(values: Iterable[int]) -> list[int]:
    vals = [int(v) for v in values]
    if any(not 0 <= v <= 0xFFFF for v in vals):
        raise ValueError("u16 stream contains an out-of-range value")
    words = [0] * words_for_bits(len(vals) * 16)
    for i, value in enumerate(vals):
        _put_bits(words, i * 16, value, 16)
    return words


def u16_at(words: list[int], index: int, count: int) -> int:
    if not 0 <= index < count:
        raise IndexError(index)
    # This generic spelling is the oracle. The assembly decoder can use the
    # equivalent index%3 specialization (0: low16(w0), 1: high8(w0)|low8(w1),
    # 2: high16(w1)) and is gated against this result.
    return _get_bits(words, index * 16, 16)


def unpack_u16(words: list[int], count: int) -> list[int]:
    return [u16_at(words, i, count) for i in range(count)]


@dataclass(frozen=True)
class PackedEnvelope:
    words: tuple[int, ...]
    delta_bits: int
    count: int = ENVELOPE_SAMPLES
    block: int = ENVELOPE_BLOCK

    @property
    def max_adds(self) -> int:
        return self.block - 1


def _block_bits(block: int, width: int) -> int:
    return 16 + (block - 1) * width


def pack_envelope(values: Iterable[int], *, block: int = ENVELOPE_BLOCK) -> PackedEnvelope:
    vals = [int(v) for v in values]
    if len(vals) != ENVELOPE_SAMPLES:
        raise ValueError(f"envelope must contain {ENVELOPE_SAMPLES} values")
    if any(not 0 <= v <= 0xFFFF for v in vals):
        raise ValueError("envelope contains an out-of-range u16")
    if block != ENVELOPE_BLOCK:
        raise ValueError(f"shipping envelope block is fixed at {ENVELOPE_BLOCK}")

    deltas = [
        vals[i + 1] - vals[i]
        for i in range(len(vals) - 1)
        if (i + 1) % block != 0
    ]
    width = signed_width(deltas)
    blocks = (len(vals) + block - 1) // block
    bits = blocks * _block_bits(block, width)
    words = [0] * words_for_bits(bits)

    for bi, start in enumerate(range(0, len(vals), block)):
        chunk = vals[start:start + block]
        bitpos = bi * _block_bits(block, width)
        _put_bits(words, bitpos, chunk[0], 16)
        bitpos += 16
        for previous, current in zip(chunk, chunk[1:]):
            _put_bits(words, bitpos, _signed_encode(current - previous, width), width)
            bitpos += width

    return PackedEnvelope(tuple(words), width, len(vals), block)


def envelope_at(table: PackedEnvelope, index: int) -> int:
    if not 0 <= index < table.count:
        raise IndexError(index)
    bi, within = divmod(index, table.block)
    bitpos = bi * _block_bits(table.block, table.delta_bits)
    value = _get_bits(list(table.words), bitpos, 16)
    bitpos += 16
    for _ in range(within):
        raw = _get_bits(list(table.words), bitpos, table.delta_bits)
        value += _signed_decode(raw, table.delta_bits)
        bitpos += table.delta_bits
    if not 0 <= value <= 0xFFFF:
        raise AssertionError(f"decoded envelope escaped u16: {value}")
    return value


def unpack_envelope(table: PackedEnvelope) -> list[int]:
    return [envelope_at(table, i) for i in range(table.count)]


@dataclass(frozen=True)
class PackedWaves:
    words: tuple[int, ...]
    addresses: tuple[int, ...]

    @property
    def samples(self) -> int:
        return len(self.addresses) * WAVE_SAMPLES


def pack_waves(waves: Iterable[tuple[int, Iterable[int]]]) -> PackedWaves:
    pairs = [(int(address) & 0xFFFFFFFF, [int(v) & 0xFFFF for v in values])
             for address, values in waves]
    if not pairs:
        raise ValueError("at least one wave is required")
    addresses = tuple(address for address, _ in pairs)
    if len(set(addresses)) != len(addresses):
        raise ValueError("wave identities must be unique")
    for address, values in pairs:
        if len(values) != WAVE_SAMPLES:
            raise ValueError(f"wave 0x{address:08x} has {len(values)} samples")
    flat = [sample for _address, values in pairs for sample in values]
    return PackedWaves(tuple(pack_u16(flat)), addresses)


def wave_at(table: PackedWaves, address: int, index: int) -> int:
    if not 0 <= index < WAVE_SAMPLES:
        raise IndexError(index)
    try:
        wi = table.addresses.index(int(address) & 0xFFFFFFFF)
    except ValueError as exc:
        raise KeyError(f"unknown wave identity 0x{int(address)&0xFFFFFFFF:08x}") from exc
    return u16_at(list(table.words), wi * WAVE_SAMPLES + index, table.samples)
