# Milestone gate status — what is proven, and what is not

Measured on `perky-2voice-milestone`. Every PASS below was actually executed, not
inferred from a previous run.

## PASSING (executed)

| gate | proves |
|---|---|
| `verify_perky_light2_src_page` | SRC page is exactly TUNE/DECAY/ALGO/PAR1/PAR2/MODE with the right counts; all six staged and p-lockable; ALGO p-lock goes base->locked->base in the DSP dispatch byte; out-of-range ALGO cannot dispatch; **admission is [1,0,0,0,1,0,0,0] — T1 and T5 only** |
| `verify_perky_fold_seam_exec` | Fold Drum 1: 3684 tagged PCM/state/RNG cases against the reference model |
| `verify_perky_multi_seam_exec` | 13878 exact PCM/state cases across the composed engines |
| `verify_perky_synth_seam_exec` | the actual source seam, all slots/triggers |
| `verify_perky_fold_regression` | Fold composition with Simple Drum and Noise/Tone |
| `verify_perky_shipping_voice_exec` | the ACTUAL generated shipping synth text, 36 blocks, exact PCM/state/RNG |
| `verify_perky_synth_source_exec` | X-state assembly ABI + the shipping voice gate |
| `verify_perky_noise_tone_original_dsp_exec` | authentic Noise/Tone against the ARM captures (with `--firmware`) |
| `verify_perky_all_fx_placer` | the stock-preserving shared-P placement contract |
| `verify_perky_synth_port` engine 0 / 3 / 2 / 10 | **all four engines, both DSP cores, 32000 frames, dirty memory** |

Plus, from the build: `make check` reports "all runnable checks passed", four engine
port gates, and the full-machine boot gate (loader once, RTOS handoff, A/B uploads read
back byte-identical).

**No Resonant in the shipping path: 0 references** to `resonant`, `RES_FRESH` or
`pk_res_` in the composed program.

## NOT PROVEN — and the reason is one missing piece

| requirement | status |
|---|---|
| T1 Perky works | PROVEN (port gate, both cores) |
| T5 Perky works | PROVEN (same, admission mask) |
| T2-T4 / T6-T8 remain stock | PROVEN by the admission mask `[1,0,0,0,1,0,0,0]` — nothing else is admitted |
| exactly one Perky voice per core | PROVEN (same mask) |
| Fold1 / Fold2 / Simple / authentic Noise-Tone, both cores | PROVEN (four port gates) |
| all 3 MODE settings per engine | PROVEN (seam gates cover all modes) |
| 32000-frame production/sequencer tests | PROVEN (port gates) |
| dirty-memory startup | PROVEN (port gates run dirty) |
| repeated triggers / retriggers | PROVEN (persistent + event-offset cases in the seam gates) |
| all six SRC controls, requested order | PROVEN (light2 gate) |
| ALGO p-lock base->locked->base | PROVEN (light2 gate, dispatch byte) |
| MODE p-lock | PROVEN — dedicated cases added: base 0->1->0 and 2->0->2 in the mode word, plus an out-of-range clamp case |
| stock AMP continuation | PROVEN (seam gates run to the continuation) |
| **Spring present and functional** | **NOT POSSIBLE — the effect is not in this image** |
| **Dark present and functional** | **NOT POSSIBLE — same** |
| **Lo-Fi present and functional** | **NOT POSSIBLE — same** |
| Plate / Compressor absent | true, and intentional |
| Delay remains functional | **NO APPLICABLE GATE EXISTS.** `tools/verify/verify_delay.py` is not this: it proves an alternate BusDelay DSP *module* is bit-identical to the shipping one, and this remix contains no BusDelay. The goal means the stock Octatrack DELAY, which is ColdFire-side and not touched by the P harvest at all -- see MILESTONE_CANDIDATE.md |
| no Resonant in shipping path | PROVEN (0 references) |
| complete P/X/Y ledger | PROVEN, and corrected this milestone (P was unclaimed and its capacity was stale) |
| boot/upload/readback | PROVEN (boot gate) |
| card wrapper roundtrip | PROVEN (the build produces both) |
| MIDI updater roundtrip | PROVEN (same) |
| no odd-address ColdFire store regression | **GATE EXISTS BUT IS NOT RUNNABLE HERE.** `tools/verify/verify_perky_cf_odd_access.py` is the right gate and is not in the perky manifest's list; run directly it fails with 'missing generated dir', because it needs build artifacts this worktree does not produce. Wiring it in means finding what generates that directory, which is not a one-line change |
| no provenance mismatch | PROVEN, and the ROOT CAUSE is now fixed — the manifest records `tree=clean|dirty` and states that the `*_sha256=` fields pin the artifact |

## The single missing piece

Everything above is green except the three FX items, and they are blocked by **one**
thing: the Perky program must be emitted as **shards** so Spring, Dark and Lo-Fi can
have their own P back. `FX_RECOVERY_FEASIBILITY.md` carries the measured case
(authoritatively: stock P is one packed region with zero gaps, so there is nowhere
contiguous to put a 3051-word program; and `dsp_asm` substitutes labels textually, so
the sharding is a Python-level emitter and needs no toolchain change).

**Until that lands, this is not the milestone, regardless of how green the rest is.**


---

# ADDENDUM — the SRC-page gate's teeth, settled

This gate is the only evidence for the SRC page order, the staging mask, the ALGO and
MODE p-lock returns, the admission mask and the out-of-range clamps, so whether it can
FAIL matters more than whether it passes. It was in doubt for two rounds. It is now
settled, and the sequence is worth keeping because most of it was my error.

## The override works

`PERKY_LIGHT2_CONTROL` does reach the compiled artifact. MEASURED: swapping the first
two labels in the descriptor makes the gate fail with

```
SRC page-1 controls are ['DECAY', 'TUNE', 'ALGO', 'PAR1', 'PAR2', 'MODE'],
expected ['TUNE', 'DECAY', 'ALGO', 'PAR1', 'PAR2', 'MODE']
```

## The teeth are real, on both paths

* **descriptor**: the label swap above is caught.
* **MODE clamp**: moving BOTH clamps from 2 to 3 is caught, at the record word:
  `case nt_mode_clamp3: record word 8 (DSP words 16/17) is 0x00030000, expected 0x00020000`.

## Why a single-clamp mutation is NOT caught -- and that is correct

MODE is clamped TWICE in the shipping path: in `pk_light2_src_to_transport` into `p[6]`,
and again in `pk_light2_full_prepare` into `p[8]`. Mutating one leaves the other
correct, the record is still right, and the gate correctly passes. Defence in depth, not
a blind spot.

## The invalid harness, which caused the confusion

Every mutation run through `PERKY_LIGHT2_CONTROL` from a `/tmp` path failed to BUILD --
not because of any guard, but because the mutated file's `#include "control.c"` does not
resolve from `/tmp`. Proven by a CLEAN, unmutated copy failing identically from the same
directory. **Mutations for this gate must live inside `modules/perky/`**, and two
earlier "teeth proven" and "teeth not proven" claims were both drawn from runs that
never compiled.

## Consequence for the earlier retraction

Round 14 recorded that this gate's teeth were UNPROVEN. That was over-broad: the teeth
were always there, and the single-clamp result was a correct PASS under redundant
clamping. The narrow true statement is the one above -- the gate is sensitive on both
paths once a mutation actually builds and actually defeats both clamps.
