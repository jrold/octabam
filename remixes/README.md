# Remixes

A remix is a named selection of modules; `make image REMIX=<name> BUILD=<n>` builds it into a card-flashable image from your own OS 1.40C. Each remix is a directory here: `remix.py` is the selection, `README.md` says what is in it, where it has run and how to flash it. This index is rendered from the selections (`make docs`).

- What to install first (the Xcode Command Line Tools, Homebrew, Python 3.10+, `cmake`, `uv`) and every step to a flashed unit: [BUILDING.md](../docs/guide/BUILDING.md).
- Composing your own: [REMIXER.md](../docs/guide/REMIXER.md).
- The remixes that carry one module for its gates: [test/](test/README.md).

## The delay and reverb bus

| remix | contains | proof |
|---|---|---|
| [`bottleservice`](bottleservice/README.md) | The delay and reverb bus (BusDelay on T1's FX2, BusVerb on T5's FX2, SEND on every other track's FX2, the stock DELAY on T8) + SPECTRUM, CHARACTER and MODULATION on FX1 + USB MIDI + USB AUDIO OUT MASTER (T8 to the computer) + KITS. | on hardware: Sam's MKII (image A6 with KITS, 6 Oct 2026; images A0-A3 with Octakit, 4 Oct 2026) |

## Effects

| remix | contains | proof |
|---|---|---|
| [`wave`](wave/README.md) | Experiment: a 4-voice wavetable synth on FX2, played by a sine on its track; SCALE QUANTIZER, page-2 tools, USB out; DARK and SPRING REV give up their words. | on hardware: Sam's MKII, image 93, 3 Oct 2026: plays, PTCH and the CHROMATIC keys move the pitch |

## Firmware mods on the stock effects

| remix | contains | proof |
|---|---|---|
| [`analog-bassdrum`](analog-bassdrum/README.md) | Analog BD source machine, switchable 808/909, stock AMP and FX. | port-gated: source/UI under the port; earlier ANALOGBD1 auditioned on MK1, current revision unflashed |
| [`octatrick`](octatrick/README.md) | SYNTH MACHINE + SCALE QUANTIZER + DIRECT JUMP + TUNER + USB MIDI + USB AUDIO (20 channels out, 4 in onto A-D) on the stock effects less SPATIALIZER. | on hardware: Tim's MKI, test build 3.0 b40 (this selection at BUILD 40), 29 Sep 2026: USB AUDIO IN brings the Mac's audio onto the inputs in a one-minute check (long runs not yet tested). The same four modules with the 26 Sep USB AUDIO (out only) ran on the same MKI through the 2.9 test builds; the tuner works on test build 3.0 b40 (UP + TEMPO); the last two 2.9 fixes are not yet confirmed on hardware |
| [`ok-ms`](ok-ms/README.md) | KITS + MIDI SCENES on the stock effects: the two mods alone. | port-gated: with Octakit on midisc's author's unit, 14 Sep 2026 (OKMS2); with KITS under the port |

Never share a built image: it contains Elektron's OS.
