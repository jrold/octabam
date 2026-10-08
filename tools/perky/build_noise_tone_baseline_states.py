#!/usr/bin/env python3
"""Pack authentic settled baseline compact states for Noise/Tone M1/M2/M3.

The exact 128-position original-ARM grid contains four independent captures of
the center point for each physical mode (one in each single-axis control sweep).
All four MUST collapse to the same compact renderer state.  This builder proves
that identity, then writes one raw 24-bit DSP word per compact u16 value so a
MODE change can copy the correct baseline into the 58-word T6 overlay cheaply.

M1 baseline: 25 words (Waveform2 compact ABI)
M2 baseline: 41 words (shared Noise/Tone compact ABI)
M3 baseline: 41 words (shared Noise/Tone compact ABI)

The 17-word shared-envelope cache is intentionally not stored here.  T6 mode
initialization invalidates/clears it separately after loading an M2/M3 baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky"), str(ROOT / "tools/re")]

import hw4_memory as memory
import noise_tone_ot_control_analyze as grid_analyze
from build_noise_tone_payload import words24_bytes

ASSET_SCHEMA = "octabam.perky.noise-tone-authentic-assets.v1"
OUT_SCHEMA = "octabam.perky.noise-tone-baselines.v1"
DEFAULT_GRID = ROOT / "out/perky/control-probes/noise-tone-grid/noise-tone-ot-control.jsonl"
DEFAULT_ASSETS = ROOT / "out/perky/noise-tone-authentic/manifest.json"
DEFAULT_OUT = ROOT / "out/perky/noise-tone-baselines"
CENTER = 64


def die(message: str) -> NoReturn:
    raise SystemExit("build-noise-tone-baselines: " + message)


def load_json(path: Path, schema: str) -> dict:
    if not path.is_file():
        die(f"missing {path}")
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        die(f"{path}: {exc}")
    if value.get("schema") != schema:
        die(f"{path}: schema {value.get('schema')!r}, expected {schema!r}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    memory.validate()
    grid_path = args.grid.expanduser().resolve()
    assets_path = args.assets.expanduser().resolve()
    out = args.out.expanduser().resolve()
    if not grid_path.is_file():
        die(f"missing exact OT grid {grid_path}")
    assets = load_json(assets_path, ASSET_SCHEMA)

    header, rows = grid_analyze.load(grid_path)
    grid = grid_analyze.validate(rows)
    cursor = int(assets["asset_end_exclusive"])
    if not memory.HW4_Y_END <= cursor < memory.HW4_Y_BOOT_CLEAR:
        die(f"asset end Y:${cursor:04x} outside HW4 Y arena")

    out.mkdir(parents=True, exist_ok=True)
    states = []
    for panel in range(3):
        captures = []
        names = None
        for parameter in range(4):
            raw = bytes.fromhex(grid[(panel, parameter, CENTER)]["state"])
            row_names, words = grid_analyze.compact(panel, raw)
            if names is None:
                names = list(row_names)
            elif list(row_names) != names:
                die(f"M{panel + 1}: compact names changed across baseline captures")
            captures.append(list(words))
        if any(values != captures[0] for values in captures[1:]):
            die(
                f"M{panel + 1}: center-point compact state depends on which "
                "single-axis sweep produced it"
            )

        words = captures[0]
        expected = 25 if panel == 0 else 41
        if len(words) != expected:
            die(f"M{panel + 1}: compact size {len(words)}, expected {expected}")
        if any(not 0 <= value <= 0xFFFF for value in words):
            die(f"M{panel + 1}: baseline escaped u16")

        payload = words24_bytes(words)
        path = out / f"m{panel + 1}-baseline.bin"
        path.write_bytes(payload)
        states.append({
            "panel": f"M{panel + 1}",
            "panel_mode": panel,
            "firmware_mode": (1, 0, 2)[panel],
            "renderer": "Waveform2" if panel == 0 else "NoiseToneShared",
            "file": path.name,
            "base_word": cursor,
            "words": len(words),
            "compact_names": names,
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
        cursor += len(words)

    if cursor > memory.HW4_Y_BOOT_CLEAR:
        die(f"baseline states end at Y:${cursor:04x}, past boot-clear boundary")

    report = {
        "schema": OUT_SCHEMA,
        "grid_schema": header["schema"],
        "grid": str(grid_path),
        "assets": str(assets_path),
        "center_ot_value": CENTER,
        "mode_map": [1, 0, 2],
        "states": states,
        "end_exclusive": cursor,
        "boot_clear": memory.HW4_Y_BOOT_CLEAR,
        "free_words": memory.HW4_Y_BOOT_CLEAR - cursor,
        "shared_cache_policy": "clear 17 words; cache key word 41 becomes 0xffff",
        "shipping_qualification": False,
    }
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")

    print("Noise/Tone authentic baselines: generated")
    for state in states:
        print(
            f"  {state['panel']} {state['renderer']:15s}: "
            f"Y:${state['base_word']:04x}, {state['words']} words"
        )
    print(
        f"  end Y:${cursor:04x}; "
        f"{memory.HW4_Y_BOOT_CLEAR - cursor} words remain before boot clear"
    )


if __name__ == "__main__":
    main()
