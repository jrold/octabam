#!/usr/bin/env python3
"""Build exact compact static assets for the PERKY Simple Drum DSP port.

Input is a local extraction directory containing the authentic v1.2.1 assets:
``pitch.bin``, ``envelope1.bin`` and the three ``wave_<address>.bin`` files.
No firmware-derived bytes are stored in this source file or expected in Git.

Output is deterministic and split by placement class so the combined PERKY
image builder can place each stream independently without changing its ABI:
- ``waves.bin``      512 24-bit DSP words;
- ``envelope.bin``   179 24-bit DSP words;
- ``pitch.bin``       67 24-bit DSP words;
- ``layout.json`` hashes, identities, counts and codec metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import simple_drum_control as control  # noqa: E402
import simple_drum_tables as tables  # noqa: E402

WAVE_ADDRESSES = tuple(control.wave_for_panel_mode(i) for i in range(3))


def read_u16(path: Path, count: int) -> list[int]:
    raw = path.read_bytes()
    if len(raw) != count * 2:
        raise ValueError(f"{path}: {len(raw)} bytes, expected {count * 2}")
    return list(struct.unpack(f"<{count}H", raw))


def words24_bytes(words) -> bytes:
    out = bytearray()
    for raw in words:
        value = int(raw)
        if not 0 <= value <= 0xFFFFFF:
            raise ValueError(f"DSP word outside 24-bit range: {value}")
        out += bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF))
    return bytes(out)


def write_stream(out: Path, stem: str, words) -> dict:
    values = tuple(int(x) & 0xFFFFFF for x in words)
    blob = words24_bytes(values)
    (out / f"{stem}.bin").write_bytes(blob)
    (out / f"{stem}.words").write_text(
        "\n".join(f"{value:06x}" for value in values) + "\n"
    )
    return {
        "file": f"{stem}.bin",
        "words": len(values),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def build(directory: Path, out: Path) -> dict:
    pitch_values = read_u16(directory / "pitch.bin", 4096)
    envelope_values = read_u16(directory / "envelope1.bin", 2048)

    wave_values: list[int] = []
    wave_sources = []
    for address in WAVE_ADDRESSES:
        name = f"wave_{address:08x}.bin"
        path = directory / name
        values = read_u16(path, tables.WAVE_SAMPLES)
        wave_values.extend(values)
        wave_sources.append({
            "address": f"0x{address:08x}",
            "file": name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })

    packed_waves = tables.pack_u16(wave_values)
    packed_env = tables.pack_pitch_envelope(envelope_values)
    packed_pitch = tables.pack_pitch_basis(pitch_values)

    if len(packed_waves) != 512:
        raise AssertionError(f"wave payload is {len(packed_waves)} words, expected 512")
    if len(packed_env.words) != 179:
        raise AssertionError(f"envelope payload is {len(packed_env.words)} words, expected 179")
    if len(packed_pitch.words) != 67:
        raise AssertionError(f"pitch payload is {len(packed_pitch.words)} words, expected 67")

    # Re-read every source value through the exact runtime codecs before any
    # output is admitted.  This also pins the 1024 duplicate endpoint policy.
    for index, want in enumerate(pitch_values):
        got = tables.pitch_at(packed_pitch, index)
        if got != want:
            raise AssertionError(f"pitch round-trip mismatch at {index}: {got} != {want}")
    for index in range(1025):
        got = tables.envelope_at(packed_env, index)
        want = envelope_values[index]
        if got != want:
            raise AssertionError(f"envelope round-trip mismatch at {index}: {got} != {want}")
    for index, want in enumerate(wave_values):
        got = tables.u16_at(packed_waves, index, len(wave_values))
        if got != want:
            raise AssertionError(f"wave round-trip mismatch at {index}: {got} != {want}")

    out.mkdir(parents=True, exist_ok=True)
    wave_meta = write_stream(out, "waves", packed_waves)
    env_meta = write_stream(out, "envelope", packed_env.words)
    pitch_meta = write_stream(out, "pitch", packed_pitch.words)

    source_hashes = {
        "pitch.bin": hashlib.sha256((directory / "pitch.bin").read_bytes()).hexdigest(),
        "envelope1.bin": hashlib.sha256((directory / "envelope1.bin").read_bytes()).hexdigest(),
    }
    source_hashes.update({item["file"]: item["sha256"] for item in wave_sources})

    layout = {
        "schema": "perky-simple-drum-dsp-tables-v1",
        "dsp_word_bytes": 3,
        "total_words": wave_meta["words"] + env_meta["words"] + pitch_meta["words"],
        "streams": {
            "waves": wave_meta,
            "pitch_envelope": {
                **env_meta,
                "stored_samples": tables.ENV_SAMPLES_STORED,
                "runtime_endpoint": tables.ENV_ENDPOINT_INDEX,
                "block_samples": tables.BLOCK,
                "first_delta_bits": packed_env.first_delta_bits,
                "second_delta_bits": packed_env.second_delta_bits,
            },
            "pitch_basis": {
                **pitch_meta,
                "stored_samples": tables.PITCH_BASIS_SAMPLES,
                "reconstructs_samples": 4096,
                "block_samples": tables.BLOCK,
                "first_delta_bits": packed_pitch.first_delta_bits,
                "second_delta_bits": packed_pitch.second_delta_bits,
            },
        },
        "waves": [
            {
                **item,
                "physical_mode": ordinal + 1,
                "global_sample_base": ordinal * tables.WAVE_SAMPLES,
            }
            for ordinal, item in enumerate(wave_sources)
        ],
        "source_sha256": source_hashes,
    }
    if layout["total_words"] != 758:
        raise AssertionError(f"Simple Drum payload is {layout['total_words']} words, expected 758")
    (out / "layout.json").write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n")
    return layout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path, help="local authentic Simple Drum extraction")
    ap.add_argument("--out", type=Path, default=Path("out/perky/simple-drum-packed"))
    args = ap.parse_args()
    layout = build(args.directory, args.out)
    print(
        "PERKY Simple Drum payload: PASS "
        f"({layout['total_words']} exact DSP words: "
        f"{layout['streams']['waves']['words']} waves + "
        f"{layout['streams']['pitch_envelope']['words']} envelope + "
        f"{layout['streams']['pitch_basis']['words']} pitch)"
    )
    for key in ("waves", "pitch_envelope", "pitch_basis"):
        stream = layout["streams"][key]
        print(f"  {key}: {stream['words']} words sha256={stream['sha256']}")


if __name__ == "__main__":
    main()
