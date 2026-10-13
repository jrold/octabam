#!/usr/bin/env python3
"""Generate the level-calibration WAVs for the physical Perky A/B.

`out/` is gitignored, so the WAVs themselves are not committed -- which is why this
generator is. Run it to reproduce them:

    python3 tools/perky/make_calibration_wavs.py [outdir]

Task 4 of the milestone asks, if practical, for a small calibration file that can also
be loaded onto the physical Octatrack, so the level match is checked by ear against
real hardware rather than argued from the source.

Two files, 44.1 kHz / 16-bit stereo:

``level-ladder.wav``
    A 1 kHz tone in nine one-second steps, 0 to -24 dBFS in 3 dB increments, with
    0.25 s of silence between steps. The user loads it on a stock track at
    LEVEL 128 / VOL 0, trigs Perky on another track at the same settings, walks the
    ladder, and reports the step whose loudness matches. That number IS the residual
    error after the shipped trim, read off a file instead of estimated.

``reference-hit.wav``
    One decaying hit at -6 dBFS (180 Hz + 1300 Hz, exponential decay, 1.5 s) for a
    drum-like comparison. Perky is a drum machine, and matching a transient is not the
    same judgement as matching a sustained sine.

The step peaks are exact, not nominal: the ladder is generated from
``32767 * 10**(dB/20)`` and rounded, so re-reading the file reproduces the labels.

What this cannot measure: it is the INTEGRATION level, which is what the source trim
controls. It says nothing about the renderer's arithmetic, which the seam gates pin
separately against the PerkyBits reference and which the trim does not touch.
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 44100
CHANNELS = 2
FULL_SCALE = 32767
LADDER_DB = (0, -3, -6, -9, -12, -15, -18, -21, -24)
STEP_SECONDS = 1.0
GAP_SECONDS = 0.25
HIT_DB = -6


def amplitude(dbfs: float) -> float:
    """Linear amplitude for a level in dBFS, where full scale is FULL_SCALE."""
    return FULL_SCALE * (10.0 ** (dbfs / 20.0))


def clamp(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def tone(freq: float, amp: float, seconds: float, fade: float = 0.005) -> list[int]:
    """A sine with click-free edges, so the step boundaries are not themselves audible."""
    total = int(SAMPLE_RATE * seconds)
    edge = max(1, int(SAMPLE_RATE * fade))
    out = []
    for i in range(total):
        s = amp * math.sin(2.0 * math.pi * freq * i / SAMPLE_RATE)
        if i < edge:
            s *= i / edge
        elif i > total - edge:
            s *= (total - i) / edge
        out.append(clamp(s))
    return out


def ladder() -> list[int]:
    silence = [0] * int(SAMPLE_RATE * GAP_SECONDS)
    out: list[int] = []
    for dbfs in LADDER_DB:
        out += tone(1000.0, amplitude(dbfs), STEP_SECONDS)
        out += silence
    return out


def reference_hit() -> list[int]:
    total = int(SAMPLE_RATE * 1.5)
    amp = amplitude(HIT_DB)
    out = []
    for i in range(total):
        t = i / SAMPLE_RATE
        env = math.exp(-t * 9.0)
        if t < 0.002:
            env *= t / 0.002
        s = (0.75 * math.sin(2 * math.pi * 180 * t)
             + 0.25 * math.sin(2 * math.pi * 1300 * t)) * amp * env
        out.append(clamp(s))
    return out


def write(path: Path, frames: list[int]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(struct.pack("<hh", v, v) for v in frames))


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/calib")
    outdir.mkdir(parents=True, exist_ok=True)
    for name, frames in (("level-ladder.wav", ladder()),
                         ("reference-hit.wav", reference_hit())):
        path = outdir / name
        write(path, frames)
        print(f"  {path}  {path.stat().st_size} B")
    print()
    print("  ladder steps, nominal vs the level actually written:")
    for dbfs in LADDER_DB:
        print(f"    {dbfs:+4d} dBFS   peak {clamp(amplitude(dbfs)):5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
