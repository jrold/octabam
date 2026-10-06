"""Exact compact static-table formats for the v1.2.1 PERKY Simple Drum port.

No firmware data is embedded here. Callers supply extracted values.

Layout candidates are chosen from measured v1.2.1 structure:
- three 256-sample signed16 waves: ordinary packed-u16 stream (3 samples / 2 DSP words);
- 512-entry top-octave pitch basis: 16-sample blocks using u16 anchor, u6 first
  delta, then fourteen signed-2 second differences;
- pitch-envelope curve indices 0..1023: 16-sample blocks using u16 anchor, u9
  first delta, then fourteen signed-3 second differences. Runtime index 1024
  clamps to index 1023, matching the authentic duplicate endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DSP_BITS = 24
DSP_MASK = (1 << DSP_BITS) - 1
WAVE_SAMPLES = 256
WAVES = 3
PITCH_BASIS_SAMPLES = 512
ENV_SAMPLES_STORED = 1024
ENV_ENDPOINT_INDEX = 1024
BLOCK = 16


def words_for_bits(bits: int) -> int:
    return (bits + DSP_BITS - 1) // DSP_BITS


def _put_bits(words: list[int], bitpos: int, value: int, width: int) -> None:
    value &= (1 << width) - 1
    left = width
    shift = 0
    while left:
        wi, off = divmod(bitpos, DSP_BITS)
        take = min(left, DSP_BITS - off)
        words[wi] |= ((value >> shift) & ((1 << take) - 1)) << off
        words[wi] &= DSP_MASK
        bitpos += take
        shift += take
        left -= take


def _get_bits(words: tuple[int, ...] | list[int], bitpos: int, width: int) -> int:
    result = 0
    out_shift = 0
    left = width
    while left:
        wi, off = divmod(bitpos, DSP_BITS)
        take = min(left, DSP_BITS - off)
        result |= ((words[wi] >> off) & ((1 << take) - 1)) << out_shift
        bitpos += take
        out_shift += take
        left -= take
    return result


def _signed_encode(value: int, width: int) -> int:
    lo, hi = -(1 << (width - 1)), (1 << (width - 1)) - 1
    if not lo <= value <= hi:
        raise ValueError(f"{value} does not fit signed {width}-bit")
    return value & ((1 << width) - 1)


def _signed_decode(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def pack_u16(values: Iterable[int]) -> tuple[int, ...]:
    vals = [int(v) & 0xFFFF for v in values]
    words = [0] * words_for_bits(16 * len(vals))
    for i, value in enumerate(vals):
        _put_bits(words, i * 16, value, 16)
    return tuple(words)


def u16_at(words: tuple[int, ...] | list[int], index: int, count: int) -> int:
    if not 0 <= index < count:
        raise IndexError(index)
    return _get_bits(words, 16 * index, 16)


@dataclass(frozen=True)
class SecondDeltaTable:
    words: tuple[int, ...]
    count: int
    first_delta_bits: int
    second_delta_bits: int
    block: int = BLOCK

    @property
    def bits_per_block(self) -> int:
        return 16 + self.first_delta_bits + (self.block - 2) * self.second_delta_bits


def pack_second_delta(values: Iterable[int], *, first_bits: int,
                      second_bits: int) -> SecondDeltaTable:
    vals = [int(v) for v in values]
    if not vals or len(vals) % BLOCK:
        raise ValueError("second-delta stream must be a non-empty multiple of 16")
    if any(not 0 <= v <= 0xFFFF for v in vals):
        raise ValueError("second-delta value outside u16")
    bits_per = 16 + first_bits + (BLOCK - 2) * second_bits
    words = [0] * words_for_bits((len(vals) // BLOCK) * bits_per)
    for bi in range(len(vals) // BLOCK):
        chunk = vals[bi * BLOCK:(bi + 1) * BLOCK]
        deltas = [chunk[i + 1] - chunk[i] for i in range(BLOCK - 1)]
        if not 0 <= deltas[0] < (1 << first_bits):
            raise ValueError(f"block {bi} first delta {deltas[0]} exceeds u{first_bits}")
        second = [deltas[i + 1] - deltas[i] for i in range(BLOCK - 2)]
        bit = bi * bits_per
        _put_bits(words, bit, chunk[0], 16)
        bit += 16
        _put_bits(words, bit, deltas[0], first_bits)
        bit += first_bits
        for value in second:
            _put_bits(words, bit, _signed_encode(value, second_bits), second_bits)
            bit += second_bits
    return SecondDeltaTable(tuple(words), len(vals), first_bits, second_bits)


def second_delta_at(table: SecondDeltaTable, index: int) -> int:
    if not 0 <= index < table.count:
        raise IndexError(index)
    bi, within = divmod(index, table.block)
    bit = bi * table.bits_per_block
    value = _get_bits(table.words, bit, 16)
    bit += 16
    if within == 0:
        return value
    delta = _get_bits(table.words, bit, table.first_delta_bits)
    bit += table.first_delta_bits
    value += delta
    if within == 1:
        return value
    for _ in range(1, within):
        dd = _signed_decode(
            _get_bits(table.words, bit, table.second_delta_bits),
            table.second_delta_bits,
        )
        bit += table.second_delta_bits
        delta += dd
        value += delta
    if not 0 <= value <= 0xFFFF:
        raise AssertionError(f"decoded second-delta value outside u16: {value}")
    return value


def pack_pitch_basis(full_pitch: Iterable[int]) -> SecondDeltaTable:
    vals = [int(v) & 0xFFFF for v in full_pitch]
    if len(vals) != 4096:
        raise ValueError("full pitch table must contain 4096 u16 entries")
    basis = vals[-PITCH_BASIS_SAMPLES:]
    table = pack_second_delta(basis, first_bits=6, second_bits=2)
    for index, want in enumerate(vals):
        octave = index >> 9
        got = second_delta_at(table, index & 0x1FF) >> (7 - octave)
        if got != want:
            raise ValueError(
                f"pitch basis reconstruction mismatch at {index}: {got} != {want}"
            )
    return table


def pitch_at(table: SecondDeltaTable, index: int) -> int:
    if not 0 <= index < 4096:
        raise IndexError(index)
    return second_delta_at(table, index & 0x1FF) >> (7 - (index >> 9))


def pack_pitch_envelope(full_curve: Iterable[int]) -> SecondDeltaTable:
    vals = [int(v) & 0xFFFF for v in full_curve]
    if len(vals) != 2048:
        raise ValueError("full envelope curve must contain 2048 u16 entries")
    if vals[ENV_ENDPOINT_INDEX] != vals[ENV_ENDPOINT_INDEX - 1]:
        raise ValueError("Simple Drum curve endpoint 1024 must duplicate index 1023")
    return pack_second_delta(
        vals[:ENV_SAMPLES_STORED], first_bits=9, second_bits=3
    )


def envelope_at(table: SecondDeltaTable, index: int) -> int:
    if not 0 <= index <= ENV_ENDPOINT_INDEX:
        raise IndexError(index)
    if index == ENV_ENDPOINT_INDEX:
        index = ENV_ENDPOINT_INDEX - 1
    return second_delta_at(table, index)
