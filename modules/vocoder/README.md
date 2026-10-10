# `vocoder` -- VOCODER

A ten-band channel vocoder after the Roland VP-330: the track's audio (a voice) shapes a carrier.

> **It runs on FX2 of tracks 2, 3, 6 and 7 only**, and passes audio through untouched on tracks 1, 4, 5 and 8 and on any FX1 slot. On a MKII two VOCODERs on a DSP core (tracks 1-4 share one, 5-8 the other) play, and a third overran the core (a loud glitch, then no audio and no sequencer until a reboot; OCTABAM7-9, 4 Oct 2026). The real cost is about 850-940 cycles a sample, not the 760 `make cycles` counts (one-word displaced moves measured at about 4 cycles, CHIP.md section 2), and the 3,120 usable already includes the four FX1 FILTERs the pricer does not charge. So the limit is built in rather than documented: a third VOCODER on a core stays dry instead of stalling the unit. It avoids each core's first track (T1, T5). On T1, VOCODER put left-only click bursts into the main out at one phase of the pattern, worst at trigs (measured: Ignorato's MKII, 5 Oct 2026, captured at the main outs; absent with FX2 NONE and on T2 and T3; FAILURE_MODES.md, "Left-only click bursts from VOCODER on T1"). The cause is inferred: an effect at a core's position 0 finishing before the ColdFire's pull, as in "Junk on main R ... T1 with BusDelay", though that entry is main R and 16-24 samples of junk. T5, core 0's first track, is excluded by analogy, not measured.

On the unit it is an FX2 effect. Put it on track 2, 3, 6 or 7, playing a voice, sample or live through a THRU machine: with MODE INT the carrier is built in, two sawtooths an octave apart at NOTE, so turning NOTE (or parameter-locking it on the steps) plays the vocoded voice as a melody. With MODE EXT the carrier is the track's right channel: a THRU track with the voice on input A and a synth on input B. [`DESIGN.md`](DESIGN.md) has the law and the reasons; [`vocoder_ref.py`](vocoder_ref.py) is the float reference the DSP is proved against.

## Knobs

| page | slot | name | range | what it does |
|---|---|---|---|---|
| 1 | 0 | NOTE | C1..C6 | the built-in carrier's pitch, shown as a note; parameter-lock it to play a melody; default C3 |
| 1 | 1 | CONS | 0-127 | consonants: the voice above 4 kHz passed through, as the VP-330's high-consonant circuit does; default 48 |
| 1 | 2 | DRY | 0-127 | the dry voice mixed in; default 0 |
| 1 | 3 | LEVL | 0-127 | output level, 127 = unity; default 100 |
| 2 | 6 | MODE | INT, EXT | the carrier: INT the built-in sawtooths at NOTE; EXT the right channel |

The modulator is the left and right channels averaged (INT), or the left channel (EXT). The output is mono, on both channels.

## Measured

All by `tools/verify/verify_vocoder.py` through `dsp_host` on the audition's scratch image, 4 Oct 2026, unless stated. The test modulator is synthetic: a 120 Hz glottal pulse train through three formants, the vowel changing every 200 ms, with noise bursts for consonants.

- ✅ The output matches the float reference within -62.4 dB (INT at C3) and -64.2 dB (EXT with a chord carrier), level within 0.001 dB. The difference is the band sum's 24-bit rounding (it was -85.7 dB with a 48-bit sum, which cost two moves a band); it exists only while a band is active.
- ✅ Silence in gives silence out, bit-exact, with CONS and DRY up.
- ✅ 0.3 s into a pause the output is -136.3 dBFS: the envelopes decay in 48 bits (in 24 they stuck at about -90 dBFS and let the carrier through between words).
- ✅ A sine at a band's centre keeps that band at least 18.6 dB above its neighbours.
- ✅ NOTE: C1, C3 and C6 within 0.05 % (measured 32.703, 130.813 and 1046.503 Hz); a saved NOTE past C6 plays C6.
- ✅ Every knob at both ends renders.
- ✅ Two per core, built in: it runs at r7 0x6500 and 0x6800 (the FX2 state blocks of a core's second and third tracks) and is an exact dry pass at the other FX2 blocks (0x6200, 0x6b00) and every FX1 block (0x6100, 0x6400, 0x6700, 0x6a00).
- 🟡 760 counted cycles a sample (`make cycles REMIX=vocoder`); `make accept` passes, pricing four on a core at 3,040. On the unit this is not true: see the status note above. The first version counted 1,085 (three on a core stalled the unit on OCTABAM7); the parallel-move rewrite, a peak-detector envelope, a 24-bit band sum and the tables in X memory (DJ EQ out of the remix) brought the count down, but three on a core with FX1 FILTERs still overrun (OCTABAM8 and OCTABAM9).
- Listened to (4 Oct 2026): a LibriVox reading (public domain) through this DSP code in `dsp_host`, at C3, C2, without consonants, a melody parameter-locked per 1/8 and an external chord carrier; judged intelligible and "really good" by the tester. The design was chosen by ear and measurement: the VP-330's steep bands against a first law with shallow ones (DESIGN.md).

## On the unit

- OCTABAM7-9 (Ignorato's MKII, 4 Oct 2026, by ear): VOCODER plays and is intelligible; one or two per core play; a third on a core (FX1 = FILTER) overran it, a loud glitch, then no audio or sequencer until a reboot.
- ✅ OCTABAM12 (`make image REMIX=vocoder BUILD=12`, from the card), same unit and day, by ear: on the Octatrack Advisor's project with VOCODER on FX2 of T1, T2 and T3 (the set that stalled OCTABAM9), T1 and T2 vocode and T3 passes its audio dry; with T4 added, T4 is dry too; then VOCODER on FX2 of all eight tracks: T1, T2, T5 and T6 vocode, T3, T4, T7 and T8 are dry, stable on both cores. Those were the earlier positions.
- 🟡 The current positions (T2, T3, T6, T7) are not flashed on this build. They were heard clean on the 0.2 code (OCTABAM20, branch `vocoder-0.2` at `f83463c8`; Ignorato's MKII, 5 Oct 2026, by ear): alone and with two per core, through trigs and knob sweeps, T1 dry.

## Open

- The VP-330's ensemble (a bucket-brigade chorus on its output) is not modelled; a chorus on the Octatrack's FX would come after FX2's output only on another track.
- More than two per core: getting four to fit beside four FILTERs needs under about 590 real cycles each; until then the limit is built in.
- The pricing gap is worth reporting upstream: displaced moves and table reads counted as one cycle, and FX1 FILTERs not charged against a budget that contains them.

## Gates

- `tools/verify/verify_vocoder.py` (the manifest's `Gate`). It refuses to run if the id resolves to SEND's entry points.
- `make check REMIX=vocoder`; with `OT_PROJECT=<a project>` it adds `verify_set` under the ColdFire port.

## Design

[`DESIGN.md`](DESIGN.md): the VP-330 as documented, why the bands are steep, what the 24-bit version changed and why, the r7 slots and the tables.
