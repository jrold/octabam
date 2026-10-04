"""Assembler-shaped bit cursor for PERKY packed envelope blocks.

``noise_tone_tables`` defines the format.  This module defines the operations
that the DSP56300 decoder should implement: a `(word_index, bit_offset)` cursor
over 24-bit words, with fields of 1..17 bits and no arbitrary-size integer.
Every read touches one or two adjacent DSP words only.

It is generic in delta width because the real v1.2.1 curves have not yet been
extracted.  The shipping image can substitute each curve's measured constant
width while using this same cursor algorithm.
"""
from __future__ import annotations

from dataclasses import dataclass

from noise_tone_tables import DSP_BITS, DSP_MASK, ENVELOPE_BLOCK, PackedEnvelope


@dataclass(frozen=True)
class Cursor:
    word: int
    bit: int

    def __post_init__(self) -> None:
        if self.word < 0:
            raise ValueError("negative DSP word index")
        if not 0 <= self.bit < DSP_BITS:
            raise ValueError("bit offset must be 0..23")


def block_bits(delta_bits: int) -> int:
    if not 1 <= delta_bits <= 17:
        raise ValueError("envelope delta width must be 1..17")
    return 16 + (ENVELOPE_BLOCK - 1) * delta_bits


def block_cursor(block_id: int, delta_bits: int) -> Cursor:
    if block_id < 0:
        raise ValueError("negative block id")
    bitpos = block_id * block_bits(delta_bits)
    word, bit = divmod(bitpos, DSP_BITS)
    return Cursor(word, bit)


def read_bits(words: tuple[int, ...] | list[int], cursor: Cursor,
              width: int) -> tuple[int, Cursor]:
    """Read one unsigned field and return its advanced 24-bit-word cursor."""
    if not 1 <= width <= 17:
        raise ValueError("runtime field width must be 1..17")
    if cursor.word >= len(words):
        raise IndexError("packed-envelope cursor starts past table")

    first = int(words[cursor.word]) & DSP_MASK
    room = DSP_BITS - cursor.bit
    if width <= room:
        value = (first >> cursor.bit) & ((1 << width) - 1)
    else:
        if cursor.word + 1 >= len(words):
            raise IndexError("packed-envelope field crosses table end")
        low = first >> cursor.bit
        high_bits = width - room
        second = int(words[cursor.word + 1]) & DSP_MASK
        high = second & ((1 << high_bits) - 1)
        value = low | (high << room)

    absolute = cursor.bit + width
    return value, Cursor(cursor.word + absolute // DSP_BITS,
                         absolute % DSP_BITS)


def signed_decode(raw: int, width: int) -> int:
    sign = 1 << (width - 1)
    return raw - (1 << width) if raw & sign else raw


def decode_block(table: PackedEnvelope, block_id: int) -> list[int]:
    if table.block != ENVELOPE_BLOCK:
        raise ValueError("shipping cursor requires 16-sample envelope blocks")
    blocks = (table.count + table.block - 1) // table.block
    if not 0 <= block_id < blocks:
        raise IndexError(block_id)

    cursor = block_cursor(block_id, table.delta_bits)
    value, cursor = read_bits(table.words, cursor, 16)
    out = [value]
    for _ in range(1, ENVELOPE_BLOCK):
        raw, cursor = read_bits(table.words, cursor, table.delta_bits)
        value += signed_decode(raw, table.delta_bits)
        if not 0 <= value <= 0xFFFF:
            raise AssertionError(f"decoded envelope escaped u16: {value}")
        out.append(value)
    return out
