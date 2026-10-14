"""bus-notempo -- bus with TEMPO SYNC's CAVE at OFF: a diagnostic image.

scripts/refhash.sh builds it (case notempo). BusDelay's panel name
reads BusDlyNOC. Not a remix to flash for playing.
"""

from remix.schema import Pin, Proof, Remix

REMIX = Remix(
    name="bus-notempo",
    family="reference", proof=Proof.PORT, proof_note="",
    doc="bus with TEMPO SYNC's CAVE pinned OFF (diagnostic).",
    modules=("REVERB SERVER", "DELAY SERVER", "SEND", "TEMPO SYNC"),
    fallback="SEND",
    settings={("octabam.tempo-sync", "CAVE"): Pin("OFF")},
)
