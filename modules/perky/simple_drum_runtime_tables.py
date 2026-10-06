"""Low-cycle exact runtime tables for the v1.2.1 PERKY Simple Drum port.

The maximum-compression Simple Drum codec remains useful as a memory proof, but
it is unnecessary in the realtime renderer.  Authentic prepared states show
that Simple Drum uses one shaped curve (envelope1); the amplitude envelope is
shape 0 and therefore follows the renderer's analytic linear path.

That makes the simpler direct packed-u16 layout fit comfortably in the measured
PERKY Y-memory window while keeping every table fetch O(1):

- three 256-sample waves:                 512 DSP words;
- envelope1 indices 0..1023:              683 DSP words;
- top-octave 512-entry pitch basis:        342 DSP words;
- total:                                  1537 DSP words.

Runtime envelope index 1024 clamps to 1023, matching the authentic duplicate
endpoint.  The pitch basis reconstructs all 4096 v1.2.1 pitch entries exactly
with an octave right shift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import simple_drum_tables as packed

WAVE_SAMPLES = 256
WAVES = 3
ENV_STORED = 1024
ENV_ENDPOINT = 1024
PITCH_BASIS = 512

WAVE_WORDS = 512
ENV_WORDS = 683
PITCH_WORDS = 342
TOTAL_WORDS = 1537


@dataclass(frozen=True)
class RuntimeTables:
    waves: tuple[int, ...]
    envelope: tuple[int, ...]
    pitch_basis: tuple[int, ...]


def build(full_pitch: Iterable[int], full_envelope: Iterable[int],
          waves: Iterable[int]) -> RuntimeTables:
    pitch = [int(value) & 0xFFFF for value in full_pitch]
    envelope = [int(value) & 0xFFFF for value in full_envelope]
    wave_values = [int(value) & 0xFFFF for value in waves]

    if len(pitch) != 4096:
        raise ValueError("pitch must contain 4096 u16 entries")
    if len(envelope) != 2048:
        raise ValueError("envelope must contain 2048 u16 entries")
    if len(wave_values) != WAVES * WAVE_SAMPLES:
        raise ValueError("waves must contain 768 u16 entries")
    if envelope[ENV_ENDPOINT] != envelope[ENV_ENDPOINT - 1]:
        raise ValueError("envelope endpoint 1024 must duplicate index 1023")

    basis = pitch[-PITCH_BASIS:]
    for index, want in enumerate(pitch):
        got = basis[index & 0x1FF] >> (7 - (index >> 9))
        if got != want:
            raise ValueError(
                f"pitch basis reconstruction mismatch at {index}: {got} != {want}"
            )

    out = RuntimeTables(
        packed.pack_u16(wave_values),
        packed.pack_u16(envelope[:ENV_STORED]),
        packed.pack_u16(basis),
    )
    got_words = (len(out.waves), len(out.envelope), len(out.pitch_basis))
    if got_words != (WAVE_WORDS, ENV_WORDS, PITCH_WORDS):
        raise AssertionError(f"runtime table word layout drifted: {got_words!r}")
    return out


def pitch_at(table: RuntimeTables, index: int) -> int:
    if not 0 <= index < 4096:
        raise IndexError(index)
    basis = packed.u16_at(table.pitch_basis, index & 0x1FF, PITCH_BASIS)
    return basis >> (7 - (index >> 9))


def envelope_at(table: RuntimeTables, index: int) -> int:
    if not 0 <= index <= ENV_ENDPOINT:
        raise IndexError(index)
    if index == ENV_ENDPOINT:
        index = ENV_ENDPOINT - 1
    return packed.u16_at(table.envelope, index, ENV_STORED)


def wave_at(table: RuntimeTables, wave: int, index: int) -> int:
    if not 0 <= wave < WAVES or not 0 <= index < WAVE_SAMPLES:
        raise IndexError((wave, index))
    return packed.u16_at(
        table.waves,
        wave * WAVE_SAMPLES + index,
        WAVES * WAVE_SAMPLES,
    )
