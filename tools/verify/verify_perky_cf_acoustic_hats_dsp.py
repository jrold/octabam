#!/usr/bin/env python3
"""ColdFire Acoustic Hats renderer vs the real firmware's own captured output.

Family V4 algorithm 3.  The object is 0x10C bytes at wrapper + 0x2A80 and its
one-pole filter is the only float arithmetic in the port:

    decayed = previous * 0.98f;   summed = input + previous;

so this gate is also the qualification of modules/perky/cf_softfloat.h (checked
separately against the host's own float by verify_perky_cf_softfloat.py).

It renders the authentic captured snapshots through the production ColdFire
translation and requires bit-exact PCM, a bit-exact object AND the exact
firmware-global held sample (0x20007598) for all three panel modes, all three
control corners and three independent blocks: first, continuation, retrigger.
No firmware is flashed; the envelope tables and the three hat samples come from
the SHA-pinned image's own assets.
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
# Digest over every engine-12 capture file this gate reads, sorted by relative
# path.  Regenerate with --print-digest.
CAPTURE_SET_SHA256 = "961dc17ff2010a3a6745744f407adef088d84e55dd89ad3cf61fa8678e6e174e"

FILES = (
    "wrapper-window-before.bin", "arm-pcm.bin", "wrapper-window-after.bin",
    "wrapper-window-continuation-after.bin", "arm-pcm-continuation.bin",
    "acoustic-hold-continuation-before.bin", "acoustic-hold-continuation-after.bin",
    "wrapper-window-retrigger-before.bin", "arm-pcm-retrigger.bin",
    "wrapper-window-retrigger-after.bin",
    "acoustic-hold-retrigger-before.bin", "acoustic-hold-retrigger-after.bin",
)

ENV1 = (0x08022EA0, 4096)
ENV2 = (0x080236A2, 4096)
CLOSED = (0x080CBEF0, 20202)
OPEN = (0x080A1BF0, 172800)
RIDE = (0x080627CC, 259106)


def run(cmd: list) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def capture_digest(fixtures: pathlib.Path) -> tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    for mode in (1, 2, 3):
        for corner in (0, 1, 2):
            rel = f"engine-12-mode-{mode}-corner-{corner}"
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
                    default=ROOT / "out/perky/cf-acoustic-hats")
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
        raise SystemExit(f"engine-12 capture drift: {digest} != {CAPTURE_SET_SHA256}")
    print(f"PERKY acoustic-hats evidence identity: PASS (firmware + {count} captures)")

    work = args.work.resolve()
    assets = work / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    segment = find_m7(parse_container(firmware.read_bytes())[1])
    for name, spec in (("envelope1.bin", ENV1), ("envelope2.bin", ENV2),
                       ("closed.bin", CLOSED), ("open.bin", OPEN), ("ride.bin", RIDE)):
        (assets / name).write_bytes(segment.read(*spec))

    obj = work / "cf_acoustic_hats.o"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         "-c", ROOT / "modules/perky/cf_acoustic_hats.c", "-o", obj])
    exe = work / "perky_cf_acoustic_hats_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_acoustic_hats_diff.cpp", obj, "-o", exe])
    run([exe, fixtures, assets])
    print("PERKY CF Acoustic Hats DSP: PASS "
          "(bit-exact PCM, object and global hold; M1/M2/M3 x 3 corners x 3 blocks)")


if __name__ == "__main__":
    main()
