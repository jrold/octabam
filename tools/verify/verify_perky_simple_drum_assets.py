#!/usr/bin/env python3
"""Verify Simple Drum prepared-state decoding and authentic-asset extraction."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "perky"
sys.path.insert(0, str(TOOLS))

import extract_simple_drum_assets as ext  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_u16(count: int, seed: int) -> bytes:
    out = bytearray()
    for i in range(count):
        out += struct.pack("<H", (seed + i * 109 + (i * i >> 3)) & 0xFFFF)
    return bytes(out)


def main() -> None:
    base = 0x08000000
    size = 0x40000
    image = bytearray(size)

    pitch = blob_u16(4096, 0x1234)
    env1 = blob_u16(2048, 0x2345)
    env2 = blob_u16(2048, 0x3456)
    wave0 = blob_u16(256, 0x4567)
    wave1 = blob_u16(256, 0x5678)
    wave0_addr = 0x08030000
    wave1_addr = 0x08030200

    def place(address: int, data: bytes) -> None:
        off = address - base
        image[off:off + len(data)] = data

    place(ext.PITCH_ADDR, pitch)
    place(ext.ENVELOPE1_ADDR, env1)
    # The two 2048-entry extraction windows overlap after the first 1025
    # curve entries. Model the actual contiguous flash image in the fixture.
    overlap = ext.ENVELOPE2_ADDR - ext.ENVELOPE1_ADDR
    env1 = env1[:overlap] + env2[:len(env1) - overlap]
    place(ext.ENVELOPE1_ADDR, env1)
    place(ext.ENVELOPE2_ADDR, env2)
    place(wave0_addr, wave0)
    place(wave1_addr, wave1)

    state = bytearray(ext.STATE_BYTES)
    state[ext.VELOCITY_OFFSET] = 211
    state[ext.MUTE_OFFSET] = 1
    struct.pack_into("<I", state, ext.WAVE_POINTER_OFFSETS[0], wave0_addr)
    struct.pack_into("<I", state, ext.WAVE_POINTER_OFFSETS[1], wave1_addr)
    struct.pack_into("<H", state, ext.RAW_PITCH_OFFSET, 0x5A3C)
    struct.pack_into("<H", state, ext.PITCH_ENV_AMOUNT_OFFSET, 0xBEEF)

    meta = ext.state_metadata(bytes(state))
    if meta != {
        "velocity": 211,
        "mute": 1,
        "raw_pitch": 0x5A3C,
        "pitch_env_amount": 0xBEEF,
        "wave_addresses": [wave0_addr, wave1_addr],
    }:
        raise AssertionError(f"prepared-state decode mismatch: {meta!r}")

    segment = ext.Segment(base, bytes(image), 0)
    with tempfile.TemporaryDirectory(prefix="perky-simple-assets.") as td:
        out = Path(td)
        manifest = ext.extract_from_segment(
            segment,
            out,
            state=bytes(state),
            source_image="fixture.img",
            source_sha256="fixture-sha",
            product="fixture",
            state_name="m1-mid.bin",
            # Duplicate wave0 deliberately: manifest must preserve first-seen
            # order but emit each asset only once.
            extra_waves=(wave0_addr,),
        )

        expected = {
            "pitch.bin": pitch,
            "envelope1.bin": env1,
            "envelope2.bin": env2,
            f"wave_{wave0_addr:08x}.bin": wave0,
            f"wave_{wave1_addr:08x}.bin": wave1,
        }
        for name, want in expected.items():
            got = (out / name).read_bytes()
            if got != want:
                raise AssertionError(f"{name}: extracted bytes differ")

        if manifest["wave_addresses"] != [
            f"0x{wave0_addr:08x}",
            f"0x{wave1_addr:08x}",
        ]:
            raise AssertionError("wave-address order/dedup drifted")
        if manifest["state_sha256"] != sha(bytes(state)):
            raise AssertionError("state hash drifted")
        if manifest["prepared_state"]["raw_pitch"] != 0x5A3C:
            raise AssertionError("prepared raw pitch missing from manifest")
        file_hashes = {entry["file"]: entry["sha256"] for entry in manifest["files"]}
        for name, want in expected.items():
            if file_hashes.get(name) != sha(want):
                raise AssertionError(f"{name}: manifest hash mismatch")

    bad = bytearray(state)
    struct.pack_into("<I", bad, ext.WAVE_POINTER_OFFSETS[0], 0)
    try:
        ext.state_metadata(bytes(bad))
    except ValueError as exc:
        if "null wave pointer" not in str(exc):
            raise
    else:
        raise AssertionError("null Simple Drum wave pointer was accepted")

    try:
        ext.state_metadata(bytes(state[:-1]))
    except ValueError as exc:
        if "exactly 0x120" not in str(exc):
            raise
    else:
        raise AssertionError("short Simple Drum state was accepted")

    print(
        "PERKY Simple Drum assets: PASS "
        "(prepared state fields, pitch/envelopes, 2 waves, SHA256, dedup, rejection gates)"
    )


if __name__ == "__main__":
    main()
