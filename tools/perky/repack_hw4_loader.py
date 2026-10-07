#!/usr/bin/env python3
"""Repack the existing PERKY platform loader with HW4 X/Y DSP uploads.

The stable repacker already owns all platform-loader safety checks.  HW4 only
changes the DSP-data integrator so it can append the qualified Karplus ring.
Keep that substitution scoped to this call; stable PERKY2/PERKY4 builds continue
to use tools/build/perky_image.py unchanged.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/build'), str(ROOT / 'tools/perky')]

import perky_image as stable
import perky_hw4_image as hw4
import repack_machine_loader as repack


class _HW4ImageAdapter:
    X_BASE = stable.X_BASE
    Y_BASE = stable.Y_BASE
    integrate = staticmethod(hw4.integrate)


def build(image_path: Path, table_dir: Path, output: Path,
          platform_dir: Path | None = None, work: Path | None = None):
    previous = repack.perky_image
    try:
        repack.perky_image = _HW4ImageAdapter
        return repack.build(
            image_path, table_dir, output,
            platform_dir=platform_dir, work=work,
        )
    finally:
        repack.perky_image = previous


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('table_dir', type=Path)
    ap.add_argument('--image', type=Path, default=ROOT / 'out/mainos_bus.bin')
    ap.add_argument('--platform', type=Path, default=ROOT / 'out/platform')
    ap.add_argument('--work', type=Path, default=ROOT / 'out/platform-perky-hw4')
    ap.add_argument('--out', type=Path, default=ROOT / 'out/mainos_perky_hw4.bin')
    a = ap.parse_args()
    build(a.image, a.table_dir, a.out, a.platform, a.work)
