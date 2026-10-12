#!/usr/bin/env python3
"""Prove the composed renderers equal the qualified standalone ones.

The composed machine (``tools/perky/build_dsp_3algo_source.py``) emits the
shipping image for both payloads. This gate assembles the composition and the
standalone renderer programs side by side, disassembles both, and requires that
**every renderer entry point is instruction-identical** apart from the operands
that necessarily move when code relocates: the absolute target of a ``DO``,
``JSR``/``JSRL`` or branch.

It exists because the composed execution gate's host harness is not yet wired
correctly (see ``modules/perky/DSP_3ALGO.md``), and a bit-exactness claim
should not depend on a harness that is still being debugged. Every other
operand -- every accumulator, register, displacement, immediate and parallel
move -- must match word for word, so an accidental change to a shift, a guard,
a table base or a slot fails the build.

The standalone oracle for each algorithm is built from exactly the sources the
existing qualified gates use:

* Fold Drum 1   -- ``verify_perky_fold_drum_exec.py``'s composition;
* Resonant Bass -- ``resonant_dsp.source('bass', core_variables_fixed=True)``
  plus the shared decoder tail;
* Resonant Snare-- the same for ``snare``.

Standalone P sizes are also reported for the ledger.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky")]

import build_dsp_3algo_source as composed  # noqa:E402

OUT = ROOT / "out/perky/dsp-3algo"
FIX = ROOT / "out/perky/engine-fixtures"
ASM = composed.ASM
# `lua (rN+d)` takes d in -64..63; anything larger wraps silently, so operands
# are compared as written and never normalised through a displacement range.
OPERAND_ADDRESS = re.compile(r"(?<![A-Za-z0-9_])\$([0-9a-f]{4,6})(?![A-Za-z0-9_])")
MNEMONIC = re.compile(r"^\s*([a-z][a-z0-9]*)")


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-equivalence: " + message)


def routine_lines(binary: Path, org: int, address: int) -> list[str]:
    """Disassemble one routine, starting at its own address.

    The disassembler is handed a slice starting exactly at the routine, so the
    file's PC base is the routine's address -- passing the image origin instead
    silently disassembles from the wrong offset.
    """
    raw = binary.read_bytes()
    start = (address - org) * 3
    temp = OUT / "equiv-routine.bin"
    temp.write_bytes(raw[start:])
    result = subprocess.run(
        [str(composed.ASM.parent.parent / "disassemble/dsp56kDisassemble"),
         "-in", str(temp), "-pc", format(address, "x"), "-le"],
        capture_output=True, text=True, check=True)
    lines = []
    for line in result.stdout.splitlines():
        if ";" not in line:
            continue
        left = line.split(";")[0]
        if ":" not in left:
            continue
        text = left.split(":", 1)[1].strip()
        # Stop at the routine's own `rts`, which is where the body ends; the
        # next definition follows immediately in a composed image.
        if text:
            lines.append(text)
            if text.split()[0] == "rts":
                break
    return lines


def assemble(text: str, org: int, out: Path) -> tuple[Path, dict[str, int]]:
    out.parent.mkdir(parents=True, exist_ok=True)
    asm, binary, symbols = (out.with_suffix(ext) for ext in (".asm", ".bin", ".sym"))
    asm.write_text(text)
    result = subprocess.run(
        [str(ASM), "-in", str(asm), "-org", format(org, "x"),
         "-out", str(binary), "-sym", str(symbols)],
        capture_output=True, text=True)
    if result.returncode:
        die("dsp_asm failed:\n" + result.stdout[-4000:] + result.stderr[-2000:])
    labels = {p[0]: int(p[1], 16)
              for p in map(str.split, symbols.read_text().splitlines()) if len(p) == 2}
    return binary, labels


RELOCATED_TARGET = frozenset({
    "do", "jsr", "jsrl", "jmp", "bsr", "bra",
    "bcc", "bcs", "beq", "bge", "bgt", "bhs", "ble", "blo", "bls",
    "blt", "bmi", "bne", "bpl", "bvc", "bvs",
})


# A relocated CODE target is the last thing on the line. `DO` spells it as
# `do n7,$1b39` (the count and the target share one token) or as a trailing
# `>$1b39`; a branch/call spells it `$1b39` / `>$1b39` / `func_001b39`. Only
# that trailing address is erased -- an immediate that is data (a shift count,
# a table base, a coefficient, the `DO` loop count) is kept, because a change
# to one is a real behaviour change and must fail this gate.
def _is_target(token: str) -> bool:
    """True for a relocated code target.

    A disassembler prints a resolved address (`$1b39`, `func_001b39`); a source
    label (`pk3c_silence`, `pksdd_decoded`) names the same thing before linking.
    Both move when code relocates, so both are erased -- and ONLY they are.
    """
    body = token.lstrip(">")
    if body.startswith("$") or body.startswith("func_"):
        return True
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*|[0-9a-f]{2,6}", body))


def instruction_key(text: str) -> str:
    """The instruction with a relocated code target removed.

    Only the trailing CODE address of a `DO`/`JSR`/branch is erased. Every
    other operand -- an immediate, a register, a displacement, a parallel move
    -- is kept and compared, because a change to one is a real behaviour
    change.
    """
    tokens = re.sub(r"\s+", " ", text).strip().split()
    if not tokens:
        return ""
    mnemonic, rest = tokens[0], tokens[1:]
    if mnemonic.lower() not in RELOCATED_TARGET or not rest:
        return " ".join(tokens)
    # `DO count,target` keeps the count and drops only the address.
    if mnemonic.lower() == "do" and "," in rest[-1]:
        count, _, target = rest[-1].rpartition(",")
        if _is_target(target):
            return f"{mnemonic} {count}"
        return " ".join(tokens)
    if _is_target(rest[-1]):
        return " ".join([mnemonic] + rest[:-1])
    return " ".join(tokens)


def r5_offsets(text: str, advance: int) -> str:
    """Rewrite `x:(r5+/-$N)` to its offset FROM THE SCRATCH BLOCK BASE.

    The composition uses ONE scratch convention: every body carries centred
    displacements (`r5-$40`-style) and the CALLER advances r5 by 0x40 before
    entering it. The standalone recipes carry the uncentred form and no advance.
    The two name the same words -- so the gate compares the effective offset
    (advance + signed displacement), not the written displacement. Any real
    addressing difference still fails; only the bookkeeping convention folds.
    """
    def rewrite(match):
        sign = 1 if match.group(1) == "+" else -1
        offset = advance + sign * int(match.group(2), 16)
        return ("x:(r5+$%x)" % offset) if offset >= 0 else ("x:(r5-$%x)" % -offset)
    return re.sub(r"x:\(r5([+-])\$([0-9a-f]+)\)", rewrite, text)


def drop_scratch_prologue(body: list[str]) -> list[str]:
    """Remove an `r5 += 0x40` ABI prologue, in either spelling.

    The recipes carry it inside the body; this composition hoists it to the
    single caller. It is an ABI detail, not renderer content, so the gate
    compares what is left. The `move a1,r4` variables-pointer derivation is NOT
    a base advance and is deliberately kept.
    """
    out, index = [], 0
    while index < len(body):
        window = [" ".join(l.split()) for l in body[index:index + 3]]
        if window == ["move r5,a", "add #>$40,a", "move a1,r5"]:
            index += 3
            continue
        out.append(body[index])
        index += 1
    return out


def compare(name: str, composed_body: list[str], standalone_body: list[str],
            composed_advance: int = 0) -> None:
    composed_body = drop_scratch_prologue(composed_body)
    standalone_body = drop_scratch_prologue(standalone_body)
    if len(composed_body) != len(standalone_body):
        die(f"{name}: composed has {len(composed_body)} instructions, "
            f"standalone has {len(standalone_body)}")
    for index, (left, right) in enumerate(zip(composed_body, standalone_body)):
        # The composed side runs one scratch base advanced by 0x40; the
        # standalone side does not. Fold that convention away and compare the
        # EFFECTIVE addresses the two builds touch.
        left_key = instruction_key(r5_offsets(left, composed_advance))
        right_key = instruction_key(r5_offsets(right, 0))
        if left_key != right_key:
            die(f"{name}: instruction {index} differs\n"
                f"  composed   : {left}\n"
                f"  standalone : {right}\n"
                "Only a relocated DO/JSR/JSRL/branch target may differ.")


def fold_standalone() -> str:
    """The exact source `verify_perky_fold_drum_exec.py` assembles."""
    perky = ROOT / "modules/perky"
    parts = [(perky / "fold_drum_voice.asm").read_text()]
    for name, label in (("envelope", "pk_simple_envelope"),
                        ("frequency", "pk_simple_frequency"),
                        ("oscillator", "pk_simple_oscillator")):
        text = (perky / f"simple_drum_{name}.asm").read_text()
        text = text[text.index("\n" + label + ":"):]
        text = text.replace("#>$0009a5,r1", "#>$000c50,r1")
        text = text.replace("#>$0007a5,r1", "#>$000a50,r1")
        parts.append(text)
    parts.append((perky / "simple_drum_delta.asm").read_text())
    parts.append("\npknv_noise:"
                 + (perky / "noise_tone_voice_native_xstate.asm").read_text()
                 .split("\npknv_noise:", 1)[1])
    parts.append((perky / "noise_tone_math.asm").read_text())
    return composed.normalize("\n".join(parts))


def resonant_standalone(family: str) -> str:
    """One family plus its shared decoder tail, as the resonant gate builds it."""
    import resonant_dsp as recipe
    text, _ = recipe.source(family, core_variables_fixed=True,
                            interp_a=composed.Y_INTERP_A,
                            interp_b=composed.Y_INTERP_B)
    return composed.normalize(text)


def body_of(source: str, label: str, *, limit: int | None = None) -> list[str]:
    """Extract one routine's lines, stopping at the next top-level label."""
    lines = source.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == label + ":")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i]
        if stripped and not stripped[0].isspace() and stripped.endswith(":"):
            end = i
            break
    return lines[start + (limit or 0):end]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shipping = composed.normalize(composed.compose())
    # The seam's continuation address is build_bus's per-payload substitution.
    # This gate compares renderer bodies, so any legal absolute address serves;
    # the seam contract itself is exercised by the boot/seam gates.
    shipping_asm = shipping.replace("@CONT@", "$000426")
    composed_binary, composed_labels = assemble(shipping_asm, composed.DSP_ORG,
                                                OUT / "equiv-shipping")

    results = {}

    def check(label: str, standalone_source: str, standalone_org: int,
              standalone_out: Path, pairs: list[tuple[str, str]],
              shared: list[str], composed_advance: int = 0) -> dict:
        sys.path.insert(0, str(ROOT / "tools/perky"))
        binary, labels = assemble(standalone_source, standalone_org, standalone_out)
        for composed_label, standalone_label in pairs:
            if composed_label not in composed_labels:
                die(f"{composed_label} is not in the shipping composition")
            if standalone_label not in labels:
                die(f"{standalone_label} is not in the standalone build")
            compare(composed_label,
                    routine_lines(composed_binary, composed.DSP_ORG,
                                  composed_labels[composed_label]),
                    routine_lines(binary, standalone_org, labels[standalone_label]),
                    composed_advance)
        for label in shared:
            if label in composed_labels and label in labels:
                compare(label,
                        routine_lines(composed_binary, composed.DSP_ORG,
                                      composed_labels[label]),
                        routine_lines(binary, standalone_org, labels[label]),
                        composed_advance)
        return {"standalone_p_words": binary.stat().st_size // 3}

    # ---- Fold Drum 1 -----------------------------------------------------
    fold = check(
        "fold", fold_standalone(), 0x2800, OUT / "equiv-fold",
        [("pk_fold_voice", "pk_fold_voice"), ("pk_simple_base", "pk_simple_base"),
         ("pk_simple_delta_at", "pk_simple_delta_at"),
         ("pk_simple_envelope", "pk_simple_envelope"),
         ("pk_simple_frequency", "pk_simple_frequency"),
         ("pk_simple_oscillator", "pk_simple_oscillator")],
        [],
        # fold_standalone() assembles the raw uncentred bodies; the composition
        # centres them and hoists the r5 advance to its caller.
        composed.SCRATCH_ABI - composed.SCRATCH_BASE)
    results["fold"] = fold
    print(f"Fold Drum 1     : identical ({fold['standalone_p_words']} P words standalone)",
          flush=True)

    # ---- Resonant bass / snare ------------------------------------------
    for family in ("bass", "snare"):
        result = check(
            family, resonant_standalone(family), 0x2800, OUT / f"equiv-{family}",
            [(f"{composed.P}{family}_voice", f"pk_resonant_{family}_voice")],
            ["pk_resonant_decay", "pk_resonant_core", "pk_resonant_noise",
             "pk_noise_hat_envelope", "pk_rng_step", "pk_noise_step",
             "pk_u32_add", "pk_u32_sub", "pk_u32_asr", "pk_u32_mul_low"])
        results[family] = result
        print(f"Resonant {family:5s} : identical ({result['standalone_p_words']} P words standalone)",
              flush=True)

    shipping_words = composed_binary.stat().st_size // 3
    naive = sum(v["standalone_p_words"] for v in results.values())
    print()
    print(f"composed shipping source : {shipping_words} P words")
    print(f"naive standalone sum     : {naive} P words")
    print(f"deduplicated saving      : {naive - shipping_words} P words")
    print("perky-3algo-equivalence: PASS (every renderer instruction identical "
          "apart from relocated DO/JSR/branch targets)")

    import json
    (OUT / "equivalence.json").write_text(json.dumps(
        {"schema": "perky-3algo-equivalence-v1",
         "shipping_p_words": shipping_words,
         "naive_standalone_p_words": naive,
         "saving_p_words": naive - shipping_words,
         "engines": composed.ENGINE_LABELS, "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
