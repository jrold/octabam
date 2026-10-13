# The Fold Drum audio fault — root cause, measured

**Status: root cause identified on the shipped DSP code, and it is NOT in this branch's
composition path.** This is the record, so it is not re-derived.

## The finding

**The Fold renderer and the Fold state layout are unchanged between the physically working
PERKY4 machine and the wedging modern machine. What changed is WHO WRITES THE STATE.**

* **PERKY4** writes the record's prepared control pairs into the Fold voice words **every
  block** (`pks_tone_common`, composed `fold.asm:196-247`).
* **The modern 3ALGO machine writes only MODE (word 34) live.** TUNE, DECAY, ENV, MIX and FOLD
  exist only inside a frozen 40-word seed blob (`PK_RES_FRESH_FOLD`, `resonant_fresh.h:53-60`)
  copied to `X:$3800` when the engine+hit-count ledger changes.

**The producer exists on both sides; the single copy between them does not.**

| record word | field | PERKY4 | modern 3ALGO |
|---|---|---|---|
| `0x08/0x09` | **TUNE** | voice word **32** | **dead store** to `r6+$67` |
| `0x0a/0x0b` | **DECAY** | voice word **20** | **dead** `r5+$70` |
| `0x0c/0x0d` | **ENV** | word 31 → then FOLD word 36 | **dead** `r5+$71` |
| `0x0e/0x0f` | **MIX** | voice word **33** | **dead** `r5+$72` |
| `0x10` | **MODE** | word 34 | word 34 ✅ |
| `0x11` | p9 (amp gate) | word 14 | never read |

**MODE is the only control that works, because it has its own explicit write** (commit
`3677f266`, added after an earlier audit). The pair-copy block was **never ported** into
`build_dsp_3algo_source.py`: `git log -S 'r6+$20'` on that file returns nothing since its first
commit `f8386b08`.

## Why that is exactly "MODE-3 click, TUNE/DECAY dead"

`record word 0x10 → (p8+1)%3 → word 34` is the **only** live write, so MODE reaches the renderer
and changes the sound — panel 2 gives internal MODE 0, whose pulse branch produces the rising
8-sample ramp that is the click. TUNE's chain is

```
record 0x08/0x09 → [MISSING COPY] → voice word 32 → pk_simple_base → words 52/53 → pitch
```

and DECAY's is `record 0x0a/0x0b → [MISSING COPY] → word 20 → the AMP release step`. With no
live value ever written, the envelopes are whatever the frozen blob holds, so the voice is a
transient and nothing else, and the knobs are inert **even though the ColdFire side produces
their values correctly** — `pk_fold_prepare` is byte-identical between the two refs.

Model cross-check with the branch's own `fold_drum_compact.py`: MODE peaks 90 / 1954 / 1270 and
MODE 3 starts `[83,168,251,…]`, the ramp. With no re-seed all three reach 17558.

## Two hypotheses this refutes, both of which I had held

1. **"The 58 → 108-word slot enlargement breaks a byte-identical renderer."** Falsified. The
   Fold fields are at the **same indices on the same base `X:$3800`** in both machines, and
   **words 40..107 of the 108-word block are never read by Fold**.
2. **"The 40-word seed leaves the envelope/cache tail uninitialised."** Falsified. The 108-word
   clear and the 40-word copy **do** cover every word Fold reads. Coverage is fine; **content and
   cadence** are not.

## Ruled out by measurement

renderer and primitives byte-identical; composed renderer bit-exact against standalone; same
base and indices; both candidate defines present; n=40 and the blob really sent; the pitch cache
is not overlapped; PERKY4's extra `move #>$10,n7` is inert because no renderer body writes `n7`
in either machine and the stock continuation overwrites it from `X:$20c` anyway.

**Retracted:** `tools/verify/repro_perky_3algo_fold.py`'s "composed silent" is a **fixture
artifact** — it seeds the waves at `Y:$0a50` (PERKY4's address) while the composed code names
`Y:$07a5`. With the bank also at `Y:$7a5`, standalone == composed == the ARM fixture. That
diagnostic should be retired.

## What this means for THIS branch

**This branch does not use `build_dsp_3algo_source.py`.** It composes with
`build_fold_candidate.py`, and that path **does** copy the control pairs:

```asm
fold_drum2_seam.asm:27   move x:(r4+$8),a      ; record 0x08 = TUNE
fold_drum2_seam.asm:34   move a1,x:(r6+$20)    ; -> voice word 32   (TUNE)
fold_drum2_seam.asm:44   move a1,x:(r6+$14)    ; -> voice word 20   (DECAY)
simple_drum_seam.asm:13/20/28   the same three writes for Fold Drum 1
```

and `pk_fold2_apply_controls` writes words 20, 32 and 44 — which is why
`verify_perky_fold2_trigger_contract.py` lists `{14,20,31,32,33,42,44}` as control-owned.

**So the Fold audio fault is a property of the 3ALGO composition path, not of the light path,
and this branch is already the PERKY4-correct one.** The fix for the 3ALGO machine, if it is ever
wanted, is to port PERKY4's four pair assemblies into its `pk3e_entry` (≈16–24 P words, no UI
change) — but that machine's Resonant engines are being retired, so it is not on this path.

## Confidence, stated as the project requires

* **[M] measured** on the shipped DSP code by assembling `pk3e_entry` verbatim and dumping state
  across record permutations — the dead stores, the identical layouts, the missing copy.
* **[M]** the file contents above, with line numbers.
* **[I]** the model's absolute click level, which is the branch's own model rather than the unit.
  **A hardware A/B is the only closure for absolute levels**; the relative pattern is reproduced.
