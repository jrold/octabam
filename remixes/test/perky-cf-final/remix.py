"""Final four-track ColdFire Perky Machines profile with every stock FX retained."""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-cf-final",
    family="probes",
    proof=Proof.CHECK,
    proof_note=(
        "four independent ColdFire Perky voices; exact native PCM/control gates; "
        "stock DSP boot/payload byte identity required"
    ),
    doc=(
        "Perky Machines final four-algorithm milestone: T1/T2/T5/T6; "
        "SRC A-F = Decay/Tune/Param1/Param2/Mode/Algo; all stock FX retained."
    ),
    modules=(
        "PERKY PROBE",
        "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
        "PLATE REV", "SPRING REV", "DARK REV",
    ),
    fallback="NONE",
)
