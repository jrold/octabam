#!/usr/bin/env python3
"""Compare the recovered Karplus update() with complete original ARM objects.

This is an external-reference qualification gate.  It requires the user's
pinned PĒRKONS v1.2.1 image plus the ignored all-engine fixture corpus generated
by ``tools/perky/capture_engine_fixtures.py``.  No firmware/table bytes are
stored in Git.

The renderer, trigger and update paths are deliberately separate proofs.  This
gate covers the mandatory control update that follows both first triggers and
active retriggers, including Karplus' second TUNE smoother and exact integer
divisions used to derive delay/filter state.
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

import karplus_control_update as control
from extract_noise_tone_tables import find_m7, parse_container

FIX = ROOT / "out/perky/engine-fixtures"
FIRMWARE_SHA = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
ENGINE = 9               # fixture schema uses one-based catalog identity
OBJECT_OFFSET = 0x2908   # Voice-3 wrapper -> Karplus object
OBJECT_SIZE = 0x10E0


def checked(path: Path, manifest: dict) -> bytes:
    raw = path.read_bytes()
    name = str(path.relative_to(FIX))
    expected = manifest["files"].get(name)
    if expected is None:
        raise RuntimeError(f"fixture manifest does not name {name}")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"capture hash drift: {name}: expected {expected}, got {actual}"
        )
    return raw


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
    args = parser.parse_args()

    global FIX
    FIX = args.fixtures.expanduser().resolve()
    firmware = args.firmware.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit(f"missing PĒRKONS v1.2.1 firmware: {firmware}")
    if not (FIX / "manifest.json").is_file():
        raise SystemExit(f"missing all-engine fixture manifest: {FIX / 'manifest.json'}")

    blob = firmware.read_bytes()
    actual_sha = hashlib.sha256(blob).hexdigest()
    if actual_sha != FIRMWARE_SHA:
        raise RuntimeError(
            "Karplus control update gate requires pinned PĒRKONS v1.2.1: "
            f"expected {FIRMWARE_SHA}, got {actual_sha}"
        )

    manifest = json.loads((FIX / "manifest.json").read_text())
    if manifest.get("firmware_sha256") != FIRMWARE_SHA:
        raise RuntimeError("control-update fixture firmware drift")

    m7 = find_m7(parse_container(blob)[1])
    pitch = m7.read(0x080202A0, 8192)
    chromatic = m7.read(0x08030ECC, 24)

    count = 0
    for mode in range(1, 4):
        for corner in range(3):
            case = FIX / f"engine-{ENGINE}-mode-{mode}-corner-{corner}"
            for pre_name, post_name in (
                ("wrapper-window-trigger-only.bin", "wrapper-window-before.bin"),
                ("wrapper-window-retrigger-only.bin", "wrapper-window-retrigger-before.bin"),
            ):
                pre_path = case / pre_name
                post_path = case / post_name
                target_path = case / (pre_name + ".targets.bin")
                before_window = checked(pre_path, manifest)
                expected_window = checked(post_path, manifest)
                target_raw = checked(target_path, manifest)
                if len(target_raw) != 16:
                    raise AssertionError(
                        f"{target_path.relative_to(FIX)} has {len(target_raw)} bytes, expected 16"
                    )

                before = before_window[OBJECT_OFFSET:OBJECT_OFFSET + OBJECT_SIZE]
                expected = expected_window[OBJECT_OFFSET:OBJECT_OFFSET + OBJECT_SIZE]
                if len(before) != OBJECT_SIZE or len(expected) != OBJECT_SIZE:
                    raise AssertionError(f"{case.name}: truncated Karplus object window")
                targets = struct.unpack("<4I", target_raw)
                actual = control.karplus_update(before, targets, pitch, chromatic)
                if actual != expected:
                    differences = [
                        i for i, (left, right) in enumerate(zip(actual, expected))
                        if left != right
                    ]
                    preview = ", ".join(f"0x{offset:x}" for offset in differences[:32])
                    if len(differences) > 32:
                        preview += f", ... (+{len(differences) - 32})"
                    raise AssertionError(
                        f"{case.name}/{pre_name}: Karplus update differs at {preview}"
                    )
                count += 1

    if count != 18:
        raise AssertionError(f"expected 18 first/retrigger Karplus updates, got {count}")

    print(
        "Karplus original ARM control update: PASS "
        f"({count} complete 0x{OBJECT_SIZE:x}-byte objects; captured targets/history; "
        "double TUNE smoother; exact delay/filter/envelope integer arithmetic)"
    )


if __name__ == "__main__":
    main()
