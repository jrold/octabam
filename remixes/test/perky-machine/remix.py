"""PERKY two-voice development remix retaining every mandatory stock effect.

Only Plate Reverb and Compressor are omitted. The tracked module is the tiny
impulse probe; the light2 canary upgrades it with the four-engine source,
fragmented P placement, and the existing ColdFire machine/control runtime.
Spring and Dark remain on FX2 (their stock slots); Lo-Fi remains on both.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-machine",
    family="probes",
    proof=Proof.CHECK,
    proof_note="development full PERKY machine; emulator/hardware qualification pending",
    doc=(
        "Full PERKY source-machine canary: chooser/signature/UI/control runtime "
        "plus fragmented DSP renderer; only Plate and Compressor omitted."
    ),
    modules=(
        "PERKY PROBE",
        "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "DELAY",
        "SPRING REV", "DARK REV", "LO-FI",
    ),
    # FX1 accepts only its stock effects. Spring/Dark/Delay are retained on
    # FX2 by modules above. Both choosers omit only Plate and Compressor.
    fx1=(
        "FILTER", "SPATIALIZER", "EQUALIZER", "DJ EQ", "PHASER",
        "FLANGER", "CHORUS", "COMB FILTER", "LO-FI",
    ),
    fallback="NONE",
)
