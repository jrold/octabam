# octabam-core

A remix of Octatrack OS 1.40C, built from your own copy of it, that adds the
core modules and changes no effect: all 14 stock effects and both effect
menus stay as stock has them, with stock LO-FI's AMF knob fixed (the LOFI AMF
FIX module). The other official remixes add effects to this set:
[octabam-inserts](remix-inserts.md) (effects that run on any track) and
[octabam-bus](remix-bus.md) (a delay and reverb bus).

## The core modules

| group | module | what it does |
|---|---|---|
| platform | BRAIN | card-wide settings, defaults and templates, remix switch, TOOLS (MIDI monitor, LOAD) |
| | STORE | the save, load, copy and Part sites KITS and PLOCKS P2 share |
| sequencing | KITS | 255 Kits per project; each pattern plays its Kit |
| | MIDI SCENES | scene locks for MIDI tracks |
| | SCENES P2, PLOCKS P2 | scene locks and parameter locks on FX page 2 |
| | CC MAP, CC FEEDBACK | CC onto page 2; knob changes out as CC |
| | DIRECT_JUMP_KYOTI, RELOAD_FROM_PROJECT | clock-locked direct jump; reload one track from the card |
| | SCALE QUANTIZER, TUNER | scale quantizing on PTCH; a tuner window (UP + TEMPO) |
| USB | USB MIDI, USB AUDIO OUT | MIDI both ways; tracks, MAIN and CUE to a computer (layout MAIN CUE) |
| recorder and fixes | RECORDER LOOP FIX, RLEN PLEN | the loop click; RLEN value PLEN |
| | BATCH_BUGFIXES, ERASE_EMPTY_TRIGLESS_LOCKS, QUANTIZE_LIVE_REC_TOGGLE, REC_TRIG_MUTE, MUTE_MODES | Zac-Kyoti's fixes and mute modes (MUTE_MODES runs from DRAM) |

Every module in the image, credited to its author:

--8<-- "reference/_remix-octabam-core.md"

## What it costs

| | stock | octabam-core |
|---|---|---|
| sample and recorder memory | 14,602 pages | 12,895 pages (the platform reserve) |
| DSP words free | | 0: LOAD METER does not fit, so core has no LOAD view DSP rows |

## Where it has run

Port gates only: `make check REMIX=octabam-core` and the reach round. Not on
a unit.

## How to flash

The [build and flash guide](build-flash.md) has every step, from what to
install to the way back to stock. For this remix:

1. **Build.** Pick a build number; it becomes the OS version the unit shows.

   ```bash
   make image REMIX=octabam-core BUILD=91        # -> out/OCTATRACK_OCTABAM91.bin
   ```

2. **Back up the card.** KITS writes `kits.work` into each project it loads.
3. **Flash from the card**, then power-cycle once more. SYSTEM STATUS → OS
   VERSION reads `OCTABAM91`.
4. **Back to stock:** [Safety and recovery](safety.md).

If the unit misbehaves, the failure register lists what has gone wrong and
why: https://github.com/sambanks/octabam/blob/main/docs/contributing/FAILURE_MODES.md
