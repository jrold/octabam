"""Exact v1.2.1 Noise Hat init/update recovery (ColdFire oracle).

Engine 010 lives inside the Voice-4 wrapper.  `obj[4]` is the family and
`obj[5]` the panel MODE; the wrapper dispatches to a limb:

  MODE 0 -> metallic  at +0x0C4  init 0x080263AC  update 0x08026454
  MODE 1 -> white     at +0x318  init 0x08025750  update 0x08025770
  MODE 2 -> pulse     at +0x2C98 init 0x08026ED0  update 0x08026F34

The wrapper update (0x080255C0) runs common_update, dispatches to the limb,
calls the limb's own update through its vtable (limb[0]+8) and finally stores
PARAM1 into the wrapper's post-engine delay mix at +0x2DD4.  The wrapper trigger
(0x08025524) sets the limb's velocity/note and runs common_trigger on it.

Helpers recovered alongside: 0x080288C0 sets damping = min(v, 0x800); 0x080288D0
writes the Karplus coefficient law (literal pair 0x6486C / 0x57619F1) as the
filter coefficient.  No firmware table bytes are embedded.
"""
from __future__ import annotations

import struct

import fold_control_update as fold
import karplus_control_update as common

MASK16 = 0xFFFF
MASK32 = 0xFFFFFFFF

CLASSIC_BYTES = 0x2DD8
PULSE_BYTES = 0x160

LIMB0 = 0x0C4
LIMB1 = 0x318
PULSE = 0x2C98
RING = 0x3F8
RING_LEN = 0x12C5
DELAY_MIX = 0x2DD4

PULSE_INC = (0x021C, 0x0320, 0x0277, 0x0170, 0x01BE, 0x00F8)
PULSE_BASES = tuple(LIMB0 + off for off in range(0x118, 0x250, 0x34))


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def p16(b, o, v):
    struct.pack_into("<H", b, o, v & MASK16)


def p32(b, o, v):
    struct.pack_into("<I", b, o, v & MASK32)


def _s16(v):
    v &= MASK16
    return v - 0x10000 if v & 0x8000 else v


def _set_damp(b, base, value):
    """0x080288C0: damping = min(value, 0x800), stored at base+0x0C."""
    p16(b, base + 0x0C, min(value & MASK16, 0x800))


def _set_coeff(b, base, value):
    """0x080288D0: Karplus coefficient law stored at base+0x0E."""
    p16(b, base + 0x0E, common.karplus_coefficient(value & MASK16))


def _osc_increment(value):
    """Helper 0x08028464: the oscillator increment for a prepared frequency
    word (same law the port uses as osc_increment)."""
    shifted = s32((value & MASK16) << 20)
    high = s32(_mul_hi_s32(shifted, 0x057619F1))
    return ((high >> 10) - (shifted >> 31)) & MASK32


def s32(v):
    v &= MASK32
    return v - 0x100000000 if v & 0x80000000 else v


def _mul_hi_s32(a, b):
    return ((s32(a) * s32(b)) >> 32) & MASK32


def _init_common(b, base, note):
    limb = fold._init_common(0x300)
    b[base:base + 0x300] = limb
    p16(b, base + 8, 0x0FF0)          # the shared sustain threshold
    b[base + 6] = 255
    b[base + 7] = note


def _init_limb0(b, note):
    _init_common(b, LIMB0, note)
    p32(b, LIMB0 + 0x8C, 0x02EE0009)
    p32(b, LIMB0 + 0x90, 0x02EE0009)
    b[LIMB0 + 0x7C] = 1
    for i, base in enumerate(PULSE_BASES):
        p32(b, base + 0x00, 4)
        p32(b, base + 0x24, 0x08000800)   # width and reload are both 0x0800
        p32(b, base + 8, PULSE_INC[i])
        p32(b, base + 4, 0)
        # Each pulse sub-object carries the same oscillator entry point; it is
        # present in every capture and the renderer does not read it.
        p32(b, base + 0x2C, 0x080282AD)
    for off, coeff in ((0x9C, 0x1B58), (0xC4, 0x1A90), (0xE0, 0x1A90), (0xFC, 0x04B0)):
        _set_damp(b, LIMB0 + off, 0x06AB if off == 0x9C else 0x02AB)
        _set_coeff(b, LIMB0 + off, coeff)
        p32(b, LIMB0 + off + 0x10, 0)
        p32(b, LIMB0 + off + 0x14, 0)
        p32(b, LIMB0 + off + 0x18, 0)


def _init_limb1(b, note):
    _init_common(b, LIMB1, note)
    p32(b, LIMB1 + 0x8C, 0x0FA00000)
    p32(b, LIMB1 + 0x90, 0x0FA00003)
    p16(b, LIMB1 + 0xC4, 0x0001)      # hold reload
    p16(b, LIMB1 + 0xC8, 0x0080)      # range, constant in every capture
    p32(b, LIMB1 + 0x60, 0x00020000)
    _set_damp(b, LIMB1 + 0x9C, 0x0800)
    _set_coeff(b, LIMB1 + 0x9C, 0x0800)
    p32(b, LIMB1 + 0x9C + 0x10, 0)
    p32(b, LIMB1 + 0x9C + 0x14, 0)
    p32(b, LIMB1 + 0x9C + 0x18, 0)


def fresh_classic(note=63):
    b = bytearray(CLASSIC_BYTES)
    _init_limb0(b, note)
    _init_limb1(b, note)
    p16(b, 8, 0x0FF0)
    # The wrapper's post-engine delay: five tap/gain pairs, then the cleared
    # 4,805-sample ring starting at +0x3F8 (0x08024364) and a zero write index.
    for i, (tap, gain) in enumerate(zip((0x23D, 0x4B1, 0x602, 0xC43, 0x12C4),
                                        (0x01, 0x01, 0x03, 0x05, 0x07))):
        p16(b, 0x3E4 + 2 * i, tap)
        p16(b, 0x3EE + 2 * i, gain)
    p16(b, 0x2982, 0)
    p16(b, DELAY_MIX, 0)
    return b


def prepare_classic(b, targets, pitch, chromatic, mode):
    """The wrapper's own update pass (0x080255C0) for one Noise Hat mode."""
    _common_update_at(b, 0, targets, pitch, chromatic)
    base = (LIMB0, LIMB1, PULSE)[mode]
    p16(b, base + 0xBA, u16(b, 0xBA))
    p16(b, base + 0xBE, u16(b, 0xBE))
    b[base + 4] = 0
    b[base + 5] = mode
    if mode == 0:
        update_limb0(b, targets, pitch, chromatic)
    elif mode == 1:
        update_limb1(b, targets, pitch, chromatic)
    else:
        update_limb2(b, targets, pitch, chromatic)
    p16(b, DELAY_MIX, u16(b, 0xBE))
    return b


def fresh_pulse(note=63):
    b = bytearray(CLASSIC_BYTES + PULSE_BYTES)
    _init_pulse(b, PULSE, note)
    return b


def _init_pulse(b, base, note):
    _init_common(b, base, note)
    b[base + 0x7C] = 1
    p32(b, base + 0x8C, 0x02EE0009)
    p32(b, base + 0x90, 0x02EE0012)
    for off in range(base + 0xFC, base + 0x134):
        b[off] = 0
    _set_damp(b, base + 0xC4, 0x03E8)
    _set_coeff(b, base + 0xC4, 0x0B40)
    _set_damp(b, base + 0xE0, 0x0640)
    _set_coeff(b, base + 0xE0, 0x0B40)
    for off in (0xC4, 0xE0):
        p32(b, base + off + 0x10, 0)
        p32(b, base + off + 0x14, 0)
        p32(b, base + off + 0x18, 0)


def fresh_wrapper(note=63):
    b = fresh_classic(note)
    _init_pulse(b, PULSE, note)
    return b


def _common_update_at(b, base, targets, pitch, chromatic):
    """common_update 0x08024714 applied at `base` inside a larger buffer."""
    prepared = tuple(common.control.smooth_control(u32(b, base + 0x1C + 4 * i), int(t))
                     for i, t in enumerate(targets))
    for i, value in enumerate(prepared):
        p32(b, base + 0x1C + 4 * i, value)
    tune, decay, p1, p2 = (value & MASK16 for value in prepared)
    index = max(0, min(4095, common.s16(tune - 0x800
                                        + common.note_offset(b[base + 7], chromatic))))
    p16(b, base + 0xBA, index)
    p16(b, base + 0xBC, decay)
    p16(b, base + 0xBE, p1)
    p16(b, base + 0xC0, p2)
    p32(b, base + 0x34, common.pitch_at(pitch, index))
    b[base + 0x7B] = int(u16(b, base + 8) <= decay)
    p16(b, base + 0x94, common._envelope_rate(
        b, base + 0x74, common.control._time_parameter(u16(b, base + 0x0A)), False))
    p16(b, base + 0x96, common._envelope_rate(
        b, base + 0x74, common.control._time_parameter(decay), True))
    return prepared


def update_limb0(b, targets, pitch, chromatic):
    """Metallic limb update 0x08026454."""
    _common_update_at(b, LIMB0, targets, pitch, chromatic)
    p16(b, LIMB0 + 0x0A, u16(b, LIMB0 + 0xC0))
    delta = (u16(b, LIMB0 + 0xBA) >> 2) - 0xC8
    for i, base in enumerate(PULSE_BASES):
        p32(b, base + 8, _osc_increment(_s16(PULSE_INC[i] + delta) & MASK16))
    return b


def update_limb1(b, targets, pitch, chromatic):
    """White limb update 0x08025770."""
    _common_update_at(b, LIMB1, targets, pitch, chromatic)
    p16(b, LIMB1 + 0x0A, u16(b, LIMB1 + 0xC0))
    index = u16(b, LIMB1 + 0xBA)
    rng = u16(b, LIMB1 + 0xC8)
    if index < 0x800:
        b[LIMB1 + 0xC2] = 0
        _set_coeff(b, LIMB1 + 0x9C, (index << 1) & MASK16)
        threshold = (0x800 - rng) & MASK16
        p16(b, LIMB1 + 0xC6, (index + rng - 0x800) & MASK16 if index > threshold else 0)
    else:
        b[LIMB1 + 0xC2] = 2
        _set_coeff(b, LIMB1 + 0x9C, (index - 0x800) & MASK16)
        threshold = (rng + 0x800) & MASK16
        p16(b, LIMB1 + 0xC6, 0 if index >= threshold else (rng + 0x7FF - index) & MASK16)
    return b


def update_limb2(b, targets, pitch, chromatic):
    """Pulse stack update 0x08026F34 (OT pitch domain)."""
    _common_update_at(b, PULSE, targets, pitch, chromatic)
    p16(b, PULSE + 0x0A, u16(b, PULSE + 0xC0))
    step = _s16((u16(b, PULSE + 0xBA) >> 1) + 0x708)
    table = common.pitch_at(pitch, min(max(step, 0), 4095))
    base = (table << 12) & MASK32
    q = base >> 10
    p32(b, PULSE + 0x118, base)
    p32(b, PULSE + 0x11C, (q * 0x5ED1) >> 4)
    p32(b, PULSE + 0x120, (q * 0x3111) >> 4)
    p32(b, PULSE + 0x124, (q * 0x47F1) >> 4)
    p32(b, PULSE + 0x128, (q * 0x57B4) >> 4)
    p32(b, PULSE + 0x12C, (q * 0x7C72) >> 4)
    p32(b, PULSE + 0x130, ((base + (table << 13)) << 3) & MASK32)
    p16(b, PULSE + 0x138, (u16(b, PULSE + 0xBE) << 3) & MASK16)
    return b


def trigger_limb(b, base, velocity=255, note=45):
    b[base + 6] = max(1, min(255, int(velocity)))
    if note:
        b[base + 7] = max(0, min(127, int(note)))
    fold._env_trigger(b, base + 0x74)
    return b
