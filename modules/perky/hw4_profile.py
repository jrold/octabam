"""Static four-voice PĒRKONS audition profile for Octatrack.

This is deliberately smaller than the eventual unrestricted PERKY design.
It mirrors the hardware's four logical voices and three algorithms per voice,
while spreading two logical voices across each Octatrack DSP core.

Global OT tracks are zero based here:
  T1 / track 0 -> PĒRKONS V1
  T2 / track 1 -> PĒRKONS V4
  T5 / track 4 -> PĒRKONS V2
  T6 / track 5 -> PĒRKONS V3

Tracks 1-4 share one DSP and tracks 5-8 share the other. Measured HW4
cycle costs pair V1+V4 and V2+V3 to fit the unchanged two-times model margin.
"""

VOICE_ENGINES = {
    1: (0, 1, 2),     # Fold Drum 1 / Wavetable V1 / Simple Drum
    2: (3, 4, 5),     # Fold Drum 2 / Wavetable V2 / Complex Drum
    3: (6, 7, 8),     # Resonant / Slap / Karplus
    4: (9, 10, 11),   # Noise Hat / Noise-Tone / Acoustic Hats
}

TRACK_VOICE = {
    0: 1,  # OT T1, DSP local slot 0
    1: 4,  # OT T2, DSP local slot 1
    4: 2,  # OT T5, DSP local slot 0
    5: 3,  # OT T6, DSP local slot 1
}

# Names are kept here only as an audit/reference table.  A browser entry must
# not be exposed merely because it appears in this catalog; shipping builders
# still have to prove the corresponding production renderer/control path.
ENGINE_NAMES = (
    "001 FOLD DRUM",
    "002 WAVETABLE V1",
    "003 SIMPLE DRUM",
    "004 FOLD DRUM 2",
    "005 WAVETABLE V2",
    "006 COMPLEX DRUM",
    "007 RESONANT DRUMS",
    "008 SLAP",
    "009 KARPLUS",
    "010 NOISE HAT",
    "011 NOISE/TONE",
    "012 ACOUSTIC HATS",
)

DSP_GROUPS = {
    1: (0, 1),  # global T1/T2; stock core serving tracks 1-4
    0: (4, 5),  # global T5/T6; stock core serving tracks 5-8
}


def voice_for_track(track: int) -> int | None:
    return TRACK_VOICE.get(int(track))


def track_allowed(track: int) -> bool:
    return int(track) in TRACK_VOICE


def engine_allowed(track: int, engine: int) -> bool:
    voice = voice_for_track(track)
    return voice is not None and int(engine) in VOICE_ENGINES[voice]


def local_slot_allowed(local_slot: int) -> bool:
    """Only the first two stock track slots on either DSP are HW4 voices."""
    return int(local_slot) in (0, 1)


def validate() -> None:
    assert set(VOICE_ENGINES) == {1, 2, 3, 4}
    flat = [engine for voice in range(1, 5) for engine in VOICE_ENGINES[voice]]
    assert flat == list(range(12)), flat
    assert set(TRACK_VOICE.values()) == {1, 2, 3, 4}
    assert set(TRACK_VOICE) == {0, 1, 4, 5}
    assert DSP_GROUPS == {1: (0, 1), 0: (4, 5)}
    for track, voice in TRACK_VOICE.items():
        assert track % 4 in (0, 1)
        for engine in range(12):
            assert engine_allowed(track, engine) == (engine in VOICE_ENGINES[voice])


validate()
