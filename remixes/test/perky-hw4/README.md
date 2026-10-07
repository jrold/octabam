# PERKY HW4 — first four-voice hardware audition

This is intentionally **not** the final unrestricted PERKY architecture.  It is
the smallest useful physical checkpoint: two admitted synth voices per Octatrack
DSP core and one fixed engine from each PĒRKONS hardware voice family.

| OT track | PĒRKONS voice | First-audition engine |
|---|---|---|
| T1 | V1 | Fold Drum 1 |
| T2 | V3 | Karplus |
| T5 | V2 | Fold Drum 2 |
| T6 | V4 | Noise / Tone |

T1/T2 share one DSP core; T5/T6 share the other.  T3/T4/T7/T8 are not PERKY
voices in this image.

For this audition only, stock **FILTER** and **DELAY** are retained.  The other
stock DSP effects are omitted so their program/data regions can be reclaimed.
DELAY is the stock ColdFire effect and consumes no DSP P program words.

Karplus uses the exact renderer plus evidence-derived first-trigger and active-
retrigger state laws, but its source controls are temporarily frozen at one real
v1.2.1 ARM mid-control fixture.  Noise/Tone is the preserved physically tested
PERKY2 production path and is not yet the final original-v1.2.1 replacement.
The firmware manifest repeats these limitations so a successful four-voice test
is not confused with final twelve-algorithm sonic qualification.

## Build

From the repository checkout, with the normal Octabam toolchain already set up:

```sh
export OT_PROJECT=/path/to/a/saved/octatrack/project
python3 tools/perky/build_hw4_machine.py
```

Defaults expect:

```text
~/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img
~/Downloads/perkybits
```

Override them with `--firmware` / `--source` or `PERKONS_FIRMWARE` /
`PERKYBITS_ROOT`.

The command runs the local Fold2 and Karplus ARM/DSP evidence chains, assembles
the complete four-engine DSP program, builds the aggressive HW4 remix, injects
private X/Y state including Karplus envelopes/ring at Y:$1000..$1dff, boots the image in the local
emulator, and requires simultaneous varying audio from T1/T2/T5/T6.  It stops
on the first failed gate.

`build_hw4_machine.py` and `build_hw4_release.py` both delegate to
`build_hw4_machine_canary.py`. Qualification, cycle measurement and packaging
therefore consume the same `build_hw4_audition_candidate.py` composition.
Use `--reuse-fixtures` to reuse hash-verified captures while rerunning every
qualification gate; it does not skip qualification. The Karplus envelope tables
occupy Y:$1000 and Y:$12ac, and its feedback ring occupies Y:$1600..$1dff.

The current local qualification blocker is recorded in
[the PERKY handoff](../../../modules/perky/HANDOFF.md). A source checkpoint is
not a packaged or qualified HW4 firmware.

Only after all of those pass does it emit the flashable artifacts, normally:

```text
out/OCTATRACK_PERKYH4.bin
out/OCTATRACK_OS1.40C_PERKYH4.syx
out/mainos_perky_hw4.bin
out/PERKYH4_PERKY_TEST.txt
```

No GitHub Actions/CI or network dependency installation is used.

## Physical test

The first test is deliberately simple: load PERKY on T1, T2, T5 and T6, place
trigs, and verify all four tracks can sound together.  Do not evaluate the
missing algorithm browser yet; engine identity is pinned by track in this image.
Start with both track FX slots empty.  FILTER and DELAY are the only stock effects
expected to remain selectable in this audition profile.
