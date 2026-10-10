# TESTGEN: design note

The knobs, the signals' levels and every measured figure are in [`README.md`](README.md); this note keeps the reasons behind the design. Status: 0.1 on hardware since OCTABAM4; 0.2's NEEDLE, DC and FX1 listing on hardware as OCTABAM10; FX1-only in the emulator so far (README, On the unit).

## What it is

An Octabam FX1 insert that **replaces** its track's audio with an exact, reproducible test signal. Put it on any track, play a trig (or use a THRU machine), and that track's output (analogue, or a channel of Octabam's USB audio out) carries a known signal. Uses:

- measuring the Octatrack's own path: level, frequency response, noise, distortion, channel mapping, latency;
- measuring Octabam's USB audio on a host: dropouts, latency, the order of channels at stream start;
- proving other modules' claims: a sweep through any FX chain gives its impulse and frequency response by deconvolution.

## Signals

| MODE | Signal | Why this form |
|---|---|---|
| SINE | A sine at FREQ, tuned by FINE | A 24-bit phase accumulator and a quarter-wave odd polynomial (max error 3.4e-9, -169 dB), with rounding multiplies: truncation left the peak 5 LSB short of full scale. Measured THD -149.5 dB at 1 kHz, -140.5 dB at 100 Hz (`verify_testgen`) |
| SWEEP | An exponential (Farina) sweep, 20 Hz to 20 kHz over LEN seconds, then 1 s of silence, repeating | A 48-bit increment grown by a constant ratio each sample: no per-sample exp, and the law is modelled bit for bit in `testgen_ref.sweep_phases`, so a capture deconvolves with its exact inverse. The silence lets a path's tail ring out and marks where each period starts |
| PINK | WHITE through Paul Kellet's three-pole filter, one per channel | A cheap, well-known approximation; its slope is gated, -3 dB/octave within 0.3 |
| WHITE | x' = 0x5DEECE66D x + 11 mod 2^46 (drand48's multiplier), the sample its top 23 bits, one generator per channel | A 24-bit generator came first: its low bits repeated on short cycles (the low 16 every 1.5 s, -48 dB under the noise). x is held as two 23-bit halves, so every product has non-negative operands. R starts 0x3243f6a8885 steps ahead of L: a half-period jump only flips the top bit, so R would be a fixed function of L; the irregular jump was tested (cross-correlation and a 2-D chi-square) |
| IMPULSE | One full-scale sample every LEN/4 seconds | Exact; its period is computed from the sweep's length rather than tabled, to save words |
| NEEDLE | One full-scale sample every P = round(2^24 / inc) samples: the whole period nearest FREQ and FINE | A strictly periodic train has a clean line spectrum; a phase-accumulator train would hit the exact frequency on average but jitter by a sample, spreading spurs between the lines. P comes from one 48-by-24 integer division per block, and the train reuses IMPULSE's loop |
| DC | Full scale on every sample, times LEVL | IMPULSE's loop with a period of one: no code of its own |

Any change of MODE, FREQ or LEN restarts every generator from the same state (FINE does not, so tuning by ear is smooth), so a capture lines up with the reference from the change on.

LEVL 0 is silent and the default: the first image started a -6 dBFS tone on insert, which the tester found hard on ears and speakers. FREQ is a select shown in Hz for a reason the tester also gave: as a plain 0-127 knob, its 31 steps sat in the first quarter of the turn.

## DSP56300 constraints (Octabam's rules)

- No per-sample division, log or exp: the sweep's ratio, the sine's polynomial and FINE's 2^x (a quartic within 0.19 ppm, per block) are all multiplies; levels come from a table per block.
- FX1 only (`Claims.fx1_only`, Spectrum's idiom): init reads the allocator base, and an FX2 instance returns before it touches a frame. A source belongs at the head of the chain, and two in series on one track crackled on the unit (cause not found). No buffers, no lookahead. 150 cycles a sample at most, in PINK and WHITE (two generators and two filters); SWEEP 85, SINE 51, IMPULSE, NEEDLE and DC 18.
- Size: PLATE REV's 594 words. The first full build was one word over; then the impulse table went, the sine core became a shared subroutine (for FINE and A440), and short-form compares, one restart routine for init and proc and one noise routine for both channels made room for the stereo noise: 588 words (396 of code, 192 of table). For 0.2 the sweep's length table went too (it is (t + 1) 44100, one multiply), which paid for NEEDLE and DC: 594 words exactly (418 of code, 176 of table). FX1-only cost about ten words more; reading the tables at (r4+n4), a shorter division for NEEDLE, -g kept in a register and `lua` paid for it: 592 words (416 of code), 2 spare.
- Output replaces the input: a THRU track becomes a signal source.

## The reference (testgen_ref.py)

Every signal as the module computes it (the sweep's and the noise's integer laws exactly), plus the analysis the gate uses: THD of the sine, deconvolution of the sweep (Farina inverse filter), the octave-band slope of the noise. The self-check proves the analysis on ideal signals; `verify_testgen` proves the module against the same reference.

## What would falsify it

- A sine whose THD is above -120 dB in `dsp_host`, or a frequency off its stated value by more than the accumulator's resolution.
- A sweep whose deconvolved impulse response shows anything but a single clean peak through an identity path.
- Noise that differs from the reference's generator, L and R correlated with CHAN L+R, or pink octave bands off -3 dB/octave by more than the stated tolerance.
