"""Static four-voice PĒRKONS audition image.

This is intentionally an aggressive test remix, not the long-term feature mix.
Only stock FILTER and DELAY are retained while the HW4 synth owns the contiguous
DSP effect-code run needed for four hardware-style voices.  DELAY is ColdFire
and consumes no DSP P words.

The explicit FX1 list matters: leaving it empty means "stock FX1 chooser", which
would keep the omitted stock effects alive and therefore make their P code
unharvestable.  FILTER is the only stock DSP insert retained on either chooser.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-hw4",
    family="probes",
    proof=Proof.CHECK,
    proof_note="four-voice PERKY audition profile; physical hardware pending",
    doc=(
        "Four-voice hardware-style PERKY audition image. T1/T2/T5/T6 host "
        "V1/V3/V2/V4; stock FILTER and DELAY retained, other stock DSP FX "
        "temporarily harvested for synth code/data qualification."
    ),
    modules=(
        "PERKY PROBE",
        "FILTER",
        "DELAY",
    ),
    fallback="NONE",
    fx1=("FILTER",),
)
