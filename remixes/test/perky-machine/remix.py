"""PERKY Noise/Tone full machine development canary.

The build wrapper upgrades the tracked PERKY PROBE module in memory only with
machine.s, generated control.s and the complete packed Noise/Tone DSP source.
PLATE/SPRING/DARK are omitted so the correctness-first renderer owns their
contiguous donor P region. The tracked impulse probe remains unchanged.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-machine",
    family="probes",
    proof=Proof.CHECK,
    proof_note="development full PERKY Noise/Tone machine; emulator/hardware qualification pending",
    doc=(
        "Full PERKY Noise/Tone source-machine canary: chooser/signature/UI/control "
        "runtime plus packed DSP renderer; three stock reverbs intentionally omitted."
    ),
    modules=(
        "PERKY PROBE",
        "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
    ),
    fallback="NONE",
)
