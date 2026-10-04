#!/usr/bin/env python3
"""Generate the correctness-first PERKY Noise/Tone synth-seam DSP source.

The standalone primitive probes intentionally each carry their own exact
32-bit helper implementations so they can be tested in isolation. A firmware
image must not pay for those duplicates. This generator therefore composes the
same already-gated algorithm bodies but mechanically redirects their identical
add/sub/ASR/low32-multiply calls to the single ``pk_u32_*`` implementation in
``noise_tone_math.asm`` and removes only the duplicate helper sections.

The development synthetic-control mapper is deliberately one isolated piece.
It makes the five Octatrack controls audible for the synthetic canary while the
real PĒRKONS v1.2.1 update/control law is still being ported; replacing that one
piece later must not alter the qualified per-sample renderer.

No synthesis state-transition or sample-math body is rewritten here. Every cut
is guarded by exact marker/label counts so a source edit fails generation
rather than silently moving a boundary.

The generated source keeps ``@CONT@`` unresolved. build_bus applies the normal
PERKY A/B continuation substitution after the one-shot canary wrapper swaps
this generated path into the in-memory module declaration.

First-canary placement may use the contiguous PLATE/SPRING/DARK donor:
P:$1000..$1aa3 = 2724 words. ``measure()`` reports whether the deduplicated
source also happens to fit SPRING alone (1063 words), but only the full-donor
limit is mandatory at this milestone.
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
SPRING_DONOR_WORDS = 1063

PIECES = (
    "synth_seam_glue.asm",
    "synthetic_control_map.asm",
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


def exactly_once(text: str, token: str, where: str) -> None:
    count = text.count(token)
    if count != 1:
        die(f"{where}: expected one {token!r}, found {count}")


def redirect(text: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        text = text.replace(old, new)
    return text


def truncate_at(text: str, marker: str, where: str) -> str:
    exactly_once(text, marker, where)
    return text.split(marker, 1)[0].rstrip() + "\n"


def compact_piece(name: str, text: str) -> str:
    """Drop only standalone-probe helper duplicates from one source file."""
    if name == "noise_tone_filter.asm":
        text = redirect(text, {
            "pkf_add": "pk_u32_add",
            "pkf_sub": "pk_u32_sub",
            "pkf_asr": "pk_u32_asr",
            "pkf_mul_low": "pk_u32_mul_low",
        })
        marker = "; ---- exact two-limb helpers"
        clamp = "; Input +0/+1 is a signed 32-bit value."
        exactly_once(text, marker, name)
        exactly_once(text, clamp, name)
        before = text.split(marker, 1)[0].rstrip()
        unique = text[text.index(clamp):].rstrip()
        return before + "\n\n" + unique + "\n"

    if name == "noise_tone_oscillator_packed.asm":
        text = redirect(text, {
            "pkop_add": "pk_u32_add",
            "pkop_asr": "pk_u32_asr",
            "pkop_mul_low": "pk_u32_mul_low",
        })
        return truncate_at(text, "; ---- exact two-limb helpers", name)

    if name == "noise_tone_envelope_packed7.asm":
        # This wrapper intentionally calls the raw-envelope helper names so it
        # can be concatenated with that standalone probe. In shipping source
        # those helpers are replaced by the one shared math implementation.
        return redirect(text, {
            "pke_add": "pk_u32_add",
            "pke_asr": "pk_u32_asr",
            "pke_mul_low": "pk_u32_mul_low",
        })

    if name == "noise_tone_envelope.asm":
        text = redirect(text, {
            "pke_add": "pk_u32_add",
            "pke_sub": "pk_u32_sub",
            "pke_asr": "pk_u32_asr",
            "pke_mul_low": "pk_u32_mul_low",
        })
        return truncate_at(text, "; ---- exact two-limb helpers", name)

    if name == "noise_tone_mix.asm":
        text = redirect(text, {
            "pkm_add": "pk_u32_add",
            "pkm_sub": "pk_u32_sub",
            "pkm_asr": "pk_u32_asr",
            "pkm_mul_low": "pk_u32_mul_low",
        })
        add_label = "pk_u32_add:"
        clamp = "; Clamp signed32 +0/+1 to [-32768,32767]"
        # The global name appears once here ONLY because the local pkm_add
        # definition was renamed. Calls appear without a colon.
        exactly_once(text, add_label, name)
        exactly_once(text, clamp, name)
        start = text.index(add_label)
        end = text.index(clamp)
        if not start < end:
            die(f"{name}: helper/clamp boundaries reversed")
        return text[:start].rstrip() + "\n\n" + text[end:].rstrip() + "\n"

    # Seam, synthetic control mapper, complete voice glue and
    # noise_tone_math.asm carry no duplicate helper family to remove.
    return text


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
        body = compact_piece(name, path.read_text())
        chunks.append(f"; ===== BEGIN {name} =====\n" + body
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
    if src.count("pk_synth_apply_controls:") != 1:
        die("generated source must contain exactly one synthetic control mapper")
    if src.count("jsr     pk_synth_apply_controls") != 1:
        die("source seam must call the synthetic control mapper exactly once")

    # Dedupe invariants: one shared arithmetic definition, no local copies.
    for label in ("pk_u32_add:", "pk_u32_sub:", "pk_u32_asr:", "pk_u32_mul_low:"):
        if src.count(label) != 1:
            die(f"generated source expected one shared {label}, found {src.count(label)}")
    for label in (
        "pkf_add:", "pkf_sub:", "pkf_asr:", "pkf_mul_low:",
        "pkop_add:", "pkop_asr:", "pkop_mul_low:",
        "pke_add:", "pke_sub:", "pke_asr:", "pke_mul_low:",
        "pkm_add:", "pkm_sub:", "pkm_asr:", "pkm_mul_low:",
    ):
        if label in src:
            die(f"generated source still defines duplicate helper {label}")
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
            f"deduplicated synth is {words} P words, larger than the full "
            f"three-reverb donor ({FULL_DONOR_WORDS})"
        )
    return words


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("layout", type=Path,
                    help="layout.json from build_noise_tone_payload.py")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "out/perky/synth-canary/perky_synth.asm")
    ap.add_argument("--measure", action="store_true",
                    help="assemble payload-A copy and enforce full-donor budget")
    args = ap.parse_args()

    src = generate(args.layout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(src)
    print(f"PERKY synth source: wrote {args.out} ({len(src):,} source bytes)")
    if args.measure:
        words = measure(src, args.out)
        fit = "YES" if words <= SPRING_DONOR_WORDS else "not yet"
        print(
            f"PERKY synth source: {words}/{FULL_DONOR_WORDS} P words, "
            f"FREE {FULL_DONOR_WORDS - words}; SPRING-only <= {SPRING_DONOR_WORDS}: {fit}"
        )


if __name__ == "__main__":
    main()
