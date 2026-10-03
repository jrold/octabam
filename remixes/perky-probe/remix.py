"""Isolated PERKY ColdFire -> transport -> DSP source-seam canary."""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-probe",
    family="mods",
    proof=Proof.CHECK,
    proof_note="development canary; hardware flash pending",
    doc="FLEX source probe proving PK/Y1 transport and sample-offset DSP injection before AMP/FX.",
    modules=(
        "PERKY PROBE",
        "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
        "PLATE REV", "DARK REV",
    ),
    fallback="NONE",
)
