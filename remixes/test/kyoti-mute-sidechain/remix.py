"""stock effects with MUTE_MODES and SIDECHAIN_COMPRESSOR together: a muted KEY track keeps feeding the compressor (SC_KEY)."""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="kyoti-mute-sidechain",
    family="mods", proof=Proof.CHECK, proof_note="",
    doc="stock effects with MUTE_MODES and SIDECHAIN_COMPRESSOR together: a muted KEY track keeps feeding the compressor (SC_KEY).",
    modules=("MUTE_MODES",
             "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
             "CHORUS", "SPATIALIZER", "COMB FILTER", "SIDECHAIN_COMPRESSOR", "LO-FI",
             "DELAY", "PLATE REV", "DARK REV"),
    fallback="NONE",
)
