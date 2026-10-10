#!/usr/bin/env python3
"""ColdFire Simple Drum renderer vs the real firmware's own captured output.

Family V1 algorithm 3.  The object sits at wrapper + 0x1F8 and is 0x120 bytes;
it was located by rendering every 0x120-byte window of the wrapper snapshot
through the already-qualified compact model and keeping the one that reproduced
the firmware's PCM -- exactly one candidate matched.

This gate renders the authentic snapshots through the production ColdFire
translation and requires bit-exact PCM and a bit-exact object for all three
panel modes, all three control corners and three independent blocks: the first
block, the continuation block and a real active retrigger 512 samples in.
No firmware is flashed; the tables come from the SHA-pinned image's own assets.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"), str(ROOT / "modules/perky")]

# SHA-pinned PĒRKONS v1.2.1 image.
FIRMWARE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"

# Canonical digest over the exact engine-3 captures this gate compares against:
# every file it reads, sorted by relative path, hashed as path\\0sha256\\n.
# Regenerate with --print-digest after a deliberate re-capture.
CAPTURE_SET_SHA256 = "fefe9cd9e9b5ec717643b9942f351b650a8cc644a1f32d515dc7e013bac192e2"

FILES = (
    "wrapper-window-before.bin", "arm-pcm.bin", "wrapper-window-after.bin",
    "wrapper-window-continuation-after.bin", "arm-pcm-continuation.bin",
    "wrapper-window-retrigger-before.bin", "arm-pcm-retrigger.bin",
    "wrapper-window-retrigger-after.bin",
)


def run(cmd) -> None:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True)


def capture_digest(fixtures: pathlib.Path) -> tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    for mode in (1, 2, 3):
        for corner in (0, 1, 2):
            rel = f"engine-3-mode-{mode}-corner-{corner}"
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
                    default=pathlib.Path(__import__("os").environ.get("PERKONS_FIRMWARE", "")))
    ap.add_argument("--fixtures", type=pathlib.Path,
                    default=ROOT / "out/perky/engine-fixtures")
    ap.add_argument("--assets", type=pathlib.Path,
                    default=ROOT / "out/perky/cf-final-verify/fixtures/assets")
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/cf-simple-drum")
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
        raise SystemExit(f"engine-3 capture drift: {digest} != {CAPTURE_SET_SHA256}")
    print(f"PERKY simple-drum evidence identity: PASS (firmware + {count} engine-3 files)")

    assets = args.assets.expanduser().resolve()
    for name in ("pitch.bin", "envelope1.bin", "envelope2.bin",
                 "w0.bin", "w1.bin", "w2.bin", "w3.bin"):
        if not (assets / name).is_file():
            raise SystemExit(f"missing shared asset {assets / name}; "
                             "run verify_perky_cf_final.py once")

    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    obj = work / "cf_simple_drum.o"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         "-c", ROOT / "modules/perky/cf_simple_drum.c", "-o", obj])
    exe = work / "perky_cf_simple_drum_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_simple_drum_diff.cpp", obj, "-o", exe])
    run([exe, fixtures, assets])
    print("PERKY CF Simple Drum DSP: PASS "
          "(bit-exact PCM and object, M1/M2/M3 x 3 corners x 3 blocks)")


if __name__ == "__main__":
    main()
