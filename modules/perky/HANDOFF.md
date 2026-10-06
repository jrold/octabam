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
