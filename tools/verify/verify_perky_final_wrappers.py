#!/usr/bin/env python3
"""Round-trip final Perky card and MIDI wrappers back to their exact inputs.

Release-only packaging gate. The card image must decode to the exact ELEK
container emitted by elektron-firmware-tool, and the MIDI SysEx must decompress
section 3 back to the exact final MAIN OS bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/build"))
import bin_decode  # noqa:E402


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_card(card: Path) -> tuple[bytes, int]:
    data = card.read_bytes()
    if len(data) < 12 or len(data) % 4:
        raise SystemExit(f"PERKY wrapper round-trip: invalid ELUP size {len(data)}")
    words = struct.unpack(f">{len(data)//4}I", data)
    if words[0] != bin_decode.MAGIC:
        raise SystemExit(f"PERKY wrapper round-trip: card magic {words[0]:#x} != ELUP")
    seed = words[1]
    k = seed
    acc = 0
    plain: list[int] = []
    for c in words[2:-1]:
        p = bin_decode.decode_word(k, c)
        plain.append(p)
        acc = (acc + p) & 0xFFFFFFFF
        k = c
    expected = bin_decode.decode_word(k, words[-1])
    if acc != expected:
        raise SystemExit(
            f"PERKY wrapper round-trip: ELUP checksum mismatch {acc:#010x} != {expected:#010x}"
        )
    payload = struct.pack(f">{len(plain)}I", *plain)
    if len(payload) < 4:
        raise SystemExit("PERKY wrapper round-trip: decoded ELUP payload is truncated")
    declared = struct.unpack_from(">I", payload, 0)[0]
    if declared > len(payload) - 4:
        raise SystemExit(
            f"PERKY wrapper round-trip: ELEK declared {declared} bytes, only {len(payload)-4} available"
        )
    elek = payload[4:4 + declared]
    pad = payload[4 + declared:]
    if any(pad):
        raise SystemExit("PERKY wrapper round-trip: non-zero ELUP padding after ELEK container")
    if not elek.startswith(b"ELEK"):
        raise SystemExit(f"PERKY wrapper round-trip: decoded container is not ELEK: {elek[:8]!r}")
    return elek, seed


def extract_midi_main(eft: Path, midi: Path, work: Path, expected: bytes) -> Path:
    out = work / "midi-section-3"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    subprocess.run(
        [str(eft), "-i", str(midi), "-d", "3", "-o", str(out)],
        cwd=ROOT,
        check=True,
    )
    files = [p for p in out.rglob("*") if p.is_file()]
    exact = [p for p in files if p.read_bytes() == expected]
    if len(exact) != 1:
        details = ", ".join(f"{p.name}:{p.stat().st_size}" for p in files) or "<none>"
        raise SystemExit(
            "PERKY wrapper round-trip: generated MIDI did not yield exactly one "
            f"section-3 file equal to MAIN OS; extracted={details}"
        )
    return exact[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mainos", type=Path, required=True)
    ap.add_argument("--elek", type=Path, required=True)
    ap.add_argument("--card", type=Path, required=True)
    ap.add_argument("--midi", type=Path, required=True)
    ap.add_argument("--eft", type=Path, required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--work", type=Path, default=ROOT / "out/perky/cf-final/wrapper-verify")
    args = ap.parse_args()

    for name, path in (("MAIN OS", args.mainos), ("ELEK", args.elek),
                       ("card", args.card), ("MIDI", args.midi), ("EFT", args.eft)):
        if not path.is_file():
            raise SystemExit(f"PERKY wrapper round-trip: missing {name}: {path}")

    mainos = args.mainos.read_bytes()
    emitted = args.elek.read_bytes()
    if not emitted.startswith(b"ELEK"):
        raise SystemExit("PERKY wrapper round-trip: emitted container does not start ELEK")
    if not (1 <= len(args.version) <= 10 and args.version.isascii()
            and not any(ch.isspace() for ch in args.version)):
        raise SystemExit("PERKY wrapper round-trip: version must be 1..10 ASCII non-whitespace characters")
    if len(emitted) < 18:
        raise SystemExit("PERKY wrapper round-trip: ELEK container is too short for version field")
    want_version = args.version.rjust(10, " ").encode("ascii")
    got_version = emitted[0x08:0x12]
    if got_version != want_version:
        raise SystemExit(
            "PERKY wrapper round-trip: ELEK version field mismatch "
            f"{got_version!r} != {want_version!r}"
        )
    card_elek, seed = decode_card(args.card)
    if card_elek != emitted:
        raise SystemExit(
            "PERKY wrapper round-trip: CF-card ELEK differs from emitted container "
            f"({sha256_bytes(card_elek)} != {sha256_bytes(emitted)})"
        )

    extracted = extract_midi_main(args.eft, args.midi, args.work, mainos)
    print(
        "PERKY final wrapper round-trip: PASS\n"
        f"  card: ELUP checksum valid; seed=0x{seed:08x}; ELEK={len(emitted):,} B exact; version={args.version}\n"
        f"  MIDI: section 3 -> {extracted.name}; MAIN OS={len(mainos):,} B exact\n"
        f"  MAIN OS sha256={sha256_bytes(mainos)}"
    )


if __name__ == "__main__":
    main()
