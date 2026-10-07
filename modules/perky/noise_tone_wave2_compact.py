"""Exact compact NativeV121NoiseToneWaveform2 (Noise/Tone panel M1).

This is distinct from the shared noise/two-oscillator modes and preserves its
phase-reduction, phase-offset and deferred 2K table switching semantics.
"""
from dataclasses import dataclass
import resonator_compact as c

WORDS = 25
VELOCITY, MUTE, ENV = 0, 1, 2
PHASE, INCREMENT, OFFSET, CURRENT, NEXT, REDUCTION = 13, 15, 17, 19, 21, 23


@dataclass
class NoiseToneWave2:
    words: list[int]

    def __post_init__(self):
        if len(self.words) != WORDS:
            raise ValueError(f'Noise/Tone Waveform2 needs {WORDS} words')
        self.words = [v & 65535 for v in self.words]

    @classmethod
    def from_arm(cls, raw):
        if len(raw) != 0x120:
            raise ValueError('Noise/Tone Waveform2 ARM state must be 0x120 bytes')
        w = [0] * WORDS
        w[0], w[1] = raw[6], raw[0xB8]
        c.copy_env_from_arm(w, ENV, raw, 0x74)
        for dst, src in ((PHASE, 0xD8), (INCREMENT, 0xDC), (OFFSET, 0xE0),
                         (CURRENT, 0xE4), (NEXT, 0xE8), (REDUCTION, 0xC8)):
            c.set_u32(w, dst, c.u32(raw, src))
        return cls(w)

    def apply_to_arm(self, template):
        if len(template) != 0x120:
            raise ValueError('Noise/Tone Waveform2 template must be 0x120 bytes')
        raw = bytearray(template)
        raw[6], raw[0xB8] = self.words[0] & 255, self.words[1] & 255
        c.copy_env_to_arm(self.words, ENV, raw, 0x74)
        for src, dst in ((PHASE, 0xD8), (INCREMENT, 0xDC), (OFFSET, 0xE0),
                         (CURRENT, 0xE4), (NEXT, 0xE8), (REDUCTION, 0xC8)):
            c.put32(raw, dst, c.get_u32(self.words, src))
        return bytes(raw)

    def render(self, n, waves):
        w, out = self.words, []
        if w[ENV + c.ENV_SHAPE] != 0:
            raise ValueError('Original Waveform2 mode requires its linear envelope')
        for _ in range(n):
            amp = c.render_envelope(w, ENV, None, None)
            phase = c.get_u32(w, PHASE)
            reduction = c.get_u32(w, REDUCTION)
            if phase > reduction:
                phase = (phase - reduction) & c.MASK32
            phase = (phase + c.get_u32(w, INCREMENT)) & c.MASK32
            if c.s32(phase) > 0x100000:
                phase = (phase - 0x100000) & c.MASK32
                c.set_u32(w, CURRENT, c.get_u32(w, NEXT))
            c.set_u32(w, PHASE, phase)
            lookup = phase
            offset = c.get_u32(w, OFFSET)
            if offset:
                lookup = (lookup + offset) & c.MASK32
                if c.s32(lookup) > 0x100000:
                    lookup = (lookup - 0x100000) & c.MASK32
            table = waves[c.get_u32(w, CURRENT)]
            index, fraction = (lookup >> 9) & 0x7FF, lookup & 0x1FF
            first = c.s16(c.table_u16(table, index))
            second = c.s16(c.table_u16(table, (index + 1) & 0x7FF))
            osc = c.s16(first + c.asr(c.mullo(second - first, fraction), 9))
            value = c.asr(c.mullo(osc, amp), 17)
            out.append(0 if w[MUTE] else c.velocity_scale(w[VELOCITY], value))
        return out
