#!/usr/bin/env python3
"""Statically qualify PERKY's in-memory full-machine module declaration.

This gate needs no m68k/DSP toolchain. It proves the development constructor
uses the same measured source-machine hook sites/guards as Analog BD while the
tracked PERKY manifest remains the isolated impulse canary.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky")]

import perky_machine_module  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


perky = load_module("perky_machine_gate_manifest", ROOT / "modules/perky/manifest.py").MODULE
analog = load_module("perky_machine_gate_ab", ROOT / "modules/analog-bassdrum/manifest.py").MODULE


def main() -> None:
    if perky.dsp is None or perky.dsp.asm != "modules/perky/probe_glue.asm":
        raise AssertionError("tracked PERKY manifest must remain the impulse probe")
    if tuple(u.label for u in perky.linked) != ("pkprobe",):
        raise AssertionError("tracked PERKY manifest unexpectedly contains full machine units")

    full = perky_machine_module.build(
        perky,
        control_source="out/perky/machine-canary/control.s",
        dsp_source="out/perky/machine-canary/perky_synth.asm",
    )
    linked = [(u.label, u.source, u.dram) for u in full.linked]
    want_linked = [
        ("pkmachine", "modules/perky/machine.s", True),
        ("pkcontrol", "out/perky/machine-canary/control.s", True),
    ]
    if linked != want_linked:
        raise AssertionError(f"full PERKY linked units {linked!r} != {want_linked!r}")
    if full.dsp is None or full.dsp.asm != "out/perky/machine-canary/perky_synth.asm":
        raise AssertionError("full PERKY module did not select generated synth DSP source")
    if full.dsp.hooks != perky.dsp.hooks or full.dsp.subst != perky.dsp.subst:
        raise AssertionError("full machine changed the proven DSP seam/continuations")
    if full.arena != perky.arena or full.claims != perky.claims:
        raise AssertionError("full machine changed the frozen PERKY memory ownership")

    refs = {(r.address, r.expect, r.unit, r.symbol) for r in full.symbol_refs}
    want_refs = {
        (0x400D6438, 0x40004008, "pkcontrol", "pk_render"),
        (0x400CE10E, 0, "pkcontrol", "pk_engine_left"),
        (0x400CF714, 0x4007909C, "pkcontrol", "pk_engine_right"),
    }
    if refs != want_refs:
        raise AssertionError(f"PERKY symbol refs differ: {refs!r}")

    # The source-machine patch surface must be exactly Analog BD's already
    # measured/qualified addresses and guards. Destination symbols differ by
    # design, but adding/removing/moving a firmware patch is not allowed here.
    def detour_shape(module):
        return {(d.address, d.expect, d.kind, d.pad_to) for d in module.detours}

    if detour_shape(full) != detour_shape(analog):
        missing = detour_shape(analog) - detour_shape(full)
        extra = detour_shape(full) - detour_shape(analog)
        raise AssertionError(f"PERKY detour surface differs; missing={missing!r} extra={extra!r}")

    def poke_shape(module):
        return {(p.address, p.expect, p.write) for p in module.pokes}

    if poke_shape(full) != poke_shape(analog):
        missing = poke_shape(analog) - poke_shape(full)
        extra = poke_shape(full) - poke_shape(analog)
        raise AssertionError(f"PERKY chooser pokes differ; missing={missing!r} extra={extra!r}")

    targets = {d.symbol for d in full.detours}
    required = {
        "pk_pool_title", "pk_list_draw", "pk_pool_open", "pk_machine_name",
        "pk_src_names", "pk_name_a", "pk_name_b", "pk_setup_row",
        "pk_chooser_row", "pk_setup_open", "pk_tick_hook", "pk_chooser_open",
        "pk_resolve_pb", "pk_main_commit", "pk_src_commit", "pk_src_commit2",
        "pk_setup_edit6", "pk_setup_draw6", "pk_validate",
    }
    if targets != required:
        raise AssertionError(f"PERKY machine targets differ: {targets ^ required!r}")

    print(
        "PERKY full-machine declaration: PASS "
        "(tracked impulse probe preserved; 2 DRAM units; 3 symbol refs; "
        f"{len(full.detours)} Analog-BD-qualified detours; {len(full.pokes)} chooser pokes; "
        "DSP seam/memory claims unchanged)"
    )


if __name__ == "__main__":
    main()
