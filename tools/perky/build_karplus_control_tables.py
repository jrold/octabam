#!/usr/bin/env python3
"""Generate exact v1.2.1 Karplus live-control lookup tables for HW4.

The shipping DSP should not approximate the recovered ARM update law.  This
builder derives three 4096-entry u16 functions from the user's pinned firmware
and authenticated Karplus fixture:

* prepared TUNE -> 2K-ring delay length;
* prepared DECAY -> amplitude-envelope decay rate;
* prepared EDGE -> resonant-filter coefficient.

TWANG is exactly ``prepared >> 1`` and needs no table.  The amplitude attack
rate and decay/gate threshold are constants from the authentic initialized
Karplus object and are recorded in the manifest.

Each u16 table uses Octabam's existing 3-samples-in-2-DSP-words packing.  Three
4096-entry tables therefore cost 3 * 2731 = 8193 Y words.  No firmware/table
bytes are committed; output lives under ignored ``out/perky``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky")]

import hw4_memory as memory
import karplus_control_update as update
import simple_drum_control as simple_control
import simple_drum_tables as packed_u16
from build_noise_tone_payload import words24_bytes
from extract_noise_tone_tables import find_m7, parse_container

FIRMWARE_SHA = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
FIX = ROOT / "out/perky/engine-fixtures"
CASE = FIX / "engine-9-mode-1-corner-1"
STATE_FILE = CASE / "wrapper-window-trigger-only.bin"
STATE_OFFSET = 0x2908
STATE_SIZE = 0x10E0
DEFAULT_OUT = ROOT / "out/perky/karplus-live-control"


def die(message: str) -> "NoReturn":
    raise SystemExit("build-karplus-control-tables: " + message)


def authenticated_state(fixtures: Path) -> tuple[bytes, dict]:
    manifest_path = fixtures / "manifest.json"
    case = fixtures / CASE.relative_to(FIX)
    state_path = case / STATE_FILE.name
    if not manifest_path.is_file() or not state_path.is_file():
        die(
            "missing authenticated Karplus fixture corpus; regenerate "
            "out/perky/engine-fixtures from the pinned v1.2.1 image"
        )
    manifest = json.loads(manifest_path.read_text())
    name = str(state_path.relative_to(fixtures))
    raw_window = state_path.read_bytes()
    expected = manifest.get("files", {}).get(name)
    actual = hashlib.sha256(raw_window).hexdigest()
    if expected is None or actual != expected:
        die(f"fixture hash drift: {name}")
    state = raw_window[STATE_OFFSET:STATE_OFFSET + STATE_SIZE]
    if len(state) != STATE_SIZE:
        die(f"truncated Karplus state: {len(state)} bytes")
    return state, manifest


def table_file(path: Path, values: list[int]) -> dict:
    if len(values) != 4096 or any(not 0 <= value <= 0xFFFF for value in values):
        raise ValueError("Karplus control table must be exactly 4096 u16 values")
    words = packed_u16.pack_u16(values)
    if len(words) != memory.KARPLUS_CONTROL_LUT_WORDS:
        raise AssertionError(
            f"4096 u16 values packed to {len(words)} words, "
            f"expected {memory.KARPLUS_CONTROL_LUT_WORDS}"
        )
    payload = words24_bytes(words)
    path.write_bytes(payload)
    return {
        "file": path.name,
        "entries": len(values),
        "words": len(words),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "first": values[0],
        "middle": values[2048],
        "last": values[-1],
    }


def build(firmware: Path, out: Path, fixtures: Path = FIX) -> dict:
    memory.validate()
    firmware = firmware.expanduser().resolve()
    fixtures = fixtures.expanduser().resolve()
    out = out.expanduser().resolve()
    if not firmware.is_file():
        die(f"missing PĒRKONS v1.2.1 image: {firmware}")

    image = firmware.read_bytes()
    image_sha = hashlib.sha256(image).hexdigest()
    if image_sha != FIRMWARE_SHA:
        die(f"firmware SHA {image_sha}, expected pinned v1.2.1 {FIRMWARE_SHA}")

    state, fixture_manifest = authenticated_state(fixtures)
    if fixture_manifest.get("firmware_sha256") != FIRMWARE_SHA:
        die("fixture corpus was not captured from the pinned v1.2.1 image")

    m7 = find_m7(parse_container(image)[1])
    pitch = m7.read(0x080202A0, 8192)
    chromatic = m7.read(0x08030ECC, 24)
    if len(pitch) != 8192 or len(chromatic) != 24:
        die("pinned pitch/chromatic table geometry drift")

    note = state[7]
    gate_threshold = update.u16(state, 8)
    attack_parameter = simple_control._time_parameter(update.u16(state, 0x0A))
    attack_rate = update._envelope_rate(state, 0x74, attack_parameter, False)

    tune_delay = [
        update.karplus_delay(value, note, pitch, chromatic)
        for value in range(4096)
    ]
    decay_rate = [
        update._envelope_rate(
            state,
            0x74,
            simple_control._time_parameter(value),
            True,
        )
        for value in range(4096)
    ]
    edge_coeff = [update.karplus_coefficient(value) for value in range(4096)]

    # Delay is a 2K ring index distance.  All three functions are u16-valued and
    # deterministic over the complete prepared-control domain.
    if max(tune_delay) > 0x800:
        raise AssertionError(f"Karplus delay exceeds ring: {max(tune_delay)}")

    out.mkdir(parents=True, exist_ok=True)
    table_specs = (
        ("tune-delay", memory.KARPLUS_TUNE_DELAY_BASE, tune_delay),
        ("decay-rate", memory.KARPLUS_DECAY_RATE_BASE, decay_rate),
        ("edge-coeff", memory.KARPLUS_EDGE_COEFF_BASE, edge_coeff),
    )
    tables = []
    for name, base, values in table_specs:
        info = table_file(out / f"karplus-{name}.bin", values)
        info.update(name=name, base_word=base)
        tables.append(info)

    report = {
        "schema": "octabam.perky.karplus-live-control.v1",
        "firmware_sha256": image_sha,
        "fixture": str((fixtures / CASE.relative_to(FIX) / STATE_FILE.name)),
        "prepared_domain": [0, 4095],
        "note": note,
        "gate_threshold": gate_threshold,
        "attack_rate": attack_rate,
        "twang_law": "prepared >> 1",
        "mode_map": [1, 0, 2],
        "tables": tables,
        "y_end_exclusive": memory.HW4_Y_END,
        "boot_clear": memory.HW4_Y_BOOT_CLEAR,
        "free_words_before_boot_clear": memory.HW4_Y_BOOT_CLEAR - memory.HW4_Y_END,
        "shipping_qualification": False,
    }
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")

    print("Karplus live-control tables: generated")
    for table in tables:
        print(
            f"  {table['name']:10s}: Y:${table['base_word']:04x} "
            f"{table['words']} words"
        )
    print(
        f"  end Y:${memory.HW4_Y_END:04x}; "
        f"{memory.HW4_Y_BOOT_CLEAR - memory.HW4_Y_END} words before boot clear"
    )
    print(f"  attack={attack_rate} gate-threshold={gate_threshold} note={note}")
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
    parser.add_argument("--fixtures", type=Path, default=FIX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    build(args.firmware, args.out, args.fixtures)


if __name__ == "__main__":
    main()
