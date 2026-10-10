#!/usr/bin/env python3
"""ColdFire Slap renderer vs the real firmware's own captured output.

Family V3 algorithm 2.  Object at wrapper + 0xC4, 0x2670 bytes (it embeds a
4,805-word delay ring at +0xE0).  Slap consumes the shared 32-bit PRNG, so this
gate seeds the ColdFire renderer from the capture's own RNG state and requires
bit-exact PCM, a bit-exact object *and* a bit-exact RNG after every block.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]

FIRMWARE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"

CAPTURE_SET_SHA256 = "c499ef1cc17a9cebcb16e8c81092432c3bcb4941ebb6325b971be20f354a9c43"

FILES = (
    "wrapper-window-after.bin", "rng-continuation-before.bin",
    "arm-pcm-continuation.bin", "wrapper-window-continuation-after.bin",
    "rng-continuation-after.bin",
    "wrapper-window-retrigger-before.bin", "rng-retrigger-before.bin",
    "arm-pcm-retrigger.bin", "wrapper-window-retrigger-after.bin",
    "rng-retrigger-after.bin",
)


def run(cmd) -> None:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True)


def capture_digest(fixtures: pathlib.Path) -> tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    for mode in (1, 2, 3):
        for corner in (0, 1, 2):
            rel = f"engine-8-mode-{mode}-corner-{corner}"
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
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/cf-slap")
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
        raise SystemExit(f"engine-8 capture drift: {digest} != {CAPTURE_SET_SHA256}")
    print(f"PERKY slap evidence identity: PASS (firmware + {count} engine-8 files)")

    assets = args.assets.expanduser().resolve()
    for name in ("envelope1.bin", "envelope2.bin"):
        if not (assets / name).is_file():
            raise SystemExit(f"missing shared asset {assets / name}; "
                             "run verify_perky_cf_final.py once")

    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    obj = work / "cf_slap.o"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         "-c", ROOT / "modules/perky/cf_slap.c", "-o", obj])
    exe = work / "perky_cf_slap_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_slap_diff.cpp", obj, "-o", exe])
    run([exe, fixtures, assets])
    print("PERKY CF Slap DSP: PASS "
          "(bit-exact PCM, object and RNG; M1/M2/M3 x 3 corners)")


if __name__ == "__main__":
    main()
