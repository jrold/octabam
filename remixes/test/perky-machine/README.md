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
- packed wave/envelope payload at `Y:$0795`;
- one shared Octabam loader carrying both the ColdFire runtime and the two
  extended DSP uploads.

The tracked `PERKY PROBE` manifest remains the small impulse diagnostic. This
full machine is assembled by an in-memory module upgrade and never replaces the
fallback canary on disk.

## First audible build

Prerequisites are the normal octabam setup from `docs/guide/BUILDING.md`:

```sh
make setup
make os
make recon
```

Then build the PERKY sound-test image:

```sh
python3 tools/perky/build_machine_canary.py --build 1
```

The builder first executes the critical local DSP/machine preflights. It will
**not** produce a flashable image if the five-control mapper, complete packed
voice, generated synth, or control-to-PCM path fails.

Successful output ends with `READY FOR FIRST SOUND TEST` and writes:

```text
out/OCTATRACK_PERKY1.bin                 CF-card update image
out/OCTATRACK_OS1.40C_PERKY1.syx         MIDI update/recovery-format image
out/mainos_perky_machine.bin             intermediate patched MAIN OS
out/PERKY1_PERKY_TEST.txt                git revision + SHA256 hashes
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
3. Copy `out/OCTATRACK_PERKY1.bin` to the **root** of the CF card.
4. Eject the card from the computer, then leave USB DISK MODE.
5. **PROJECT -> SYSTEM -> OS UPGRADE -> YES**, confirm, and let it finish.
6. After it restarts, power-cycle the Octatrack once more before testing.
7. In **SYSTEM STATUS -> OS VERSION**, confirm the unit reports `PERKY1`.

Do not flash `mainos_perky_machine.bin` directly; it is only the patched MAIN
OS section. The file intended for the card is `OCTATRACK_PERKY1.bin`.

## First sound test

Use a new/throwaway project or Part for the first test.

1. Pick any audio track and open the normal machine chooser.
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

The source is rendered before stock AMP -> FX1 -> FX2, so normal track volume
and effects remain downstream. For the first test, keep the AMP and FX simple
so a silent/misconfigured effect is not confused with a source failure.

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
