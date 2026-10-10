"""STEMS -- STEM REC on the stock effects.

Every track to the card while the sequencer plays, one file each, from
MAIN MENU > STEMS, streamed while it records (git show 4d2d6456:docs/superpowers/
specs/2026-09-22-stem-rec-streaming-design.md). No octabam DSP: the 14
stock effects are listed so the FX2 chooser is stock's. STEMS1 listed STEM
REC alone and drew a one-row chooser with nothing in it (Yves's MKII,
30 Sep 2026); ok-ms lists them for the same reason.
"""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="stems",
    family="mods", proof=Proof.HARDWARE, proof_note="Yves's MKII, 6 Oct 2026 (STEMS3)",
    doc="STEM REC on the stock effects: multitrack recording to the card, each track, MAIN, CUE and the inputs as separate WAV files.",
    modules=("STEM REC",
             "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
             "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
             "PLATE REV", "SPRING REV", "DARK REV"),
    fallback="NONE",
)
