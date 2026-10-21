# Noise Hat lifecycle qualification — PKNHE1

The later [PKNHF7 handoff experiment](NOISE_HAT_HANDOFF.md) implements a
nonblocking ownership protocol. This page preserves the unchanged PKNHE1
rejection and the limits of its earlier instruments.

**Live backend switching fails qualification.** The target records six
transport failures across three DSP→CF→DSP round trips, one in each Noise Hat
mode. Timing and active audio alone would have accepted this run: its peak is
354.000 µs with zero deadline misses and all eight tracks active.

STOP/START, Part 1→3→1, live Bank A→B→A and all six directed Noise Hat mode
changes pass their bounded model scopes. The three fresh fixed-mode
WT/WT + Slap + Hat workload rows also reproduce the previous exactness and
timing results. This is a qualification record, not a firmware fix or release.

Machine-readable evidence: [NOISE_HAT_LIFECYCLE.json](NOISE_HAT_LIFECYCLE.json).
The target remains **PKNHE1, build 19**, byte-identical to the
[control-settling experiment](NOISE_HAT_CONTROLS.md):

- MAIN SHA256: `68d5adda3fc03972b2c0b67e98cef7a0aa78e3933a51228c1b3a0d0d1e376546`
- CF ELF SHA256: `19f4dcfcb62b7e05b38d2edca25dc44797e1b2587b070cf83794e13fff298641`
- No target instructions, DSP uploads, source latency or memory claims change.
- Work stays in the existing `perky-cf-dsp-hybrid` checkout; no release wrapper,
  commit, push, CI run or flash is produced.

## Measured lifecycle scopes

All runs use CF 264 MHz, PIT 132 MHz, the uniform startup/pre-roll/transport
cycle clock and dirty DSP seed 123. The modeled deadline remains
16/44,100 seconds = **362.811791 µs**. DSP scheduling remains the established
4,532-instruction-per-sample model, not a silicon cycle proof.

| Campaign | Observed behavior | Peak ISR | Misses | Result |
| --- | --- | ---: | ---: | --- |
| Actual panel | Three STOP/START cycles; Part 1→3→1; playing Bank A→B→A | 327.943 µs | 0 | Pass, continuous probe state |
| Diagnostic MODE | All six directed mode pairs, with warm limbs and active locks | 325.197 µs | 0 | Pass, transport audio/state contract |
| Diagnostic backend | DSP→CF→DSP in white, metallic and pulse modes | 354.000 µs | 0 | **Fail: six target transport errors** |
| CF calibration | CF selected from boot; all three modes | 345.769 µs | 0 | Pass, stateless native arithmetic only |

The panel campaign checks **49,565 DSP source frames** and **49,566 CF control
calls**, with zero source PCM, resident state, native clock, feedback,
committed-ring or control-update mismatches. It observes 49,567 ISR entries
and 49,566 returns; one ISR is in flight when the interactive run quits.
The timing maximum covers completed ISRs. DMA overlaps/restarts, guard writes,
stack extent and private-stack ownership violations are all zero. All eight
source/post-FX paths are active over the capture.

The separate mode campaign checks **5,220 source frames** and **5,222 control
calls**, again with zero mismatches or safety failures. MODE is the probe's
diagnostic selector; control values still arrive through the real sequencer,
locks, LFOs and scenes. These are not product ALGO/MODE persistence tests.

Bank readiness is checked before selection. The first short 4.8-second Bank
window expired before the queued change; that was an inconclusive test, not
evidence of a Bank failure. With a 13-second bound, the actual playing/working
bank bytes and bank pointer confirm A→B→A. Part changes use the real chooser
and verify the selected target Part. Only Parts 1 and 3 are covered.

**The probe keeps global diagnostic selectors and resident histories across
Part/Bank loads.** Thus the positive result proves navigation and exact
continuing probe audio. It does not certify saved ALGO/MODE delivery, fresh
generation resets, deselection/reselection, or every Part/Bank/mode combination.

## Backend rejection and oracle limits

The target's `pk_nhr_failures` counter progresses **0→2→4→6** after the three
returns to DSP. The final request/consumption counts are **7,105 / 7,096**;
normal steady operation leaves three outstanding, while this run leaves nine.
The largest pending classic-ring count rises from 52 to **122**, still below
the 573-tap guard. That guard does not establish a valid ownership transfer.

Code inspection explains why a live toggle is unsupported: the CF branch of
`pk_nhr_frame` immediately renders from the CF object, while dynamic histories
and the active native clock have lived on A. It does not drain pending jobs,
import resident state, or reconcile the two clocks/cursors. On return to DSP,
it resumes the resident path without importing CF evolution. The disabled DMA
path also skips its normal mailbox extraction/padding clearing. These are
observed implementation omissions; this campaign does not assign every
counter increment to an individually isolated cause.

The DSP continuity oracle **stops at the first live backend departure**. Its
5,221 source comparisons before that boundary have zero mismatches; no exact
continuous stream after departure is claimed. All 7,846 control calls still
match the original control routine.

CF arithmetic is checked separately by copying the complete target object,
RNG and hold state immediately before each native render, running the original
renderer at the requested count, and comparing its returned PCM. The cold-CF
calibration passes **9,073 calls / 81,996 samples**; the backend run passes
**1,481 calls / 12,897 samples**. This stateless proof accepts whatever state
the caller supplies and **cannot certify migration or clock continuity**.

An attempted stateful CF extension of the transport oracle failed its own
cold-CF calibration and was withdrawn. Its PCM mismatch counts are not firmware
evidence. The initial host/ColdFire structure-alignment error is also guarded
and recorded in [TRAPS](../../../docs/contributing/TRAPS.md#trap-cf-host-abi).

To falsify the backend rejection, a new image must pass the same live
transitions with zero transport errors **and** an independent continuous
original-engine PCM/state/RNG/ring/clock proof across each ownership boundary.
Ignoring repeated mail or resetting a voice does not supply that proof.
A nonblocking ownership protocol needs pending-job drain/epoch handling and a
coherent state/clock transfer before the new owner renders.

## Fresh complete-workload rerun

Each row runs 4,096 transport frames with WT/WT, Slap, the four stock STATIC
tracks, all eight active source/post-FX paths, twelve retained FX in sixteen
slots, locks/LFOs/scenes and 568 card reads after PLAY.

| Hat mode | Peak ISR | Mean ISR | Deadline misses |
| --- | ---: | ---: | ---: |
| White | 324.841 µs | 232.409 µs | 0 |
| Metallic | 327.299 µs | 234.849 µs | 0 |
| Pulse stack | 316.902 µs | 222.413 µs | 0 |

The three rows check **12,319 current source frames**, **214,651 native
samples** and **12,325 control calls**, with zero control/source/state/clock/
feedback/ring mismatches. Loaded private/shared P matches the candidate
uploads except the known stock bank-mask writes; all twelve retained FX
code/dispatch regions remain exact. Stack, ownership and DMA gates pass.
These reproduce the earlier optimized rows exactly, including modeled cycle
maxima. Stock audio checks establish activity and retained program identity;
they are not a bit-identity comparison of every stock output through UI edits.

## Evidence and reproduction

New local tools:

- `build_perky_noise_hat_lifecycle_observer.py`: isolated host observer and
  original native/control references; no target modification.
- `qualify_perky_noise_hat_lifecycle.py`: actual panel actions and diagnostic
  selectors, immutable per-case instrument/source archives, bounded Bank waits,
  child-exit wait before reading final reports, and generated-card cleanup.
- `verify_perky_noise_hat_lifecycle_ids.py`: 628 checks of the actual compiled
  observer ID-extension helper across two 16-bit wire wraps. The live panel run
  stays below the first wrap; long target wrap behavior remains unqualified.
- `rerun_perky_noise_hat_lifecycle_workload.py --frames 4096`: the unchanged
  fixed-mode workload driver in a separate result directory.
- `verify_perky_noise_hat_lifecycle_campaign.py`: input/output/receipt binding,
  including the archived earlier observer used for CF calibration/backend and
  the later observer with wire-ID extension used for panel/modes.

Run those tools in the order listed, with the campaign binder last. The
workload rerun also has the exact emulator commands in its row receipts.
The observed files live under `out/perky/hybrid/noise-hat-lifecycle/`;
reproducible cards, block captures and project copies are removed after use.
Author fixtures, stock input and useful proof artifacts are preserved.

`make check REMIX=perky-machine` passes **84 shared + 4 image gates**;
project-specific floor gates skip without `OT_PROJECT`. The dedicated runs
above supply this experiment's project evidence. The previous nine-row/profile
campaign binder still passes. `REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh
check` also passes all **24 cases bit-identically** against the existing local
baseline; that baseline is not re-saved. No shared build code changes here.
The default bus artifact is restored to SHA256
`354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58`.

Physical timing, private-B tail behavior, complete voice-family placement,
production Part/generation semantics and live backend migration remain open.
