# PERKY control conversion

The Octatrack port needs more than the already-native per-sample renderers.
PerkyBits intentionally leaves **control conversion and smoothing** in the
original PĒRKONS firmware and replaces only the validated render routine.

That boundary is explicit in PerkyBits:

- the four panel sound controls are `TUNE`, `DECAY`, `P1`, `P2`, each 0..4095;
- MODE is 0..2;
- trigger velocity is a retained 0..255 byte, not a continuously applied
  panel control;
- firmware v1.2.1 also carries a 0..127 note byte;
- `setSoundParameters()` writes the four 12-bit values to the voice's four
  control words and then calls the original voice `update()` repeatedly;
- the plugin normally settles a changed sound with 16 update iterations;
- every native render path still performs the original update when a pending
  control-smoothing step must be consumed.

Therefore a DSP56300 renderer alone is not a faithful Octatrack machine. The
Noise / Tone milestone must also reproduce the original update mapping that
turns those controls into its 0x120-byte render state.

## Executable probe

The probe strategy below is now implemented rather than aspirational.

A supporting branch in the private PerkyBits repository,
`octabam-control-probe`, adds the headless CMake target
`perkybits-control-probe`. It runs the original v1.2.1 firmware `update()` under
the existing Unicorn runtime and writes JSON Lines containing **numeric state
only**. No firmware instructions or waveform/envelope table blobs are copied to
Octabam.

The target is deliberately pinned to the already-qualified v1.2.1 ABI and
refuses another image identity. Its first target is Voice 4 panel algorithm 1
(internal algorithm 0), whose panel modes 0 and 2 share the renderer at
`0x08025a14` and the 0x120-byte state object at `0x200034dc`. Panel mode 1 is
the separate waveform-2 renderer and stays out of this first fixture.

The default run records:

- 13 anchor values for each of TUNE, DECAY, P1 and P2 with the other controls
  held at 2048;
- the state immediately after the target control words are written;
- every one of the next 16 firmware `update()` passes;
- the complete 0x120 renderer state, the first 0x40 wrapper bytes, and the four
  32-bit control words at every point;
- pre/post-trigger snapshots across velocity and chromatic-note anchors.

`--pairwise` additionally settles every pair of controls on a 0/2048/4095 grid
so cross-terms cannot hide behind four independent one-dimensional sweeps.

On the PerkyBits checkout:

```sh
git fetch origin
git switch octabam-control-probe
cmake -S smoke -B build-control-probe -DCMAKE_BUILD_TYPE=Release
cmake --build build-control-probe --target perkybits-control-probe -j
./build-control-probe/perkybits-control-probe \
  ~/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img \
  ~/Downloads/perky-control.jsonl --pairwise
```

Then, from this Octabam branch:

```sh
python3 tools/re/perky_control_analyze.py \
  ~/Downloads/perky-control.jsonl \
  --json ~/Downloads/perky-control-analysis.json
```

The analyzer refuses malformed fixtures, proves that the four control RAM words
match the requested values, reports settled renderer/wrapper byte ownership per
control, groups bytes by the last smoothing iteration that moved them, reports
note/velocity trigger deltas, and identifies pairwise bytes not explained by
either control's univariate ownership set.

## Probe strategy

Do not attempt a 4096^4 lookup table. Treat the existing PerkyBits firmware
runtime as a control oracle and identify the mapping experimentally, then
translate the resulting integer math.

For each shared Noise / Tone mode:

1. initialize the original voice at the known defaults;
2. capture the complete selected render state before and after one `update()`;
3. sweep each of TUNE, DECAY, P1 and P2 independently across a coarse 0..4095
   grid while holding the other controls fixed;
4. record which state bytes/words change and their exact values;
5. repeat around discontinuities with a dense local sweep;
6. run pairwise sweeps to detect cross-terms instead of assuming each control
   is independent;
7. repeat updates at one fixed target to identify smoothing state and the
   convergence recurrence;
8. trigger at multiple velocities and notes to separate trigger-owned state
   from continuously updated state.

The output fixture should contain only numeric input/output state required for
verification. It must not embed firmware code or bulk firmware-owned tables.

## First target: Noise / Tone

Known renderer state from the native reference:

- mutable state size: `0x120` bytes;
- amplitude envelope base: `0x74`;
- noise/sample-and-hold base: `0x60`;
- resonant noise-filter base: `0x9c`;
- oscillator 1 base: `0x2c`;
- oscillator 2 base: `0xc4`;
- noise/tone mix word: `0xf8`;
- velocity byte: state byte `+6`;
- shared modes use four referenced 256-sample signed-16 wave tables;
- waveform 2 uses its separately validated renderer/table geometry and should
  stay a separate control probe until equivalence is demonstrated.

The first useful probe is not a PCM sweep. It is a **state-delta sweep**: which
bytes at these regions change for each front-panel input and after how many
update iterations. Once that is understood, the DSP port can consume Octatrack
0..127 knob values by scaling them to the same 0..4095 control domain and run
the translated update recurrence at the same control cadence.

## Octatrack mapping policy

The source page should expose the original sound controls before adding new
convenience controls:

- `TUNE`
- `DECAY`
- engine-specific `P1` (Noise / Tone: envelope amount)
- engine-specific `P2` (Noise / Tone: noise/tone mix)
- `MODE` (3 positions)

A 7-bit Octatrack knob value maps into the original 12-bit panel domain using a
single documented integer rule shared by p-locks and LFO delivery. The exact
rule will be fixed by endpoint/midpoint tests in the control gate; do not mix
multiple scaling formulas in ColdFire and DSP code.

Velocity/accent and chromatic note should be kept separate from the four sound
controls because the original firmware does so. Their final Octatrack source
semantics will be chosen only after the trigger record path is working.
