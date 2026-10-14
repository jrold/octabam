"""octabam-core -- the core ColdFire modules on the 14 stock effects.

CORE (BRAIN, STORE, KITS, MIDI SCENES, SCENES P2, PLOCKS P2, CC MAP, CC FEEDBACK,
USB MIDI, USB AUDIO OUT MAIN CUE, the recorder and bug fixes, MUTE_MODES from
DRAM, SCALE QUANTIZER, TUNER, DIRECT_JUMP_KYOTI, RELOAD_FROM_PROJECT, RLEN PLEN)
with all 14 stock effects and LOFI AMF FIX. No octabam DSP code and no LOAD
METER (its DSP half needs 156 words per payload; the 14 stock effects leave none).
"""

from remix.schema import Pin, Proof, Remix

CORE = ("BRAIN", "STORE", "KITS", "MIDI SCENES", "SCENES P2", "PLOCKS P2",
        "CC MAP", "CC FEEDBACK", "USB MIDI", "USB AUDIO OUT",
        "RECORDER LOOP FIX", "BATCH_BUGFIXES", "ERASE_EMPTY_TRIGLESS_LOCKS",
        "QUANTIZE_LIVE_REC_TOGGLE", "REC_TRIG_MUTE", "MUTE_MODES",
        "SCALE QUANTIZER", "TUNER", "DIRECT_JUMP_KYOTI", "RELOAD_FROM_PROJECT", "RLEN PLEN")
STOCK14 = ("FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS", "SPATIALIZER",
           "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY", "PLATE REV", "SPRING REV", "DARK REV")

REMIX = Remix(
    name="octabam-core",
    family="mods", proof=Proof.PORT, proof_note="",
    doc="The core ColdFire modules on the 14 stock effects, with LOFI AMF FIX.",
    modules=CORE + ("LOFI AMF FIX",) + STOCK14,
    fallback="NONE",
    settings={("octabam.usb-audio-out", "LAYOUT"): Pin("MAIN CUE"),
              ("kyoti.mute-modes", "PLACE"): Pin("DRAM")},
)
