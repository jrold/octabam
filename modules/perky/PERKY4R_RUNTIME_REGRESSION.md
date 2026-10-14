# PERKY4R physical lock: guarded placement passes reported hardware cases

The MKII user reports PERKY4R locking with T1 and T5 assigned to PERKY,
including non-Complex algorithms and blank projects. The subsequent report
confirms **PERKY4R, T1 alone, no FX: empty playback works; the first manual
sound trigger or sequencer trig instantly locks**. A second PERKY voice and
stock FX are not required. A subsequent **P4RNDISP** manual trigger also stalls
the sequencer; the user confirms its screen and encoders still respond.
**P4ROLDDSP subsequently plays sound and runs the sequencer without lockups.** This
supersedes any assumption that the failure is isolated to Complex controls.
**P4RPG6 now passes reported MKII testing: T1 and T5, all algorithms,
Dark Reverb used on both; audio plays and the sequencer does not stall.**
The emulator still does not reproduce the original failure.

Frozen comparison points are PERKY4 `11f0165f702ddac17bd61a5b19cdbe43cca740f9`
and PERKY4R `afedc8925b616cbc9aa7786208f9aa4a14e7ae5d`. Their MAIN OS hashes are
`b412c1a1cfc8f738fcccddb78b1f85f028d7d27aff8eafbc7d05e701940710f2` and
`6499de13d66ab4099ad87521e93e3f362c4fa80259deb95b6e86190f20ecd495`.
Neither original worktree nor rollback artifact was modified. This investigation
changes qualification tools and builds diagnostic images from frozen inputs;
it does not change the shipping AU control repairs.

## Actual global differences

Only three DSP source shards changed: `simple_drum_frequency.asm` gains an
11-word private Complex updater; `pk_three_segment` gains an eight-word dispatch
block per core; `pk_three_common_controls` grows three shared words for the
Complex sustain gate and masks both MODE decoders to two bits. The dispatch
block executes on **every** accepted engine before the base-pitch converter.
Disassembly of the actual words is `move X:39bf,A; cmp #5,A; bne +4; jsr updater`.
Its actual P locations are A `0x33e7f..0x33e86`, B `0x3fddb..0x3fde2`.

The exhaustive packer changed placement throughout the shared program:

| Executed shard | PERKY4 | PERKY4R |
|---|---|---|
| Common control decoder | `0x3fda3` (bank 7) | `0x33ede` (bank 1) |
| Common pitch converter | `0x33da3` (bank 1) | unchanged |
| T1 segment | `0x3bf66` (bank 5) | `0x3fda3` (bank 7) |
| T1 frame | `0x3ff8e` | `0x3ffc5` |
| Common Simple initialization | `0x3ffc8` | `0x37fcd` |
| RNG helper | `0x37fcd` | `0x3bfd0` |

The common noise arithmetic helper also moved from bank 1 to bank 7, but fetch
traces show **zero calls to it** in the measured Fold1/Simple/Complex source
scenarios. Its move is not demonstrated as a direct cause. An initial
math-bank placement experiment was consequently excluded from hardware delivery.

The new updater preserves R4/R6 and runs before the existing base converter
changes R4. It clobbers arithmetic registers already consumed/redefined by the
following base converter. It is never called in the strict Fold1/Simple runs.
Measured returns leave SP balanced on both cores. Actual producer packets and
complete post-chain audio are identical between PERKY4 and R for those engines.
This rules out a demonstrated control/ABI/audio discrepancy in these replays;
it does not prove every physical register/pipeline behavior.

Private P use rose from 759 to 770 words per core (free 15 to 4); shared P from
2379 to 2398 (free 25 to 6). All extents remain within the existing donors and
exclude the mailbox. The startup-clear origins, protected extents, X/Y assets,
two-voice admission and twelve retained stock effects remain unchanged. The
ColdFire runtime grew 80 bytes, 17124 to 17204. Its Fold/Simple output records
are bit-identical in complete actual-image replays. Boot gates execute the
packed loaders and read back both extended uploads and runtime bytes.

## What the emulator cannot establish

The original project replay p-locked **all four** algorithms even when its base
ALGO was Fold1 or Simple. It did not establish a never-Complex scenario. The
new `--fixed-algorithm` mode fixes every ALGO p-lock and checks **all delivered
records**, not just triggers. `--stock-only` checks absence of every signed
PERKY record; `--dry` enables a no-FX control; original default coverage remains.

The port schedules DSP **instructions** at 4532/sample; it does not schedule
individual opcode/extension fetches through the DSP56721 shared-memory banks.
The source meter prices opcodes, but does not model simultaneous bank accesses.
`docs/firmware/CHIP.md` section 3 records one P wait and contention per 8K bank.
Scheduling quanta 16 and 256 exercise ordering, not silicon bank arbitration.
The 23040 source ceiling also does not constitute a measured complete hardware
AMP/FX execution deadline. No ceiling was raised. Local equality can therefore
coexist with the reported physical lock. Bank placement and deadline behavior
remain hypotheses, not proven explanations.

### Updated first-trigger discrimination

The single-voice, no-FX first-trigger report weakens the hypothesis that two
active PERKY renderers must contend. It does not establish a control-law defect.
The entry is gated by a signed PK/Y1 source record: assigning the machine or
running empty playback need not enter synthesis at all. The ColdFire producer
publishes that record when its renderer is called for a complete source frame.
The source entry then resolves the voice, initializes its engine, prepares
controls and base pitch, applies the trigger, renders, adapts the clock and
continues into stock AMP. Thus the observation narrows the failure to activation
of this path, but does not yet distinguish initialization from first rendering
or the stock continuation.

The P4RNDISP manual-trigger failure establishes that the new dispatch block is
**not required** for the sequencer stall: both eight-word blocks were replaced
by NOPs with all other words and P origins unchanged. This does not establish
whether the original block has any additional defect. The responsive UI is
evidence against calling this a complete CPU/UI hard lock; it does not identify
which audio/transport worker has stopped or whether a DSP is waiting.

The next hardware image is now **P4ROLDDSP**: T1 alone, Fold1, no FX, one manual
sound trigger. It restores the complete frozen PERKY4 DSP component while
retaining the exact R ColdFire runtime SHA-256
`637af5f61a6dc5c46d1b3576585f338ac402d0c6dea36cc0cf4b8d2e3ddc27fe`.
NDISP uses that same runtime. The successful OLDDSP first trigger now implicates
the remaining DSP changes, physical placement or their upload integration.
It does not prove that every R ColdFire/Complex path is hardware qualified. Use only
Fold1/Simple on these diagnostic images. PLACE remains available as the later
placement comparison. Firmware binaries and their hashes are unchanged.

`--first-trigger-delay 16 --t1-only --dry --fixed-algorithm --algorithm 0`
extends the actual-image replay with sixteen leading empty steps. It records
the first signed-source frame, first trigger frame and first audible sample;
it requires the leading audio interval to stay silent. This explicitly tests
the empty-playback-to-first-sound transition, rather than starting with a trig
at step zero. Its local outcome still cannot establish hardware stability.

Both frozen images completed this T1-only/no-FX delayed replay. No signed PERKY
record reached the DSP before frame **5514**; the first signed record was also
the first trigger record. Both first audible samples were at **88248**, and
their complete audio SHA-256 was
`b3dd105222dbf4f97adc0bc3b273e84ae1ece07932ad3c9e514ddd3cea920a35`.
Thus empty playback in this reproducer does not warm up the PERKY renderer:
the reported lock coincides with its first invocation. The complete source
records and post-chain audio match locally. The new BNE+4 opcode pair also has
precedents in preserved PERKY4 and stock DSP code; a novel branch instruction
form is not demonstrated. Hardware behavior remains unproven.

### Shared-P end-of-map prefetch discriminator

The physical observations are now: R fails, NDISP fails with a responsive UI,
OLDDSP works. A specific placement hazard appears at T1's common frame return:
R's `pk_three_frame` occupies `0x3ffc5..0x3fffe`, leaving just `0x3ffff` below
the unmapped `0x40000` boundary. PERKY4's frame ends at `0x3ffc7`; its highest
placed routine ends at `0x3fff7`. The instruction-only emulator does not fetch
the sequential pipeline words beyond a return instruction and allocates memory
beyond this silicon map, so PCM/state and boot readback cannot expose this risk.

The [DSP56720/21 reference manual, section 4.3.3](https://www.nxp.com/docs/en/reference-manual/DSP56720RM.pdf)
documents instruction prefetch and a seven-stage pipeline; chapter 3 gives the
shared-memory limit. Repository `CHIP.md` also records freezes at `0x40000+`.
**The claim that speculative fetch explains this stall is an inference, not
yet a physical measurement.** Six words are a conservative experimental margin,
not a claimed measured number of speculative fetches.

P4RPG6 constrains placement below `0x3fffa` and explicitly uploads six NOPs at
`0x3fffa..0x3ffff`. The complete R DSP source and ColdFire runtime are unchanged;
no helper or algorithm is removed and all three AU fixes remain. The constrained
packer fits all 2398 shared code words; padding uses the former six free words.
Physical shared-P use is now 2404/2404, with **zero free shared words**; private P
remains 770/774, four free per core. The startup-clear bytes remain identical.
All twelve stock effects and the two-voice architecture remain.

`verify_perky_prefetch_guard.py` is a conservative placement/explicit-padding
gate. Its preserved-R negative control identifies T1's frame ending at
`0x3fffe`; it is not a new hardware pipeline emulator or proof of the root cause.
P4RPG6 boot/readback, all four fixed-algorithm 36000-frame replays, complete
PCM/producer differentials, retained-FX readback, and representative source-cost
checks qualify the new physical placement locally. The source meter compares
all four algorithms on both cores, including cold hits and interior retriggers,
without changing the 23040 ceiling. Direct AU evidence remains the earlier R
capture; the new candidate preserves R's synthesis rather than retuning it.

The user reports P4RPG6 working on T1 and T5 with all algorithms and Dark
Reverb used on both. Test duration and exhaustive modulation/transition coverage
were not specified. This supports the guarded placement as the stability repair
for the reported first-trigger regression. It does not isolate an exact silicon
prefetch depth: the packer necessarily relocates several shards.

PERKY4S integrates that same six-word guard and explicit padding into the normal
four-engine build. Its MAIN OS must be byte-identical to hardware-tested P4RPG6
(`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`).
The guard affects only four-engine placement; stock startup clear spans/bytes
and the AU-qualified renderer/control source remain unchanged. The full release
suite additionally runs the unsafe frozen-R negative control, actual-upload
PCM/state/cost comparisons for all engines/cores, and delayed first activation.

## Controlled hardware images

| Identifier | Variable changed relative to frozen R | Complex status |
|---|---|---|
| **P4RPLACE** | DSP placement policy only: common controls constrained to their original bank 7; the nearly-full packer necessarily relocates other shards | All three AU fixes retained |
| **P4RNDISP** | Only the two eight-word dispatch blocks replaced by NOPs; all P origins and other words retained | Missing modulation update; do not use Complex |
| **P4ROLDDSP** | Frozen PERKY4 DSP component substituted; PERKY4R ColdFire runtime retained byte-for-byte | Old DSP/transport combination; do not use Complex |

P4RPLACE retains identical R DSP source, private placement, allocation sizes and
ColdFire runtime. It is not a proposal to change the algorithm. Its shared
control decoder is `0x3febe`, pitch converter `0x37da3`, A segment `0x33ea9`, B
segment `0x3fda3`. The additional experiment constraining both the pitch helper
to bank 1 and controls to bank 7 failed packing:
`ValueError: PERKY4 physical P placement failed: 2398 words across [605, 349, 240, 605, 605]`.
No unsafe gap, extra memory or sacrificed FX was used to force it through.

The diagnostic builder first repacks unmodified R and requires an identical
MAIN OS. Both shared uploads carry the identical union. Each variant executes
boot/readback checks. Card and MIDI wrappers must round-trip to the exact
diagnostic MAIN OS. Generated images, loader blobs and extracted assets stay
ignored; only scripts and this report enter Git.

## Local results and reproduction

Delivered-scope results: **18 complete 36000-frame project replays, zero failures,
zero skips**. They include frozen Fold1-only and Simple-only pairs, two Fold1
scheduling quanta, stock-only pairs, NDISP T1-only/T5-only dry controls, the three
diagnostic pairs, and fixed Complex R/PLACE comparisons. Ten complete differential
comparisons assert identical producer packets and full T1/T5 post-chain PCM.
P4RPLACE's Complex comparison is against frozen AU-qualified R, rather than a
new independent AU capture; its source behavior matches throughout the replay.

P4RPLACE also passes eight retained-FX configurations (Fold1/Complex, all twelve
FX, both cores, complete physical P and waveform readback). Twelve representative
actual-upload source measurements cover engines 0/2/5 on both cores and both
placements: identical audio, balanced stack and identical modeled cycles. Their
maximum is 17427 including the measurement wrapper; this is a representative
measurement, not a replacement for R's full corner/transition qualification.
P4RPLACE retains R's 770 private/2398 shared words and 4 private/6 shared free.
Three diagnostic boot checks and three card/MIDI wrapper checks pass. The clean
committed rebuild is identical. No full release requalification or physical
stability is claimed for these diagnostic images.

Commands, logs, per-image metadata, measured bank fetch counts, hashes and
source commit are in ignored `out/regression` and `out/discriminators`, with a
portable receipt beside the Downloads delivery. Reproduction starts with the
two frozen directories, the user's stock image, qualified local dependencies
and packaging tool:

```sh
.venv/bin/python3 tools/perky/build_runtime_discriminators.py --frozen out/frozen --out out/discriminators
.venv/bin/python3 tools/verify/verify_perky_four_project.py --image out/discriminators/P4RPLACE/fragmented-mainos.bin --project "$OT_PROJECT" --work out/regression/P4RPLACE-fold1-q16 --algorithm 0 --fixed-algorithm --quantum 16
.venv/bin/python3 tools/verify/verify_perky_runtime_differential.py --work out/regression --report out/regression/differential-FoldSimple.json
.venv/bin/python3 tools/perky/measure_runtime_images.py --reference out/frozen/PERKY4R --candidate out/discriminators/P4RPLACE --out out/regression/place-source-cost
```

## Original multi-voice protocol (superseded for the next experiment)

First use **P4RPLACE**, a fresh blank project, 120 BPM, 64 steps, all FX NONE.
Set T1/T5 to PERKY, ALGO 1, MODE 1, TUNE 64, DECAY 96, PAR1/PAR2 64. Put trigs
at steps 1/5/9/.../61. Play T1 alone, T5 alone, then both for two minutes each.
Repeat both tracks with ALGO 3 (Simple). Do not save over the original projects.
Record which phase locks, time/step, preceding audio glitch, UI response and
whether either solo case fails. A stock-only blank-playback control will resolve
whether assignment is required. PERKY4 remains the rollback/control.

If PLACE still locks, test **NDISP** with the identical Fold1/Simple fixture.
If that still locks, test **OLDDSP**. A stable PLACE implicates placement/bank
behavior; stable NDISP implicates the added execution block or its timing;
stable OLDDSP isolates the DSP changes/upload component from the R ColdFire
runtime. Those interpretations require repeatable physical A/B observations.
If all fail, the next differential is the ColdFire/runtime or loader integration.
No algorithm changes are authorized by these outcomes alone.

Current branch is `codex/perky4r-runtime-regression`. Source is committed clean;
the PG6 hardware discriminator has passed the cases reported above. The normal
PERKY4S release still requires its complete local receipts and clean rebuild.
