"""PERKY Noise/Tone synth canary.

The normal perky-probe test keeps PLATE/DARK and therefore proves the source
transport in a deliberately small donor footprint. This next-layer canary
omits all three stock reverbs so Octabam may harvest their contiguous P region
for the correctness-first complete Noise/Tone renderer. The build wrapper
supplies that generated renderer source only for this invocation; the PERKY
module manifest on disk still points at the impulse probe.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-synth",
    family="probes",
    proof=Proof.CHECK,
    proof_note="development Noise/Tone synth canary; hardware flash pending",
    doc=(
        "PERKY Noise/Tone source canary using full packed X/Y state and the "
        "three-reverb donor region; stock reverbs intentionally omitted."
    ),
    modules=(
        "PERKY PROBE",
        "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
    ),
    fallback="NONE",
)
