"""Candidate Fold Drum 2 PK/Y1 prepared-control transport.

PĒRKONS v1.2.1 uses the same front-panel smoother and Fold-family control law
for Voice 2 / A1 as Voice 1 / A1. Reuse the already-qualified Fold Drum 1
transport exactly; only the zero-based engine-family byte changes from 0 to 3.

This is a control-record oracle. It does not expose Fold Drum 2 in the
Octatrack browser or claim shipping/hardware qualification by itself.
"""
from __future__ import annotations

from dataclasses import dataclass

import fold_drum_transport as fold1

ENGINE_INDEX = 3


@dataclass
class State(fold1.State):
    def prepare(self, raw, mode, *, trigger):
        record = bytearray(super().prepare(raw, mode, trigger=trigger))
        record[11] = ENGINE_INDEX
        return bytes(record)
