#!/usr/bin/env python3
"""Exact storage analysis for extracted PERKY Noise/Tone tables.

Input is the directory produced by ``extract_noise_tone_tables.py``.  This tool
never needs the PĒRKONS update itself and never writes firmware-owned samples
back into the repository.  It answers the concrete Octatrack question: can the
four 256-sample waves plus two 2048-entry envelope curves fit in the measured
private DSP data-memory headroom without approximation?

The formats reported here are all lossless and random-access capable:

* ``raw24``: one 16-bit sample per DSP word (simple, expensive);
* ``u16pack``: three 16-bit values in two 24-bit words;
* ``block-delta``: one 16-bit anchor per block followed by fixed-width signed
  deltas inside that block.  Lookup starts from the block anchor, so it never
  needs a prefix sum from the beginning of the curve.

The report also includes the renderer's compact DSP-native live-state budget.
The ARM oracle has a 0x120-byte object, but the shared Noise/Tone renderer only
reads/writes a much smaller field set.  Keeping those fields as direct DSP
words is both faster and dramatically smaller than the intentionally wasteful
one-byte-per-word Python word model.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
import struct
from typing import Iterable

PRIVATE_X_WORDS = 616
PRIVATE_Y_WORDS = 2155
WAVE_SAMPLES = 256
ENVELOPE_SAMPLES = 2048

# Direct DSP words per voice for fields actually touched by the validated
# shared Noise/Tone renderer. u32 values are two 16-bit limbs.
LIVE_STATE_FIELDS = {
    "velocity": 1,
    "envelope": 11,     # state, shape, 3 flags, value, hold-test, atk, decay
    "noise": 3,         # count, reload, held sample
    "filter": 8,        # damping, coefficient, first/second/velocity u32
    "oscillators": 16,  # two x (phase/inc/current/next u32)
    "mix": 2,           # u32
}
LIVE_STATE_WORDS_PER_VOICE = sum(LIVE_STATE_FIELDS.values())
GLOBAL_RNG_WORDS = 4     # two u32 words, shared like the firmware PRNG
VOICE_COUNT_PER_CORE = 4
LIVE_STATE_X_WORDS = LIVE_STATE_WORDS_PER_VOICE * VOICE_COUNT_PER_CORE + GLOBAL_RNG_WORDS


@dataclass(frozen=True)
class Encoding:
    name: str
    words: int
    bits: int
    block: int | None = None
    delta_bits: int | None = None
    max_decode_deltas: int = 0


def read_u16(path: Path, expected: int) -> list[int]:
    raw = path.read_bytes()
    if len(raw) != expected * 2:
        raise ValueError(
            f"{path}: {len(raw)} bytes, expected {expected * 2} "
            f"({expected} little-endian u16 values)"
        )
    return list(struct.unpack(f"<{expected}H", raw))


def signed_delta(a: int, b: int) -> int:
    """Mathematical difference between adjacent unsigned-16 curve values."""
    return int(b) - int(a)


def signed_bits(values: Iterable[int]) -> int:
    vals = list(values)
    if not vals:
        return 1
    for width in range(1, 18):
        lo = -(1 << (width - 1))
        hi = (1 << (width - 1)) - 1
        if all(lo <= value <= hi for value in vals):
            return width
    raise ValueError("u16 first differences require more than 17 signed bits")


def words_for_bits(bits: int) -> int:
    return (bits + 23) // 24


def u16pack_count(count: int) -> Encoding:
    bits = count * 16
    return Encoding("u16pack", words_for_bits(bits), bits)


def block_delta(values: list[int], block: int) -> Encoding:
    if block <= 1:
        raise ValueError("block must be >1")
    widths: list[int] = []
    bits = 0
    max_decode = 0
    for start in range(0, len(values), block):
        chunk = values[start:start + block]
        bits += 16  # direct random-access anchor
        if len(chunk) <= 1:
            continue
        deltas = [signed_delta(a, b) for a, b in zip(chunk, chunk[1:])]
        width = signed_bits(deltas)
        widths.append(width)
        # Shipping decoder is simplest if the width is fixed for the entire
        # curve. Recompute below after finding the global width.
        max_decode = max(max_decode, len(deltas))

    all_deltas = [
        signed_delta(values[i], values[i + 1])
        for i in range(len(values) - 1)
        if (i + 1) % block != 0
    ]
    width = signed_bits(all_deltas)
    anchors = (len(values) + block - 1) // block
    delta_count = len(values) - anchors
    bits = anchors * 16 + delta_count * width
    return Encoding(
        f"block-delta-{block}",
        words_for_bits(bits),
        bits,
        block=block,
        delta_bits=width,
        max_decode_deltas=max_decode,
    )


def best_curve_encoding(values: list[int]) -> tuple[Encoding, list[Encoding]]:
    candidates = [u16pack_count(len(values))]
    candidates += [block_delta(values, b) for b in (4, 8, 16, 32, 64, 128, 256)]
    # Prefer fewer words, then fewer decode additions, then simpler raw packing.
    best = min(candidates, key=lambda x: (x.words, x.max_decode_deltas, x.name != "u16pack"))
    return best, candidates


def delta_stats(values: list[int]) -> dict:
    deltas = [signed_delta(a, b) for a, b in zip(values, values[1:])]
    if not deltas:
        return {"min": 0, "max": 0, "signed_bits": 1, "unique": 0}
    return {
        "min": min(deltas),
        "max": max(deltas),
        "signed_bits": signed_bits(deltas),
        "unique": len(set(deltas)),
    }


def analyze(directory: Path) -> dict:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"{directory}: missing manifest.json from table extractor")
    manifest = json.loads(manifest_path.read_text())

    envelopes = [directory / "envelope1.bin", directory / "envelope2.bin"]
    for path in envelopes:
        if not path.exists():
            raise ValueError(f"{directory}: missing {path.name}")

    wave_names = [item["file"] for item in manifest.get("files", [])
                  if str(item.get("file", "")).startswith("wave_")]
    # The shared renderer needs four state-selected wave references. Duplicate
    # pointers are allowed; storage needs one copy per unique extracted file.
    wave_names = list(dict.fromkeys(wave_names))
    if not wave_names:
        raise ValueError(
            f"{directory}: manifest has no wave_*.bin files; extract with --state "
            "or the required --wave addresses"
        )
    waves = []
    for name in wave_names:
        path = directory / name
        if not path.exists():
            raise ValueError(f"{directory}: manifest names missing {name}")
        waves.append(read_u16(path, WAVE_SAMPLES))

    env_report = []
    env_best_words = 0
    for path in envelopes:
        values = read_u16(path, ENVELOPE_SAMPLES)
        best, candidates = best_curve_encoding(values)
        env_best_words += best.words
        env_report.append({
            "file": path.name,
            "delta": delta_stats(values),
            "best": asdict(best),
            "candidates": [asdict(x) for x in candidates],
        })

    # Every wave is random-indexed twice per sample. Use dense 16-bit bitpacking
    # as the baseline exact representation: 3 samples / 2 DSP words. Delta
    # forms are reported only as information because they add prefix/decode work
    # to the hottest path.
    wave_words_each = u16pack_count(WAVE_SAMPLES).words
    wave_packed_words = wave_words_each * len(waves)
    wave_raw24_words = WAVE_SAMPLES * len(waves)
    wave_report = []
    for name, values in zip(wave_names, waves):
        delta_best, delta_candidates = best_curve_encoding(values)
        wave_report.append({
            "file": name,
            "raw24_words": WAVE_SAMPLES,
            "u16pack_words": wave_words_each,
            "delta": delta_stats(values),
            "informational_best_delta": asdict(delta_best),
            "delta_candidates": [asdict(x) for x in delta_candidates],
        })

    table_words = wave_packed_words + env_best_words
    y_margin = PRIVATE_Y_WORDS - table_words
    x_margin = PRIVATE_X_WORDS - LIVE_STATE_X_WORDS

    return {
        "schema": "perky-noise-tone-memory-v1",
        "source_manifest": manifest_path.name,
        "unique_wave_tables": len(waves),
        "budgets": {
            "private_x_words": PRIVATE_X_WORDS,
            "private_y_words": PRIVATE_Y_WORDS,
        },
        "live_state": {
            "fields_words_per_voice": LIVE_STATE_FIELDS,
            "words_per_voice": LIVE_STATE_WORDS_PER_VOICE,
            "voices_per_core": VOICE_COUNT_PER_CORE,
            "global_rng_words": GLOBAL_RNG_WORDS,
            "x_words": LIVE_STATE_X_WORDS,
            "x_margin_words": x_margin,
            "fits_private_x": x_margin >= 0,
        },
        "waves": {
            "raw24_words": wave_raw24_words,
            "u16pack_words": wave_packed_words,
            "tables": wave_report,
        },
        "envelopes": {
            "best_exact_words": env_best_words,
            "tables": env_report,
        },
        "combined": {
            "table_y_words": table_words,
            "y_margin_words": y_margin,
            "fits_private_y": y_margin >= 0,
            "fits_measured_private_xy": y_margin >= 0 and x_margin >= 0,
        },
    }


def print_report(report: dict) -> None:
    print("PERKY Noise/Tone exact memory analysis")
    b = report["budgets"]
    s = report["live_state"]
    print(
        f"  measured private budget/core: X {b['private_x_words']} words, "
        f"Y {b['private_y_words']} words"
    )
    print(
        f"  live state: {s['words_per_voice']} words/voice x "
        f"{s['voices_per_core']} + RNG {s['global_rng_words']} = "
        f"{s['x_words']} X words (margin {s['x_margin_words']:+d})"
    )
    w = report["waves"]
    print(
        f"  waves: {report['unique_wave_tables']} unique x {WAVE_SAMPLES}; "
        f"raw24 {w['raw24_words']} words, u16pack {w['u16pack_words']} words"
    )
    for env in report["envelopes"]["tables"]:
        best = env["best"]
        d = env["delta"]
        extra = ""
        if best["block"] is not None:
            extra = (
                f", block {best['block']}, {best['delta_bits']}-bit deltas, "
                f"<= {best['max_decode_deltas']} adds/lookup"
            )
        print(
            f"  {env['file']}: delta {d['min']}..{d['max']} "
            f"({d['signed_bits']} bits global); best {best['name']} = "
            f"{best['words']} words{extra}"
        )
    c = report["combined"]
    print(
        f"  exact table plan: {c['table_y_words']} Y words "
        f"(margin {c['y_margin_words']:+d})"
    )
    print(
        "  RESULT: " + (
            "FITS measured private X/Y budget"
            if c["fits_measured_private_xy"]
            else "DOES NOT FIT measured private X/Y budget"
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path,
                    help="directory from extract_noise_tone_tables.py")
    ap.add_argument("--json", type=Path,
                    help="also write the machine-readable report")
    args = ap.parse_args()
    report = analyze(args.directory)
    print_report(report)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
