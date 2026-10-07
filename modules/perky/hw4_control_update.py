"""Original v1.2.1 Fold2/Karplus update arithmetic, separate from trigger.

Callers provide the user's extracted pitch/chromatic tables and captured panel
inputs. No firmware data is embedded here. Addresses document the instruction
paths: common 0x08024714, Fold2 0x08024e54, Karplus 0x08026aa8.
"""
from __future__ import annotations
import struct
import simple_drum_control as control

MASK32 = 0xffffffff


def u16(raw, offset):
    return struct.unpack_from('<H', raw, offset)[0]


def u32(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0]


def put16(raw, offset, value):
    struct.pack_into('<H', raw, offset, value & 0xffff)


def put32(raw, offset, value):
    struct.pack_into('<I', raw, offset, value & MASK32)


def s16(value):
    value &= 0xffff
    return value - 0x10000 if value & 0x8000 else value


def note_offset(note, chromatic):
    """0x080248e8: the original twelve-entry note table, supplied by caller."""
    if len(chromatic) != 24:
        raise ValueError('chromatic table must have twelve u16 entries')
    octave, step = divmod((note & 0xff) + 3, 12)
    return s16(u16(chromatic, step * 2) + (octave << 9))


def pitch_at(pitch, index):
    if len(pitch) != 8192 or not 0 <= index < 4096:
        raise ValueError('pitch table/index geometry')
    return u16(pitch, index * 2)


def _envelope_rate(raw, offset, parameter, decay):
    # MUL keeps only low 32 bits before LSR #12; UDIV-by-zero returns zero
    # on this ARM path (the capture runtime has divide traps disabled).
    config = offset + (0x1c if decay else 0x18)
    product = (48 * (u16(raw, config + 2) - 1) * parameter) & MASK32
    denominator = (48 * (u16(raw, config) + 1) + (product >> 12)) & MASK32
    return 0 if denominator == 0 else 0xfffff // denominator


def common_update(raw, targets, pitch, chromatic):
    """Mutate one engine object using captured target words and its history."""
    if len(targets) != 4:
        raise ValueError('four target words required')
    prepared = [control.smooth_control(u32(raw, 0x1c + 4*i), target)
                for i, target in enumerate(targets)]
    for i, value in enumerate(prepared):
        put32(raw, 0x1c + 4*i, value)
    tune, decay, p1, p2 = [v & 0xffff for v in prepared]
    index = max(0, min(4095, s16(tune - 0x800 + note_offset(raw[7], chromatic))))
    put16(raw, 0xba, index)
    put16(raw, 0xbc, decay)
    put16(raw, 0xbe, p1)
    put16(raw, 0xc0, p2)
    put32(raw, 0x34, pitch_at(pitch, index))
    raw[0x7b] = int(u16(raw, 8) <= decay)
    put16(raw, 0x94, _envelope_rate(raw, 0x74, control._time_parameter(u16(raw, 0xa)), False))
    put16(raw, 0x96, _envelope_rate(raw, 0x74, control._time_parameter(decay), True))
    return prepared


def fold2_update(state, targets, pitch, chromatic):
    if len(state) != 0x134:
        raise ValueError('Fold2 object must be 0x134 bytes')
    raw = bytearray(state)
    common_update(raw, targets, pitch, chromatic)
    put16(raw, 0xee, u16(raw, 0xc0))
    put16(raw, 0xf0, u16(raw, 0xbe))
    return bytes(raw)


def karplus_delay(prepared_tune, note, pitch, chromatic):
    index = max(0, min(4095, s16((3*s16(prepared_tune) >> 3) - 0x514 + note_offset(note, chromatic))))
    def divide(n, d):
        return 0 if d == 0 else n // d
    reciprocal = divide(0x100000, pitch_at(pitch, index))
    frequency = divide(0x17700, reciprocal)
    fractional_delay = (divide(0x05dc0000, frequency) - 0x400) & MASK32
    return fractional_delay >> 11 if fractional_delay <= 0x400000 else 0x800


def karplus_coefficient(prepared_p1):
    # 0x080288d0: MUL low32, UMULL high32, then LSR #10.
    product = (prepared_p1 * 0x6486c) & MASK32
    return ((product * 0x57619f1) >> 42) & 0xffff


def karplus_update(state, targets, pitch, chromatic):
    if len(state) != 0x10e0:
        raise ValueError('Karplus object must be 0x10e0 bytes')
    raw = bytearray(state)
    prepared = common_update(raw, targets, pitch, chromatic)
    # Karplus runs the tune smoother a second time, including its history store.
    tune = control.smooth_control(prepared[0], targets[0])
    put32(raw, 0x1c, tune)
    raw[0x10dc] = int(u16(raw, 0xbc) > u16(raw, 8))
    put16(raw, 0xc2, u16(raw, 0xc0) >> 1)
    put32(raw, 0x10c8, karplus_delay(tune, raw[7], pitch, chromatic))
    put16(raw, 0xaa, karplus_coefficient(u16(raw, 0xbe)))
    return bytes(raw)
