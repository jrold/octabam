#!/usr/bin/env python3
"""Exact storage analysis for extracted PERKY Noise/Tone tables.

Input is the directory produced by ``extract_noise_tone_tables.py``. This tool
never needs the PĒRKONS update itself and never writes firmware-owned samples
back into the repository. It answers the concrete Octatrack question: can the
four 256-sample waves plus two 2048-entry envelope curves fit in the measured
private DSP data-memory headroom without approximation?

The formats reported here are all lossless and random-access capable:

* ``raw24``: one 16-bit sample per DSP word (simple, expensive);
* ``u16pack``: three 16-bit values in two 24-bit words;
* ``block-delta``: one 16-bit anchor per block followed by fixed-width signed
  deltas inside that block. Lookup starts from the block anchor, so it never
  needs a prefix sum from the beginning of the curve.

The packing helpers below are executable specifications, not just size maths:
the verifier round-trips them and checks random access at every sample.

The report also includes the renderer's compact DSP-native live-state budget.
The ARM oracle has a 0x120-byte object, but the shared Noise/Tone renderer only
reads/writes a much smaller field set. Keeping those fields as direct DSP
words is both faster and dramatically smaller than the intentionally wasteful
one-byte-per-word Python word model.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import struct
from typing import Iterable

PRIVATE_X_WORDS = 616
PRIVATE_Y_WORDS = 2155
WAVE_SAMPLES = 256
ENVELOPE_SAMPLES = 2048
DSP_WORD_BITS = 24
DSP_WORD_MASK = (1 << DSP_WORD_BITS) - 1

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
    return (bits + DSP_WORD_BITS - 1) // DSP_WORD_BITS


def _put_bits(words: list[int], bitpos: int, value: int, width: int) -> None:
    """Write low ``width`` bits into a 24-bit-word array, LSB-first."""
    value &= (1 << width) - 1
    remaining = width
    shift = 0
    while remaining:
        wi, off = divmod(bitpos, DSP_WORD_BITS)
        take = min(remaining, DSP_WORD_BITS - off)
        mask = (1 << take) - 1
        words[wi] |= ((value >> shift) & mask) << off
        words[wi] &= DSP_WORD_MASK
        bitpos += take
        shift += take
        remaining -= take


def _get_bits(words: list[int], bitpos: int, width: int) -> int:
    """Read ``width`` bits from a 24-bit-word array, LSB-first."""
    result = 0
    out_shift = 0
    remaining = width
    while remaining:
        wi, off = divmod(bitpos, DSP_WORD_BITS)
        take = min(remaining, DSP_WORD_BITS - off)
        mask = (1 << take) - 1
        result |= ((words[wi] >> off) & mask) << out_shift
        bitpos += take
        out_shift += take
        remaining -= take
    return result


def pack_fixed(values: Iterable[int], width: int) -> list[int]:
    vals = list(values)
    if not 1 <= width <= 24:
        raise ValueError("fixed packing width must be 1..24")
    words = [0] * words_for_bits(len(vals) * width)
    for index, value in enumerate(vals):
        if not 0 <= value < (1 << width):
            raise ValueError(f"value {value} does not fit unsigned {width} bits")
        _put_bits(words, index * width, value, width)
    return words


def unpack_fixed(words: list[int], count: int, width: int) -> list[int]:
    return [_get_bits(words, index * width, width) for index in range(count)]


def u16pack(values: Iterable[int]) -> list[int]:
    return pack_fixed(values, 16)


def u16unpack(words: list[int], count: int) -> list[int]:
    return unpack_fixed(words, count, 16)


def _signed_encode(value: int, width: int) -> int:
    lo = -(1 << (width - 1))
    hi = (1 << (width - 1)) - 1
    if not lo <= value <= hi:
        raise ValueError(f"signed value {value} does not fit {width} bits")
    return value & ((1 << width) - 1)


def _signed_decode(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def block_delta_layout(values: list[int], block: int) -> tuple[int, int, int, int]:
    """Return (width, anchors, delta_count, total_bits) for one curve."""
    if block <= 1:
        raise ValueError("block must be >1")
    all_deltas = [
        signed_delta(values[i], values[i + 1])
        for i in range(len(values) - 1)
        if (i + 1) % block != 0
    ]
    width = signed_bits(all_deltas)
    anchors = (len(values) + block - 1) // block
    delta_count = len(values) - anchors
    bits = anchors * 16 + delta_count * width
    return width, anchors, delta_count, bits


def _block_bitpos(block_index: int, block: int, width: int) -> int:
    return block_index * (16 + (block - 1) * width)


def pack_block_delta(values: list[int], block: int) -> tuple[list[int], int]:
    width, _anchors, _delta_count, bits = block_delta_layout(values, block)
    words = [0] * words_for_bits(bits)
    for block_index, start in enumerate(range(0, len(values), block)):
        chunk = values[start:start + block]
        bitpos = _block_bitpos(block_index, block, width)
        _put_bits(words, bitpos, chunk[0], 16)
        bitpos += 16
        for previous, current in zip(chunk, chunk[1:]):
            delta = signed_delta(previous, current)
            _put_bits(words, bitpos, _signed_encode(delta, width), width)
            bitpos += width
    return words, width


def block_delta_at(words: list[int], index: int, count: int,
                   block: int, width: int) -> int:
    """Random-access one decoded value with at most ``block-1`` additions."""
    if not 0 <= index < count:
        raise IndexError(index)
    block_index, within = divmod(index, block)
    bitpos = _block_bitpos(block_index, block, width)
    value = _get_bits(words, bitpos, 16)
    bitpos += 16
    for _ in range(within):
        value += _signed_decode(_get_bits(words, bitpos, width), width)
        bitpos += width
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"decoded curve value escaped u16: {value}")
    return value


def unpack_block_delta(words: list[int], count: int,
                       block: int, width: int) -> list[int]:
    return [block_delta_at(words, i, count, block, width) for i in range(count)]


def u16pack_count(count: int) -> Encoding:
    bits = count * 16
    return Encoding("u16pack", words_for_bits(bits), bits)


def block_delta(values: list[int], block: int) -> Encoding:
    width, anchors, delta_count, bits = block_delta_layout(values, block)
    max_decode = min(block - 1, max(0, len(values) - 1))
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
        # The analysis must describe a format that actually round-trips.
        if best.block is None:
            if u16unpack(u16pack(values), len(values)) != values:
                raise AssertionError(f"{path.name}: u16pack round-trip failed")
        else:
            packed, width = pack_block_delta(values, best.block)
            if width != best.delta_bits:
                raise AssertionError(f"{path.name}: block-delta width drift")
            if unpack_block_delta(packed, len(values), best.block, width) != values:
                raise AssertionError(f"{path.name}: block-delta round-trip failed")
        env_best_words += best.words
        env_report.append({
            "file": path.name,
            "delta": delta_stats(values),
            "best": asdict(best),
            "candidates": [asdict(x) for x in candidates],
        })

    # Every wave is random-indexed twice per sample. Use one contiguous dense
    # 16-bit stream: three samples per two DSP words. Keeping all unique waves
    # in one stream avoids a padding word at each 256-sample table boundary.
    wave_values = [value for table in waves for value in table]
    wave_words_each = u16pack_count(WAVE_SAMPLES).words
    wave_packed = u16pack(wave_values)
    if u16unpack(wave_packed, len(wave_values)) != wave_values:
        raise AssertionError("wave u16pack round-trip failed")
    wave_packed_words = len(wave_packed)
    wave_raw24_words = WAVE_SAMPLES * len(waves)
    wave_report = []
    for name, values in zip(wave_names, waves):
        delta_best, delta_candidates = best_curve_encoding(values)
        wave_report.append({
            "file": name,
            "raw24_words": WAVE_SAMPLES,
            "standalone_u16pack_words": wave_words_each,
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
        f"raw24 {w['raw24_words']} words, contiguous u16pack "
        f"{w['u16pack_words']} words"
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
