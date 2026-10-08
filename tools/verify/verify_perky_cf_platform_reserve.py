#!/usr/bin/env python3
"""Gate the automatic DRAM reserve used by final ColdFire Perky Machines.

The final module intentionally has no explicit module arena: that removes the
legacy PERKY DSP/preboot reservation.  Octabam's platform builder must still
reserve its normal bottom-of-audio-pool DRAM arena whenever the remix contains
``dram=True`` Linked units.  This gate freezes that distinction.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"), str(ROOT / "modules/perky")]

from remix import arena
import perky_cf_machine_module


def load(path: Path):
    spec = importlib.util.spec_from_file_location("perky_cf_platform_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.MODULE


def main() -> None:
    original = load(ROOT / "modules/perky/manifest.py")
    final = perky_cf_machine_module.build(original)
    dram = tuple(u for u in final.linked if u.dram)
    if len(dram) != 7:
        raise AssertionError(f"expected seven final Perky DRAM units, got {len(dram)}")
    if final.arena is not None:
        raise AssertionError("final Perky must not restore a legacy explicit arena")

    # This mirrors build_bus.py section 1e: any DRAM-linked runtime receives the
    # standard platform reservation independently of Module.arena.
    reservations = []
    if dram:
        reservations.append(("octabam platform", "bottom", arena.PLATFORM_PAGES))
    placed, base, count = arena.layout(reservations)
    if len(placed) != 1:
        raise AssertionError(f"unexpected placement set: {placed!r}")
    p = placed[0]
    if (p.owner, p.where, p.pages) != ("octabam platform", "bottom", arena.PLATFORM_PAGES):
        raise AssertionError(f"unexpected platform placement: {p!r}")
    if p.start != arena.BASE or p.end - p.start != arena.PLATFORM_PAGES * arena.PAGE:
        raise AssertionError(f"platform reserve extent drifted: {p!r}")
    if count != arena.PAGES - arena.PLATFORM_PAGES or count < arena.MIN_PAGES_LEFT:
        raise AssertionError(f"unexpected remaining page count: {count}")

    pokes = arena.pokes(reservations)
    if len(pokes) != 28:
        raise AssertionError(f"expected 28 guarded arena geometry writes, got {len(pokes)}")

    build_bus = (ROOT / "tools/build/build_bus.py").read_text()
    for needle in (
        'if _dram:',
        '_reservations.append(("octabam platform", "bottom", arena.PLATFORM_PAGES))',
        'reserve=_reserve',
    ):
        if needle not in build_bus:
            raise AssertionError(f"platform auto-reserve plumbing drifted: missing {needle!r}")

    print(
        "PERKY CF platform reserve: PASS "
        f"({len(dram)} DRAM units; automatic {arena.PLATFORM_PAGES}-page reserve "
        f"{p.start:#010x}..{p.end:#010x} = {p.end-p.start:,} B; "
        f"{count:,} pages/{count*arena.PAGE//1048576} MiB remain; "
        "zero explicit Perky DSP/preboot arena)"
    )


if __name__ == "__main__":
    main()
