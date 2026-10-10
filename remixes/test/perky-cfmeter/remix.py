"""Perky Machines + CF METER: the ColdFire's real per-frame cost, on the unit.

DIAGNOSTIC, not a release profile. CF METER wraps the frame interrupt
(vector 0x41) to time it and reads the numbers out on T8's FX2, and it
needs a DSP insert and FILTER's FX2 id; the insert's words are DARK REV's.
So two of the fourteen stock effects are given up for the measurement --
neither runs on the ColdFire, and both are back in `perky-cf-final`.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-cfmeter",
    family="probes",
    proof=Proof.PORT,
    proof_note=(
        "four independent ColdFire Perky voices plus the CF METER frame-interrupt "
        "probe; the instrument for pricing the Perky frame on hardware"
    ),
    doc=(
        "Perky Machines (T1/T2/T3/T4) with CF METER on T8's FX2: the frame "
        "interrupt's mean/longest duration and the frame period, on the unit. "
        "Diagnostic only -- FILTER and DARK REV are given up to the probe."
    ),
    modules=(
        "PERKY PROBE",
        "CF METER",
        "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
        "PLATE REV", "SPRING REV",
    ),
    fallback="NONE",
)
