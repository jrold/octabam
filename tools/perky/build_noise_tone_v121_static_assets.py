#!/usr/bin/env python3
"""Build the statically verified PĒRKONS v1.2.1 T6 asset pack.

This is a firmware-only proof path for the exact v1.2.1 image. It does not
replace the full OT-grid reachability capture; instead it lets the authentic
M1 and M2/M3 renderers consume the real firmware tables while the external ARM
control probe is unavailable. Every hard-coded address is hash-gated to the
exact firmware image from which it was disassembled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky")]

import hw4_memory as memory
from build_noise_tone_authentic_assets import emit_envelope, emit_group
from extract_noise_tone_tables import ENVELOPE1_ADDR, ENVELOPE2_ADDR, find_m7, parse_container

FIRMWARE_SHA = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
M1_WAVES = [0x080310E0]
# Keep the shared bank in the renderer-qualified ordinal order, not numeric
# address order: 22a0 -> 0, 26a0 -> 1, 28a0 -> 2, 24a0 -> 3.
SHARED_WAVES = [0x080222A0, 0x080226A0, 0x080228A0, 0x080224A0]


def build(firmware: Path, out: Path) -> dict:
    memory.validate()
    raw = firmware.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != FIRMWARE_SHA:
        raise SystemExit(f"expected PĒRKONS v1.2.1 sha256 {FIRMWARE_SHA}, got {sha}")
    _product, segments = parse_container(raw)
    m7 = find_m7(segments)
    out.mkdir(parents=True, exist_ok=True)

    assets = [
        emit_group(out, "waveform2-waves", m7, M1_WAVES, 2048),
        emit_envelope(out, "envelope1", m7, ENVELOPE1_ADDR),
        emit_envelope(out, "envelope2", m7, ENVELOPE2_ADDR),
        emit_group(out, "shared-waves", m7, SHARED_WAVES, 256),
    ]
    cursor = memory.HW4_Y_END
    placed = []
    for asset in assets:
        row = dict(asset)
        row["base_word"] = cursor
        cursor += int(row["words"])
        placed.append(row)
    if cursor > memory.HW4_Y_BOOT_CLEAR:
        raise SystemExit(
            f"T6 asset proof ends Y:${cursor:04x}, beyond Y:${memory.HW4_Y_BOOT_CLEAR:04x}"
        )

    report = {
        "schema": "octabam.perky.noise-tone-v121-static-assets.v1",
        "firmware_sha256": sha,
        "evidence": "addresses statically disassembled from exact v1.2.1; OT-grid reachability still separate",
        "mode_map": [1, 0, 2],
        "assets": placed,
        "asset_end_exclusive": cursor,
        "boot_clear": memory.HW4_Y_BOOT_CLEAR,
        "free_words_after_assets": memory.HW4_Y_BOOT_CLEAR - cursor,
        "shipping_qualification": False,
    }
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PĒRKONS v1.2.1 T6 static assets: PASS")
    for row in placed:
        print(f"  {row['name']:16s} Y:${row['base_word']:04x} +{row['words']} words")
    print(f"  end Y:${cursor:04x}; {memory.HW4_Y_BOOT_CLEAR - cursor} words remain")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("firmware", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "out/perky/noise-tone-v121-static")
    args = ap.parse_args()
    build(args.firmware, args.out)


if __name__ == "__main__":
    main()
