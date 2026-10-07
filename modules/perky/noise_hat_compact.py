"""Compact exact host models for PĒRKONS v1.2.1 Noise Hat.

Firmware modes 0/1 run through the Voice 4 wrapper.  The wrapper contains two
different classic hat limbs plus a 4,805-sample post-engine delay ring; keep
that ring external so only the live control/filter state consumes compact
words.  Firmware mode 2 is the separate Pulse Stack renderer and has no large
ring.

The panel order is not firmware order: M1/M2/M3 -> 1/0/2.
"""
from __future__ import annotations

from dataclasses import dataclass

import resonator_compact as c

RING_LEN = 0x12C5

FILTER_WORDS = 8
F_DAMP = 0
F_COEFF = 1
F_FIRST = 2
F_SECOND = 4
F_VELOCITY = 6

PULSE_WORDS = 6
P_PHASE = 0
P_INCREMENT = 2
P_WIDTH = 4
P_RELOAD = 5

# Classic wrapper compact layout. Both firmware-mode limbs are retained so a
# later shipping port can preserve state across live MODE changes.
CLASSIC_WORDS = 121
C_MUTE = 0

C0_VELOCITY = 1
C0_ENV = 2
C0_PULSES = C0_ENV + c.ENV_WORDS              # 13 .. 48
C0_FILTERS = C0_PULSES + 6 * PULSE_WORDS      # 49 .. 80

C1_VELOCITY = C0_FILTERS + 4 * FILTER_WORDS   # 81
C1_ENV = C1_VELOCITY + 1                       # 82 .. 92
C1_NOISE = C1_ENV + c.ENV_WORDS                # 93 .. 95
C1_FILTER = C1_NOISE + 3                       # 96 .. 103
C1_USE_SECOND = C1_FILTER + FILTER_WORDS       # 104
C1_MUTE = C1_USE_SECOND + 1                    # 105
C1_HOLD_RELOAD = C1_MUTE + 1                   # 106
C1_MIX = C1_HOLD_RELOAD + 1                    # 107
C1_RANGE = C1_MIX + 1                          # 108

C_DELAY_TAPS = C1_RANGE + 1                     # 109 .. 118
C_DELAY_INDEX = C_DELAY_TAPS + 10               # 119
C_DELAY_MIX = C_DELAY_INDEX + 1                 # 120
assert C_DELAY_MIX + 1 == CLASSIC_WORDS

# Pulse Stack compact layout.
PULSE_STACK_WORDS = 60
PS_VELOCITY = 0
PS_ENV = 1
PS_FILTER_A = PS_ENV + c.ENV_WORDS              # 12 .. 19
PS_FILTER_B = PS_FILTER_A + FILTER_WORDS        # 20 .. 27
PS_PHASES = PS_FILTER_B + FILTER_WORDS           # 28 .. 39 (6 x u32)
PS_INCREMENTS = PS_PHASES + 12                  # 40 .. 51 (6 x u32)
PS_RANDOM_PHASE = PS_INCREMENTS + 12            # 52 .. 53
PS_RANDOM_INCREMENT = PS_RANDOM_PHASE + 2       # 54 .. 55
PS_RANDOM = PS_RANDOM_INCREMENT + 2             # 56 .. 57
PS_SECOND_INPUT = PS_RANDOM + 2                 # 58
PS_MIX = PS_SECOND_INPUT + 1                    # 59
assert PS_MIX + 1 == PULSE_STACK_WORDS

CLASSIC0_BASE = 0x0C4
CLASSIC1_BASE = 0x318
DELAY_BASE = 0x3E4

PULSE_BASES = tuple(CLASSIC0_BASE + off
                    for off in range(0x118, 0x250, 0x34))
CLASSIC0_FILTER_BASES = tuple(CLASSIC0_BASE + off
                              for off in (0x9C, 0xC4, 0xE0, 0xFC))

PS_PHASE_OFFSETS = (0x100, 0x0FC, 0x104, 0x108, 0x10C, 0x110)
PS_INCREMENT_OFFSETS = (0x11C, 0x118, 0x120, 0x124, 0x128, 0x12C)


def _sat_filter(value: int) -> int:
    return max(-32767, min(32767, value))


def _sat16(value: int) -> int:
    return max(-32768, min(32767, value))


def _velocity(velocity: int, value: int) -> int:
    scaled = c.asr(c.mullo(value, velocity & 0xFF), 8)
    return _sat16(scaled)


def _filter_from_arm(words: list[int], dst: int,
                     raw: bytes | bytearray, src: int) -> None:
    words[dst + F_DAMP] = c.u16(raw, src + 0x0C)
    words[dst + F_COEFF] = c.u16(raw, src + 0x0E)
    c.set_u32(words, dst + F_FIRST, c.u32(raw, src + 0x10))
    c.set_u32(words, dst + F_SECOND, c.u32(raw, src + 0x14))
    c.set_u32(words, dst + F_VELOCITY, c.u32(raw, src + 0x18))


def _filter_to_arm(words: list[int], src: int,
                   raw: bytearray, dst: int) -> None:
    c.put16(raw, dst + 0x0C, words[src + F_DAMP])
    c.put16(raw, dst + 0x0E, words[src + F_COEFF])
    c.put32(raw, dst + 0x10, c.get_u32(words, src + F_FIRST))
    c.put32(raw, dst + 0x14, c.get_u32(words, src + F_SECOND))
    c.put32(raw, dst + 0x18, c.get_u32(words, src + F_VELOCITY))


def _advance_filter(words: list[int], base: int, input_value: int) -> None:
    coefficient = words[base + F_COEFF]
    velocity = c.s32(c.get_u32(words, base + F_VELOCITY))

    product = c.mullo(velocity, coefficient)
    if product < 0:
        product = c.s32(c.u32bits(product) + 0xFFFF)

    first = c.add(c.s32(c.get_u32(words, base + F_FIRST)),
                  c.asr(product, 16))
    first = _sat_filter(first)
    c.set_u32(words, base + F_FIRST, first)

    second = c.sub(input_value, first)
    second = c.sub(
        second,
        c.asr(c.mullo(velocity, words[base + F_DAMP]), 10),
    )
    second = _sat_filter(second)
    c.set_u32(words, base + F_SECOND, second)

    feedback = c.mullo(second, coefficient)
    if feedback < 0:
        feedback = c.s32(c.u32bits(feedback) + 0xFFFF)

    velocity = c.add(velocity, c.asr(feedback, 16))
    velocity = _sat_filter(velocity)
    c.set_u32(words, base + F_VELOCITY, velocity)


def _pulse_from_arm(words: list[int], dst: int,
                    raw: bytes | bytearray, src: int) -> None:
    c.set_u32(words, dst + P_PHASE, c.u32(raw, src + 4))
    c.set_u32(words, dst + P_INCREMENT, c.u32(raw, src + 8))
    words[dst + P_WIDTH] = c.u16(raw, src + 0x24)
    words[dst + P_RELOAD] = c.u16(raw, src + 0x26)


def _pulse_to_arm(words: list[int], src: int,
                  raw: bytearray, dst: int) -> None:
    c.put32(raw, dst + 4, c.get_u32(words, src + P_PHASE))
    c.put32(raw, dst + 8, c.get_u32(words, src + P_INCREMENT))
    c.put16(raw, dst + 0x24, words[src + P_WIDTH])
    c.put16(raw, dst + 0x26, words[src + P_RELOAD])


def _render_pulse(words: list[int], base: int) -> int:
    phase = (
        c.get_u32(words, base + P_PHASE)
        + c.get_u32(words, base + P_INCREMENT)
    ) & c.MASK32
    c.set_u32(words, base + P_PHASE, phase)
    if c.s32(phase) > 0x100000:
        phase = (phase - 0x100000) & c.MASK32
        c.set_u32(words, base + P_PHASE, phase)
        words[base + P_WIDTH] = words[base + P_RELOAD]
    return 32767 if words[base + P_WIDTH] > c.asr(c.s32(phase), 8) else -32767


@dataclass
class NoiseHatClassic:
    """Firmware modes 0/1 including the wrapper-owned post-engine delay."""

    words: list[int]
    ring: list[int]
    hold: list[int]  # [count u16, held sample u16]

    def __post_init__(self) -> None:
        if len(self.words) != CLASSIC_WORDS:
            raise ValueError(
                f'Noise Hat classic state must be {CLASSIC_WORDS} words'
            )
        if len(self.ring) != RING_LEN:
            raise ValueError(
                f'Noise Hat classic ring must be {RING_LEN} samples'
            )
        if len(self.hold) != 2:
            raise ValueError('Noise Hat hold state must be [count, sample]')
        self.words = [int(v) & c.MASK16 for v in self.words]
        self.ring = [int(v) & c.MASK16 for v in self.ring]
        self.hold = [int(v) & c.MASK16 for v in self.hold]

    @classmethod
    def from_arm(cls, raw: bytes | bytearray,
                 hold: bytes | bytearray) -> 'NoiseHatClassic':
        if len(raw) != 0x2DD8:
            raise ValueError('Noise Hat classic ARM state must be 0x2dd8 bytes')
        if len(hold) != 4:
            raise ValueError('Noise Hat hold state must be 4 bytes')

        w = [0] * CLASSIC_WORDS
        w[C_MUTE] = raw[0xB8]

        w[C0_VELOCITY] = raw[CLASSIC0_BASE + 6]
        c.copy_env_from_arm(w, C0_ENV, raw, CLASSIC0_BASE + 0x74)
        for i, src in enumerate(PULSE_BASES):
            _pulse_from_arm(w, C0_PULSES + i * PULSE_WORDS, raw, src)
        for i, src in enumerate(CLASSIC0_FILTER_BASES):
            _filter_from_arm(w, C0_FILTERS + i * FILTER_WORDS, raw, src)

        w[C1_VELOCITY] = raw[CLASSIC1_BASE + 6]
        c.copy_env_from_arm(w, C1_ENV, raw, CLASSIC1_BASE + 0x74)
        c.copy_noise_from_arm(w, C1_NOISE, raw, CLASSIC1_BASE + 0x60)
        _filter_from_arm(w, C1_FILTER, raw, CLASSIC1_BASE + 0x9C)
        w[C1_USE_SECOND] = raw[CLASSIC1_BASE + 0xC2]
        w[C1_MUTE] = raw[CLASSIC1_BASE + 0xB8]
        w[C1_HOLD_RELOAD] = c.u16(raw, CLASSIC1_BASE + 0xC4)
        w[C1_MIX] = c.u16(raw, CLASSIC1_BASE + 0xC6)
        w[C1_RANGE] = c.u16(raw, CLASSIC1_BASE + 0xC8)

        for i in range(5):
            w[C_DELAY_TAPS + i] = c.u16(raw, DELAY_BASE + 2 * i)
            w[C_DELAY_TAPS + 5 + i] = c.u16(
                raw, DELAY_BASE + 0x0A + 2 * i
            )
        ring = [
            c.u16(raw, DELAY_BASE + 0x14 + 2 * i)
            for i in range(RING_LEN)
        ]
        w[C_DELAY_INDEX] = c.u16(raw, DELAY_BASE + 0x259E)
        w[C_DELAY_MIX] = c.u16(raw, 0x2DD4)

        hold_words = [c.u16(hold, 0), c.u16(hold, 2)]
        return cls(w, ring, hold_words)

    def apply_to_arm(
        self,
        template: bytes | bytearray,
    ) -> tuple[bytes, bytes]:
        if len(template) != 0x2DD8:
            raise ValueError('Noise Hat classic template must be 0x2dd8 bytes')
        raw = bytearray(template)
        w = self.words
        raw[0xB8] = w[C_MUTE] & 0xFF

        raw[CLASSIC0_BASE + 6] = w[C0_VELOCITY] & 0xFF
        c.copy_env_to_arm(w, C0_ENV, raw, CLASSIC0_BASE + 0x74)
        for i, dst in enumerate(PULSE_BASES):
            _pulse_to_arm(w, C0_PULSES + i * PULSE_WORDS, raw, dst)
        for i, dst in enumerate(CLASSIC0_FILTER_BASES):
            _filter_to_arm(w, C0_FILTERS + i * FILTER_WORDS, raw, dst)

        raw[CLASSIC1_BASE + 6] = w[C1_VELOCITY] & 0xFF
        c.copy_env_to_arm(w, C1_ENV, raw, CLASSIC1_BASE + 0x74)
        c.copy_noise_to_arm(w, C1_NOISE, raw, CLASSIC1_BASE + 0x60)
        _filter_to_arm(w, C1_FILTER, raw, CLASSIC1_BASE + 0x9C)
        raw[CLASSIC1_BASE + 0xC2] = w[C1_USE_SECOND] & 0xFF
        raw[CLASSIC1_BASE + 0xB8] = w[C1_MUTE] & 0xFF
        c.put16(raw, CLASSIC1_BASE + 0xC4, w[C1_HOLD_RELOAD])
        c.put16(raw, CLASSIC1_BASE + 0xC6, w[C1_MIX])
        c.put16(raw, CLASSIC1_BASE + 0xC8, w[C1_RANGE])

        for i in range(5):
            c.put16(raw, DELAY_BASE + 2 * i, w[C_DELAY_TAPS + i])
            c.put16(
                raw,
                DELAY_BASE + 0x0A + 2 * i,
                w[C_DELAY_TAPS + 5 + i],
            )
        for i, value in enumerate(self.ring):
            c.put16(raw, DELAY_BASE + 0x14 + 2 * i, value)
        c.put16(raw, DELAY_BASE + 0x259E, w[C_DELAY_INDEX])
        c.put16(raw, 0x2DD4, w[C_DELAY_MIX])

        hold = bytearray(4)
        c.put16(hold, 0, self.hold[0])
        c.put16(hold, 2, self.hold[1])
        return bytes(raw), bytes(hold)

    def _delay(self, input_value: int) -> int:
        w = self.words
        index = w[C_DELAY_INDEX]
        next_index = index + 1
        if next_index > RING_LEN - 1:
            next_index = 0

        stage = input_value
        for tap in range(5):
            delay = w[C_DELAY_TAPS + tap]
            gain = w[C_DELAY_TAPS + 5 + tap]
            accumulator = c.mullo(stage, c.s32(gain) - 0x10)
            read_index = (
                index - delay
                if index >= delay
                else RING_LEN + index - delay
            )
            delayed = c.s16(self.ring[read_index])
            accumulator = c.add(
                accumulator,
                c.mullo(gain, delayed),
            )
            stage = c.asr(accumulator, 4)
            stage = _sat_filter(stage)

        self.ring[next_index] = stage & c.MASK16
        w[C_DELAY_INDEX] = next_index
        mix = c.s16(w[C_DELAY_MIX])
        wet = c.asr(c.mullo(stage, 5), 1)
        output = c.mullo(input_value, 0x0FFF - mix)
        output = c.add(output, c.mullo(mix, wet))
        return c.asr(output, 12)

    def _mode0(self, envelope1: bytes | None,
               envelope2: bytes | None) -> int:
        w = self.words
        total = 0
        for i in range(6):
            pulse = _render_pulse(w, C0_PULSES + i * PULSE_WORDS)
            excitation = c.s16((c.u32bits(pulse) >> 5) & c.MASK16)
            total = c.add(total, excitation)

        f0 = C0_FILTERS
        f1 = f0 + FILTER_WORDS
        f2 = f1 + FILTER_WORDS
        f3 = f2 + FILTER_WORDS

        _advance_filter(w, f0, total)
        _advance_filter(w, f1, c.s32(c.get_u32(w, f0 + F_FIRST)))
        _advance_filter(w, f2, c.s32(c.get_u32(w, f1 + F_SECOND)))
        _advance_filter(w, f3, c.s32(c.get_u32(w, f2 + F_SECOND)))

        amplitude = c.render_envelope(w, C0_ENV, envelope1, envelope2)
        value = c.asr(
            c.mullo(c.s32(c.get_u32(w, f3 + F_VELOCITY)), amplitude),
            11,
        )
        return _velocity(w[C0_VELOCITY], value)

    def _mode1(self, envelope1: bytes | None,
               envelope2: bytes | None, rng: list[int]) -> int:
        w = self.words
        amplitude = c.render_envelope(w, C1_ENV, envelope1, envelope2)

        count = self.hold[0]
        if count:
            self.hold[0] = (count - 1) & c.MASK16
            sample = c.s16(self.hold[1])
        else:
            sample = c.render_noise(w, C1_NOISE, rng)
            self.hold[1] = sample & c.MASK16
            self.hold[0] = w[C1_HOLD_RELOAD]

        _advance_filter(w, C1_FILTER, sample)
        _advance_filter(w, C1_FILTER, sample)

        first = c.s32(c.get_u32(w, C1_FILTER + F_FIRST))
        second = c.s32(c.get_u32(w, C1_FILTER + F_SECOND))
        if not w[C1_USE_SECOND]:
            second = first
        if w[C1_MUTE]:
            return 0

        ratio = c.s32(
            int(w[C1_RANGE]) - 1 - int(w[C1_MIX])
        )
        mixed = c.add(
            c.mullo(second, ratio),
            c.mullo(w[C1_MIX], sample),
        )
        mixed = c.asr(mixed, 7)
        mixed = c.asr(c.mullo(amplitude, mixed), 16)
        return _velocity(w[C1_VELOCITY], mixed)

    def render(self, n: int, firmware_mode: int,
               envelope1: bytes | None, envelope2: bytes | None,
               rng: list[int]) -> list[int]:
        if firmware_mode not in (0, 1):
            raise ValueError('classic Noise Hat firmware mode must be 0 or 1')
        if len(rng) != 2:
            raise ValueError('rng must be [low32, high32]')

        out: list[int] = []
        for _ in range(n):
            if self.words[C_MUTE]:
                out.append(0)
                continue
            inner = (
                self._mode0(envelope1, envelope2)
                if firmware_mode == 0
                else self._mode1(envelope1, envelope2, rng)
            )
            # Native wrapper narrows the post-delay result to int16 rather than
            # saturating it.
            out.append(c.s16(self._delay(inner)))
        return out


@dataclass
class NoiseHatPulseStack:
    """Firmware mode 2 Pulse Stack renderer."""

    words: list[int]

    def __post_init__(self) -> None:
        if len(self.words) != PULSE_STACK_WORDS:
            raise ValueError(
                f'Noise Hat Pulse Stack state must be '
                f'{PULSE_STACK_WORDS} words'
            )
        self.words = [int(v) & c.MASK16 for v in self.words]

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> 'NoiseHatPulseStack':
        if len(raw) != 0x160:
            raise ValueError('Noise Hat Pulse Stack ARM state must be 0x160 bytes')
        w = [0] * PULSE_STACK_WORDS
        w[PS_VELOCITY] = raw[6]
        c.copy_env_from_arm(w, PS_ENV, raw, 0x74)
        _filter_from_arm(w, PS_FILTER_A, raw, 0xC4)
        _filter_from_arm(w, PS_FILTER_B, raw, 0xE0)

        for i, off in enumerate(PS_PHASE_OFFSETS):
            c.set_u32(w, PS_PHASES + 2 * i, c.u32(raw, off))
        for i, off in enumerate(PS_INCREMENT_OFFSETS):
            c.set_u32(w, PS_INCREMENTS + 2 * i, c.u32(raw, off))
        c.set_u32(w, PS_RANDOM_PHASE, c.u32(raw, 0x114))
        c.set_u32(w, PS_RANDOM_INCREMENT, c.u32(raw, 0x130))
        c.set_u32(w, PS_RANDOM, c.u32(raw, 0x134))
        w[PS_SECOND_INPUT] = c.u16(raw, 0x136)
        w[PS_MIX] = c.u16(raw, 0x138)
        return cls(w)

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        if len(template) != 0x160:
            raise ValueError('Noise Hat Pulse Stack template must be 0x160 bytes')
        raw = bytearray(template)
        w = self.words
        raw[6] = w[PS_VELOCITY] & 0xFF
        c.copy_env_to_arm(w, PS_ENV, raw, 0x74)
        _filter_to_arm(w, PS_FILTER_A, raw, 0xC4)
        _filter_to_arm(w, PS_FILTER_B, raw, 0xE0)

        for i, off in enumerate(PS_PHASE_OFFSETS):
            c.put32(raw, off, c.get_u32(w, PS_PHASES + 2 * i))
        for i, off in enumerate(PS_INCREMENT_OFFSETS):
            c.put32(raw, off, c.get_u32(w, PS_INCREMENTS + 2 * i))
        c.put32(raw, 0x114, c.get_u32(w, PS_RANDOM_PHASE))
        c.put32(raw, 0x130, c.get_u32(w, PS_RANDOM_INCREMENT))
        c.put32(raw, 0x134, c.get_u32(w, PS_RANDOM))
        c.put16(raw, 0x136, w[PS_SECOND_INPUT])
        c.put16(raw, 0x138, w[PS_MIX])
        return bytes(raw)

    def render(self, n: int, envelope1: bytes | None,
               envelope2: bytes | None) -> list[int]:
        w = self.words
        out: list[int] = []

        for _ in range(n):
            old_phase = c.get_u32(w, PS_RANDOM_PHASE)
            random_phase = (
                old_phase + c.get_u32(w, PS_RANDOM_INCREMENT)
            ) & c.MASK32
            c.set_u32(w, PS_RANDOM_PHASE, random_phase)
            if random_phase < old_phase:
                random_value = (
                    c.get_u32(w, PS_RANDOM) * 0x0019660D
                    + 0x3C6EF35F
                ) & c.MASK32
                c.set_u32(w, PS_RANDOM, random_value)

            sign_count = 0
            for i in range(6):
                phase_off = PS_PHASES + 2 * i
                increment_off = PS_INCREMENTS + 2 * i
                phase = (
                    c.get_u32(w, phase_off)
                    + c.get_u32(w, increment_off)
                ) & c.MASK32
                c.set_u32(w, phase_off, phase)
                sign_count += phase >> 31

            pulse_stack = c.mullo(sign_count - 3, 0x1555)
            _advance_filter(w, PS_FILTER_A, pulse_stack)

            second_input = w[PS_SECOND_INPUT] - 0x8000
            previous = c.s32(c.get_u32(w, PS_FILTER_A + F_VELOCITY))
            _advance_filter(w, PS_FILTER_B, second_input)
            target = c.s32(c.get_u32(w, PS_FILTER_B + F_SECOND))

            mix = c.s16(w[PS_MIX])
            delta = c.sub(target, previous)
            interpolation = c.asr(c.mullo(mix, delta), 15)
            filtered = c.add(previous, interpolation)

            amplitude = c.render_envelope(
                w, PS_ENV, envelope1, envelope2
            )
            value = c.asr(c.mullo(filtered, amplitude), 16)
            value = c.asr(c.mullo(value, w[PS_VELOCITY] & 0xFF), 8)
            out.append(_sat16(value))

        return out
