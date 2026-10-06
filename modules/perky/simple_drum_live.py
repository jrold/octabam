"""Live 34-word state preparation for engine-003 Simple Drum.

This is the bridge between the prepared PK/Y1 record and the already-qualified
compact sample renderer. It models only state that the renderer consumes.

Authentic v1.2.1 trigger semantics were recovered from the ARM code and checked
against 27 pre-render RAM captures:
- both envelopes are triggered by setting state=1 and hold=1;
- because Simple Drum configures reset-on-trigger for both envelopes, their
  accumulated values reset to zero;
- oscillator phase/current wave are NOT reset by a trigger;
- the normal post-trigger update installs raw pitch, decay rates, pitch amount,
  the amplitude gate bit and the deferred next-wave target.

Consequently retriggering restarts the envelopes while preserving oscillator
phase. That distinction matters for repeated hits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import simple_drum_compact as compact
import simple_drum_control as control
import simple_drum_transport as transport

INITIAL_CURRENT_WAVE = 0x080228A0
VELOCITY = 255
AMP_ATTACK = 0x2AAA
PITCH_ATTACK = 0x5555


@dataclass
class LiveSimpleDrum:
    voice: compact.CompactSimpleDrum

    @classmethod
    def fresh(cls) -> "LiveSimpleDrum":
        words = [0] * compact.WORDS_PER_VOICE
        words[compact.VELOCITY] = VELOCITY
        words[compact.MUTE] = 0
        compact.CompactSimpleDrum._set_list_u32(words, compact.OSC_PHASE, 0)
        compact.CompactSimpleDrum._set_list_u32(words, compact.OSC_INCREMENT, 0)
        compact.CompactSimpleDrum._set_list_u32(
            words, compact.OSC_CURRENT, INITIAL_CURRENT_WAVE
        )
        compact.CompactSimpleDrum._set_list_u32(
            words, compact.OSC_NEXT, INITIAL_CURRENT_WAVE
        )

        cls._init_envelope(words, compact.AMP_ENV, shape=0, attack=AMP_ATTACK)
        cls._init_envelope(
            words, compact.PITCH_ENV, shape=1, attack=PITCH_ATTACK
        )
        return cls(compact.CompactSimpleDrum(words))

    @staticmethod
    def _init_envelope(words: list[int], base: int,
                       *, shape: int, attack: int) -> None:
        words[base + compact.ENV_STATE] = 0
        words[base + compact.ENV_SHAPE] = shape
        words[base + compact.ENV_FLAG4] = 0
        words[base + compact.ENV_FLAG6] = 1
        words[base + compact.ENV_TRIGGER] = 0
        compact.CompactSimpleDrum._set_list_u32(
            words, base + compact.ENV_VALUE, 0
        )
        compact.CompactSimpleDrum._set_list_u32(
            words, base + compact.ENV_HOLD, 0
        )
        words[base + compact.ENV_ATTACK] = attack
        words[base + compact.ENV_DECAY] = 0

    def trigger(self) -> None:
        """Apply the original Simple Drum envelope trigger helper.

        Do not reset oscillator phase/current here. The v1.2.1 engine does not.
        """
        for base in (compact.AMP_ENV, compact.PITCH_ENV):
            self.voice.words[base + compact.ENV_STATE] = 1
            self.voice.set_u32(base + compact.ENV_HOLD, 1)
            self.voice.set_u32(base + compact.ENV_VALUE, 0)

    def apply_prepared_record(
        self,
        record: bytes,
        *,
        pitch_increment: Callable[[int], int] | None = None,
    ) -> None:
        """Install the post-update values carried by engine-003 PK/Y1.

        ``pitch_increment`` is the exact v1.2.1 pitch-table lookup for the
        prepared raw pitch. Supplying it makes the compact state itself match
        pre-render firmware RAM. The sample renderer recomputes oscillator
        frequency before output, so it is optional for transport-only tests.
        """
        fields = transport.decode(record)
        if fields["engine"] != transport.ENGINE_INDEX:
            raise ValueError("record is not Simple Drum engine 003")

        raw_pitch = fields["raw_pitch"]
        self.voice.words[compact.RAW_PITCH] = raw_pitch
        self.voice.words[compact.PITCH_ENV_AMOUNT] = fields["pitch_env_amount"]
        self.voice.words[compact.AMP_ENV + compact.ENV_DECAY] = fields["amp_decay"]
        self.voice.words[
            compact.PITCH_ENV + compact.ENV_DECAY
        ] = fields["pitch_decay"]
        self.voice.words[
            compact.AMP_ENV + compact.ENV_TRIGGER
        ] = fields["amp_gate"] & 0xFF
        self.voice.words[
            compact.PITCH_ENV + compact.ENV_TRIGGER
        ] = 0
        self.voice.set_u32(
            compact.OSC_NEXT,
            control.wave_for_panel_mode(fields["mode"]),
        )

        if pitch_increment is not None:
            self.voice.set_u32(
                compact.OSC_INCREMENT,
                int(pitch_increment(raw_pitch)) & 0xFFFFFFFF,
            )

    def trigger_with_record(
        self,
        record: bytes,
        *,
        pitch_increment: Callable[[int], int] | None = None,
    ) -> None:
        """Mirror v1.2.1 wrapper order: trigger engine, then post-trigger update."""
        self.trigger()
        self.apply_prepared_record(record, pitch_increment=pitch_increment)
