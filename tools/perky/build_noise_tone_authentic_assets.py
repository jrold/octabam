#!/usr/bin/env python3
"""Build the authentic v1.2.1 T6 Noise/Tone asset pack for HW4.

Inputs stay local/ignored:

* user's pinned PĒRKONS v1.2.1 update image;
* exact 128-position grid from ``perkybits-noise-tone-ot-control-probe``.

The builder scans every captured state, not just one baseline, so a wave identity
reachable only at an extreme control value cannot be omitted accidentally.
It extracts:

* M1/Waveform2: every reachable 2048-sample wave table;
* M2/M3 shared renderer: every reachable 256-sample wave table;
* the two fixed 2048-entry v1.2.1 envelope curves used by the shared renderer.

Waves use the existing 3*u16 -> 2*DSP-word packing. Envelope curves use the
repository's exact 16-sample-block anchor/delta codec with a per-curve signed
width chosen from the real v1.2.1 values. No firmware bytes or generated asset
binaries are committed to Git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Iterable, NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky"), str(ROOT / "tools/re")]

import hw4_memory as memory
import noise_tone_ot_control_analyze as grid_analyze
import noise_tone_tables as nt_tables
import simple_drum_tables as packed_u16
from build_noise_tone_payload import words24_bytes
from extract_noise_tone_tables import (
    ENVELOPE1_ADDR,
    ENVELOPE2_ADDR,
    ENVELOPE_BYTES,
    WAVE_POINTER_OFFSETS,
    find_m7,
    parse_container,
)

FIRMWARE_SHA = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
WAVEFORM2_POINTER_OFFSETS = (0xE4, 0xE8)
WAVEFORM2_SAMPLES = 2048
SHARED_SAMPLES = 256
DEFAULT_GRID = ROOT / "out/perky/control-probes/noise-tone-grid/noise-tone-ot-control.jsonl"
DEFAULT_OUT = ROOT / "out/perky/noise-tone-authentic"


def die(message: str) -> NoReturn:
    raise SystemExit("build-noise-tone-authentic-assets: " + message)


def le32(raw: bytes, offset: int) -> int:
    return struct.unpack_from("<I", raw, offset)[0]


def u16_values(raw: bytes) -> list[int]:
    if len(raw) % 2:
        raise ValueError("u16 blob has odd byte count")
    return list(struct.unpack(f"<{len(raw) // 2}H", raw))


def packed_blob(values: Iterable[int]) -> tuple[bytes, int]:
    words = packed_u16.pack_u16(list(values))
    return words24_bytes(words), len(words)


def collect_addresses(grid: dict[tuple[int, int, int], dict]) -> tuple[list[int], list[int]]:
    m1: list[int] = []
    shared: list[int] = []
    for (panel, _parameter, _ot), row in sorted(grid.items()):
        state = bytes.fromhex(row["state"])
        offsets = WAVEFORM2_POINTER_OFFSETS if panel == 0 else WAVE_POINTER_OFFSETS
        target = m1 if panel == 0 else shared
        for offset in offsets:
            address = le32(state, offset)
            if address == 0:
                die(f"M{panel + 1} state contains null wave pointer at 0x{offset:x}")
            if address not in target:
                target.append(address)
    return m1, shared


def emit_group(out: Path, name: str, m7, addresses: list[int], samples: int) -> dict:
    values: list[int] = []
    identities = []
    for ordinal, address in enumerate(addresses):
        raw = m7.read(address, samples * 2)
        table = u16_values(raw)
        if len(table) != samples:
            raise AssertionError("wave extraction geometry")
        start = len(values)
        values.extend(table)
        identities.append({
            "ordinal": ordinal,
            "address": f"0x{address:08x}",
            "sample_offset": start,
            "samples": samples,
            "sha256": hashlib.sha256(raw).hexdigest(),
        })

    payload, words = packed_blob(values)
    path = out / f"{name}.bin"
    path.write_bytes(payload)
    return {
        "name": name,
        "file": path.name,
        "codec": "u16-lsb-3-samples-2-dsp-words",
        "table_samples": samples,
        "tables": len(addresses),
        "total_samples": len(values),
        "words": words,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "identities": identities,
    }


def emit_envelope(out: Path, name: str, m7, address: int) -> dict:
    raw = m7.read(address, ENVELOPE_BYTES)
    values = u16_values(raw)
    if len(values) != nt_tables.ENVELOPE_SAMPLES:
        raise AssertionError("envelope extraction geometry")
    packed = nt_tables.pack_envelope(values)
    payload = words24_bytes(list(packed.words))
    path = out / f"{name}.bin"
    path.write_bytes(payload)
    # Prove the codec immediately rather than trusting only construction.
    if nt_tables.unpack_envelope(packed) != values:
        raise AssertionError(f"{name}: packed envelope round-trip mismatch")
    return {
        "name": name,
        "file": path.name,
        "codec": "u16-anchor-plus-signed-fixed-width-deltas",
        "address": f"0x{address:08x}",
        "samples": len(values),
        "block": packed.block,
        "delta_bits": packed.delta_bits,
        "block_bits": 16 + (packed.block - 1) * packed.delta_bits,
        "max_adds": packed.max_adds,
        "words": len(packed.words),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build(firmware: Path, grid_path: Path, out: Path) -> dict:
    memory.validate()
    firmware = firmware.expanduser().resolve()
    grid_path = grid_path.expanduser().resolve()
    out = out.expanduser().resolve()
    if not firmware.is_file():
        die(f"missing PĒRKONS v1.2.1 image: {firmware}")
    if not grid_path.is_file():
        die(f"missing exact Noise/Tone OT grid: {grid_path}")

    image = firmware.read_bytes()
    image_sha = hashlib.sha256(image).hexdigest()
    if image_sha != FIRMWARE_SHA:
        die(f"firmware SHA {image_sha}, expected pinned v1.2.1 {FIRMWARE_SHA}")

    header, rows = grid_analyze.load(grid_path)
    grid = grid_analyze.validate(rows)
    m1_addresses, shared_addresses = collect_addresses(grid)
    if not m1_addresses:
        die("no Waveform2 wave identities found")
    if not shared_addresses:
        die("no shared Noise/Tone wave identities found")
    if len(m1_addresses) > 2:
        die(f"Waveform2 exposes {len(m1_addresses)} reachable waves, expected <=2")
    if len(shared_addresses) > 4:
        die(f"shared Noise/Tone exposes {len(shared_addresses)} reachable waves, expected <=4")

    _product, segments = parse_container(image)
    m7 = find_m7(segments)
    out.mkdir(parents=True, exist_ok=True)

    waveform2 = emit_group(out, "waveform2-waves", m7, m1_addresses, WAVEFORM2_SAMPLES)
    envelope1 = emit_envelope(out, "envelope1", m7, ENVELOPE1_ADDR)
    envelope2 = emit_envelope(out, "envelope2", m7, ENVELOPE2_ADDR)
    shared_waves = emit_group(out, "shared-waves", m7, shared_addresses, SHARED_SAMPLES)

    cursor = memory.HW4_Y_END
    assets = []
    for item in (waveform2, envelope1, envelope2, shared_waves):
        row = dict(item)
        row["base_word"] = cursor
        cursor += int(item["words"])
        assets.append(row)
    if cursor > memory.HW4_Y_BOOT_CLEAR:
        die(
            f"authentic Noise/Tone assets end at Y:${cursor:04x}, beyond "
            f"boot-clear boundary Y:${memory.HW4_Y_BOOT_CLEAR:04x}"
        )

    report = {
        "schema": "octabam.perky.noise-tone-authentic-assets.v1",
        "firmware_sha256": image_sha,
        "grid_schema": header["schema"],
        "grid_path": str(grid_path),
        "mode_map": [1, 0, 2],
        "assets": assets,
        "asset_end_exclusive": cursor,
        "boot_clear": memory.HW4_Y_BOOT_CLEAR,
        "free_words_after_assets": memory.HW4_Y_BOOT_CLEAR - cursor,
        "shipping_qualification": False,
    }
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")

    print("Authentic Noise/Tone assets: generated")
    for item in assets:
        detail = ""
        if item.get("codec", "").startswith("u16-anchor"):
            detail = f", delta={item['delta_bits']} bits"
        print(
            f"  {item['name']:16s}: Y:${item['base_word']:04x}, "
            f"{item['words']} words{detail}"
        )
    print(
        f"  end Y:${cursor:04x}; "
        f"{memory.HW4_Y_BOOT_CLEAR - cursor} words remain for exact control tables"
    )
    print(
        f"  reachable waves: M1={len(m1_addresses)} x 2048, "
        f"M2/M3={len(shared_addresses)} x 256"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--firmware",
        type=Path,
        default=Path(os.environ.get(
            "PERKONS_FIRMWARE",
            Path.home() / "Downloads/perkons_both_v1.2.1-0-gbcccfd0.img",
        )),
    )
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    build(args.firmware, args.grid, args.out)


if __name__ == "__main__":
    main()
