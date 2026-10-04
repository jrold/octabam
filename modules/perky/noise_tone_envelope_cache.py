"""Cached decoder for packed PERKY Noise/Tone envelope curves.

The packed format remains the exact 16-sample block-delta stream defined by
``noise_tone_tables.py``.  This layer adds the intended realtime access pattern:
one cached block id plus sixteen decoded u16 values per voice.

A lookup within the current block is O(1).  Crossing to another block decodes
one anchor plus fifteen deltas exactly once, then subsequent lookups reuse it.
The cache is derived state, not part of the PĒRKONS oracle state.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from noise_tone_tables import (
    ENVELOPE_BLOCK,
    PackedEnvelope,
    _block_bits,
    _get_bits,
    _signed_decode,
)

CACHE_WORDS_PER_VOICE = 1 + ENVELOPE_BLOCK
INVALID_BLOCK = 0xFFFF


@dataclass
class EnvelopeCache:
    block_id: int = INVALID_BLOCK
    values: list[int] = field(default_factory=lambda: [0] * ENVELOPE_BLOCK)
    decode_count: int = 0

    def __post_init__(self) -> None:
        if len(self.values) != ENVELOPE_BLOCK:
            raise ValueError(f"cache needs {ENVELOPE_BLOCK} values")
        self.block_id &= 0xFFFF
        self.values = [int(v) & 0xFFFF for v in self.values]


def decode_block(table: PackedEnvelope, block_id: int) -> list[int]:
    blocks = (table.count + table.block - 1) // table.block
    if not 0 <= block_id < blocks:
        raise IndexError(block_id)
    if table.block != ENVELOPE_BLOCK:
        raise ValueError("runtime cache requires the shipping 16-sample block")

    words = list(table.words)
    bitpos = block_id * _block_bits(table.block, table.delta_bits)
    value = _get_bits(words, bitpos, 16)
    bitpos += 16
    out = [value]
    for _ in range(1, table.block):
        raw = _get_bits(words, bitpos, table.delta_bits)
        value += _signed_decode(raw, table.delta_bits)
        if not 0 <= value <= 0xFFFF:
            raise AssertionError(f"decoded envelope escaped u16: {value}")
        out.append(value)
        bitpos += table.delta_bits
    return out


def envelope_at_cached(table: PackedEnvelope, index: int,
                       cache: EnvelopeCache) -> int:
    if not 0 <= index < table.count:
        raise IndexError(index)
    block_id, within = divmod(index, table.block)
    if cache.block_id != block_id:
        cache.values[:] = decode_block(table, block_id)
        cache.block_id = block_id
        cache.decode_count += 1
    return cache.values[within]
