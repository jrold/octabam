"""Perky Machines + CF METER + CF METER IDLE: one flash, frame cost and idle.

DIAGNOSTIC, not a release profile. CF METER wraps the frame interrupt
(vector 0x41) and times it; CF METER IDLE times main's idle loop on DMA
timer 3 and adds its reading to the same T8 telemetry. Together one flash
reports the frame interrupt's cost AND how much slack main has left, which
is the pair needed to explain audio-landing-immediately while the screen
lags. FILTER and DARK REV are given up to the probe; both are back in
`perky-cf-final`.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-cfmeter-idle",
    family="probes",
    proof=Proof.PORT,
    proof_note=(
        "four independent ColdFire Perky voices plus the CF METER frame-interrupt "
        "probe and the idle-loop probe; the instrument for pricing the Perky frame "
        "and main's remaining slack on hardware at once"
    ),
    doc=(
        "Perky Machines (T1/T2/T3/T4) with CF METER and CF METER IDLE on T8's FX2: "
        "the frame interrupt's mean/longest duration, the frame period, and main's "
        "idle share, on the unit. Diagnostic only -- FILTER and DARK REV are given "
        "up to the probe."
    ),
    modules=(
        "PERKY PROBE",
        "CF METER",
        "CF METER IDLE",
        # FILTER is KEPT: every reference cfmeter remix (cfmeter, cfmeter-post,
        # cfmeter-tracks, cfmeter-port) lists it, and a project whose tracks use
        # FILTER on FX1/FX2 loses its audio without it. The probe takes DARK REV's
        # words, not FILTER's id.
        "FILTER",
        "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
        "PLATE REV", "SPRING REV",
    ),
    fallback="NONE",
)
