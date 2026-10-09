"""stock effects with REPITCH_REPEAT98_KYOTI: RPCH / RPS9 / RPSP and QUAN; SPRING REV gives up its words: its P run for the DSP kernel, its own X data for the two table blocks (#603)."""

from remix.schema import Proof, Remix

REMIX = Remix(
    name="repitch-repeat98-kyoti",
    family="mods", proof=Proof.CHECK, proof_note="",
    doc="stock effects with REPITCH_REPEAT98_KYOTI: RPCH / RPS9 / RPSP and QUAN; SPRING REV gives up its words: its P run for the DSP kernel, its own X data for the two table blocks (#603).",
    modules=("REPITCH_REPEAT98_KYOTI",
             "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
             "CHORUS", "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI",
             "DELAY", "PLATE REV", "DARK REV"),
    fallback="NONE",
)
