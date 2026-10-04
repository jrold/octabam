"""Cached decoder for packed PERKY Noise/Tone envelope curves.

The packed format remains the exact 16-sample block-delta stream defined by
``noise_tone_tables.py``. This layer adds the intended realtime access pattern:
one cached key plus sixteen decoded u16 values per voice.

The key contains BOTH the curve selector and block id. A voice therefore needs
one 17-word cache total, not one cache per curve. This matters to the shipping
memory budget: a voice renders only one envelope shape at a time, and a shape
change simply invalidates/refills the same derived cache.

A lookup within the current curve/block is O(1). Crossing to another block or
switching curve decodes one anchor plus fifteen deltas exactly once, then
subsequent lookups reuse it. The cache is derived state, not part of the
PĒRKONS oracle state.
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
INVALID_KEY = 0xFFFF
# Seven bits hold block 0..127. Bit 7 distinguishes the two Noise/Tone curves.
CURVE_SHIFT = 7
BLOCK_MASK = (1 << CURVE_SHIFT) - 1


@dataclass
class EnvelopeCache:
    key: int = INVALID_KEY
    values: list[int] = field(default_factory=lambda: [0] * ENVELOPE_BLOCK)
    decode_count: int = 0

    def __post_init__(self) -> None:
        if len(self.values) != ENVELOPE_BLOCK:
            raise ValueError(f"cache needs {ENVELOPE_BLOCK} values")
        self.key &= 0xFFFF
        self.values = [int(v) & 0xFFFF for v in self.values]

    @property
    def block_id(self) -> int:
        """Current block for diagnostics; INVALID_KEY remains distinguishable."""
        return INVALID_KEY if self.key == INVALID_KEY else self.key & BLOCK_MASK

    @property
    def curve_id(self) -> int:
        return -1 if self.key == INVALID_KEY else (self.key >> CURVE_SHIFT) & 1


def cache_key(curve_id: int, block_id: int) -> int:
    if curve_id not in (0, 1):
        raise ValueError("Noise/Tone curve id must be 0 or 1")
    if not 0 <= block_id <= BLOCK_MASK:
        raise ValueError(f"envelope block {block_id} does not fit 7 bits")
    return (curve_id << CURVE_SHIFT) | block_id


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
                       cache: EnvelopeCache, *, curve_id: int = 0) -> int:
    if not 0 <= index < table.count:
        raise IndexError(index)
    block_id, within = divmod(index, table.block)
    key = cache_key(curve_id, block_id)
    if cache.key != key:
        cache.values[:] = decode_block(table, block_id)
        cache.key = key
        cache.decode_count += 1
    return cache.values[within]
