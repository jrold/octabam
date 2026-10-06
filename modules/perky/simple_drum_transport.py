"""Byte-level Simple Drum PK/Y1 transport model.

The existing PERKY source record carries twelve one-byte parameter slots. For
engine 003 the ColdFire writer repacks them with renderer-ready values. Engine
011 Noise/Tone keeps the original raw-byte record unchanged.

This model mirrors the v1.2.1/PerkyBits control cadence used by the authentic
state captures:
- a dirty GUI/control change performs setAlgorithm/update + setMode/update
  against the old targets, then writes all four targets and performs 16 update
  passes;
- a trigger performs one further update pass before rendering.

Octatrack's 7-bit controls are expanded to the firmware's 12-bit target domain
with 127 mapping to 4095 and all other values mapping to value<<5.

Record bytes 0..7 hold four big-endian u16 prepared values. Byte 8 is physical
MODE. Byte 9 carries Simple Drum's amplitude-envelope gate bit: the original
v1.2.1 update sets it when the smoothed DECAY control is >= 4080. Byte 10 is
reserved and byte 11 is the zero-based engine index.
"""
from __future__ import annotations

from dataclasses import dataclass

import simple_drum_control as ctl

ENGINE_INDEX = 2
AMP_GATE_THRESHOLD = 4080


def _be16(value: int) -> tuple[int, int]:
    value &= 0xFFFF
    return (value >> 8, value & 0xFF)


@dataclass
class State:
    prepared: list[int]
    targets: list[int]
    last_raw: tuple[int, int, int, int] | None = None
    last_mode: int | None = None

    @classmethod
    def fresh(cls) -> "State":
        return cls(prepared=[0, 0, 0, 0], targets=[0, 0, 0, 0])

    def _update_once(self) -> None:
        self.prepared = [
            ctl.smooth_control(old, target)
            for old, target in zip(self.prepared, self.targets)
        ]

    def prepare(self, raw: tuple[int, int, int, int], mode: int,
                *, trigger: bool) -> bytes:
        raw = tuple(max(0, min(127, int(value))) for value in raw)
        mode = max(0, min(2, int(mode)))
        dirty = self.last_raw != raw or self.last_mode != mode

        if dirty:
            # PerkyBits MainComponent applies setAlgorithm and setMode before
            # setSoundParameters. Both calls execute one update with the old
            # targets still installed.
            self._update_once()
            self._update_once()
            self.targets = [ctl.panel_to_target(value) for value in raw]
            for _ in range(16):
                self._update_once()
            self.last_raw = raw
            self.last_mode = mode

        if trigger:
            # v1.2.1 trigger() performs one update-after-trigger pass.
            self._update_once()

        tune, decay, env, mix = self.prepared
        raw_pitch = ctl.raw_pitch(tune)
        amp_decay = ctl.amplitude_decay_rate(decay)
        pitch_decay = ctl.pitch_envelope_decay_rate(env)
        amount = ctl.pitch_envelope_amount(mix)

        record = bytearray(12)
        record[0:2] = bytes(_be16(raw_pitch))
        record[2:4] = bytes(_be16(amp_decay))
        record[4:6] = bytes(_be16(pitch_decay))
        record[6:8] = bytes(_be16(amount))
        record[8] = mode
        record[9] = int(decay >= AMP_GATE_THRESHOLD)
        record[10] = 0
        record[11] = ENGINE_INDEX
        return bytes(record)


def decode(record: bytes) -> dict[str, int]:
    if len(record) != 12:
        raise ValueError("Simple Drum transport record must contain 12 bytes")
    u16 = lambda offset: (record[offset] << 8) | record[offset + 1]
    return {
        "raw_pitch": u16(0),
        "amp_decay": u16(2),
        "pitch_decay": u16(4),
        "pitch_env_amount": u16(6),
        "mode": record[8],
        "amp_gate": record[9],
        "engine": record[11],
    }
