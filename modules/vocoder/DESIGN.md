# VOCODER: design note

The knobs and the measured figures are in [`README.md`](README.md); this note keeps the reasons.

## The model: the Roland VP-330

From the VP-330 service notes (Roland, 21 Sept 1979, on archive.org as `ROLAND_VP330_service_notes`), checked in the text: "ten BPFs with a high Q" covering 170 Hz to 7 kHz, at 200, 280, 400, 600, 900, 1.3k, 2k, 2.8k, 4k and 6k Hz (the FLH16 table); the microphone compressed and pre-emphasised before analysis; a synthesis response "equal to de-emphasized characteristics"; a "High Consonant Circuit" that passes the voice's top end to the output. Read from the schematic, with moderate confidence (a low-resolution scan): each band is two 2nd-order band-passes tuned apart, on both the analysis and the synthesis side; peak-detector envelopes with about 10 ms of release; the consonant high-pass is 6th order near 4 kHz; no noise generator in the vocoder.

## Why the bands are steep

The first version used sixteen 2nd-order bands. It sounded like a vocoder but the words were lost: a 2nd-order band is only about 6 dB down at its neighbour, so each envelope averages over two octaves and the formants smear, while the long-term spectrum still looks right. The VP-330's pairs are about 18 dB down at the neighbour. On the same voice (a public-domain LibriVox reading) the VP-330 law scored 0.816 on STOI against 0.764 for the same design with 2nd-order bands, and the tester heard the steep version as "clearly better" and "very intelligible". The vocoder literature agrees: spectral contrast matters more than the number of bands (Shannon et al. 1995; Xu, Thompson and Pfingst 2005; Fu and Nogaki 2005).

## The 24-bit version, and what changed

- Each band section is a Chamberlin state-variable filter with its input scaled by q = 1/7, so the section peaks at its input's level and no state outgrows the 24-bit range. Two words of state a section; four sections a band (two on the voice, two on the carrier).
- The pre-emphasis is folded into each band's output weight, with the de-emphasis (9 dB across the bands) and the pair's gain at its centre. Ahead of the filters it cut the 200 Hz band by about 20 dB, which left its rounding 51 dB under the signal; folded, the law matches the float model within 0.9996 correlation.
- The envelope followers hold 48 bits. In 24 their release step fell below one unit near zero, so they stuck at about -90 dBFS, and with the make-up gain the carrier leaked into the pauses.
- The envelope is a peak detector, e = max(v, e (1 - 0.00227)): instant attack and a 10 ms release, the VP-330's diodes. (The first version had a 0.3 ms attack; the detector is cheaper and closer to the original.)
- The band sum is 24 bits, rounded: with 48 it cost two moves a band, and four instances did not fit a core. Its rounding sits about 62 dB under the vocoded signal and is zero in a pause.
- The VP-330's extra 2.2 ms envelope smoother is left out: with it, ten bands would need 120 of the 132 state words. Without it the output differs by about 19 dB under the signal, slightly buzzier; STOI was unchanged (0.828).
- The built-in carrier is the VP-330's 8' and 4' ramps: two polyBLEP sawtooths on one phase, the 4' being the phase doubled. The polyBLEP correction is branch-free: (1 - min(u/du, 1))^2 - (1 - min((1 - u)/du, 1))^2, with 1/du from a table per NOTE. At C6 the aliasing in the bands is 61 dB under the harmonics.

## r7 slots and tables

The header of `vocoder.asm` has the slot map (ten blocks of ten words, the carrier phase, the consonant filter, per-sample and per-block scratch: 127 of the 132) and the P table (each band's coefficients in the order the loop reads them, the NOTE increments and their reciprocals: 172 words). The band loop walks its states with (r5)+ so the filter arithmetic carries its loads and stores as parallel moves; scratch sits low so its moves take one word. `vocoder_law.py` computes the tables for the manifest; `vocoder_ref.py` uses the same functions, so the two cannot disagree.

## What would falsify it

- The DSP differing from `vocoder_ref.py` by more than -50 dB, or in level by more than 0.1 dB.
- Carrier audible in a pause: above -100 dBFS 0.3 s after the voice stops.
- A centre sine leaking into a neighbouring band less than 15 dB down.
