#!/usr/bin/env python3
"""ColdFire Complex Drum renderer vs the real firmware's own captured output.

Family V2 algorithm 3.  Object at wrapper + 0x1F8, 0x140 bytes, located by
rendering every window of the wrapper snapshot through the already-qualified
complex_drum_compact model: exactly one candidate reproduced the firmware's PCM.

Both the renderer and the control path are recovered from the firmware (see
modules/perky/CONTROL_RECOVERY.md).  This gate renders the authentic snapshots
through the production ColdFire translation and requires bit-exact PCM and a
bit-exact object for all three panel modes, all three control corners and three
independent blocks: first, continuation and a real active retrigger.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

FIRMWARE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"

# Canonical digest over every engine-6 capture this gate reads:
# sorted relative path, NUL, sha256 of the file, newline.  Regenerate with
# --print-digest after a deliberate re-capture.
CAPTURE_SET_SHA256 = "7ce287f17a477967b1716888564d40161bfbb894478c09048f8938b9cd2434ab"

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
            rel = f"engine-6-mode-{mode}-corner-{corner}"
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
    ap.add_argument("--assets", type=pathlib.Path,
                    default=ROOT / "out/perky/cf-final-verify/fixtures/assets")
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/cf-complex-drum")
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
        raise SystemExit(f"engine-6 capture drift: {digest} != {CAPTURE_SET_SHA256}")
    print(f"PERKY complex-drum evidence identity: PASS (firmware + {count} engine-6 files)")

    assets = args.assets.expanduser().resolve()
    for name in ("pitch.bin", "envelope1.bin", "envelope2.bin",
                 "w0.bin", "w1.bin", "w2.bin", "w3.bin"):
        if not (assets / name).is_file():
            raise SystemExit(f"missing shared asset {assets / name}; "
                             "run verify_perky_cf_final.py once")

    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    obj = work / "cf_complex_drum.o"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         "-c", ROOT / "modules/perky/cf_complex_drum.c", "-o", obj])
    exe = work / "perky_cf_complex_drum_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_complex_drum_diff.cpp", obj, "-o", exe])
    run([exe, fixtures, assets])
    print("PERKY CF Complex Drum DSP: PASS "
          "(bit-exact PCM and object, M1/M2/M3 x 3 corners x 3 blocks)")


if __name__ == "__main__":
    main()
