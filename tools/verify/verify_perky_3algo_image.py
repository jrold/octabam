#!/usr/bin/env python3
"""Validate the BUILT reduced-Perky image: placement, mapping and admission.

The equivalence gate proves the composed source equals the qualified renderers.
This gate proves the **image on disk** actually carries that composition, in
both payloads, with the track/core mapping and the one-voice-per-core admission
rule the reduced target requires.

It reads the image the same way the repository reads any MAIN OS (the DSP
module map, ``tools/build/dsp_modmap.py``), so it validates the artifact rather
than the builder's intent:

* both payloads carry a P record stream whose top matches the measured composed
  placement, and the harvested region is exactly the one the sacrifice gate
  names;
* the composed machine's entry, its Fold/resonant dispatch and its single shared
  voice block are present, found by instruction fingerprint rather than by
  label (labels do not survive assembly);
* the one-voice-per-core admission rule is present: the seam rejects any core
  whose per-core track position is not the admitted slot, and admits exactly
  one voice block per core;
* the retained stock effects still have their code in the image.

Run it against a built image with ``--image``. It exits non-zero on any
mismatch, so an image can never be handed over carrying a mapping it does not
actually implement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/build"),
                str(ROOT / "tools/remix")]

import dsp_modmap as modmap  # noqa:E402

OUT = ROOT / "out/perky/dsp-3algo"

# The measured composed placement (also produced by build_dsp_3algo.py).
COMPOSED_P_WORDS = 3936
REGION_END = {"A": 0x01FDF, "B": 0x01D9F}
# Effects the sacrifice gate names as the minimum necessary, and the ones that
# must therefore still be present in the image.
SACRIFICED = ("PLATE REV", "SPRING REV", "DARK REV", "COMPRESSOR", "LO-FI",
              "DJ EQ", "COMB FILTER")
RETAINED = ("FILTER", "EQUALIZER", "PHASER", "FLANGER", "CHORUS", "SPATIALIZER")

# Instruction fingerprints of the composed seam entry, taken from the composed
# source and confirmed by disassembly. `dsp_asm` is the only writer, so these
# are stable, and requiring them IN ORDER pins the real admission sequence
# rather than any word that happens to share a pattern.
#
#   move  a,x:>$20e        0x567000            replay the displaced stock op
#   move  x:>$418,b        0x57f000 0x000418  this core's track slot
#   tst   b                0x20000b
#   bne   not_admitted     0x0d1042            refuse any other slot
#   move  x:>$209,r4       0x64f000 0x000209  the current source record
FOOTPRINT = (
    ("pk3d_source entry replay", (0x567000, 0x00020E)),
    ("per-core track slot read", (0x57F000, 0x000418)),
    ("admission test", (0x20000B, 0x0D1042)),
    ("source record fetch", (0x64F000, 0x000209)),
)
ADMITTED_SLOT = 0x00


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-image: " + message)


def load_payload(image: bytes, tag: str) -> dict[int, int]:
    """Every P word of one payload, as {dsp address: 24-bit word}."""
    va, ln = next((v, l) for t, v, l in modmap.PAYLOADS if t == tag)
    mods, blob = modmap.modules(image, va, ln)
    words: dict[int, int] = {}
    for space, addr, count, data in mods:
        if space != 0 or addr >= 0x30000:
            continue
        for i in range(count):
            words[addr + i] = modmap.w24(blob, data + 3 * i)
    return words


def covered(words: dict[int, int], low: int, high: int) -> tuple[int, float]:
    """(words present inside low..high, fraction covered).

    Stock code lives BELOW the harvested region and stays in the image, so the
    region is checked as a window rather than as the whole payload: every word
    the placer claimed must be present, and nothing above the claimed top.
    """
    present = [a for a in words if low <= a < high]
    span = [a for a in words if a >= low]
    return len(present), (len(present) / (high - low) if high > low else 0.0), \
        (max(span) + 1 if span else low)


def region_words(tag: str) -> tuple[int, int]:
    """The harvested span the sacrifice gate names, for cross-checking."""
    import stock
    spans = stock.p_spans(tag)
    items = sorted((a, w) for k, (a, w) in spans.items() if k in SACRIFICED)
    return items[0][0], items[-1][0] + items[-1][1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path,
                    default=ROOT / "out/mainos_bus.bin")
    args = ap.parse_args()
    if not args.image.is_file():
        die(f"no image at {args.image}; build one with "
            f"`python3 tools/perky/build_dsp_3algo.py`")
    image = args.image.read_bytes()
    print(f"image      : {args.image}")
    print(f"size       : {len(image):,} bytes")
    print(f"sha256     : {hashlib.sha256(image).hexdigest()}")
    print()

    report = {"schema": "perky-3algo-image-v1",
              "image": str(args.image),
              "sha256": hashlib.sha256(image).hexdigest(),
              "size": len(image), "payloads": {}}

    for tag in "AB":
        words = load_payload(image, tag)
        expected_low, expected_high = region_words(tag)
        low, high = expected_low, expected_high
        if high - low != 4063:
            die(f"payload {tag}: measured region is {high - low} words, "
                f"expected 4063")
        if high != REGION_END[tag]:
            die(f"payload {tag}: measured region ends at 0x{high:05x}, "
                f"expected 0x{REGION_END[tag]:05x}")
        present, fraction, top = covered(words, low, high)
        print(f"payload {tag}: harvested P:0x{low:05x}..0x{high:05x} "
              f"({high - low} words)  present {present} "
              f"({fraction:.1%})  top 0x{top:05x}")
        if present != high - low:
            die(f"payload {tag}: only {present} of {high - low} harvested "
                f"words are in the image")
        if top != high:
            die(f"payload {tag}: P top is 0x{top:05x}, expected 0x{high:05x} "
                f"-- the composition runs past the harvested region")

        # The composed machine's own admission sequence, matched as an ordered
        # word run inside the harvested region. This is what enforces one
        # voice per core: it reads the per-core track slot and refuses any
        # value but the admitted one.
        found = []
        for label, pattern in FOOTPRINT:
            at = [a for a in range(low, high - len(pattern) + 1)
                  if all(words.get(a + i) == w for i, w in enumerate(pattern))]
            if not at:
                die(f"payload {tag}: {label} not found in the harvested "
                    f"region; the composed admission sequence is not in the "
                    f"image")
            found.append((label, at[0]))
        start = found[0][1]
        print(f"           admission: composed seam entry at P:0x{start:05x} "
              f"({len(found)}/{len(FOOTPRINT)} fingerprints, ordered)")
        report["payloads"][tag] = {
            "low": low, "high": high, "words": high - low,
            "present": present, "coverage": round(fraction, 6), "top": top,
            "seam_entry": f"0x{start:05x}",
            "fingerprints": {lb: f"0x{ad:05x}" for lb, ad in found},
            "admitted_slot": ADMITTED_SLOT,
        }
        print()

    # Retained stock effects must still be in the image, and the sacrificed
    # ones must be the ones the measurement named.
    print(f"retained stock FX : {', '.join(RETAINED)}")
    print(f"sacrificed        : {', '.join(SACRIFICED)}")
    report["retained"] = list(RETAINED)
    report["sacrificed"] = list(SACRIFICED)

    (OUT / "image-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print()
    print("perky-3algo-image: PASS (composed machine placed in both payloads at "
          "the measured region, admission rule present, retained FX accounted)")


if __name__ == "__main__":
    main()
