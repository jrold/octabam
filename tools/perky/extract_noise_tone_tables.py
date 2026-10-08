#!/usr/bin/env python3
"""Extract PERKY Noise/Tone lookup tables from a user-supplied PĒRKONS update.

Nothing is downloaded and no firmware bytes are committed.  The update
container is parsed using the same protobuf-style segment discovery as
PerkyBits' FirmwareImage class, then the Cortex-M7 image is addressed by its
runtime load address.

For the shared Noise/Tone renderer (modes 1 and 3):

* the two envelope curves live at fixed M7 addresses;
* four 256-sample wave tables are selected by pointers in the 0x120-byte
  prepared engine state.

Pass ``--state`` once we have captured/prepared a state for the requested
control point.  ``--wave`` may be used instead (or in addition) while bringing
up the DSP port.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

STATE_BYTES = 0x120
WAVE_BYTES = 256 * 2
ENVELOPE_BYTES = 2048 * 2
ENVELOPE1_ADDR = 0x08022EA0
ENVELOPE2_ADDR = 0x080236A2
WAVE_POINTER_OFFSETS = (0x38, 0x3C, 0xD0, 0xD4)
M1_WAVE_POINTER_OFFSETS = (0xE4, 0xE8)
M1_WAVE_BYTES = 2048 * 2

# Statically verified in the original v1.2.1 M7 image. Keep this path pinned to
# the exact image hash: these are firmware addresses, not a cross-version ABI.
V121_IMAGE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
V121_SHARED_WAVE_ADDRESSES = (0x080222A0, 0x080224A0, 0x080226A0, 0x080228A0)
V121_M1_WAVE_ADDRESSES = (0x080310E0,)


@dataclass(frozen=True)
class Segment:
    load_address: int
    data: bytes
    declared_crc32: int = 0

    @property
    def end_address(self) -> int:
        return self.load_address + len(self.data)

    @property
    def initial_sp(self) -> int:
        return _le32(self.data, 0)

    @property
    def reset_vector(self) -> int:
        return _le32(self.data, 4)

    def contains(self, address: int, size: int) -> bool:
        return (size >= 0 and address >= self.load_address
                and address + size <= self.end_address)

    def read(self, address: int, size: int) -> bytes:
        if not self.contains(address, size):
            raise ValueError(
                f"range 0x{address:08x}..0x{address + size:08x} is outside "
                f"segment 0x{self.load_address:08x}..0x{self.end_address:08x}"
            )
        offset = address - self.load_address
        return self.data[offset:offset + size]


def _le32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated 32-bit field")
    return struct.unpack_from("<I", data, offset)[0]


def _read_varint(data: bytes, offset: int, limit: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < limit and shift < 64:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value, offset
        shift += 7
    raise ValueError("malformed varint")


def _parse_descriptor(data: bytes, start: int, end: int) -> tuple[int, int, int]:
    address = size = crc = 0
    offset = start
    while offset < end:
        key, offset = _read_varint(data, offset, end)
        field, wire = key >> 3, key & 7
        if wire != 0:
            raise ValueError("unexpected non-varint segment descriptor field")
        value, offset = _read_varint(data, offset, end)
        if value > 0xFFFFFFFF:
            raise ValueError("oversized segment descriptor value")
        if field == 2:
            address = value
        elif field == 3:
            size = value
        elif field == 4:
            crc = value
    return address, size, crc


def parse_container(data: bytes) -> tuple[str, list[Segment]]:
    if len(data) < 16:
        raise ValueError("firmware image is too small")

    header_size, header_start = _read_varint(data, 0, len(data))
    header_end = header_start + header_size
    if header_end > len(data):
        raise ValueError("firmware header extends beyond image")

    descriptors: list[tuple[int, int, int]] = []
    product = ""
    offset = header_start
    while offset < header_end:
        key, offset = _read_varint(data, offset, header_end)
        field, wire = key >> 3, key & 7

        if wire == 0:
            _, offset = _read_varint(data, offset, header_end)
            continue
        if wire == 1:
            if offset + 8 > header_end:
                raise ValueError("truncated fixed64 header field")
            offset += 8
            continue
        if wire == 5:
            if offset + 4 > header_end:
                raise ValueError("truncated fixed32 header field")
            offset += 4
            continue
        if wire != 2:
            raise ValueError(f"unsupported protobuf wire type {wire}")

        length, offset = _read_varint(data, offset, header_end)
        end = offset + length
        if end > header_end:
            raise ValueError("length-delimited header field exceeds header")
        if field == 1:
            product = data[offset:end].decode("utf-8", errors="replace")
        elif field == 4:
            desc = _parse_descriptor(data, offset, end)
            if desc[0] and desc[1]:
                descriptors.append(desc)
        offset = end

    if not descriptors:
        raise ValueError("firmware container has no executable segments")

    payload = header_end
    segments: list[Segment] = []
    for address, size, crc in descriptors:
        if size < 8 or payload + size > len(data):
            raise ValueError("firmware segment is truncated")
        segment = Segment(address, data[payload:payload + size], crc)
        reset = segment.reset_vector & ~1
        if (segment.reset_vector & 1) == 0 or not segment.contains(reset, 1):
            raise ValueError(
                f"segment at 0x{address:08x} has implausible Thumb reset "
                f"0x{segment.reset_vector:08x}"
            )
        segments.append(segment)
        payload += size

    return product, segments


def find_m7(segments: Iterable[Segment]) -> Segment:
    candidates = [s for s in segments if 0x20000000 <= s.initial_sp < 0x20100000]
    if len(candidates) != 1:
        raise ValueError(f"expected one Cortex-M7 segment, found {len(candidates)}")
    return candidates[0]


def wave_addresses_from_state(state: bytes) -> list[int]:
    if len(state) != STATE_BYTES:
        raise ValueError(f"Noise/Tone state must be exactly 0x{STATE_BYTES:x} bytes")
    return [_le32(state, offset) for offset in WAVE_POINTER_OFFSETS]


def m1_wave_addresses_from_state(state: bytes) -> list[int]:
    """Original M1 Waveform2 current/next table pointers, not M2/M3 pointers."""
    if len(state) != STATE_BYTES:
        raise ValueError(f"Noise/Tone M1 state must be exactly 0x{STATE_BYTES:x} bytes")
    return [_le32(state, offset) for offset in M1_WAVE_POINTER_OFFSETS]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(image: Path, out_dir: Path, *, state_path: Path | None = None,
            extra_waves: Iterable[int] = (),
            m1_state_path: Path | None = None,
            v121_defaults: bool = False) -> dict:
    raw = image.read_bytes()
    image_sha = _sha256(raw)
    if v121_defaults and image_sha != V121_IMAGE_SHA256:
        raise ValueError(
            "--v121-defaults requires the pinned PĒRKONS v1.2.1 image; "
            f"got sha256={image_sha}"
        )
    product, segments = parse_container(raw)
    m7 = find_m7(segments)

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

    emit("envelope1.bin", ENVELOPE1_ADDR, ENVELOPE_BYTES)
    emit("envelope2.bin", ENVELOPE2_ADDR, ENVELOPE_BYTES)

    waves = list(extra_waves)
    if v121_defaults:
        waves.extend(V121_SHARED_WAVE_ADDRESSES)
    state_sha = None
    if state_path is not None:
        state = state_path.read_bytes()
        state_sha = _sha256(state)
        waves.extend(wave_addresses_from_state(state))

    m1_state_sha = None
    m1_waves: list[int] = list(V121_M1_WAVE_ADDRESSES) if v121_defaults else []
    if m1_state_path is not None:
        m1_state = m1_state_path.read_bytes()
        m1_state_sha = _sha256(m1_state)
        m1_waves.extend(m1_wave_addresses_from_state(m1_state))

    # Different modes use different pointer offsets AND different table sizes.
    # Deduplicate by address, but reject contradictory sizes at one address.
    unique_waves = list(dict.fromkeys(int(a) & 0xFFFFFFFF for a in waves))
    unique_m1_waves = list(dict.fromkeys(int(a) & 0xFFFFFFFF for a in m1_waves))
    for address in unique_waves + unique_m1_waves:
        if address == 0:
            raise ValueError("Noise/Tone state contains a null wave pointer")
    overlap = set(unique_waves) & set(unique_m1_waves)
    if overlap:
        raise ValueError(f"M1 and M2/M3 wave pointers overlap with incompatible lengths: {sorted(overlap)}")
    for address in unique_waves:
        emit(f"wave_{address:08x}.bin", address, WAVE_BYTES)
    for address in unique_m1_waves:
        emit(f"m1_wave_{address:08x}.bin", address, M1_WAVE_BYTES)

    manifest = {
        "source_image": image.name,
        "source_sha256": image_sha,
        "product": product,
        "m7_load_address": f"0x{m7.load_address:08x}",
        "m7_bytes": len(m7.data),
        "state_file": state_path.name if state_path is not None else None,
        "state_sha256": state_sha,
        "wave_addresses": [f"0x{x:08x}" for x in unique_waves],
        "m1_state_file": m1_state_path.name if m1_state_path is not None else None,
        "m1_state_sha256": m1_state_sha,
        "m1_wave_addresses": [f"0x{x:08x}" for x in unique_m1_waves],
        "files": files,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _parse_address(text: str) -> int:
    value = int(text, 0)
    if not 0 <= value <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("address must fit in 32 bits")
    return value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path, help="PĒRKONS firmware update obtained by the user")
    ap.add_argument("--state", type=Path,
                    help="prepared 0x120-byte shared Noise/Tone state; derives four wave pointers")
    ap.add_argument("--m1-state", type=Path,
                    help="prepared 0x120-byte M1 Waveform2 state; derives two 2048-sample wave pointers")
    ap.add_argument("--v121-defaults", action="store_true",
                    help="extract the statically verified original-v1.2.1 T6 wave bank (hash-pinned)")
    ap.add_argument("--wave", action="append", default=[], type=_parse_address,
                    help="extra/bring-up wave address (repeatable; decimal or 0xHEX)")
    ap.add_argument("--out", type=Path, default=Path("out/perky/noise-tone-tables"))
    args = ap.parse_args()

    manifest = extract(args.image, args.out, state_path=args.state,
                       extra_waves=args.wave, m1_state_path=args.m1_state,
                       v121_defaults=args.v121_defaults)
    print(f"PĒRKONS product: {manifest['product'] or '(unnamed)'}")
    print(f"M7: {manifest['m7_bytes']} bytes @ {manifest['m7_load_address']}")
    for item in manifest["files"]:
        print(f"{item['file']}: {item['bytes']} bytes from {item['address']} "
              f"sha256={item['sha256']}")


if __name__ == "__main__":
    main()
