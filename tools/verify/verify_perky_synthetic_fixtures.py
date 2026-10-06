#!/usr/bin/env python3
"""Gate the explicit synthetic PERKY Noise/Tone development fixtures."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_fabricate",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
ctl = load_module(
    "perky_control_analyze",
    ROOT / "tools/re/perky_control_analyze.py",
)
mem = load_module(
    "perky_memory_analyze",
    ROOT / "tools/perky/analyze_noise_tone_tables.py",
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="perky-synthetic.") as td:
        td = Path(td)
        tables = td / "tables"
        control = td / "control.jsonl"
        fab.emit_tables(tables)
        fab.emit_controls(control, pairwise=True)

        manifest = json.loads((tables / "manifest.json").read_text())
        if manifest.get("synthetic") is not True:
            raise AssertionError("synthetic table manifest lost its explicit marker")
        if "NOT PĒRKONS DATA" not in manifest.get("product", ""):
            raise AssertionError("synthetic table warning is no longer unmistakable")
        if len(manifest.get("wave_addresses", [])) != 4:
            raise AssertionError("synthetic fixture no longer has four wave pointers")

        for index in (1, 2):
            if (tables / f"envelope{index}.bin").stat().st_size != 4096:
                raise AssertionError("synthetic envelope geometry drifted")
        wave_files = sorted(tables.glob("wave_*.bin"))
        if len(wave_files) != 4 or any(p.stat().st_size != 512 for p in wave_files):
            raise AssertionError("synthetic wave geometry drifted")
        if (tables / "state.bin").stat().st_size != 0x120:
            raise AssertionError("synthetic prepared state geometry drifted")

        header, records = ctl.load(control)
        if header.get("synthetic") is not True:
            raise AssertionError("synthetic control capture lost its explicit marker")
        ctl.validate_control_ram(records)
        controls = ctl.analyze_controls(records)
        triggers = ctl.analyze_triggers(records)
        pairwise = ctl.analyze_pairwise(records, controls)

        # Every control in both shared modes must own at least one state byte.
        for mode in (0, 2):
            for parameter in range(4):
                key = f"m{mode}-p{parameter}"
                if not controls[key]["state_offsets"]:
                    raise AssertionError(f"{key} owns no synthetic state bytes")
            for sweep in ("velocity", "note"):
                key = f"m{mode}-{sweep}"
                if not triggers[key]["state_offsets"]:
                    raise AssertionError(f"{key} changes no synthetic renderer state")
            for a in range(4):
                for b in range(a + 1, 4):
                    key = f"m{mode}-p{a}p{b}"
                    if pairwise[key]["records"] != 9:
                        raise AssertionError(f"{key}: expected 9 pairwise records")

        report = mem.analyze(tables)
        if report["live_state"]["x_words"] != 168:
            raise AssertionError(
                f"compact live state drifted to {report['live_state']['x_words']} X words"
            )
        if report["waves"]["u16pack_words"] != 683:
            raise AssertionError(
                f"four dense synthetic waves use {report['waves']['u16pack_words']} words, expected 683"
            )
        envs = report["envelopes"]["tables"]
        if [e["realtime_best"]["words"] for e in envs] != [646, 646]:
            raise AssertionError(
                "synthetic envelopes no longer use 646 words each under the realtime <=15-add rule"
            )
        if report["combined"]["realtime_table_y_words"] != 1975:
            raise AssertionError(
                f"synthetic exact table footprint drifted to "
                f"{report['combined']['realtime_table_y_words']} Y words"
            )
        if report["combined"]["y_margin_words"] != 164:
            raise AssertionError(
                f"synthetic Y margin drifted to {report['combined']['y_margin_words']} words"
            )
        if not report["combined"]["fits_measured_private_xy_realtime"]:
            raise AssertionError(
                "synthetic exact table plan no longer fits the measured private X/Y budget"
            )

    print("PERKY synthetic fixture gate: OK -- state X=168, tables Y=1975, margin Y=164")


if __name__ == "__main__":
    main()
