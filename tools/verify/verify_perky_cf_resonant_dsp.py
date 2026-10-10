#!/usr/bin/env python3
"""ColdFire Resonant Drums renderer vs the real firmware's own captured output.

Engine 7 panel M1 is the Resonant Snare object and M2 the Resonant Bass object.
This gate takes the authentic wrapper snapshots and PCM captured by running the
real v1.2.1 M7 firmware under Unicorn, renders them with the production
ColdFire translation and requires bit-exact PCM, final state and RNG.

No firmware is flashed; the interpolation tables are read from the SHA-pinned
image at 0x0803237C / 0x08032178 the same way the DSP qualification does.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky")]
from extract_noise_tone_tables import find_m7, parse_container  # noqa:E402

INTERP_A = (0x0803237C, 514)
INTERP_B = (0x08032178, 514)
ENV1 = (0x08022EA0, 4096)
ENV2 = (0x080236A2, 4096)

# SHA-pinned PĒRKONS v1.2.1 image.
FIRMWARE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"

# The exact engine-7 captures this gate compares against, hashed in place. These
# are the firmware's own RAM and PCM recorded under Unicorn; pinning them keeps
# the comparison honest if the fixture tree is ever regenerated differently.
CAPTURE_SHA256 = {
    "engine-7-mode-1-corner-0/wrapper-window-after.bin":
        "bdd9ef86a6519c246dad4502eddec75add6519fa7b0dcd6c365118f6ea4278f7",
    "engine-7-mode-1-corner-0/wrapper-window-continuation-after.bin":
        "76dadbf4c09aa666958ca114514c84c342775b583c5cd1d99b328965ea5d90bd",
    "engine-7-mode-1-corner-0/arm-pcm-continuation.bin":
        "05a1f48940ab9797e869e8be2c3963273e66b96df34f59196e56786664fe722c",
    "engine-7-mode-1-corner-0/rng-continuation-before.bin":
        "fbf3b4956d2afa06efa18bf6f3e9bf7bd952159bcc7ec4e147a482cc465dacf2",
    "engine-7-mode-1-corner-0/rng-continuation-after.bin":
        "6f6b1bb48e269f6469584a947ad0203b1c86474e22747fe8bd8933500dc331f3",
    "engine-7-mode-1-corner-1/wrapper-window-after.bin":
        "a0da67bef2a1f497b07131ef3d0ee7295ac5ce2b5539a4730bca9b14785120b1",
    "engine-7-mode-1-corner-1/wrapper-window-continuation-after.bin":
        "d90967278090611eda272d42da02c1da5105c27c5b165ef5b61bb383be78c0f7",
    "engine-7-mode-1-corner-1/arm-pcm-continuation.bin":
        "8e768a03679a5400aba0003b74791021ce647ee62db5d1e8867337f1680d17e0",
    "engine-7-mode-1-corner-2/wrapper-window-after.bin":
        "db2298ae51c5edb7d51d6355140fb078ebec5e5e4679b8f43c0529caa0a576d8",
    "engine-7-mode-1-corner-2/wrapper-window-continuation-after.bin":
        "3f92657d0b5f5ba03a4a7298f027a22b55795ef96c2a9a57c61f4cb51a01b930",
    "engine-7-mode-1-corner-2/arm-pcm-continuation.bin":
        "74214f7466753b921537155d3a90f6db4fc19ce55979dc228dfb0d861ce7fe45",
    "engine-7-mode-2-corner-0/wrapper-window-after.bin":
        "5a5866ee6fbec74004c235168744412e20af5d5224bb873ff9a17d30a69630ab",
    "engine-7-mode-2-corner-0/wrapper-window-continuation-after.bin":
        "9395a44cf102e7c817fbbc65dcbfcb795cd95e90de1938ae4462fb10e55355e2",
    "engine-7-mode-2-corner-0/arm-pcm-continuation.bin":
        "d2d18aea2538b9863722d4fe6f24780992b3f09c394f2f3acf492b02ec73e5b2",
    "engine-7-mode-2-corner-1/wrapper-window-after.bin":
        "1c5a48a04419a8317cdbbd720eb1728e43de9e5d7fd4e8332c7a2ce1e95d8b66",
    "engine-7-mode-2-corner-1/wrapper-window-continuation-after.bin":
        "d728ca1dca27e74c3c0c6be1a0edfa28e1acf44d1d28214f30bcfcffbdd9648f",
    "engine-7-mode-2-corner-1/arm-pcm-continuation.bin":
        "35a46b6c1108f67323747f58f71b9ad973d5e819260e08c1de88f218d06582cd",
    "engine-7-mode-2-corner-2/wrapper-window-after.bin":
        "2b61b05b3ac9e22c798c6db29a4443a788455c62254886f319dc02ec7226a20c",
    "engine-7-mode-2-corner-2/wrapper-window-continuation-after.bin":
        "8b9b0451ce86a732db8dc60e994de7f6163c4b3ca86970d007cd6d40a4c59ff2",
    "engine-7-mode-2-corner-2/arm-pcm-continuation.bin":
        "12e1ed1b444c5366f7286e5e75a220b6ab1126cbedb1afca131089ac8e8dfb0e",
}


def run(cmd: list) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("PERKONS_FIRMWARE", "")))
    ap.add_argument("--fixtures", type=pathlib.Path,
                    default=ROOT / "out/perky/engine-fixtures")
    ap.add_argument("--work", type=pathlib.Path,
                    default=ROOT / "out/perky/cf-resonant")
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

    # Pin the external evidence we compare against.
    got = hashlib.sha256(firmware.read_bytes()).hexdigest()
    if got != FIRMWARE_SHA256:
        raise SystemExit(f"firmware hash drift: {got} != {FIRMWARE_SHA256}")
    for rel, want in CAPTURE_SHA256.items():
        path = fixtures / rel
        if not path.is_file():
            raise SystemExit(f"missing capture {rel}")
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        if h != want:
            raise SystemExit(f"capture drift: {rel}\n  got  {h}\n  want {want}")
    print(f"PERKY resonant evidence identity: PASS "
          f"(firmware + {len(CAPTURE_SHA256)} pinned engine-7 captures)")

    segment = find_m7(parse_container(firmware.read_bytes())[1])
    for name, (address, length) in (("envelope1.bin", ENV1), ("envelope2.bin", ENV2),
                                    ("interp_a.bin", INTERP_A), ("interp_b.bin", INTERP_B)):
        (assets / name).write_bytes(segment.read(address, length))

    # The end-to-end harness also needs the shared PĒRKONS tables.
    shared = ROOT / "out/perky/cf-final-verify/fixtures/assets"
    for name in ("pitch.bin", "chromatic.bin", "m1.bin",
                 "w0.bin", "w1.bin", "w2.bin", "w3.bin"):
        src = shared / name
        if not src.is_file():
            raise SystemExit(f"missing shared asset {src}; run verify_perky_cf_final.py once")
        (assets / name).write_bytes(src.read_bytes())

    objects = []
    for name in ("cf_fold", "cf_karplus", "cf_noise_tone", "cf_perky4",
                 "cf_resonant", "cf_noise_hat", "cf_simple_drum"):
        obj = work / f"{name}.o"
        run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", ROOT / "modules/perky",
             "-c", ROOT / "modules/perky" / f"{name}.c", "-o", obj])
        objects.append(obj)

    cf = work / "cf_resonant.o"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         "-c", ROOT / "modules/perky/cf_resonant.c", "-o", cf])
    exe = work / "perky_cf_resonant_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_resonant_diff.cpp", cf, "-o", exe])
    run([exe, fixtures, assets])
    print("PERKY CF Resonant Drums DSP: PASS (bit-exact PCM/state/RNG)")

    e2e = work / "perky4_resonant_e2e"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky4_resonant_e2e.cpp", *objects, "-o", e2e])
    run([e2e, fixtures, assets])
    print("PERKY CF Resonant Drums control path: PASS "
          "(init/update/trigger/PCM vs the real firmware captures)")


if __name__ == "__main__":
    main()
