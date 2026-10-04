#!/usr/bin/env python3
"""Build the packed PERKY Noise/Tone DSP table payload.

Input is a directory produced by ``extract_noise_tone_tables.py`` or the
explicit synthetic fixture generator.  Output contains no hidden conversion:

* ``tables.bin`` -- 24-bit little-endian DSP words, ready to place in a DSP
  upload record;
* ``layout.json`` -- offsets/word counts, wave identity map and per-envelope
  delta widths required by the renderer;
* ``tables.words`` -- human-readable six-hex-digit words for review/debugging.

The payload is deterministic.  Wave order follows ``manifest.json`` first-seen
order so the four firmware-style identities can be translated to stable local
wave ordinals by the source record/control converter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
sys.path.insert(0, str(PERKY))

import noise_tone_tables as pack  # noqa:E402


def read_u16(path: Path, count: int) -> list[int]:
    raw = path.read_bytes()
    if len(raw) != count * 2:
        raise ValueError(f"{path}: {len(raw)} bytes, expected {count*2}")
    return list(struct.unpack(f"<{count}H", raw))


def words24_bytes(words: list[int]) -> bytes:
    out = bytearray()
    for value in words:
        if not 0 <= value <= 0xFFFFFF:
            raise ValueError(f"DSP word out of range: {value}")
        out += bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF))
    return bytes(out)


def parse_wave_address(name: str) -> int:
    if not name.startswith("wave_") or not name.endswith(".bin"):
        raise ValueError(f"not a wave filename: {name}")
    return int(name[5:-4], 16)


def build(directory: Path, out: Path) -> dict:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"{directory}: missing manifest.json")
    manifest = json.loads(manifest_path.read_text())

    wave_names = [
        str(item["file"])
        for item in manifest.get("files", [])
        if str(item.get("file", "")).startswith("wave_")
    ]
    wave_names = list(dict.fromkeys(wave_names))
    if not wave_names:
        raise ValueError("manifest contains no wave_*.bin files")

    wave_pairs: list[tuple[int, list[int]]] = []
    for name in wave_names:
        path = directory / name
        if not path.exists():
            raise ValueError(f"manifest names missing {name}")
        wave_pairs.append((parse_wave_address(name), read_u16(path, pack.WAVE_SAMPLES)))

    packed_waves = pack.pack_waves(wave_pairs)
    env_values = [
        read_u16(directory / "envelope1.bin", pack.ENVELOPE_SAMPLES),
        read_u16(directory / "envelope2.bin", pack.ENVELOPE_SAMPLES),
    ]
    envelopes = [pack.pack_envelope(values) for values in env_values]

    words: list[int] = []
    wave_offset = len(words)
    words.extend(packed_waves.words)
    wave_words = len(packed_waves.words)

    env_layout = []
    for index, table in enumerate(envelopes, 1):
        offset = len(words)
        words.extend(table.words)
        env_layout.append({
            "index": index,
            "offset_words": offset,
            "words": len(table.words),
            "delta_bits": table.delta_bits,
            "block_samples": table.block,
            "max_decode_adds_on_cache_fill": table.max_adds,
        })

    blob = words24_bytes(words)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.bin").write_bytes(blob)
    (out / "tables.words").write_text(
        "\n".join(f"{value:06x}" for value in words) + "\n"
    )

    source_hashes = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in wave_names + ["envelope1.bin", "envelope2.bin"]
    }
    layout = {
        "schema": "perky-noise-tone-dsp-tables-v1",
        "synthetic": bool(manifest.get("synthetic", False)),
        "source_manifest_schema": manifest.get("schema"),
        "dsp_word_bytes": 3,
        "total_words": len(words),
        "total_bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "waves": {
            "offset_words": wave_offset,
            "words": wave_words,
            "samples_per_wave": pack.WAVE_SAMPLES,
            "identities": [
                {
                    "ordinal": ordinal,
                    "address": f"0x{address:08x}",
                    "global_sample_base": ordinal * pack.WAVE_SAMPLES,
                }
                for ordinal, (address, _values) in enumerate(wave_pairs)
            ],
        },
        "envelopes": env_layout,
        "source_sha256": source_hashes,
    }
    (out / "layout.json").write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n")
    return layout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path,
                    help="extracted/synthetic Noise-Tone table directory")
    ap.add_argument("--out", type=Path,
                    default=Path("out/perky/noise-tone-packed"))
    args = ap.parse_args()
    layout = build(args.directory, args.out)
    kind = "SYNTHETIC" if layout["synthetic"] else "REAL-DATA INPUT"
    print(
        f"PERKY packed table payload: {kind}; {layout['total_words']} DSP words, "
        f"{layout['total_bytes']} bytes, sha256={layout['sha256']}"
    )
    print(
        "  waves: " + ", ".join(
            f"#{item['ordinal']}={item['address']}"
            for item in layout["waves"]["identities"]
        )
    )
    for env in layout["envelopes"]:
        print(
            f"  env{env['index']}: +{env['offset_words']} words, "
            f"{env['words']} words, {env['delta_bits']}-bit deltas"
        )


if __name__ == "__main__":
    main()
