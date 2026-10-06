# PERKY full Noise/Tone machine canary

This is the first development image that combines all current PERKY layers:

- virtual PERKY source-machine row on top of FLEX;
- persisted `PK/1` Part signature;
- `TUNE / DECAY / ENV / MIX / MODE` source page;
- Noise/Tone engine browser entry (`011 NOISE/TONE`);
- generated ColdFire control runtime from `modules/perky/control.c`;
- sample-accurate PK/Y1 source transport;
- complete packed Noise/Tone DSP renderer on both cores;
- synthetic five-control mapper feeding the persistent DSP voice;
- 236-word X initializer at `X:$3800`;
- packed wave/envelope payload at `Y:$07a5`;
- one shared Octabam loader carrying both the ColdFire runtime and the two
  extended DSP uploads.

The tracked `PERKY PROBE` manifest remains the small impulse diagnostic. This
full machine is assembled by an in-memory module upgrade and never replaces the
fallback canary on disk.

## PERKY2 timing repair

PERKY1 produced a brief sound and stalled the hardware sequencer. The limb-based
renderer exceeded the DSP block budget. PERKY2 uses native multiply/accumulator
operations, direct compact-state access, adjacent packed-wave reads, and an exact
analytic lookup for the fingerprinted synthetic linear curve. Its shipping gate
still matches the independent PCM, compact-state and RNG oracle.

This remains a development canary: **one PERKY track per core** (T1–T4 and
T5–T8). The lowest numbered PERKY track in each group sounds; additional PERKY
tracks in that group are silent. Use **FX1 NONE and FX2 NONE** on every track in
the test Part. Effects and more simultaneous voices need separate timing qualification.

The mandatory budget gate measures the actual seam (all trigger offsets and
control corners), doubles the opcode-cycle model, and reserves stock's measured
1410 cycles/sample. The builder also runs 32,000 frames under both DSP cores
with dirty memory, later pattern trigs and six rejected voices.

Hardware report (6 Oct 2026): the user confirmed that PERKY2 works on their
Octatrack after PERKY1 stalled. Test duration and extended stress coverage
were not reported; the voice and FX limits above still apply.

## First audible build

Prerequisites are the normal octabam setup from `docs/guide/BUILDING.md`:

```sh
make setup
make os
make recon
```

Build the ColdFire emulator once so the builder can verify the actual loader
and read back the runtime and both DSP uploads before packaging:

```sh
make emu-cf
```

Then build the PERKY sound-test image:

```sh
OT_PROJECT="/path/to/a/saved/project" python3 tools/perky/build_machine_canary.py --build 2
```

The builder first executes the critical local DSP/machine preflights. It will
**not** produce a flashable image if the five-control mapper, complete packed
voice, generated synth, control-to-PCM path, actual source seam, or loader boot
with exact runtime/upload readback fails.

Successful output ends with `READY FOR FIRST SOUND TEST` and writes:

```text
out/OCTATRACK_PERKY2.bin                 CF-card update image
out/OCTATRACK_OS1.40C_PERKY2.syx         MIDI update/recovery-format image
out/mainos_perky_machine.bin             intermediate patched MAIN OS
out/PERKY2_PERKY_TEST.txt                git revision + SHA256 hashes
```

Use a different one/two-digit build number for every flash, e.g.:

```sh
python3 tools/perky/build_machine_canary.py --build 2
```

which produces `OCTATRACK_PERKY2.bin` and stamps the unit's OS version
`PERKY2`.

## Flash from CompactFlash

This is unofficial development firmware. Keep the stock 1.40C MIDI recovery
file/interface available and use stable power. The standard octabam recovery
procedure is in `docs/guide/BUILDING.md` section 7.

1. Back up the project/card you care about.
2. On the Octatrack: **PROJECT -> SYSTEM -> USB DISK MODE -> YES**.
3. Copy `out/OCTATRACK_PERKY2.bin` to the **root** of the CF card.
4. Eject the card from the computer, then leave USB DISK MODE.
5. **PROJECT -> SYSTEM -> OS UPGRADE -> YES**, confirm, and let it finish.
6. After it restarts, power-cycle the Octatrack once more before testing.
7. In **SYSTEM STATUS -> OS VERSION**, confirm the unit reports `PERKY2`.

Do not flash `mainos_perky_machine.bin` directly; it is only the patched MAIN
OS section. The file intended for the card is `OCTATRACK_PERKY2.bin`.

## First sound test

Use a new/throwaway project or Part for the first test.

1. Set FX1/FX2 to NONE on all tracks; start with T1. Pick the audio track and open the normal machine chooser.
2. A sixth machine row named **PERKY** should be present. Select it.
3. The track remains FLEX underneath but is signed `PK/1`; a fresh selection
   seeds the PERKY defaults and hidden engine family automatically.
4. Open the source page. It should identify **NOISE/TONE** and expose:
   `TUNE`, `DECAY`, `ENV`, `MIX`, and the three-position `MODE` control.
5. Put a normal audio trig on the track and press PLAY. **You should hear a
   synthesized Noise/Tone hit without assigning a sample.**
6. Turn `TUNE`, `MIX`, and `MODE` first; those should produce the most obvious
   immediate changes. `DECAY` and `ENV` alter the envelope trajectory.
7. Change controls while the voice is sounding. The synthetic development
   mapper is applied every source block, so live changes should affect the
   current voice without requiring another trig.
8. Double-tapping a PERKY track opens its sample-pool-style engine browser.
   This milestone contains one row, `011 NOISE/TONE`; LEFT returns to the
   machine chooser and RIGHT on PERKY reopens the engine pool.

The seam scales native signed16 PCM into the Octatrack signed24 source range.
The source is rendered before stock AMP -> FX1 -> FX2, so normal track volume
and effects remain downstream. PERKY2 timing qualification requires FX1 and
FX2 NONE on all tracks; effects have not been budget-qualified.

## What this sound means -- and what it does not

If the test above produces audio, we have crossed the milestone this branch was
built for: Octatrack machine selection -> persisted PERKY Part state -> PK/Y1
control transport -> sample-accurate trigger -> complete packed DSP voice ->
stock AMP/FX -> hardware output.

The sound is still a **synthetic development canary**. The waves, envelope
curves, prepared state and five-knob mapping come from the explicitly fabricated
test fixture. They exercise the final runtime architecture but are **not**
claimed to match Erica Synths PĒRKONS yet. The next phase is replacing the
synthetic control/table inputs with the measured v1.2.1 PĒRKONS update law and
then adding the remaining engine families.

## If the unit does not boot

The Startup Menu is outside the modified OS. Power off, hold **FUNC** while
powering on, choose **TRIG 3 -> MIDI UPGRADE**, and send the stock
`downloads/extracted/OCTATRACK_OS1.40C.syx` over DIN MIDI. See
`docs/guide/BUILDING.md` section 7 for the full recovery procedure.
