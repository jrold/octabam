#!/usr/bin/env python3
"""ColdFire Wavetable renderer vs the real firmware's own captured output.

Family V1/V2 algorithm 2.  The object is 0x150 bytes at wrapper + 0x2E8 (V1,
engine 2) and wrapper + 0x31C (V2, engine 5).  Its two oscillators read 4,096-
byte tables: the primary stays on the shared 0x080222A0 table and the secondary
walks a 48-table crossfade bank at 0x080327CC.

This gate renders the authentic captured snapshots through the production
ColdFire translation and requires bit-exact PCM and a bit-exact object for all
three panel modes, all three control corners and three independent blocks
(first, continuation, active retrigger) on both engines.  No firmware is
flashed; the tables come from the SHA-pinned image's own assets.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky")]
from extract_noise_tone_tables import find_m7, parse_container  # noqa:E402

FIRMWARE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
# Digest over the engine-2 and engine-5 capture directories this gate reads, in
# sorted (relative path, content) order.  Regenerate with --print-digest.
CAPTURE_SET_SHA256 = "ca829e4ac986f38271fe0a99c9f9e5a58871804bde00bfe684e533000cee0a5e"

FILES = (
    "wrapper-window-before.bin", "arm-pcm.bin", "wrapper-window-after.bin",
    "wrapper-window-continuation-after.bin", "arm-pcm-continuation.bin",
    "wrapper-window-retrigger-before.bin", "arm-pcm-retrigger.bin",
    "wrapper-window-retrigger-after.bin",
)

PITCH = (0x080202A0, 8192)
ENV1 = (0x08022EA0, 4096)
ENV2 = (0x080236A2, 4096)
WT_BASE = (0x080222A0, 4096)
WT_BANK = (0x080327CC, 196608)


def run(cmd: list) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def capture_digest(fixtures: pathlib.Path) -> tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    for engine in (2, 5):
        for mode in (1, 2, 3):
            for corner in (0, 1, 2):
                rel = f"engine-{engine}-mode-{mode}-corner-{corner}"
                for name in FILES:
                    path = fixtures / rel / name
                    if not path.is_file():
                        raise SystemExit(f"missing capture {path}")
                    h.update(f"{rel}/{name}".encode())
                    h.update(b"\0")
                    h.update(hashlib.sha256(path.read_bytes()).hexdigest().encode())
                    h.update(b"\n")
                    count += 1
    return h.hexdigest(), count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("PERKONS_FIRMWARE", "")))
    ap.add_argument("--fixtures", type=pathlib.Path,
                    default=ROOT / "out/perky/engine-fixtures")
    ap.add_argument("--work", type=pathlib.Path,
                    default=ROOT / "out/perky/cf-wavetable")
    ap.add_argument("--print-digest", action="store_true")
    args = ap.parse_args()

    fixtures = args.fixtures.expanduser().resolve()
    if not (fixtures / "cases.tsv").is_file():
        raise SystemExit(f"missing engine fixtures under {fixtures}")
    digest, count = capture_digest(fixtures)
    if args.print_digest:
        print(digest)
        return

    firmware = args.firmware.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    got = hashlib.sha256(firmware.read_bytes()).hexdigest()
    if got != FIRMWARE_SHA256:
        raise SystemExit(f"firmware hash drift: {got} != {FIRMWARE_SHA256}")
    if digest != CAPTURE_SET_SHA256:
        raise SystemExit(f"engine-2/engine-5 capture drift: {digest} != {CAPTURE_SET_SHA256}")
    print(f"PERKY wavetable evidence identity: PASS (firmware + {count} captures)")

    work = args.work.resolve()
    assets = work / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    segment = find_m7(parse_container(firmware.read_bytes())[1])
    (assets / "pitch.bin").write_bytes(segment.read(*PITCH))
    (assets / "envelope1.bin").write_bytes(segment.read(*ENV1))
    (assets / "envelope2.bin").write_bytes(segment.read(*ENV2))
    (assets / "base_wave.bin").write_bytes(segment.read(*WT_BASE))
    (assets / "bank.bin").write_bytes(segment.read(*WT_BANK))

    obj = work / "cf_wavetable.o"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         "-c", ROOT / "modules/perky/cf_wavetable.c", "-o", obj])
    exe = work / "perky_cf_wavetable_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_wavetable_diff.cpp", obj, "-o", exe])
    run([exe, fixtures, assets, "2", "0x2e8"])
    run([exe, fixtures, assets, "5", "0x31c"])
    print("PERKY CF Wavetable DSP: PASS "
          "(bit-exact PCM and object, V1+V2, M1/M2/M3 x 3 corners x 3 blocks)")


if __name__ == "__main__":
    main()
