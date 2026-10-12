#!/usr/bin/env python3
"""The PK_LADDER bisection rungs are what they claim, and rung 5 is the shipping source.

WHY THIS EXISTS. On the unit the Perky machine wedges immediately, and a wedged
machine cannot report anything -- CF METER's ColdFire-side slots freeze with the CPU
and its DSP-side slots stop when the audio does. So the fault has to be found from
the side that RUNS: a ladder of configurations, each one the same panel-selectable
module with less DSP functionality than the last, flashed from the top down.

    rung 1  the seam only -- the hook is present and NEVER ADMITS
    rung 2  + admission, record read, state load, silence (no per-sample work)
    rung 3  + the Fold renderer
    rung 4  + Bass
    rung 5  + Snare -- the shipping machine

THE FIRST RUNG THAT WEDGES NAMES THE CULPRIT. That only works if each rung really
is what its label says, which is what this gate checks -- by REGENERATING every rung
and reading the instructions, not by trusting the module that emitted them. A rung
that silently stopped disabling its renderer would make the bisection lie in the
most expensive possible way: it would move the boundary and point at the wrong
subsystem.

WHAT IT CANNOT SEE. Whether any rung wedges. That is the measurement the ladder
exists to make, and it needs the unit.

Two traps this gate also encodes, both of which cost an hour when the ladder was
built:
  * PK_LADDER must be set when REGENERATING the manifest, not when building -- the
    build reads modules/perky/machine_3algo.asm from disk, and compose() only reaches
    it through emit_3algo_manifest.py;
  * out/cache/ does not key on the environment, so a rung built without
    OCTABAM_NO_CACHE=1 comes back as the previous rung's image.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMIT = ROOT / "tools/perky/emit_3algo_manifest.py"
DSP = ROOT / "modules/perky/machine_3algo.asm"

# what each rung must and must not contain, as exact instruction text
NEVER_ADMIT = "        bra     pk3v_not_admitted   ; PK_LADDER=1: never admit"
SILENCE_BEFORE = "        bra     pk3c_silence        ; PK_LADDER=2: no renderer"
SILENCE_3 = "        bra     pk3c_silence        ; PK_LADDER=3"
SILENCE_4 = "        bra     pk3c_silence        ; PK_LADDER=4: no Snare"
FOLD = "        beq     pk3e_entry"
BASS = "        beq     pk3n_entry"
SNARE = "        beq     pk3a_entry"


def generate(rung: int) -> str:
    """Regenerate the shipping DSP source at `rung` in a scratch copy.

    The real file is restored afterwards, so this gate never leaves the tree on a
    rung -- which matters, because a tree left on rung 1 builds a machine that
    never makes a sound and looks like a fresh hardware bug.
    """
    original = DSP.read_text()
    try:
        env = {"PK_LADDER": str(rung)}
        import os
        full = dict(os.environ)
        full.update(env)
        r = subprocess.run([sys.executable, str(EMIT)], cwd=ROOT,
                           capture_output=True, text=True, env=full)
        if r.returncode:
            raise SystemExit(f"verify-perky-3algo-ladder: rung {rung} did not "
                             f"generate:\n{(r.stderr or r.stdout)[-1500:]}")
        return DSP.read_text()
    finally:
        DSP.write_text(original)


def main() -> None:
    if not EMIT.is_file():
        raise SystemExit("verify-perky-3algo-ladder: missing the 3ALGO emitter")
    src = {r: generate(r) for r in (1, 2, 3, 4, 5)}

    # ---- rung 1: the seam only. The hook must never admit.
    if src[1].count(NEVER_ADMIT) != 1:
        raise SystemExit(
            "verify-perky-3algo-ladder: rung 1 does not force the not-admitted path "
            f"({src[1].count(NEVER_ADMIT)} of the forcing branch, expected 1). The "
            "seam rung would then run the machine and the bisection would start one "
            "subsystem too deep.")
    if FOLD in src[1] and SILENCE_BEFORE not in src[1]:
        pass  # the dispatch is untouched on rung 1 and unreachable; that is fine

    # ---- rung 2: every renderer silenced, before the first compare.
    i_jump = src[2].find(SILENCE_BEFORE)
    i_cmp = src[2].find("        cmp     #>$0,a")
    if i_jump < 0 or i_cmp < 0 or i_jump > i_cmp:
        raise SystemExit(
            "verify-perky-3algo-ladder: rung 2 does not silence the renderers "
            "BEFORE the engine compares, so a renderer is still reachable and the "
            "rung would measure the renderer rather than the admission.")

    # ---- rung 3: Fold only.
    if SILENCE_3 not in src[3] or BASS in src[3] or SNARE in src[3]:
        raise SystemExit(
            "verify-perky-3algo-ladder: rung 3 is not Fold-only -- the Bass and/or "
            "Snare entries are still reachable.")
    if FOLD not in src[3]:
        raise SystemExit("verify-perky-3algo-ladder: rung 3 has lost the Fold entry.")

    # ---- rung 4: Fold + Bass.
    if SILENCE_4 not in src[4] or SNARE in src[4] or FOLD not in src[4] or BASS not in src[4]:
        raise SystemExit(
            "verify-perky-3algo-ladder: rung 4 is not Fold+Bass -- the Snare entry "
            "is reachable, or a kept renderer has been dropped.")

    # ---- rung 5: the shipping machine, untouched.
    if NEVER_ADMIT in src[5] or SILENCE_BEFORE in src[5] or SILENCE_3 in src[5] \
            or SILENCE_4 in src[5]:
        raise SystemExit(
            "verify-perky-3algo-ladder: rung 5 carries a ladder substitution, so the "
            "shipping source is NOT the default -- the whole ladder is offset.")
    for lbl, ins in (("Fold", FOLD), ("Bass", BASS), ("Snare", SNARE)):
        if ins not in src[5]:
            raise SystemExit(f"verify-perky-3algo-ladder: rung 5 has lost the {lbl} "
                             "engine entry; it is not the shipping machine.")

    # ---- and the five must be distinguishable, or the bisection cannot bisect.
    seen = {}
    for r, text in src.items():
        for other, prev in seen.items():
            if text == prev:
                raise SystemExit(
                    f"verify-perky-3algo-ladder: rungs {other} and {r} generate the "
                    "IDENTICAL source, so the ladder has a step that measures "
                    "nothing. (This is exactly what out/cache/ and setting PK_LADDER "
                    "on `make bus` instead of on the emitter both produced.)")
        seen[r] = text

    print("perky-3algo-ladder: PASS (five rungs, each regenerated and read back: "
          "rung 1 never admits, rung 2 silences every renderer before the compares, "
          "rung 3 is Fold-only, rung 4 is Fold+Bass, rung 5 is the shipping machine "
          "with all three entries; all five sources distinct. Whether a rung WEDGES "
          "is the measurement the ladder exists to make and is not something this "
          "gate can see -- that needs the unit.)")


if __name__ == "__main__":
    main()
