"""Reduced Perky DSP machine: T1/T5, three algorithms, measured FX sacrifice.

This remix packages the COMPOSED reduced Perky DSP machine:

* only Octatrack track 1 (payload B) and track 5 (payload A) are Perky-capable,
  so there is exactly one Perky voice per DSP core;
* each of those tracks exposes exactly three algorithms -- Fold Drum 1,
  Resonant Bass and Resonant Snare -- one at a time;
* tracks 2-4 and 6-8 stay ordinary Octatrack tracks, and FX1+FX2 remain
  available on all eight.

THE FX SACRIFICE IS MEASURED, NOT CHOSEN. `tools/verify/verify_perky_3algo_sacrifice.py`
links the composed source and compares it against the stock effect spans read
out of the pristine 1.40C MAIN OS:

    composed Perky DSP program .............. 3,936 P words (per payload)

    nothing removed ......................... short 3,936
    SPRING REV only ......................... short 2,873
    PLATE + SPRING + DARK (the stock donor) .. short 1,212
    + COMPRESSOR ............................ short 1,032
    + LO-FI ................................. short   495
    + DJ EQ ................................. short   150
    + COMB FILTER ........................... FITS

So Spring alone is not enough, and this is the first configuration that fits.
The sacrificed effects are the three reverbs plus COMPRESSOR, LO-FI, DJ EQ and
COMB FILTER; the contiguous run they form is P:0x1000..0x1fdf on payload A and
P:0x0dc0..0x1d9f on payload B -- 4,063 words each.

Retained and still callable: FILTER, SPATIALIZER, EQUALIZER, PHASER, FLANGER,
CHORUS.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-dsp-3algo",
    family="probes",
    proof=Proof.CHECK,
    proof_note="composed reduced Perky DSP machine; renderer equivalence and "
               "sacrifice measured, execution/placement qualification pending",
    doc=(
        "Reduced Perky DSP machine: T1/T5 only, one voice per core, three "
        "algorithms each. FX sacrifice measured at 3,936 composed P words."
    ),
    # DELAY is deliberately NOT listed. Its FX1 id (0x08) is in
    # `stock.fx1_ids()`, and `_listed` adds every effect whose id appears
    # there, so listing it silently pulls the whole FX1 row back in and the
    # harvest collapses to just the three reverbs (2,724 words -- measured,
    # and the reason the first attempt at this remix overran). DELAY's DSP
    # dispatch is stock's null stub anyway; the row is written by the build's
    # own DELAY rule without being listed here.
    modules=(
        "PERKY PROBE",
        "FILTER", "EQUALIZER", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER",
    ),
    fallback="NONE",
)
