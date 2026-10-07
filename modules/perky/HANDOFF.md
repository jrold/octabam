# PERKY continuation — PERKY4 local qualification

The user wants **all twelve PĒRKONS families working**, using local Git and local builds only. This objective remains unfinished. The latest retrieved branch base is `perky-machines` at `9b12c0ebd3301c2a691dc7e710da47be5ba64a90`. Current source changes are in a separate writable worktree; they have not yet been committed or pushed.

## Current testable firmware

**PERKY4 exposes authentic v1.2.1 `001 FOLD DRUM` and `003 SIMPLE DRUM`, alongside preserved synthetic PERKY2 `011 NOISE/TONE`.** New-engine hardware testing is pending. Noise/Tone's earlier physical success applies to PERKY2; PERKY4 regression is locally verified.

Artifacts are local, excluded from Git:

- `out/OCTATRACK_PERKY4.bin` — CF updater; checksum/container round-trip passed.
- `out/OCTATRACK_OS1.40C_PERKY4.syx` — MIDI updater.
- `out/PERKY4_PERKY_TEST.txt` — hashes and qualification status.
- Copies and `PERKY4_TEST_GUIDE.md` are in the calling task's `outputs` directory.

Select PERKY, then `003 SIMPLE DRUM`; test M1/M2/M3, TUNE/DECAY/ENV/MIX, sequencing/retriggering and live MODE changes. ENV means pitch-envelope decay; MIX means pitch-envelope amount for this family. Use FX1/FX2 NONE and retain the one-voice-per-core admission guard. Fold Drum uses FOLD/PENV; physical MODE is no transient / noise transient / pulse transient. Other nine families are not exposed.

## Measured local evidence

- `make check REMIX=perky-machine OT_PROJECT=`: all runnable checks passed; optional dependency/project skips were reported. This floor includes the three Simple Drum primitive execution gates; it does not replace full shipping gates.
- `verify_perky_simple_drum_voice_exec.py`: complete DSP renderer, 240 native C++ reference blocks, exact PCM and all 34 live state words, velocity/mute, envelopes, retriggers, oscillator wraps and all waves.
- `verify_perky_simple_drum_production_transport.py`: **actual production ColdFire `pk_render`**, 1,024 records, eight tracks, controls/modes and switching history.
- `verify_perky_multi_seam_exec.py`: mixed shipping source, tagged host records, all slots/modes/trigger offsets, overlays, unsupported-engine silence and PERKY2 PCM/state regression. 13,878 cases/blocks; worst modeled path **22,633 cycles**, cap 23,040. Persistent Noise/Tone corner sweep is a timing check; its exact regression assertions are the independent first-block seam cases.
- Final boot gate: both uploads and runtime read back exactly, loader/RTOS handoff succeeded.
- Full production firmware sequencer gate: **each of three engines ran 32,000 frames**, dirty seed 123, repeated later triggers, both cores produced varying sustained post-AMP/FX audio; six excess voices matched an independently staged signed-source zero control.
- Audibility excludes the first 4,096 samples, preventing dirty-memory startup noise from passing as synthesis. The zero control runs the same image with unsupported engine 99, retaining identical stock AMP/FX continuation. Ordinary FLEX does not always execute that continuation on startup.

Final mixed memory: **2,680/2,724 P words**, **359/616 private X words**, **1,946/2,139 private Y words**. Four 58-word overlay slots and shared RNG remain at X:$3800; initialization extends through $38F1. Scratch is X:$3900..$3963, pitch cache X:$3964..$3974. Y:$07A5..$0F3E holds preserved Noise/Tone waves, three authentic Simple Drum waves, direct envelope samples, packed pitch basis and decoder padding.

Additional PERKY4 evidence: Fold Drum matched 15 original ARM blocks and 400 randomized native blocks exactly (PCM, 40 live words and RNG). Its 160 physical noise-hold cases peaked at 19,424 modeled cycles; unconstrained states are not the production control domain. Production Fold transport passed 2,048 actual ColdFire calls. The Fold seam passed 3,684 cases/blocks, worst 20,467 modeled cycles. The full Simple/Noise gate also passed on the Fold composition, worst 22,639 cycles. Both CF and MIDI round-trips reproduced the emitted MAIN OS exactly. Full 24-case pre/post general-builder refhash matrix was bit-identical.

## Bugs fixed during integration

Incoming production DSP record words carry high tags (`$030000`). Dispatch must mask engine IDs to eight bits and byte preparation must mask each byte. Untagged-only harnesses missed this; the shipping seam gate now uses tagged inputs. Authentic trigger preserves oscillator phase/current wave and resets both envelope accumulators.

The local emulator's P-memory write hook cleared opcode cache even for writes beyond allocated P. Bounds checking now matches Memory::dspWrite behavior; the same crash was reproduced with stock and old PERKY2 images. USB verification uses an inherited socketpair because sandbox listener binding is unavailable; protocol/enumeration/MSC checks still run.

## All-family continuation

Original ARM captures now cover **12 families × 3 panel modes × 3 control corners**. Each captures a triggered 256-sample block plus a continuation block with explicit RNG inputs/output and wrapper RAM windows. Windows are not engine object sizes. `capture_engine_fixtures.py` generates them from the user's external firmware/native source; no derived assets go in Git.

Fold Drum 1 is now locally shipping-qualified in PERKY4, with physical testing pending. `build_fold_machine_canary.py` is its gated local builder. It keeps Simple Drum and Noise/Tone unchanged under exact regression gates.

Wavetable V1/V2 candidate renderer passes 18 original ARM blocks plus 240 randomized native blocks: exact PCM and all 41 live words, all 49 waveform assets, 841 standalone P words, peak 19,435 modeled cycles per 16 samples. Its current primitive gate uses a logical Y bank that crosses absent physical Octatrack addresses; **this is not a shipping memory map or port**. SURF selects among 48 × 2,048-sample tables, plus the initial deferred-switch waveform, rather than just the corner snapshot tables.

The address-independent Wavetable bank now has a host-tested lossless second-difference codec: 49 assets / 100,352 samples occupy 45,713 DSP words including directory and guards. The DSP decoder executes against every asset exactly, uses a 33-word cache, and measures at most 2,511 modeled cycles for a sequential 16-sample block. Random renderer cache misses and physical placement remain separate gates.

Complex Drum now has an exact compact host model and a native/ARM execution gate: all nine original V2 A3 mode/corner blocks match PCM and final state. Its DSP56300 candidate now has the corrected base-frequency register preservation, pitch-factor register lifetime, accumulator alignment and initialized pitch-cache tag; all three MODE-1 blocks pass exact DSP PCM/state. MODE-2 reaches the deferred `0x24a0` wave correctly but still diverges at that fourth-table interpolation boundary. No Complex browser entry or shipping DSP dispatch has been enabled.

The user explicitly selected **all 12 voices, accepting fewer stock effects**. Reclaim effect memory for the final design; do not ask again. Storage measurements and host codec round-trips alone do not establish DSP timing. Boot staging/bootstrap/mailbox ranges must survive; stock init clears local Y and shared RAM, so larger asset uploads need changed initialization or post-init loading. Shared P/X/Y aliases must have a single ledger. The final architecture is still under implementation.

Remaining: integrate Wavetable production controls and lossless physical asset access; translate and execute-gate Fold Drum 2 and Complex Drum on DSP56300; then implement resonant modes, Slap, Karplus, Noise Hat and Acoustic Hats, and replace synthetic Noise/Tone controls/assets with authentic qualified behavior. Preserve the physically working Noise/Tone path during development. Never expose placeholder browser entries or claim reference capture equals a port.

## Historical PERKY2 snapshot

Everything below is the previous handoff, retained as historical evidence. Its “current”, “pending” and memory figures refer to PERKY2 or earlier work and are superseded above.

# PERKY continuation handoff — 6 October 2026

## Current milestone and user goal

**PERKY2 Noise/Tone produces working audio on the user's Octatrack.** The user
reported “Ok that works” after flashing the PERKY2 timing repair. They now want
to continue until **all twelve PerkyBits engine families and their three modes
work**. Noise/Tone is the first audible hardware milestone, not a completed
faithful PĒRKONS port. Test duration, extended stress, and every control/mode's
hardware behavior were not reported.

The working repair is commit `74399880e518fd7f6544ef9047f909c975dc1375`, on
`perky-machines`, pushed to `origin/perky-machines`. Keep continuation work on
that branch; follow the repository worktree rules. This handoff supersedes the
old pre-audio Downloads handoff. Historical claims that no firmware was built
or flashed are obsolete.

## Working build and limits

- Exposed machine: PERKY; engine browser: `011 NOISE/TONE`.
- Controls: TUNE, DECAY, ENV, MIX, MODE. Tables and mapping are synthetic
  development fixtures. Original `update()` conversion/smoothing and complete
  original mode behavior still need qualification.
- One PERKY track per DSP core: one in T1–T4 and one in T5–T8. The lowest
  numbered selected PERKY track wins each group, even without a trig. Other
  PERKY tracks in that group are silent.
- FX1 and FX2 NONE on all tracks is the timing-qualified test layout. Additional
  voices, effects, and other modulation/scene combinations need separate checks.
- Underlying stock FLEX, PK/1 Part signature, ColdFire PK/Y1 control record,
  source seam before stock AMP/FX. The tracked manifest remains an impulse
  probe; the full machine is composed by `build_machine_canary.py`.

PERKY1 briefly sounded, then stalled the hardware sequencer. Its limb renderer
measured roughly 79k–84k modeled cycles per 16-sample block against a
72,512-cycle/core deadline before stock work. The instruction-scheduled full
emulator did not reproduce the stall; the exact hardware halt was not observed.
PERKY2 uses native DSP arithmetic, direct state access, adjacent packed reads,
and an exact analytic lookup for the fingerprinted synthetic linear envelope.
It restricts admission to one voice/core. Do not remove the guard or apply the
synthetic specialization to authentic tables without new proof.

## Evidence already obtained

- `make check REMIX=perky-machine OT_PROJECT=`: all runnable checks passed;
  optional dependencies/project gates reported their skips. This checks the
  tracked probe, separately from the full machine builder below.
- Actual shipping renderer: 36 × 16-sample blocks, exact PCM/state/RNG oracle
  agreement; audible five-control changes; all 2048 linear-curve indices exact.
- Actual seam: all source slots and 16 trigger offsets; ring/continuation checks;
  excess/invalid voice silence; signed and unsigned slot-0 reset with dirty latch.
- `verify_perky_realtime_budget.py`: 12,544 blocks / 49 control corner cases;
  worst 22,822 modeled cycles. Cap 23,040; twice the model plus 22,560 stock
  reserve is at most 68,640 versus 72,512. Conservative estimate, not a complete
  cycle-accurate hardware burn sweep.
- Boot gate: loader once, RTOS handoff, no fatal; runtime and both DSP uploads
  plus X/Y initialization read back byte-identical.
- Full native firmware: 32,000 stereo frames (~11.6 seconds), dirty DSP seed
  123, later repeated sequencer trigs, both cores audible, all eight PERKY
  selections with only T1/T5 admitted. Six rejected tracks match independently
  measured stock silence, including startup tails/tiny DC offsets.
- Full-port audio is post-AMP/FX DSP readback. The known emulator main-TX0 dry
  output defect means this capture did not certify physical main output;
  subsequent user hardware success supplies the audible milestone.
- CF checksum/container and MIDI decompressed MAIN OS round-trip passed.

## Source and memory map

Generator: `tools/perky/build_noise_tone_synth_source.py`. Native shipping pieces:
`noise_tone_voice_native_xstate.asm`, `noise_tone_filter_native.asm`,
`noise_tone_oscillator_native.asm`, `noise_tone_envelope_native.asm`,
`noise_tone_envelope_native7.asm`, `noise_tone_mix_native.asm`, plus seam,
synthetic control mapper, and shared RNG/math. Independent limb probes remain
oracle gates; they are not the shipping timing baseline.

- 41 live state + 17 cache words per voice; four slots + shared RNG = 236 X words
  at X:$3800..$38EB. Allocated slots do not imply four admitted voices.
- X:$38EC event offset; X:$38ED admission latch.
- X:$3900..$3963 = 100 shared scratch words; total private X use 338/616.
- Synthetic packed tables Y:$07A5..$0F5B = 1975 words. Envelope bases $0A50/$0CD6.
- Shipping DSP source 1626/2724 donor P words, 1098 free.
- ABI indices are decimal; assembler `$NN` displacements are hexadecimal.
- High-P internal calls require explicit `jsrl`, local conditions PC-relative
  branches. Generator normalizes both. Disassemble assembled bytes and run
  exact execution gates; successful assembly alone is insufficient.

## Continue toward all engines

Read `PORT.md`, `MEMORY.md`, `SYNTHETIC.md`, and the native PerkyBits catalog.
First audit authentic Noise/Tone reference/control/table requirements and add a
per-family qualification matrix covering every mode, triggers/retriggers,
velocity, live controls, state/RNG parity, table provenance, P/X/Y, and worst
runtime. Establish which reusable oscillator/envelope/filter primitives and
control laws are qualified before choosing the next family. Preserve the
working PERKY2 path as a regression fixture.

| Family | Octatrack status |
|---|---|
| Fold Drum 1 | Not ported/qualified |
| Wavetable Drum V1 | Not ported/qualified |
| Simple Drum | Not ported/qualified |
| Fold Drum 2 | Not ported/qualified |
| Wavetable Drum V2 | Not ported/qualified |
| Complex Drum | Not ported/qualified |
| Resonant Drums | Not ported/qualified |
| Slap | Not ported/qualified |
| Karplus | Not ported/qualified |
| Noise Hat | Not ported/qualified |
| Noise/Tone | Synthetic native renderer; PERKY2 hardware audio confirmed |
| Acoustic Hats | Not ported/qualified |

Catalog mode order is not necessarily firmware mode order: use
`Source/EngineCatalog.h`'s `panelModeToFirmware` rather than assuming 0/1/2.
Integrate families incrementally behind the existing engine browser and shared
source plumbing. Qualify each actual generated shipping path for parity,
resources, timing, boot, and sequencer behavior before emitting a new firmware
for hardware testing. No assumption that all families fit simultaneously or
that four voices/core are affordable is justified yet. Retain the guard until
a measured multi-voice design replaces it. Authentic tables may require a new
packing/cache strategy; the native curve/wave specialization is synthetic-only.

## Local paths and reproducible build

- Original repo: `/Users/jrold/Downloads/octabam` (`perky-machines`).
- Isolated worktree used for PERKY2:
  `/Users/jrold/Documents/Codex/2026-10-06/files-mentioned-by-the-user-perky/work/octabam`.
  Its `perky2-timing-fix` branch contains the same repair commit; future work
  should target `perky-machines`, not accidentally leave new commits there.
- Native reference: `/Users/jrold/Downloads/perkybits`, inspected revision
  `605cfd05d9dcdc0d0caa955297556a26ea257f82`. Verify reference revision and local
  changes before claiming oracle identity. Native renderer files include
  `Source/NativeV121NoiseToneShared.cpp` and `Source/NativeV121NoiseTone.cpp`;
  `Source/PerkonsVoices.cpp` owns firmware state/update/trigger plumbing.
- Saved project fixture: `/Users/jrold/Documents/octatrack backup/##Scratch`.
  Test tools copy it into owned output/card fixtures; never modify the original.
- Existing toolchain/stock extraction works; do not reinstall without cause.
  Build the emulator/changed hosts in the worktree, not shared vendor outputs.

```sh
make check REMIX=perky-machine OT_PROJECT=
OT_PROJECT='/Users/jrold/Documents/octatrack backup/##Scratch' \
  python3 tools/perky/build_machine_canary.py --build 2
```

The builder requires a saved project and runs the full native boot/sequencer
gates before producing `out/OCTATRACK_PERKY2.bin` and the experimental `.syx`.
Use a new version/build number for subsequent changed firmware. The raw
`mainos_perky_machine.bin` is not a CF update file.

User-facing PERKY2 files, guide, validation, patch, and stock MIDI recovery are
in `/Users/jrold/Documents/Codex/2026-10-06/files-mentioned-by-the-user-perky/outputs`.
PERKY2 card SHA256:
`99dbbd882252a56962fe4fa09f39d081312cb8ee48f6269d15cc359df45e5cdb`.
Hardware report applies to that build, not to future builds merely sharing its
version. Keep firmware-derived binaries/tables outside Git.

For recovery: FUNC during power-on → TRIG 3 MIDI UPGRADE → official stock 1.40C
SysEx over MIDI DIN. PERKY1 is a failed build and must not be reused as a test
baseline. Run available software checks autonomously before requesting another
hardware test; report exactly what remains unmeasured.
