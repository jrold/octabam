#!/usr/bin/env python3
"""Build the exact low-cycle v1.2.1 Simple Drum runtime table payload.

The source directory is a local extraction; no firmware-owned table bytes live
in Git.  SHA256 gates pin the extraction to the exact v1.2.1 assets qualified
for this port.  Output contains only packed DSP streams and a deterministic
layout manifest for the image builder.
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
import simple_drum_runtime_tables as runtime  # noqa: E402

# Source image SHA256 adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6.
# Wave pins corrected against its direct M7 flash extraction and native C++ PCM/state.
SOURCE_SHA256 = {
    "pitch.bin": "142684ed785eea7e2fe30a0b2db5fa710e2c4b6bb024226fcab46adb12ba3266",
    "envelope1.bin": "ca168bb45a7d175619eed89344d80ca8035e0fa817f825c5284a4d10082ebb40",
    "wave_080222a0.bin": "5a744b7d4b801d00a934203e47528cfa83d85457da9c7a2c29800b1cffe8ff39",
    "wave_080226a0.bin": "3511b74fa21d0c3430b7e1ddb0bbd8d76b1fd0dbc2272dfb32867b0e5412e697",
    "wave_080228a0.bin": "9cc8eeff587490a75dc669b0b9f462dd39d777061a9be6bf18658062909ece69",
}

EXPECTED_STREAM_SHA256 = {
    "waves": "91971eabda42938f157554f46e910e4967ee3d10f5c4c21c2a321d8351eb16d7",
    "envelope": "f6523d4a5d98cdd23d072174a12d30de0b21fd786920dbdc0388567613688f1e",
    "pitch_basis": "aa92e51555cd7ce7ca9b2a087716827c3dfd6d0dee2b63a109b7204319b2fc66",
}


def read_u16(path: Path, count: int) -> list[int]:
    raw = path.read_bytes()
    if len(raw) != count * 2:
        raise ValueError(f"{path}: {len(raw)} bytes, expected {count * 2}")
    return list(struct.unpack(f"<{count}H", raw))


def verify_source(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = SOURCE_SHA256.get(path.name)
    if expected is None:
        raise ValueError(f"no qualified v1.2.1 hash for {path.name}")
    if digest != expected:
        raise ValueError(
            f"{path}: SHA256 {digest} does not match qualified v1.2.1 {expected}"
        )
    return digest


def words24_bytes(words) -> bytes:
    out = bytearray()
    for raw in words:
        value = int(raw)
        if not 0 <= value <= 0xFFFFFF:
            raise ValueError(f"DSP word outside 24-bit range: {value}")
        out += bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF))
    return bytes(out)


def emit(out: Path, name: str, words) -> dict:
    values = tuple(int(word) & 0xFFFFFF for word in words)
    blob = words24_bytes(values)
    digest = hashlib.sha256(blob).hexdigest()
    expected = EXPECTED_STREAM_SHA256[name]
    if digest != expected:
        raise AssertionError(f"{name}: packed SHA256 {digest} != qualified {expected}")
    (out / f"{name}.bin").write_bytes(blob)
    (out / f"{name}.words").write_text(
        "\n".join(f"{value:06x}" for value in values) + "\n"
    )
    return {
        "file": f"{name}.bin",
        "words": len(values),
        "bytes": len(blob),
        "sha256": digest,
    }


def build(directory: Path, out: Path) -> dict:
    pitch_path = directory / "pitch.bin"
    env_path = directory / "envelope1.bin"
    verify_source(pitch_path)
    verify_source(env_path)

    pitch = read_u16(pitch_path, 4096)
    envelope = read_u16(env_path, 2048)
    waves: list[int] = []
    wave_meta = []
    for mode in range(3):
        address = control.wave_for_panel_mode(mode)
        path = directory / f"wave_{address:08x}.bin"
        digest = verify_source(path)
        waves.extend(read_u16(path, runtime.WAVE_SAMPLES))
        wave_meta.append({
            "physical_mode": mode + 1,
            "address": f"0x{address:08x}",
            "source": path.name,
            "sha256": digest,
        })

    table = runtime.build(pitch, envelope, waves)
    out.mkdir(parents=True, exist_ok=True)
    streams = {
        "waves": emit(out, "waves", table.waves),
        "envelope": emit(out, "envelope", table.envelope),
        "pitch_basis": emit(out, "pitch_basis", table.pitch_basis),
    }
    total = sum(item["words"] for item in streams.values())
    if total != runtime.TOTAL_WORDS:
        raise AssertionError(f"runtime payload uses {total} words, expected {runtime.TOTAL_WORDS}")

    layout = {
        "schema": "perky-simple-drum-runtime-v1",
        "firmware": "PĒRKONS v1.2.1",
        "dsp_word_bytes": 3,
        "y_base": "0x07a5",
        "private_y_words": 0x1000 - 0x07A5,
        "total_words": total,
        "margin_words": (0x1000 - 0x07A5) - total,
        "streams": streams,
        "waves": wave_meta,
        "source_sha256": {name: digest for name, digest in SOURCE_SHA256.items()},
        "runtime": {
            "envelope_samples_stored": runtime.ENV_STORED,
            "envelope_endpoint": runtime.ENV_ENDPOINT,
            "pitch_basis_samples": runtime.PITCH_BASIS,
            "pitch_reconstructs_samples": 4096,
            "lookup": "direct packed-u16 O(1)",
        },
    }
    if layout["margin_words"] != 602:
        raise AssertionError(f"private-Y margin drifted to {layout['margin_words']} words")
    (out / "layout.json").write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n")
    return layout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path, help="local authentic v1.2.1 Simple Drum extraction")
    ap.add_argument("--out", type=Path, default=Path("out/perky/simple-drum-runtime"))
    args = ap.parse_args()
    layout = build(args.directory, args.out)
    print(
        "PERKY Simple Drum runtime payload: PASS "
        f"({layout['total_words']} exact Y words, {layout['margin_words']} words free)"
    )
    for name, stream in layout["streams"].items():
        print(f"  {name}: {stream['words']} words sha256={stream['sha256']}")


if __name__ == "__main__":
    main()
