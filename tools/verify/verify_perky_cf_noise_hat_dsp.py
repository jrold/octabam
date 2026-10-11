#!/usr/bin/env python3
"""ColdFire Noise Hat renderer vs the real firmware's own captured output.

Engine 10 panel M1 is the white-noise limb, M2 the metallic limb (both inside
the 0x2dd8 classic object) and M3 the separate Pulse Stack limb at wrapper
+0x2C98. This gate renders the authentic captured states and requires
bit-exact PCM and final state, plus the shared 16-bit sample/hold and the RNG
for the classic limbs.

No firmware is flashed; the envelope tables come from the SHA-pinned image.
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
# Digest over every file of the nine engine-10 fixture directories, in sorted
# (relative path, content) order; keeps the compared evidence honest.
CAPTURE_SET_SHA256 = "fe75770b7cabaeec15d3493bd69eb823a94422b26d0de40b2ae7798cc79a22e0"
ENV1 = (0x08022EA0, 4096)
ENV2 = (0x080236A2, 4096)


def run(cmd: list) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def capture_digest(fixtures: pathlib.Path) -> tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    for d in sorted(fixtures.glob("engine-10-mode-*-corner-*")):
        for p in sorted(d.iterdir()):
            h.update(str(p.relative_to(fixtures)).replace("\\", "/").encode())
            h.update(hashlib.sha256(p.read_bytes()).digest())
            count += 1
    return h.hexdigest(), count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("PERKONS_FIRMWARE", "")))
    ap.add_argument("--fixtures", type=pathlib.Path,
                    default=ROOT / "out/perky/engine-fixtures")
    ap.add_argument("--work", type=pathlib.Path,
                    default=ROOT / "out/perky/cf-noise-hat")
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    fixtures = args.fixtures.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    if not (fixtures / "cases.tsv").is_file():
        raise SystemExit(f"missing engine fixtures under {fixtures}")
    work = args.work.resolve()
    assets = work / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    got = hashlib.sha256(firmware.read_bytes()).hexdigest()
    if got != FIRMWARE_SHA256:
        raise SystemExit(f"firmware hash drift: {got} != {FIRMWARE_SHA256}")
    digest, count = capture_digest(fixtures)
    if digest != CAPTURE_SET_SHA256:
        raise SystemExit(f"engine-10 capture drift: {digest} != {CAPTURE_SET_SHA256}")
    print(f"PERKY noise-hat evidence identity: PASS (firmware + {count} engine-10 files)")

    segment = find_m7(parse_container(firmware.read_bytes())[1])
    (assets / "envelope1.bin").write_bytes(segment.read(*ENV1))
    (assets / "envelope2.bin").write_bytes(segment.read(*ENV2))

    obj = work / "cf_noise_hat.o"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         "-c", ROOT / "modules/perky/cf_noise_hat.c", "-o", obj])
    exe = work / "perky_cf_noise_hat_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_noise_hat_diff.cpp", obj, "-o", exe])
    run([exe, fixtures, assets])
    print("PERKY CF Noise Hat DSP: PASS (bit-exact PCM/state/hold/RNG, all three limbs)")

    # Same captures, but through the whole C control path: cold init, sixteen
    # updates, trigger, one more update.
    shared = ROOT / "out/perky/cf-final-verify/fixtures/assets"
    for name in ("pitch.bin", "chromatic.bin", "m1.bin",
                 "w0.bin", "w1.bin", "w2.bin", "w3.bin"):
        src = shared / name
        if not src.is_file():
            raise SystemExit(f"missing shared asset {src}; run verify_perky_cf_final.py once")
        (assets / name).write_bytes(src.read_bytes())
    objects = []
    for name in ("cf_fold", "cf_karplus", "cf_noise_tone", "cf_perky4",
                 "cf_resonant", "cf_noise_hat", "cf_simple_drum", "cf_complex_drum",
                 "cf_slap", "cf_wavetable"):
        obj = work / f"{name}.o"
        run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", ROOT / "modules/perky",
             "-c", ROOT / "modules/perky" / f"{name}.c", "-o", obj])
        objects.append(obj)
    e2e = work / "perky4_noise_hat_e2e"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky4_noise_hat_e2e.cpp", *objects, "-o", e2e])
    run([e2e, fixtures, assets])
    print("PERKY CF Noise Hat control path: PASS "
          "(init/update/trigger states vs the real firmware captures)")


if __name__ == "__main__":
    main()
