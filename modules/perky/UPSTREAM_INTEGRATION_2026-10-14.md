# PERKY4S upstream integration — 14 October 2026

Local qualification is complete. The merged branch remains unpushed and has
not received a new Octatrack hardware test. The production MAIN OS is
byte-identical to the original hardware checkpoint; this is distinct from
physical validation of the merged source and the full stress matrix.

## History and scope

The original checkpoint `16a8de19a17ee4cba765cbdb30ca051f85af4e23` remains in
history. Its MAIN OS SHA256 is
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
The existing `main` fast-forwarded from `4c76bc13` to upstream `feb7af16` and
was pushed to `jrold/octabam`. The existing `perky-machines` merged that main
in `58acc806`, without rebasing. No branches, worktrees or checkouts were added.
Verification uses local tools and the user's read-only project.

Upstream added 612 reachable commits and changed 575 files relative to the old
main. PERKY already contained part of that history: 281 upstream commits were
new to it, and the merge changed 424 files. Complete commit and file inventories
are retained locally under `out/perky/upstream-integration`.

## Upstream changes

The complete inventories distinguish the old-main update from changes newly
merged into PERKY. The incoming work covers these areas:

- Build composition: bound module settings, DRAM descriptor clones and label
  formatters, dynamic MEMORY reservations, fixed arena claims, stock DSP
  buffer placement and stronger harvest/collision guards.
- Modules and remixes: BRAIN and STORE settings/templates, REMIX SWITCH and
  BOOT TRACE, LOAD METER, recorder threshold triggering, KITS and STEM REC
  changes, GATE VERB and LOFI2, and new core/inserts/bus selections. Upstream
  retires the repeat98 REPITCH modules and older diagnostic selections.
- DSP reliability: interruptible loops replace `rep`, shared-window literal
  substitution is checked, assembler operand round trips are stronger, and
  station/effect placement and controls gain regression coverage.
- Local tooling: port stepping, live-script waits, card/USB instrumentation,
  gate caching, reference-baseline storage and parallel verification runners.
  This integration uses direct local checks and one reference-matrix worker,
  avoiding the runners that create scratch worktrees.
- Documentation: the trap register moves to its own document, contributor and
  memory/firmware records change, and a generated MkDocs manual is added.

These upstream modules remain available in the repository; the PERKY4S
firmware selection still contains its existing four algorithms and twelve
retained stock effects. No new algorithm or unrelated module is selected for
that image.

## Conflict resolutions

| File | Resolution |
|---|---|
| `remixes/test/README.md` | Retain PERKY test-remix rows and upstream's relocated Octatrick row; regenerate the index. |
| `tools/build/build_bus.py` | Retain PERKY P-record remaps, extra harvest spans and its reserved loader geometry alongside upstream's bound settings, DRAM descriptors and dynamic sizing for other remixes. |
| `tools/remix/platform_build.py` | Retain separate PERKY preboot reservations and cached/uncached normalization; include upstream region sizing, fixed claims, early units and runtime patches. |
| `tools/remix/selftest.py` | Retain every PERKY harvest expectation alongside upstream's new remix expectations. |
| `tools/emu/ot_emu/machine.cpp` | Combine upstream's address-register progress detection with PERKY's bounded-scan tolerance; clear all associated observation buffers together. |
| `tools/emu/ot_emu/main.cpp` | Retain PERKY panel-queue observations and live-script steps alongside upstream's waits, time shifts and TX marks. |

The automatic merge also produced two incompatible `ArenaReserve` classes.
PERKY's page reservation is now `ArenaPages`; upstream's fixed-address
`ArenaReserve` remains intact. The PERKY manifest changes only that type name.
The 242-page preboot slice, following 1,707-page runtime reservation, DSP
placement, controls and firmware-generation path are retained. An audit finds
450 PERKY algorithm, control, builder and verifier source files unchanged from
the original checkpoint.

## Instrument repairs and prerequisites

The initial broad emulator CTest run exposed defects in the retained PERKY
timing patches. Branch costs increased the remaining budget instead of charging
elapsed cycles, and the BSR selector could not select its intended value.
`c2d99dad` fixes these instrument errors and retains the model's intended costs.
Its tests check cold branches, trained prediction, BTB collisions, total cycle
increments, 7,168 branch-condition cases and 7,104 shift cases. All nine CTest
tests pass. This changes no firmware algorithm. Earlier predictor-era ColdFire
timing figures are retracted in [the frame-cost record](CF_FRAME_COST.md).

The new manual's ignored pages were generated locally before its link gate.
The AU reference sweep also requires its generated-output directory. Failed
and interrupted attempts are retained separately; they are not qualification
results. All 24 build-reference configurations pass against a baseline saved
on updated main, using this single checkout and one worker.

## Validation and hardware status

The cold production rebuild is byte-identical to the original checkpoint.
All 50 qualification commands pass; the 49 targeted commands have zero skips.
The repository floor records 361 PASS markers, zero FAIL markers, and 88
module gate commands with zero failures. Its two skips are historical
`verify_perky_machine_boot.py` default-input and ColdFire-prototype odd-access
checks. The actual production image is explicitly boot-checked during the
four-machine build; its generated assembly passes the targeted odd-access gate.
No release gate was disabled.

| Local verification | Result and scope |
|---|---|
| `make check REMIX=perky-machine` with the real `OT_PROJECT` | Pass; two historical fixture skips as described above. |
| `REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check` | 24/24 configurations, artifacts and reports identical to the baseline saved on updated main. |
| Selected harvest, Y-base, cycle-ceiling, BRAIN-file, doclink and skip-spelling Python tests | 30/30 pass. |
| `ctest --test-dir out/emu --output-on-failure` after the prescribed rebuild | 9/9 pass, including repaired ColdFire timing, EMAC, RTOS, DSP and peripheral contracts. |
| Direct installed PerkyBits AU 0.2.0 comparisons | A and B each pass 27 four-second cases, 5,184,000 exact samples per core; dynamic events and output-clock comparisons also pass. Preserved old tune, modulation and sustain defects are detected. |
| Four-engine renderer and control gates | Both cores, all four algorithms, authentic PCM/state and control laws; 1,120 executed control/Part/dirty-LFO/ALGO-clamp cases. |
| Actual image, placement, startup, UI and prefetch guard | Pass; unsafe frozen PERKY4R placement is rejected by the negative guard test. |
| Actual placed-image source measurements | All four engines on A/B; PCM/state match the frozen reference. Tested paths peak at 19,887 modeled source cycles against the 23,040 ceiling; this is not a silicon timing measurement. |
| Individual algorithm port replays | Each of engines 0/3/2/5 completes 32,000 dirty frames on both cores; six excess voices remain silent. |
| Twelve retained effects on the production image | Eight FX configurations total, 2,600 dirty frames each, using Fold1 and Complex across all three modes. Every physical P shard, packed Y table and fourth-wave X asset survives FX init/proc. |
| Cold delayed activation | 36,000-frame dry T1 replay; first trigger delayed to step 16. |
| Legacy Fold1/Dark regression | Four 9,000-frame runs: T1 alone and T1/T5 at quanta 16/64/256; T1 PCM unchanged when adding T5. |
| Four-algorithm sequencer and p-lock regression | Five 36,000-frame runs: T1 alone, T5 alone, and T1/T5 at quanta 16/64/256. Every sequencer page and all four ALGO choices execute; ALGO/MODE and other SRC locks are exercised. At quantum 64, T1 post-chain PCM is bit-identical with/without T5, including locks and Dark. |
| Original project integrity | Before/after inventory unchanged; all fixture edits use generated copies. |

The retained effects are FILTER, SPATIALIZER, EQUALIZER, DJ EQ, PHASER, FLANGER,
CHORUS, COMB FILTER, DELAY, SPRING REV, DARK REV and LO-FI. PLATE REV and
COMPRESSOR remain unavailable. T1/T5 admission, Fold Drum 1/Fold Drum 2/Simple
Drum/Complex Drum, and TUNE/DECAY/ALGO/PAR1/PAR2/MODE remain unchanged.
The private P allocation is 770/774 words per core. Shared P is 2,398 code
words plus six uploaded NOP guard words: 2,404/2,404 physical words, zero free.

## Artifacts and reproducibility

The release procedure commits this qualification record, rebuilds the image
on that clean commit, checks equality with the qualified image/source manifest,
and independently decodes the card and MIDI wrappers. The release JSON records
that exact source commit, every command/log hash, inputs and component reports;
`verify_perky_four_provenance.py` checks it against Git and the working tree.
The newly generated files remain local, never committed or uploaded.

| Artifact | Local path | SHA256 |
|---|---|---|
| MAIN OS | `out/perky/upstream-integration/candidate/fragmented-mainos.bin` | `be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0` |
| Card ELUP | `out/OCTATRACK_PERKY4S.bin` | `bc9367ec56b2f310f733d0808a88e74e44da32b63f9483468af09760f7ac8fa9` |
| MIDI SysEx | `out/OCTATRACK_OS1.40C_PERKY4S.syx` | `922a7097062012f9a8738e6306f8a946bb4a7bc03ae37b2b4a8b9c1447d2bb1d` |
| ELEK container | `out/elek_PERKY4S.bin` | `f639d36154019dee21a1a7ac28d566b611d828abd4532b74d7a2a8e1bc4e7405` |

These are the original checkpoint's firmware bytes, generated from the merged
sources. There is no firmware-byte difference to document. The merge, build
compatibility adjustments and corrected emulator are source/tool differences.
The updater identifier remains PERKY4S, preserving the frozen image identity.

Local evidence under `out/perky/upstream-integration` includes complete
`upstream-commits.txt`, `upstream-files.txt`, `incoming-commits.txt` and
`integration-files.txt` inventories; `preserved-sources.json`; original and
updated-main reference baselines; failed-attempt diagnostics; unit/CTest logs;
`candidate/qualification-checkpoint.json`; and `candidate/PERKY4S_RELEASE.json`.
Original release images, receipts and prior AU captures are preserved under
`out/frozen/PERKY4S`; existing `out/frozen/PERKY4` and `PERKY4R` are retained.
Consumed generated card images and large replay scratch dumps are disposable;
cleanup is recorded separately, retaining source inputs, qualification logs,
component reports and firmware artifacts. All verification is local; GitHub CI
is not used.

Physical validation must exercise T1 and T5 separately and together, all four
algorithms and three modes, ALGO/MODE locks and their reversion, retriggers,
LFOs/scenes, retained effects (including Dark on both voices), cold activation
and several complete 64-step cycles. Shared-memory arbitration, speculative
fetch behavior and prolonged physical stability are outside the port's proof.
Do not push `perky-machines` until the user approves after reviewing the evidence
and any desired MKII audition.
