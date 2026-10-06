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

The shipping synthetic path uses native DSP arithmetic and direct compact
state access. Standalone limb kernels remain independent oracle probes.
Executable shipping gates require identical PCM, compact state and RNG; the
cycle gate separately enforces the single-voice-per-core development budget.

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
import re
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

# DSP56300 Jcc xxx is a 12-bit ABSOLUTE jump.  The composed synth lives above
# P:$0fff, so local conditionals written naturally as ``jcc pk_label`` assemble
# in low-origin standalone probes but become invalid in the shipping image.
# Their Bcc counterparts are PC-relative and are the correct encoding for local
# labels.  Keep this conversion mechanical and limited to PERKY-local symbols;
# external absolute control flow such as ``jmp @CONT@`` is intentionally left
# alone.
LOCAL_CONDITIONAL_JUMPS = {
    "jcc": "bcc",
    "jcs": "bcs",
    "jhs": "bhs",
    "jlo": "blo",
    "jeq": "beq",
    "jne": "bne",
    "jgt": "bgt",
    "jlt": "blt",
    "jge": "bge",
    "jle": "ble",
    "jmi": "bmi",
    "jpl": "bpl",
    "jvc": "bvc",
    "jvs": "bvs",
}
_LOCAL_JUMP_RE = re.compile(
    r"(?m)^(\s*)(jcc|jcs|jhs|jlo|jeq|jne|jgt|jlt|jge|jle|jmi|jpl|jvc|jvs)"
    r"(\s+)(pk[A-Za-z0-9_]+)(\s*(?:;.*)?)$",
    re.IGNORECASE,
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


def relativize_local_conditionals(text: str) -> str:
    """Encode PERKY-local conditional flow as PC-relative branches.

    ``jXX label`` and ``bXX label`` have the same condition semantics, but the
    former is a 12-bit absolute target on DSP56300.  Every target matched here
    is an in-image PERKY label, so a relative branch is both smaller in intent
    and valid regardless of the donor region's absolute P address.
    """
    def repl(match: re.Match[str]) -> str:
        indent, mnemonic, spacing, label, tail = match.groups()
        branch = LOCAL_CONDITIONAL_JUMPS[mnemonic.lower()]
        return f"{indent}{branch}{spacing}{label}{tail}"

    return _LOCAL_JUMP_RE.sub(repl, text)


def force_long_local_jsr(text: str) -> str:
    """Mark every internal PERKY call as an explicit two-word long JSR.

    The generated synth lives at P:$1000+, outside the DSP56300 one-word
    ``jsr xxx`` 12-bit absolute range. Octabam's dsp_asm therefore exposes the
    explicit ``jsrl label`` pseudo-op, which always emits the real two-word
    absolute JSR encoding without relying on pass-1 label guessing.
    """
    return re.sub(
        r"(?m)^(\s*)jsr(\s+)(pk[A-Za-z0-9_]+)(\s*(?:;.*)?)$",
        r"\1jsrl\2\3\4",
        text,
    )


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
        exactly_once(text, add_label, name)
        exactly_once(text, clamp, name)
        start = text.index(add_label)
        end = text.index(clamp)
        if not start < end:
            die(f"{name}: helper/clamp boundaries reversed")
        return text[:start].rstrip() + "\n\n" + text[end:].rstrip() + "\n"

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
    if widths != [7, 7]:
        die(
            f"current synth canary decoder is qualified only for 7/7-bit "
            f"envelopes; layout reports {widths!r}"
        )

    ids = wave_ids(layout)
    if layout.get("synthetic") is not True or ids != [0x10000000, 0x10000200, 0x10000400, 0x10000600]:
        die("native shipping fast path requires the qualified synthetic wave identities")
    if layout.get("source_sha256", {}).get("envelope1.bin") != "8136fff8a23fc148c79bbc3a55927ff23cadeff8623adeef2d91e7d15fd4d33b":
        die("native shipping fast path requires the qualified synthetic linear curve")
    chunks = []
    for name in PIECES:
        path = PERKY / name
        if not path.exists():
            die(f"missing {path}")
        if name in ("noise_tone_filter.asm", "noise_tone_mix.asm"):
            body = (PERKY / name.replace(".asm", "_native.asm")).read_text()
        elif name == "noise_tone_oscillator_packed.asm":
            body = compact_piece(name, (PERKY / "noise_tone_oscillator_native.asm").read_text())
        elif name == "noise_tone_envelope_packed7.asm":
            body = compact_piece(name, (PERKY / "noise_tone_envelope_native7.asm").read_text())
            if layout.get("source_sha256", {}).get("envelope1.bin") != "8136fff8a23fc148c79bbc3a55927ff23cadeff8623adeef2d91e7d15fd4d33b":
                body = body.replace("bra     pken_linear", "bra     pken_unused_shape1")
        elif name == "noise_tone_voice_xstate_glue.asm":
            body = (PERKY / "noise_tone_voice_native_xstate.asm").read_text()
        elif name == "noise_tone_envelope.asm":
            body = (PERKY / "noise_tone_envelope_native.asm").read_text()
        else:
            body = compact_piece(name, path.read_text())
        chunks.append(f"; ===== BEGIN {name} =====\n" + body
                      + f"\n; ===== END {name} =====\n")
    src = "\n".join(chunks)
    src = relativize_local_conditionals(src)
    src = force_long_local_jsr(src)

    # dsp_asm substitutes symbols by prefix. Reject ambiguous composed labels.
    labels = re.findall(r"(?m)^([A-Za-z0-9_]+):", src)
    for shorter in labels:
        for longer in labels:
            if shorter != longer and longer.startswith(shorter):
                die(f"assembler label prefix collision: {shorter} / {longer}")

    # No local absolute conditional jump may survive into a high-P image.
    leftovers = _LOCAL_JUMP_RE.findall(src)
    if leftovers:
        die(f"generated source still contains local absolute conditional jumps: {leftovers!r}")

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
    if not re.search(r"(?m)^\s*jsrl\s+pk_synth_apply_controls(?:\s|$)", src):
        die("source seam must jsrl-call the synthetic control mapper")

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
