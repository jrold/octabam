# PERKY3R repair candidate — local audit

PERKY3R is a three-engine hardware-test candidate derived from the completed
PERKY2F source. **The reported Fold1/T1 + T5 physical failure has not been
reproduced locally or physically qualified as fixed.** This document separates
confirmed defects, local evidence and the remaining hardware experiment.

No GitHub CI, hardware flash or checkpoint modification is part of this run.
The working branch is `codex/perky2f-repair` in its own worktree.

## Controls and engine identities

| Displayed ALGO | Native catalog id | Original engine |
|---|---:|---|
| 1 | 0 | Voice 1 / A1: Fold Drum 1 |
| 2 | 3 | Voice 2 / A1: Fold Drum 2 |
| 3 | 2 | Voice 1 / A3: Simple Drum |

The stock numeric formatter adds one: a displayed ALGO of 1 means internal
index 0. SRC is `TUNE / DECAY / ALGO / PAR1 / PAR2 / MODE`. Fold MODE 1/2/3
maps to original mode bytes 1/2/0: no transient, noise transient, pulse
transient. Simple MODE 1/2/3 maps to original mode bytes 1/0/2 and original
wave addresses `080222a0 / 080226a0 / 080228a0`.

Noise/Tone is absent from the shipping selection, dispatch, renderer, filters,
initializers and waveform bank. Its historical implementations remain available
for reference; the exact RNG needed by the Fold noise transient remains.
Complex and Wavetable are not added. Admission remains **T1 and T5 only**,
one synthesis voice on each core; payload B serves T1–T4, A serves T5–T8.

## Confirmed defects and repairs

* The old Fold2 shipping branch used the Simple common control/trigger seam.
  Its proper 51-word state, primary-oscillator swap, crossfade restoration,
  transient reset and original control update now have executable ARM/native
  comparisons. The initializer uses the original pre-trigger object.
* An interior Fold2 trigger needs the mandatory original update **after** its
  prefix render and primary swap. A stricter continuation oracle failed at
  block 33 before this repair. It leaves unchanged native controls alone
  between trigs rather than copying shipping updates into the oracle.
* Fold2 scratch `r5+0x64`, with `r5=0x3900`, collided with the pitch-cache tag
  at **X:0x3964**. An active Fold2 → Fold1 lock to low pitch falsely hit a
  stale pitch row. The frequency-high temporary now owns X:0x3976;
  X:0x3975 separately holds the original raw-pitch lookup. The regression
  compares every engine transition and every interior trigger offset.
* One tuple for an entire frame applied locked controls to the pre-trigger
  samples. The ColdFire producer now retains the pre-event tuple in unused
  source PCM words and publishes the locked tuple separately. Header fields
  and cursor allocation retain their stock ABI. The DSP renders the old
  controls/engine before the event and the new controls/engine afterward.
  The reserved byte of the prefix tuple is its validity marker; diagnostic
  records without it retain their existing interpretation.
* Fold1 initialization now preserves its original sample/hold reload of 2
  at compact word 38 (`+0x26`). The original pre-trigger state supplies it.
* The PerkyBits native runtime is **48 kHz**, whereas the OT runs **44.1 kHz**.
  Previously the source consumed one native sample per output sample. That
  lowers pitch by **146.707 cents** and lengthens envelopes. With the pinned
  lookup, TUNE 64 gives 119.400 Hz at 44.1 kHz versus 129.959 Hz at 48 kHz;
  old TUNE 66 gives 130.461 Hz, only 6.672 cents above the latter. This
  explains the approximate two-knob-step observation without a guessed tuning
  offset. The new FIFO follows the exact 160/147 rate ratio and the reference's
  trigger reset and linear interpolation. TUNE and renderer arithmetic are
  unchanged. Native state/RNG use the corresponding native sample count.
* Direct original wave/envelope words and an exact 16-bit-column implementation
  of the existing 64-bit LCG recover memory and execution time. The RNG has an
  independent integer oracle including carry and edge cases.
* The old double-tap browser detours and dedicated LEFT reference are removed.
  RIGHT on the virtual PERKY chooser row closes it instead of entering the
  obsolete browser or indexing past stock's five-machine table. Its dead C
  handlers/labels are excluded in the SRC-only profile.
* The legend is **SRC > PERKY**. Stock PMTR has two four-character buffers,
  so a descriptor rename alone truncated DECAY and overwrote its group label.
  The PERKY formatter/widget pair accommodates five characters. Executed
  drawing calls contain complete `DECAY` and `SRC`; non-PERKY tracks retain
  stock strings and widgets. Actual stock LFO arithmetic, then the packaged
  ColdFire renderer, proves A–F reach the intended controls and DSP records.

## Hardware-regression differential

The user reported a fresh Part/pattern, ALGO display 1 on both tracks, Dark
on T1, clicks/pops after adding T5 and one sequencer lock requiring reboot.
The separate MODE values are unknown; the replay covers all three.

The preserved working control is `PERKY2V_light_2voice.bin`, card SHA-256
`b12f1ade93e29f2aab6051057945f48b7d7db462348cf3a553242e1830c36b08`,
source `fc438e031a400d4ca326d4d6ff62328261a6dff6`.
The completed F checkpoint is `71b5c19149b2e02bbabbfbf9d2ffe250158a39aa`,
with release-source commit `0252129441269a443c096358d4322000496e3fb7`.
Its card hash is
`9d834161e25f3b7f58bf581461fab5b9aabf900d6d9d4353320679390c280fa6`.
Neither checkpoint worktree or original card/updater is modified.

Both frozen V and F completed the same 9,000-frame dirty-memory replay with
T1/Fold1/Dark and T5/Fold1, trigs and locks. **This negative emulator result
does not contradict the physical report.** A frozen-F fetch trace reached
14,837 base modeled cycles with 6,991 shared opcode fetches. Adding one wait
per such fetch gives 21,828; another contention wait gives 28,819. These are
diagnostic models, not measured silicon deadlines or upper bounds; extension
word fetches were not counted. Shared P arbitration remains a plausible
timing hypothesis, not an established cause.

The repair places envelope, oscillator, frequency, Fold2 trigger and FIFO
output kernels in private P. Core-owned shared render/control code has distinct
physical extents; common helpers are identical and cannot call core-specific
private P. The common RNG is reentrant but can still contend for shared P.
Both uploads contain the identical physical union, with overlap checks.
The preserved stock FX buffers and mailbox are excluded from that union.

The final ledger records 2,169 reachable program words per core, including
the protected startup clear, versus F's 3,099. Physical shared P uses 2,113
of 2,404 safe words, leaving 291. Each core also has 70 private P words free;
the reported usable free total is therefore 361, rather than incorrectly
counting the other core's copies as free space. Native tables occupy 2,093
low-Y words, with 46 trailing words free and 86 internal padding words
identified separately. Exact extents and all X claims are in `memory.json`.

The startup differential checks all Y words and **33 continuation register
fields** on each core; the registers match stock. Actual packed uploads and
program entrypoints are read back, not inferred from source alone. Stock
FLEX's retrigger-count read was audited: its retrigger loop is inside the
renderer PERKY replaces. No extra PERKY retriggers from the reordered E/F
slots were demonstrated. No general memory-corruption or overload diagnosis
is asserted for the Fold1/T5 physical failure.

## Qualification and provenance

The real fixture is the repository workflow's read-only project:
`/Users/jrold/Documents/EZBot templates/Hyper FX 1.0.6 Template by EZBOT/Hyper FX 1FF 1.0.6`.
Each replay modifies its own copy. Source hashes are recorded separately.

The complete repository run reports **349 PASS assertions, 0 FAIL, 2 actual
SKIP**, with **84 source gates and 4 image gates, 0 failed**. The footer's
explanatory mention of `[SKIP]` is not another skip. Missing artifacts belong
to the old machine-canary loader and old CF-only odd-access experiment; the
new image's loader and ColdFire path are checked explicitly. The build refhash
matrix reports **all 24 cases bit-identical**. Frozen F's generated control
assembly still hashes to
`7883dda373e17c3dc85318d8dbdabb00139df8e178c4c2997ac8417f8c99e4a1`.

Additional executable gates include:

| Gate | Scope |
|---|---|
| `verify_perky_three_controls.py` | 300 exact complete control records; Parts, families, locks, low LFO bytes, clamping |
| `verify_perky_three_rng.py` | 5,134 exact independent carry/edge/random LCG states and scratch ABI |
| `verify_perky_source_clock.py` | 11,760 segments, all 147 phases and lengths 1–16; rational PCM within one signed24 LSB; caller M7 deliberately non-linear |
| `verify_perky_three_audio.py`, A/B | 30 original ARM Fold2 trigger/update states, 2,304 Fold2 continuation blocks, 3,684 Fold1 cases per core at actual production addresses |
| `verify_perky_three_clock_audio.py`, A/B | 13,824 renderer/FIFO/state/RNG blocks plus 405 active-voice interior lock cases per core; every mode, gate and engine transition |
| `verify_perky_three_ui.py` | packaged CF label/widget, real LFO routing, 18 pre/post engine-lock producer cases, legend, selector-hook restoration |
| `verify_perky_three_memory.py` | all shards, physical aliases, native clock initialization, stock FX bytes and dispatch |
| final project/FX replays | exact commands, return codes, artifact hashes and logs in `out/perky/three/final-image-commands.json` |

The shipping source ceiling remains **23,040 modeled cycles**. Before the
cache repair the split Fold2 path reached 23,000; afterward the fixed-tuple
maximum is 21,398, and the engine/control transition corpus reaches 21,534.
Fold1 reaches 15,975; Simple reaches 12,559. Actual silicon P-memory waits,
cross-core phase and full real-time deadlines remain hardware measurements.

The isolated Fold2 generic renderer also passes 15 captured ARM blocks plus
400 randomized native blocks. Its arbitrary, sometimes unreachable states
are not the source-deadline corpus. The old automatic trigger-plan inference
rejected word 4: it lacked the pitch-table lookup operation. That failed
investigation is recorded; the shipping implementation uses the disassembled
mandatory update and verifies the entire 51-word state against original ARM
snapshots rather than omitting that field.

The native reference and original ARM qualification assets are the oracle.
Renderer comparisons hold raw-pitch/note state, velocity, controls, modes,
triggers, retriggers and RNG equal. GUI AU-host processing and a physical
Octatrack/AU comparison are **not automated qualification**. The FIFO uses
exact rational phase; AU floating-point details and its engine-switch declick
are separate from native renderer parity. The **−18.0618 dB** integration
trim is the exact signed16-to-signed24 alignment reduced from shift 8 to 5;
it does not feed back into renderer state or RNG.

All F-retained FX remain: Filter, Spatializer, Equalizer, DJ EQ, Phaser,
Flanger, Chorus, Comb Filter, Delay, Spring, Dark and Lo-Fi. Plate and
Compressor were already unavailable in F; no additional effect is sacrificed.

For a fresh reproducible qualification and package:

```sh
OT_PROJECT='/path/to/the/real/project' PERKY_EFT='/path/to/patched/elektron-firmware-tool' \
  .venv/bin/python3 tools/perky/build_three_machine.py
```

`--local-only` creates only the emulator MAIN OS fixture. A normal run does
not create a flash wrapper until all required local gates finish successfully.
Generated firmware, proprietary assets and slices remain outside Git.
The final artifact/commit/hash report accompanies the candidate in `out/`.

The final image qualification completed with **22 targeted commands passed,
0 failed, 0 skipped**: ten native/control/state/clock gates, memory and UI,
three 32,000-frame synth-port runs, the four-configuration FX gate, a
9,000-frame T1-only control, three 9,000-frame T1/T5 interleavings, packed
loader/boot verification and card/MIDI wrapper verification. The matched
quantum-64 replay has **bit-identical T1 post-chain PCM with and without T5**,
including Dark and parameter locks. The provenance verifier is an additional
gate; the accompanying JSON records its result separately. Qualification
logs retain the failed intermediate experiments and the corrected final runs.

The qualified MAIN OS SHA256 is
`3b45204e5aaabb899ee241ec4d7a785635aaebb77a77429a50989b8d86875d38`.
The release report pins the source commit, complete generated source manifest,
external stock/reference/tool inputs, final card/MIDI hashes and log hashes.
Rebuilding from that committed source must reproduce this exact MAIN OS before
packaging; physical qualification remains pending.

## Short hardware test before prolonged use

1. Keep the known-working V card/updater available. Start from a fresh Part
   and pattern; use only T1 and T5 for PERKY.
2. T1 alone: ALGO 1, MODE 1, TUNE 64, FX NONE. Run repeated trigs and locks
   on TUNE, DECAY, PAR1 and PAR2. Confirm stable clock and clean attacks.
3. Add T5 with ALGO 1/MODE 1 and its own trigs/locks. Check immediately for
   pops, frozen step LEDs, tempo/transport stalls or a stuck voice.
4. Add Dark on T1. Repeat the same simultaneous pattern before any long soak.
   Then test MODE 2 and 3 on each track, including rapid retriggers.
5. Lock ALGO between 1/2/3 and MODE between 1/2/3 at interior trig positions;
   release the locks. Check prefix continuity, engine identity and return to
   each track's base values. Test low TUNE after Fold2 or an ALGO switch.
6. Compare each engine to the AU with matching note/control/mode/velocity.
   Start dry. Recheck Fold1 near TUNE 64; check Fold2's swap/fade and Simple's
   three original waves. Verify SRC > PERKY, double-tap behavior and all six
   LFO labels/modulations; verify stock labels on another track.
7. Exercise Spring, Dark, Lo-Fi and the other retained FX. **Stop on the first
   pop or clock/transport fault**, record track/ALGO/MODE, locks, FX values,
   tempo and time-to-failure, and roll back to V before prolonged use.

If the Fold1/T5 failure remains, the next experiment is the same short pattern
on V, frozen F and this candidate, followed by a DSP busy/host-port timing
capture on the failing configuration. Relevant integration sources are
`perky_emit_shards.py`, `perky_fragmented_image.py`, `perky_three_placement.py`,
`three_segment_source.py` and the two control translation units. The executable
local reproducer is `verify_perky_two_core_regression.py`; its clean result
alone cannot close the physical timing question.
