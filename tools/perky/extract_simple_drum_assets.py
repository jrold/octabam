#!/usr/bin/env python3
"""Extract authentic v1.2.1 Simple Drum assets from a user-owned PĒRKONS image.

The static pitch/envelope tables live at the same fixed M7 addresses used by
PerkyBits' ``NativeV121SimpleDrum`` renderer. The two 256-sample wave addresses
come from a prepared 0x120-byte engine-state snapshot, so MODE/control-specific
wave selection is preserved instead of guessed.

No firmware bytes are stored in Git. Outputs belong under ``out/`` and the JSON
manifest records source/state hashes, addresses and the small prepared-control
fields needed by qualification gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Iterable

from extract_noise_tone_tables import Segment, find_m7, parse_container

STATE_BYTES = 0x120
PITCH_ADDR = 0x080202A0
PITCH_BYTES = 4096 * 2
ENVELOPE1_ADDR = 0x08022EA0
ENVELOPE2_ADDR = 0x080236A2
ENVELOPE_BYTES = 2048 * 2
WAVE_BYTES = 256 * 2
WAVE_POINTER_OFFSETS = (0x38, 0x3C)
RAW_PITCH_OFFSET = 0xBA
MUTE_OFFSET = 0xB8
PITCH_ENV_AMOUNT_OFFSET = 0xEC
VELOCITY_OFFSET = 0x06


def _le16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("truncated 16-bit field")
    return struct.unpack_from("<H", data, offset)[0]


def _le32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated 32-bit field")
    return struct.unpack_from("<I", data, offset)[0]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def state_metadata(state: bytes) -> dict:
    if len(state) != STATE_BYTES:
        raise ValueError(
            f"Simple Drum state must be exactly 0x{STATE_BYTES:x} bytes, "
            f"got 0x{len(state):x}"
        )
    waves = [_le32(state, off) for off in WAVE_POINTER_OFFSETS]
    if any(address == 0 for address in waves):
        raise ValueError("Simple Drum prepared state contains a null wave pointer")
    return {
        "velocity": state[VELOCITY_OFFSET],
        "mute": state[MUTE_OFFSET],
        "raw_pitch": _le16(state, RAW_PITCH_OFFSET),
        "pitch_env_amount": _le16(state, PITCH_ENV_AMOUNT_OFFSET),
        "wave_addresses": waves,
    }


def extract_from_segment(
    m7: Segment,
    out_dir: Path,
    *,
    state: bytes,
    source_image: str = "<segment>",
    source_sha256: str | None = None,
    product: str = "",
    state_name: str = "simple_drum_state.bin",
    extra_waves: Iterable[int] = (),
) -> dict:
    meta = state_metadata(state)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []

    def emit(name: str, address: int, size: int) -> None:
        blob = m7.read(address, size)
        path = out_dir / name
        path.write_bytes(blob)
        files.append({
            "file": name,
            "address": f"0x{address:08x}",
            "bytes": len(blob),
            "sha256": _sha256(blob),
        })

    emit("pitch.bin", PITCH_ADDR, PITCH_BYTES)
    emit("envelope1.bin", ENVELOPE1_ADDR, ENVELOPE_BYTES)
    emit("envelope2.bin", ENVELOPE2_ADDR, ENVELOPE_BYTES)

    waves = list(meta["wave_addresses"])
    waves.extend(int(x) & 0xFFFFFFFF for x in extra_waves)
    unique_waves = list(dict.fromkeys(waves))
    for address in unique_waves:
        if address == 0:
            raise ValueError("Simple Drum wave list contains a null pointer")
        emit(f"wave_{address:08x}.bin", address, WAVE_BYTES)

    manifest = {
        "source_image": source_image,
        "source_sha256": source_sha256,
        "product": product,
        "m7_load_address": f"0x{m7.load_address:08x}",
        "m7_bytes": len(m7.data),
        "state_file": state_name,
        "state_sha256": _sha256(state),
        "prepared_state": {
            "velocity": meta["velocity"],
            "mute": meta["mute"],
            "raw_pitch": meta["raw_pitch"],
            "pitch_env_amount": meta["pitch_env_amount"],
            "wave_addresses": [f"0x{x:08x}" for x in meta["wave_addresses"]],
        },
        "wave_addresses": [f"0x{x:08x}" for x in unique_waves],
        "files": files,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def extract(
    image: Path,
    state_path: Path,
    out_dir: Path,
    *,
    extra_waves: Iterable[int] = (),
) -> dict:
    raw = image.read_bytes()
    state = state_path.read_bytes()
    product, segments = parse_container(raw)
    m7 = find_m7(segments)
    return extract_from_segment(
        m7,
        out_dir,
        state=state,
        source_image=image.name,
        source_sha256=_sha256(raw),
        product=product,
        state_name=state_path.name,
        extra_waves=extra_waves,
    )


def _parse_address(text: str) -> int:
    value = int(text, 0)
    if not 0 <= value <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("address must fit in 32 bits")
    return value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path, help="PĒRKONS firmware update obtained by the user")
    ap.add_argument("--state", type=Path, required=True,
                    help="prepared 0x120-byte Simple Drum engine-state snapshot")
    ap.add_argument("--wave", action="append", default=[], type=_parse_address,
                    help="extra wave address for bring-up (repeatable; decimal or 0xHEX)")
    ap.add_argument("--out", type=Path,
                    default=Path("out/perky/simple-drum-assets"))
    args = ap.parse_args()

    manifest = extract(
        args.image,
        args.state,
        args.out,
        extra_waves=args.wave,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
