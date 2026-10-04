#!/usr/bin/env python3
"""Generate the correctness-first PERKY Noise/Tone synth-seam DSP source.

This is a DEVELOPMENT composition step, not the final size-optimized engine.
It concatenates the independently gated primitive sources behind the real
sample-accurate source seam, substitutes the four packed-wave identities from
``layout.json`` and aliases the seam entry to the manifest's existing
``pk_probe_source`` DspHook label.

The generated source intentionally keeps @CONT@ unresolved. build_bus.py
applies the normal PERKY per-payload substitution after the one-shot build
wrapper swaps this path into the module declaration in memory.

For the first synth canary we allow the full contiguous PLATE/SPRING/DARK donor
region: P:$1000..$1aa3 = 2724 words. ``--measure`` assembles a payload-A copy
and refuses anything larger before build_bus gets near the image. A later
optimization milestone will deduplicate the standalone arithmetic helpers and
target SPRING alone (~1063 words).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
ASM = ROOT / "vendor/dsp56300/build/source/dsp_host/dsp_asm"
FULL_DONOR_WORDS = 0x1AA4 - 0x1000  # PLATE + SPRING + DARK = 2724 words

PIECES = (
    "synth_seam_glue.asm",
    "noise_tone_voice_xstate_glue.asm",
    "noise_tone_math.asm",
    "noise_tone_filter.asm",
    "noise_tone_oscillator_packed.asm",
    "noise_tone_envelope_packed7.asm",
    "noise_tone_envelope.asm",
    "noise_tone_mix.asm",
)


def die(msg: str) -> "NoReturn":
    raise SystemExit("perky-synth-source: " + msg)


def wave_ids(layout: dict) -> list[int]:
    identities = layout.get("waves", {}).get("identities", [])
    if len(identities) != 4:
        die(f"layout has {len(identities)} wave identities, expected 4")
    out = []
    for ordinal, item in enumerate(identities):
        if item.get("ordinal") != ordinal:
            die("wave identity ordinals are not exactly 0,1,2,3")
        try:
            out.append(int(str(item["address"]), 16))
        except (KeyError, ValueError) as exc:
            die(f"bad wave identity row {item!r}: {exc}")
    if len(set(out)) != 4:
        die("wave identities are not unique")
    return out


def generate(layout_path: Path) -> str:
    try:
        layout = json.loads(layout_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"{layout_path}: {exc}")
    if layout.get("schema") != "perky-noise-tone-dsp-tables-v1":
        die(f"unsupported layout schema {layout.get('schema')!r}")

    envs = layout.get("envelopes", [])
    widths = [item.get("delta_bits") for item in envs]
    # Current assembly decoder is deliberately a synthetic 7-bit canary.
    if widths != [7, 7]:
        die(
            f"current synth canary decoder is qualified only for 7/7-bit "
            f"envelopes; layout reports {widths!r}"
        )

    ids = wave_ids(layout)
    chunks = []
    for name in PIECES:
        path = PERKY / name
        if not path.exists():
            die(f"missing {path}")
        chunks.append(f"; ===== BEGIN {name} =====\n" + path.read_text()
                      + f"\n; ===== END {name} =====\n")
    src = "\n".join(chunks)

    if src.count("pk_synth_source:") != 1:
        die("expected exactly one pk_synth_source label")
    if "pk_probe_source:" in src:
        die("component sources already define pk_probe_source")
    src = src.replace("pk_synth_source:", "pk_probe_source:", 1)

    for i, address in enumerate(ids):
        src = src.replace(f"@W{i}L@", f"${address & 0xFFFF:04x}")
        src = src.replace(f"@W{i}H@", f"${(address >> 16) & 0xFFFF:04x}")
    if "@W" in src:
        die("generated source still contains a wave-identity marker")
    if src.count("@CONT@") != 1:
        die(f"generated source contains {src.count('@CONT@')} @CONT@ markers, expected 1")
    if src.count("pk_probe_source:") != 1:
        die("generated source does not expose exactly one DspHook entry")
    return src


def measure(source: str, out: Path) -> int:
    if not ASM.exists():
        die(f"missing {ASM}; run `make setup` before --measure")
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(".measure.asm")
    binary = out.with_suffix(".measure.bin")
    # Size is independent of the payload-specific continuation value. Use A.
    temp.write_text(source.replace("@CONT@", "$000426"))
    r = subprocess.run(
        [str(ASM), "-in", str(temp), "-org", "1000", "-out", str(binary)],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        die("DSP assembler failed:\n" + r.stdout[-5000:] + r.stderr[-3000:])
    size = binary.stat().st_size
    if size % 3:
        die(f"assembled binary is {size} bytes, not a whole number of DSP words")
    words = size // 3
    if words > FULL_DONOR_WORDS:
        die(
            f"correctness synth is {words} P words, larger than the full "
            f"three-reverb donor ({FULL_DONOR_WORDS}); deduplicate helpers first"
        )
    return words


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("layout", type=Path,
                    help="layout.json from build_noise_tone_payload.py")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "out/perky/synth-canary/perky_synth.asm")
    ap.add_argument("--measure", action="store_true",
                    help="assemble a temporary payload-A copy and enforce 2724-word budget")
    args = ap.parse_args()

    src = generate(args.layout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(src)
    print(f"PERKY synth source: wrote {args.out} ({len(src):,} source bytes)")
    if args.measure:
        words = measure(src, args.out)
        print(
            f"PERKY synth source: {words}/{FULL_DONOR_WORDS} P words, "
            f"FREE {FULL_DONOR_WORDS - words} in PLATE/SPRING/DARK donor"
        )


if __name__ == "__main__":
    main()
