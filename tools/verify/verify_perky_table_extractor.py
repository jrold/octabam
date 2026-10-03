#!/usr/bin/env python3
"""Synthetic gate for tools/perky/extract_noise_tone_tables.py.

No PĒRKONS firmware is needed.  Build a tiny protobuf-style update container
with plausible M4/M7 vector tables and deterministic M7 bytes, then prove the
extractor finds the M7 segment, fixed envelope curves and four state-selected
wave tables by *runtime address* rather than historical container offsets.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/perky/extract_noise_tone_tables.py"

spec = importlib.util.spec_from_file_location("perky_tables", TOOL)
if spec is None or spec.loader is None:
    raise SystemExit("verify-perky-table-extractor: cannot import extractor")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def vi(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def vf(field: int, value: int) -> bytes:
    return vi(field << 3) + vi(value)


def ld(field: int, payload: bytes) -> bytes:
    return vi((field << 3) | 2) + vi(len(payload)) + payload


def descriptor(address: int, size: int) -> bytes:
    return vf(2, address) + vf(3, size) + vf(4, 0x12345678)


def segment(address: int, size: int, sp: int) -> bytearray:
    data = bytearray(((address + i) * 37 + 11) & 0xFF for i in range(size))
    struct.pack_into("<II", data, 0, sp, (address + 8) | 1)
    return data


def build_container() -> tuple[bytes, bytes, list[int]]:
    m4_base, m4_size = 0x08100000, 0x100
    m7_base, m7_size = 0x08020000, 0x6000
    m4 = segment(m4_base, m4_size, 0x10001000)
    m7 = segment(m7_base, m7_size, 0x20002000)

    header = bytearray()
    header += ld(1, b"PERKY SYNTHETIC")
    header += ld(4, descriptor(m4_base, m4_size))
    header += ld(4, descriptor(m7_base, m7_size))

    waves = [0x08024800, 0x08024A00, 0x08024C00, 0x08024E00]
    return vi(len(header)) + header + m4 + m7, bytes(m7), waves


def main() -> None:
    container, m7, waves = build_container()
    with tempfile.TemporaryDirectory(prefix="perky-table-gate.") as td:
        td = Path(td)
        image = td / "firmware.bin"
        state_path = td / "state.bin"
        out = td / "out"
        image.write_bytes(container)

        state = bytearray(mod.STATE_BYTES)
        for off, address in zip(mod.WAVE_POINTER_OFFSETS, waves):
            struct.pack_into("<I", state, off, address)
        state_path.write_bytes(state)

        manifest = mod.extract(image, out, state_path=state_path)
        if manifest["product"] != "PERKY SYNTHETIC":
            raise AssertionError("product-name parse failed")
        if manifest["m7_load_address"] != "0x08020000":
            raise AssertionError("M7 runtime-address classification failed")
        if manifest["wave_addresses"] != [f"0x{x:08x}" for x in waves]:
            raise AssertionError("state wave-pointer extraction failed")

        def m7_slice(address: int, size: int) -> bytes:
            at = address - 0x08020000
            return m7[at:at + size]

        expected = {
            "envelope1.bin": m7_slice(mod.ENVELOPE1_ADDR, mod.ENVELOPE_BYTES),
            "envelope2.bin": m7_slice(mod.ENVELOPE2_ADDR, mod.ENVELOPE_BYTES),
        }
        expected.update({
            f"wave_{address:08x}.bin": m7_slice(address, mod.WAVE_BYTES)
            for address in waves
        })
        for name, blob in expected.items():
            got = (out / name).read_bytes()
            if got != blob:
                raise AssertionError(f"{name}: runtime-address slice is wrong")

        disk_manifest = json.loads((out / "manifest.json").read_text())
        if disk_manifest != manifest:
            raise AssertionError("manifest.json differs from returned manifest")

        bad = bytearray(state)
        struct.pack_into("<I", bad, mod.WAVE_POINTER_OFFSETS[0], 0x09000000)
        bad_state = td / "bad-state.bin"
        bad_state.write_bytes(bad)
        try:
            mod.extract(image, td / "bad-out", state_path=bad_state)
        except ValueError as exc:
            if "outside segment" not in str(exc):
                raise
        else:
            raise AssertionError("out-of-segment wave pointer was accepted")

    print("PERKY table extractor gate: OK")


if __name__ == "__main__":
    main()
