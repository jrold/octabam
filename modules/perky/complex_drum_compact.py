"""Compact Complex Drum state and exact native v1.2.1 render model.

Complex Drum shares the Simple Drum envelope/oscillator arithmetic but adds a
modulation oscillator whose output is added to the frequency of the main
oscillator.  This is a host qualification model; dispatch and physical asset
placement are separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import simple_drum_compact as simple

MASK16 = 0xffff
WORDS = 42
VELOCITY, MUTE = 0, 1
MAIN_PHASE, MAIN_INC, MAIN_CUR, MAIN_NEXT = 2, 4, 6, 8
MOD_PHASE, MOD_INC, MOD_CUR, MOD_NEXT = 10, 12, 14, 16
AMP_ENV, PITCH_ENV = 18, 29
RAW_PITCH, PITCH_AMOUNT = 40, 41


def _u16(raw, off): return raw[off] | (raw[off + 1] << 8)
def _u32(raw, off): return _u16(raw, off) | (_u16(raw, off + 2) << 16)
def _put16(raw, off, v): raw[off:off + 2] = int(v & MASK16).to_bytes(2, 'little')
def _put32(raw, off, v): raw[off:off + 4] = int(v & 0xffffffff).to_bytes(4, 'little')


@dataclass
class CompactComplexDrum:
    words: list[int]

    def __post_init__(self):
        if len(self.words) != WORDS: raise ValueError(f'Complex state must be {WORDS} words')
        self.words = [x & MASK16 for x in self.words]

    def u32(self, off): return self.words[off] | (self.words[off + 1] << 16)
    def set_u32(self, off, value):
        self.words[off], self.words[off + 1] = value & MASK16, (value >> 16) & MASK16

    @classmethod
    def from_arm(cls, raw):
        if len(raw) != 0x140: raise ValueError('Complex ARM state must be 0x140 bytes')
        w = [0] * WORDS; w[0], w[1] = raw[6], raw[0xb8]
        for dst, src in ((MAIN_PHASE, 0x30), (MOD_PHASE, 0xc8)):
            for i in range(4):
                w[dst + 2 * i], w[dst + 2 * i + 1] = _u16(raw, src + 4 * i), _u16(raw, src + 4 * i + 2)
        for dst, src in ((AMP_ENV, 0x74), (PITCH_ENV, 0xf8)):
            s = simple.CompactSimpleDrum._copy_env_from_arm
            s(w, dst, raw, src)
        w[RAW_PITCH], w[PITCH_AMOUNT] = _u16(raw, 0xba), _u16(raw, 0x120)
        return cls(w)

    def apply_to_arm(self, template):
        raw = bytearray(template)
        raw[6], raw[0xb8] = self.words[0] & 255, self.words[1] & 255
        for src, dst in ((MAIN_PHASE, 0x30), (MOD_PHASE, 0xc8)):
            for i in range(4): _put32(raw, dst + 4 * i, self.u32(src + 2 * i))
        simple.CompactSimpleDrum._copy_env_to_arm(self, raw, 0x74, AMP_ENV)
        simple.CompactSimpleDrum._copy_env_to_arm(self, raw, 0xf8, PITCH_ENV)
        _put16(raw, 0xba, self.words[RAW_PITCH]); _put16(raw, 0x120, self.words[PITCH_AMOUNT])
        return bytes(raw)


def render_block(voice, sample_count, waves: Mapping[int, bytes], pitch_table: bytes,
                 envelope1: bytes | None, envelope2: bytes | None):
    out = []
    for _ in range(sample_count):
        amplitude = simple._render_envelope(voice, AMP_ENV, envelope1, envelope2)
        pitch_env = simple._render_envelope(voice, PITCH_ENV, envelope1, envelope2)
        mod = simple._render_oscillator(_view(voice, MOD_PHASE), waves)
        pitch = simple.ref.pitch_lookup(voice.words[RAW_PITCH], pitch_table)
        low13, high = pitch_env & 0x1fff, pitch_env >> 13
        factor = ((low13 + 0x2000) >> (13 - high)) - 1
        frequency = ((pitch * 0xBB80 >> 20) + ((voice.words[PITCH_AMOUNT] * factor) >> 10)
                     + (simple._s16(mod) >> 6)) & 0xffffffff
        simple._set_oscillator_frequency(_view(voice, MAIN_PHASE), frequency)
        osc = simple._render_oscillator(_view(voice, MAIN_PHASE), waves)
        if voice.words[MUTE]: out.append(0); continue
        value = simple._asr32(simple._mullo32(osc, amplitude), 16)
        value = simple._asr32(simple._mullo32(value, voice.words[VELOCITY]), 8)
        out.append(max(-32768, min(32767, value)))
    return out


class _view:
    """Offset view exposing the Simple Drum helpers over one oscillator."""
    def __init__(self, v, base): self.v, self.base = v, base
    @property
    def words(self): return self.v.words
    def u32(self, off): return self.v.u32(self.base + off - 2)
    def set_u32(self, off, value): self.v.set_u32(self.base + off - 2, value)
