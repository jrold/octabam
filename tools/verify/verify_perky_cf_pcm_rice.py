#!/usr/bin/env python3
"""Gate the lossless PCM stream that keeps the card OS upgrade working.

The Octatrack's card upgrade refuses an ELUP `.bin` whose payload exceeds
1 MiB (`0x4007f748`: `filesize - 12 > 0x100000` -> the error whose message is
"LENGTH ERROR").  PerkyMachines' Wavetable bank and Acoustic Hats samples are
648 KB of incompressible PCM, which pushed the payload past that.  This gate
packs those assets with the production coder (tools/perky/pcm_rice.py),
decodes them back with the production ColdFire decoder
(modules/perky/cf_pcm_rice.h) and requires every byte to come back.

It also prices the result, because the size is the whole point.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky")]
from extract_noise_tone_tables import find_m7, parse_container  # noqa:E402
import pcm_rice  # noqa:E402

# The assets carried by the stream, in stream order: label, M7 address, bytes.
ASSETS = (
    ("wt_base", 0x080222A0, 4096),
) + tuple(
    (f"wt_bank_{k}", 0x080327CC + k * 0x1000, 4096) for k in range(48)
) + (
    ("ah_closed", 0x080CBEF0, 20202),
    ("ah_open", 0x080A1BF0, 172800),
    ("ah_ride", 0x080627CC, 259106),
)

# The card OS-upgrade payload ceiling: filesize - 12 must not exceed 0x100000.
CARD_PAYLOAD_MAX = 0x100000 + 12
# What the ELUP wrapper adds on top of the ELEK container.


def run(cmd: list) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("PERKONS_FIRMWARE", "")))
    ap.add_argument("--work", type=pathlib.Path,
                    default=ROOT / "out/perky/cf-pcm-rice")
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    segment = find_m7(parse_container(firmware.read_bytes())[1])

    blobs = [segment.read(address, size) for _label, address, size in ASSETS]
    packed = pcm_rice.encode(blobs)
    (work / "pcm.pkr").write_bytes(packed)
    raw = sum(len(b) for b in blobs)

    exe = work / "pcm_rice_check"
    run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky_cf_pcm_rice_check.c", "-o", exe])
    out = work / "out"
    out.mkdir(parents=True, exist_ok=True)
    run([exe, work / "pcm.pkr", out, *[str(len(b) // 2) for b in blobs]])

    for i, (label, _address, size) in enumerate(ASSETS):
        got = (out / f"asset-{i:02d}.bin").read_bytes()
        if got != blobs[i]:
            where = next(k for k in range(min(len(got), len(blobs[i])))
                         if got[k] != blobs[i][k])
            raise SystemExit(f"PERKY CF pcm-rice: FAIL {label} differs at byte {where}")

    print(f"PERKY CF pcm-rice: PASS ({len(ASSETS)} assets, every byte back)")
    print(f"  raw {raw:,} B -> packed {len(packed):,} B "
          f"({len(packed)/raw:.3f}); saved {raw - len(packed):,} B")
    print(f"  card payload ceiling {CARD_PAYLOAD_MAX:,} B: "
          f"a .bin carrying this stream instead of the raw PCM loses "
          f"{raw - len(packed):,} B")


if __name__ == "__main__":
    main()
