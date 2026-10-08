#!/usr/bin/env python3
"""Compare PerkyBits reference PCM against Octabam DSP-host PCM.

Both inputs must be mono signed 16-bit little-endian raw PCM, at the same
sample rate, with the same note/velocity/knob/mode/trigger schedule.  No
resampling or arbitrary gain normalization is performed: those can hide bugs.
A bounded alignment search compensates for host startup latency only.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path


def read_pcm(path: Path) -> list[float]:
    data = path.read_bytes()
    if not data or len(data) % 2:
        raise ValueError(f"{path}: expected nonempty signed 16-bit LE PCM")
    return [v / 32768.0 for v in struct.unpack("<" + "h" * (len(data) // 2), data)]


def compare(ref: list[float], got: list[float], max_shift: int = 256) -> dict:
    if max_shift < 0:
        raise ValueError("max_shift must be nonnegative")
    if len(ref) < 32 or len(got) < 32:
        raise ValueError("need at least 32 samples in each stream")
    best = None
    for shift in range(-max_shift, max_shift + 1):
        r0, g0 = max(0, -shift), max(0, shift)
        n = min(len(ref) - r0, len(got) - g0)
        if n < 32:
            continue
        # Select the shift using a fixed window, not the overlap length.
        window = min(n, len(ref), len(got), 8192)
        dot = sum(ref[r0+i] * got[g0+i] for i in range(window))
        rr = sum(ref[r0+i] ** 2 for i in range(window))
        gg = sum(got[g0+i] ** 2 for i in range(window))
        correlation = dot / math.sqrt(rr * gg) if rr > 0 and gg > 0 else 0.0
        score = (correlation, -abs(shift))
        if best is None or score > best[0]:
            best = (score, shift, r0, g0, n)
    if best is None:
        raise ValueError("no usable overlapping PCM")
    _, shift, r0, g0, n = best
    delta = [ref[r0+i] - got[g0+i] for i in range(n)]
    ref_energy = sum(ref[r0+i] ** 2 for i in range(n))
    got_energy = sum(got[g0+i] ** 2 for i in range(n))
    error_energy = sum(v*v for v in delta)
    rms = math.sqrt(error_energy / n)
    normalized_error = math.sqrt(error_energy / ref_energy) if ref_energy else None
    return {
        "reference_samples": len(ref), "candidate_samples": len(got),
        "aligned_samples": n, "candidate_lag_samples": shift,
        "correlation": best[0][0],
        "reference_rms": math.sqrt(ref_energy / n),
        "candidate_rms": math.sqrt(got_energy / n),
        "error_rms": rms, "peak_abs_error": max(map(abs, delta)),
        "normalized_error": normalized_error,
        "bit_identical": all(v == 0 for v in delta),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reference", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--max-shift", type=int, default=256)
    p.add_argument("--json", type=Path)
    args = p.parse_args()
    result = compare(read_pcm(args.reference), read_pcm(args.candidate), args.max_shift)
    output = json.dumps(result, indent=2)
    if args.json:
        args.json.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
