"""Exact original v1.2.1 Karplus control-update arithmetic.

This is a qualification oracle, not shipping transport.  Callers provide the
user's extracted pitch/chromatic tables and an ARM-shaped Karplus state.  No
firmware data is embedded here.

The recovered path is intentionally kept separate from trigger handling:
common update 0x08024714 and Karplus update 0x08026aa8.  That distinction
matters for the Octatrack port because the first/active trigger routines and
the continuously running control smoother are independent operations.
"""
from __future__ import annotations

import struct

import simple_drum_control as control

MASK32 = 0xFFFFFFFF


def u16(raw: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from('<H', raw, offset)[0]


def u32(raw: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from('<I', raw, offset)[0]


def put16(raw: bytearray, offset: int, value: int) -> None:
    struct.pack_into('<H', raw, offset, value & 0xFFFF)


def put32(raw: bytearray, offset: int, value: int) -> None:
    struct.pack_into('<I', raw, offset, value & MASK32)


def s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def note_offset(note: int, chromatic: bytes) -> int:
    """0x080248e8: original twelve-entry note table, supplied by caller."""
    if len(chromatic) != 24:
        raise ValueError('chromatic table must have twelve u16 entries')
    octave, step = divmod((note & 0xFF) + 3, 12)
    return s16(u16(chromatic, step * 2) + (octave << 9))


def pitch_at(pitch: bytes, index: int) -> int:
    if len(pitch) != 8192 or not 0 <= index < 4096:
        raise ValueError('pitch table/index geometry')
    return u16(pitch, index * 2)


def _envelope_rate(raw: bytes | bytearray, offset: int,
                   parameter: int, decay: bool) -> int:
    # MUL keeps only low 32 bits before LSR #12; UDIV-by-zero returns zero on
    # this ARM path (the capture runtime has divide traps disabled).
    config = offset + (0x1C if decay else 0x18)
    product = (48 * (u16(raw, config + 2) - 1) * parameter) & MASK32
    denominator = (48 * (u16(raw, config) + 1) + (product >> 12)) & MASK32
    return 0 if denominator == 0 else 0xFFFFF // denominator


def common_update(raw: bytearray, targets: tuple[int, int, int, int] | list[int],
                  pitch: bytes, chromatic: bytes) -> tuple[int, int, int, int]:
    """Apply the common v1.2.1 smoother/update to one engine object."""
    if len(targets) != 4:
        raise ValueError('four target words required')

    prepared = tuple(
        control.smooth_control(u32(raw, 0x1C + 4 * i), int(target))
        for i, target in enumerate(targets)
    )
    for i, value in enumerate(prepared):
        put32(raw, 0x1C + 4 * i, value)

    tune, decay, p1, p2 = (value & 0xFFFF for value in prepared)
    index = max(0, min(4095, s16(tune - 0x800 + note_offset(raw[7], chromatic))))
    put16(raw, 0xBA, index)
    put16(raw, 0xBC, decay)
    put16(raw, 0xBE, p1)
    put16(raw, 0xC0, p2)
    put32(raw, 0x34, pitch_at(pitch, index))
    raw[0x7B] = int(u16(raw, 8) <= decay)
    put16(raw, 0x94,
          _envelope_rate(raw, 0x74,
                         control._time_parameter(u16(raw, 0x0A)), False))
    put16(raw, 0x96,
          _envelope_rate(raw, 0x74,
                         control._time_parameter(decay), True))
    return prepared


def karplus_delay(prepared_tune: int, note: int,
                  pitch: bytes, chromatic: bytes) -> int:
    index = max(
        0,
        min(
            4095,
            s16((3 * s16(prepared_tune) >> 3)
                - 0x514 + note_offset(note, chromatic)),
        ),
    )

    def divide(numerator: int, denominator: int) -> int:
        return 0 if denominator == 0 else numerator // denominator

    reciprocal = divide(0x100000, pitch_at(pitch, index))
    frequency = divide(0x17700, reciprocal)
    fractional_delay = (divide(0x05DC0000, frequency) - 0x400) & MASK32
    return fractional_delay >> 11 if fractional_delay <= 0x400000 else 0x800


def karplus_coefficient(prepared_p1: int) -> int:
    # 0x080288d0: MUL low32, UMULL high32, then LSR #10.
    product = (int(prepared_p1) * 0x6486C) & MASK32
    return ((product * 0x57619F1) >> 42) & 0xFFFF


def karplus_update(state: bytes, targets: tuple[int, int, int, int] | list[int],
                   pitch: bytes, chromatic: bytes) -> bytes:
    """Apply one complete original Karplus update() pass."""
    if len(state) != 0x10E0:
        raise ValueError('Karplus object must be 0x10e0 bytes')

    raw = bytearray(state)
    prepared = common_update(raw, targets, pitch, chromatic)

    # Karplus runs the TUNE smoother a second time, including its history store.
    tune = control.smooth_control(prepared[0], int(targets[0]))
    put32(raw, 0x1C, tune)

    raw[0x10DC] = int(u16(raw, 0xBC) > u16(raw, 8))
    put16(raw, 0xC2, u16(raw, 0xC0) >> 1)
    put32(raw, 0x10C8, karplus_delay(tune, raw[7], pitch, chromatic))
    put16(raw, 0xAA, karplus_coefficient(u16(raw, 0xBE)))
    return bytes(raw)
