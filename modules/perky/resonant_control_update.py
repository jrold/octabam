"""Exact v1.2.1 Resonant Drums init/update/trigger recovery (ColdFire oracle).

Translated from the original ARM routines, which this module reproduces on the
same object bytes the port uses:

  Resonant Bass  init 0x08026790  update 0x0802682C  trigger 0x080268DC
  Resonant Snare init 0x08025F8C  update 0x08026030  trigger 0x08026108
  shared                common_init 0x080246AC / common_update 0x08024714 /
                        common_trigger 0x08024878
  pitch helper 0x0802844C : f(i) = s16(min(i,0xFFF) * 3 + 0x800)

Panel mapping (engine 7): M1 -> snare, M2 -> bass, M3 -> shared Noise/Tone.
No firmware table bytes are embedded; callers supply pitch/chromatic tables.
"""
from __future__ import annotations

import struct

import fold_control_update as fold
import karplus_control_update as common

MASK16 = 0xFFFF
MASK32 = 0xFFFFFFFF

BASS_BYTES = 0x178
SNARE_BYTES = 0x1D4
## The firmware allocates one resonant object and lets bass use its prefix:
## the bass update still writes 0x17C, which is outside 0x178. Both modes
## therefore live in a 0x1D4-byte object; only the first 0x178 are compared
## against the bass captures.
FAMILY_BYTES = 0x1D4


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


def _pitch_helper(index):
    """0x0802844C: clamp to 0xFFF, *3 + 0x800, sign-extended to 16 bits."""
    i = min(index, 0xFFF)
    return _s16((i * 3 + 0x800) & MASK16)


def _common(b, size):
    """common_init 0x080246AC -- identical for every family."""
    return fold._init_common(size)


# --------------------------------------------------------------------------
# Resonant Bass (0x178)
# --------------------------------------------------------------------------
def fresh_bass(velocity=255, note=45):
    b = _common(FAMILY_BYTES, FAMILY_BYTES)
    p32(b, 0xF8, 0x00000D0C)   # DECAY_A.mul
    b[0xC4] = 1                # TONE.resonator dirty
    p32(b, 0x10C, 0x30)
    b[0x158] = 1               # NOISE.resonator dirty
    p32(b, 0x110, 0x00000C00)  # DECAY_B.mul
    p32(b, 0x124, 0xC0)
    p32(b, 0xC6, 0x40001080)   # TONE.pitch_a=0x1080, pitch_b=0x4000
    p32(b, 0xF4, 0)
    p32(b, 0x108, 0)           # A.min
    p32(b, 0x120, 0)           # B.min
    p32(b, 0x130, 0)
    p32(b, 0x138, 0)
    p32(b, 0xDC, 0)            # TONE.position
    p32(b, 0xE0, 0)            # TONE.velocity
    p32(b, 0xCC, 0x40)         # TONE.mod
    p32(b, 0x154, 0)           # DECAY_LEVEL.min
    p32(b, 0x160, 0)           # NOISE.mod
    p32(b, 0x90, 0x0FA00005)   # amplifier-envelope decay config
    p32(b, 0x128, 0x00000FFD)  # DECAY_C.mul
    p32(b, 0x12C, 0)
    p32(b, 0x140, 0)
    p32(b, 0x144, 0x00000FFD)  # DECAY_LEVEL.mul
    p32(b, 0xFC, 0); p32(b, 0x100, 0)
    p32(b, 0x114, 0); p32(b, 0x118, 0)
    p32(b, 0x148, 0); p32(b, 0x14C, 0)
    p32(b, 0x170, 0); p32(b, 0x174, 0)
    p32(b, 0x15A, 0x07D01080)  # NOISE.pitch_a=0x1080, pitch_b=0x07D0
    b[6] = max(1, min(255, int(velocity)))
    if note:
        b[7] = max(0, min(127, int(note)))
    return b


def update_bass(b, targets, pitch, chromatic):
    common.common_update(b, targets, pitch, chromatic)
    obj8 = u16(b, 8)
    decay = u16(b, 0xBC)
    p1 = u16(b, 0xBE)
    p2 = u16(b, 0xC0)
    b[0xD8] = 1 if decay > obj8 else 0     # TONE.bypass
    if decay > obj8:
        r2 = (p1 << 4) & MASK16
        b[0xC4] = b[0xC4]                  # untouched in this branch
    else:
        r1 = (0xFFF - decay) & MASK32
        b[0xC4] = 1                        # TONE.resonator dirty
        p32(b, 0x144, (decay >> 10) + 0xFFC)
        r3 = (r1 * r1) & MASK32
        r3 = r3 >> 8
        r3 = (r1 * r3) & MASK32
        r3 = r3 >> 14
        r3 = (0x7F80 - r3) & MASK32
        p16(b, 0xC8, r3)                   # TONE.pitch_b
        r2 = 0
    p16(b, 0x154, r2)                      # DECAY_LEVEL.min
    index = u16(b, 0xBA)
    r1 = b[0x158]                          # NOISE.resonator dirty
    r3 = ((index * 7) >> 3) & MASK32
    r3 = r3 & MASK16
    p16(b, 0xF0, r3 + 0xC00)               # pitch
    r3 = _s16(r3 + 0x2400)
    if r1 == 0:
        r1 = 1 if (_s16(u16(b, 0x15A)) - r3) != 0 else 0
    p16(b, 0x15A, r3)                      # NOISE.pitch_a
    r3 = ((p2 * p2) >> 8) & MASK16
    p16(b, 0x17C, p1)
    p32(b, 0xEC, 0xC1E8)
    b[0x158] = 1 if r1 else 0
    r3 = (r3 * r3) & MASK32
    p32(b, 0xCC, r3 >> 24)
    return b


def trigger_bass(b, velocity=255, note=45):
    b[6] = max(1, min(255, int(velocity)))
    if note:
        b[7] = max(0, min(127, int(note)))
    fold._env_trigger(b, 0x74)
    p32(b, 0x11C, 0xFFFFCA3D)
    p32(b, 0x104, 0x00043333)
    p32(b, 0x12C, (u32(b, 0x124) + 1) & MASK32)
    p32(b, 0xFC, (u32(b, 0xF4) + 1) & MASK32)
    p32(b, 0x114, (u32(b, 0x10C) + 1) & MASK32)
    p32(b, 0x150, ((u16(b, 0x17C) << 4) & MASK16) & MASK32)
    p32(b, 0x134, 0x4650)
    p32(b, 0x148, (u32(b, 0x140) + 1) & MASK32)
    return b


# --------------------------------------------------------------------------
# Resonant Snare (0x1d4)
# --------------------------------------------------------------------------
def fresh_snare(velocity=255, note=45):
    b = _common(FAMILY_BYTES, FAMILY_BYTES)
    p32(b, 0x174, 0x600)       # DECAY_A.mul
    p32(b, 0x1A0, 0x30)
    p32(b, 0x170, 0)
    p32(b, 0x184, 0)           # A.min
    p32(b, 0x19C, 0)           # B.min
    p32(b, 0x1AC, 0)           # C.value
    p32(b, 0x1B4, 0)           # C.min
    p32(b, 0x1B8, 0)
    p32(b, 0x1CC, 0)           # D.min
    b[0xF8] = 1                # RES1.dirty
    p32(b, 0x100, 0)           # RES1.mod
    b[0x11C] = 1               # RES2.dirty
    p32(b, 0x124, 0)           # RES2.mod
    p32(b, 0x188, 0x30)
    p32(b, 0x18C, 0x00000C00)  # DECAY_B.mul
    p32(b, 0xFA, 0x40001080)   # RES1.pitch_a=0x1080, pitch_b=0x4000
    p32(b, 0x11E, 0x07D01080)  # RES2.pitch_a=0x1080, pitch_b=0x07D0
    p32(b, 0x1A4, 0x4B0)       # DECAY_C.mul
    p32(b, 0x1A8, 0)           # DECAY_C.count
    p32(b, 0x178, 0); p32(b, 0x17C, 0)
    p32(b, 0x190, 0); p32(b, 0x194, 0)
    p32(b, 0x1C0, 0); p32(b, 0x1C4, 0)
    p32(b, 0x110, 0); p32(b, 0x114, 0)
    p32(b, 0x134, 0); p32(b, 0x138, 0)
    p32(b, 0x158, 0); p32(b, 0x15C, 0)
    p32(b, 0x1BC, 0x00000FFD)  # DECAY_D.mul
    b[0x140] = 1               # RES3.dirty
    p32(b, 0x148, 0)           # RES3.mod
    p32(b, 0x142, 0x07D01080)  # RES3.pitch_a=0x1080, pitch_b=0x07D0
    p32(b, 0x90, 0x0FA00005)
    b[6] = max(1, min(255, int(velocity)))
    if note:
        b[7] = max(0, min(127, int(note)))
    return b


def update_snare(b, targets, pitch, chromatic):
    common.common_update(b, targets, pitch, chromatic)
    obj8 = u16(b, 8)
    decay = u16(b, 0xBC)
    p1 = u16(b, 0xBE)
    p2 = u16(b, 0xC0)
    v = 1 if decay > obj8 else 0
    b[0x10C] = v               # RES1.bypass
    b[0x130] = v               # RES2.bypass
    if decay > obj8:
        p32(b, 0x1CC, (p2 << 4) & MASK16)      # DECAY_D.min
    else:
        b[0xF8] = 1                            # RES1.dirty
        p16(b, 0xFC, 0x6FFF + decay)           # RES1.pitch_b
        p16(b, 0x120, 0x6784 + decay)          # RES2.pitch_b
        b[0x11C] = 1                           # RES2.dirty
        p32(b, 0x1BC, (decay >> 10) + 0xFFC)   # DECAY_D.mul
    r0 = _pitch_helper(u16(b, 0xBA))
    dirty1 = b[0xF8]
    if dirty1 == 0:
        dirty1 = 1 if (_s16(u16(b, 0xFA)) - r0) != 0 else 0
    r3 = r0 & MASK16
    b[0xF8] = dirty1
    p16(b, 0xFA, r3)
    r2 = _s16(r3 + 0x600)
    dirty2 = b[0x11C]
    if dirty2 == 0:
        dirty2 = 1 if (_s16(u16(b, 0x11E)) - r2) != 0 else 0
    b[0x11C] = dirty2
    p16(b, 0x11E, r2)
    r3 = _s16(r3 + 0x1800)
    dirty3 = b[0x140]
    if dirty3 == 0:
        dirty3 = 1 if (_s16(u16(b, 0x142)) - r3) != 0 else 0
    b[0x140] = dirty3
    p16(b, 0x142, r3)
    p32(b, 0x164, (0x55F0 - (p1 << 2)) & MASK32)   # MIX_FIRST
    p32(b, 0x168, (0x55F0 + (p1 << 2)) & MASK32)   # MIX_SECOND
    p16(b, 0x16C, p2)
    return b


def trigger_snare(b, velocity=255, note=45):
    b[6] = max(1, min(255, int(velocity)))
    if note:
        b[7] = max(0, min(127, int(note)))
    fold._env_trigger(b, 0x74)
    p32(b, 0x198, 0xFFFF8000)
    p32(b, 0x180, 0x00078000)
    p32(b, 0x178, (u32(b, 0x170) + 1) & MASK32)
    p32(b, 0x190, (u32(b, 0x188) + 1) & MASK32)
    p32(b, 0x1A8, (u32(b, 0x1A0) + 1) & MASK32)
    p32(b, 0x1C0, (u32(b, 0x1B8) + 1) & MASK32)
    p32(b, 0x1B0, 0x3333)
    p32(b, 0x1C8, ((_s16(u16(b, 0x16C)) << 4) & MASK32))
    return b
