#!/usr/bin/env python3
"""Build the packed PERKY Noise/Tone DSP payload.

Input is a directory produced by ``extract_noise_tone_tables.py`` or the
explicit synthetic fixture generator. Output contains two deterministic DSP
assets:

* ``tables.bin`` -- 24-bit little-endian words for private Y;
* ``state_init.bin`` -- 236 24-bit words for private X: four 41-word voices,
  one 17-word curve-aware cache per voice, then four shared RNG limbs;
* ``layout.json`` -- offsets/counts, wave identities, envelope widths, hashes;
* human-readable ``*.words`` mirrors for review/debugging.

No firmware table bytes live in this source. For real-data input, state.bin is
compacted exactly as supplied. For the explicitly synthetic fixture only, the
otherwise pointer-only state is patched into a deterministic audible canary
preset before compaction; layout.json keeps ``synthetic=true`` so it cannot be
mistaken for a measured PĒRKONS state.
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

import noise_tone_compact as compact  # noqa:E402
import noise_tone_tables as pack  # noqa:E402

X_BASE = 0x3800
VOICES = 4
CACHE_WORDS = 17
RNG_WORDS = 4
STATE_INIT_WORDS = VOICES * (compact.WORDS_PER_VOICE + CACHE_WORDS) + RNG_WORDS


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


def _put16(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", raw, off, value & 0xFFFF)


def _put32(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", raw, off, value & 0xFFFFFFFF)


def synthetic_audible_state(raw: bytes) -> bytes:
    """Patch only synthetic fixture state into an audible deterministic preset."""
    if len(raw) != 0x120:
        raise ValueError(f"synthetic state is {len(raw)} bytes, expected 0x120")
    s = bytearray(raw)
    s[6] = 255                         # velocity

    e = 0x74
    s[e] = 0                           # idle until trig flag is published
    s[e + 1] = 1                       # synthetic envelope 1
    s[e + 4] = 0
    s[e + 6] = 1
    s[e + 7] = 0
    _put32(s, e + 0x0C, 0)
    _put32(s, e + 0x10, 0)
    _put16(s, e + 0x20, 0x3000)        # attack
    _put16(s, e + 0x22, 0x0800)        # decay

    n = 0x60
    _put16(s, n, 0)
    _put16(s, n + 2, 2)                # sample/hold reload
    _put16(s, n + 0x10, 0)

    f = 0x9C
    _put16(s, f + 0x0C, 0x1800)        # damping
    _put16(s, f + 0x0E, 0x5000)        # coefficient
    _put32(s, f + 0x10, 0)
    _put32(s, f + 0x14, 0)
    _put32(s, f + 0x18, 0)

    # The fixture already carries four synthetic wave pointers at current/next
    # slots. Give both oscillators a stable musical-rate phase increment.
    _put32(s, 0x2C + 4, 0)
    _put32(s, 0x2C + 8, 0x00004000)
    _put32(s, 0xC4 + 4, 0)
    _put32(s, 0xC4 + 8, 0x00003100)
    _put32(s, 0xF8, 0x00000800)         # balanced noise/tone mix
    return bytes(s)


def build_state_init(directory: Path, manifest: dict) -> tuple[list[int], dict]:
    state_name = str(manifest.get("state_file", "state.bin"))
    state_path = directory / state_name
    if not state_path.exists():
        raise ValueError(f"manifest state_file {state_name!r} is missing")
    raw = state_path.read_bytes()
    if len(raw) != 0x120:
        raise ValueError(f"{state_path}: {len(raw)} bytes, expected 0x120")
    synthetic = bool(manifest.get("synthetic", False))
    if synthetic:
        raw = synthetic_audible_state(raw)

    voice = compact.CompactVoice.from_arm(raw).words
    words: list[int] = []
    for _ in range(VOICES):
        words.extend(voice)
        words.append(0xFFFF)            # curve-aware envelope cache invalid key
        words.extend([0] * 16)
    # Deterministic non-zero two-u32 RNG state: low=1, high=0.
    words.extend((1, 0, 0, 0))
    if len(words) != STATE_INIT_WORDS:
        raise AssertionError(f"state init is {len(words)} words, expected {STATE_INIT_WORDS}")

    blob = words24_bytes(words)
    meta = {
        "base_word": X_BASE,
        "words": len(words),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "voices": VOICES,
        "voice_words": compact.WORDS_PER_VOICE,
        "cache_words_per_voice": CACHE_WORDS,
        "rng_words": RNG_WORDS,
        "synthetic_audible_preset": synthetic,
        "source_state_file": state_name,
        "source_state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
    }
    return words, meta


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

    table_blob = words24_bytes(words)
    state_words, state_meta = build_state_init(directory, manifest)
    state_blob = words24_bytes(state_words)

    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.bin").write_bytes(table_blob)
    (out / "tables.words").write_text(
        "\n".join(f"{value:06x}" for value in words) + "\n"
    )
    (out / "state_init.bin").write_bytes(state_blob)
    (out / "state_init.words").write_text(
        "\n".join(f"{value:06x}" for value in state_words) + "\n"
    )

    state_name = str(manifest.get("state_file", "state.bin"))
    source_hashes = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in wave_names + ["envelope1.bin", "envelope2.bin", state_name]
    }
    layout = {
        "schema": "perky-noise-tone-dsp-tables-v1",
        "synthetic": bool(manifest.get("synthetic", False)),
        "source_manifest_schema": manifest.get("schema"),
        "dsp_word_bytes": 3,
        "total_words": len(words),
        "total_bytes": len(table_blob),
        "sha256": hashlib.sha256(table_blob).hexdigest(),
        "x_init": state_meta,
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
        f"PERKY packed table payload: {kind}; {layout['total_words']} Y words, "
        f"{layout['total_bytes']} bytes, sha256={layout['sha256']}"
    )
    xi = layout["x_init"]
    print(
        f"  X init: {xi['words']} words at X:{xi['base_word']:04x}, "
        f"sha256={xi['sha256']}"
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
