"""Exact Complex state overlay used by the one-voice-per-core profile.

Keep the common Simple envelope/control offsets; put the second oscillator
after them. The original 42-word/ARM geometry stays the reference seam.
"""
import complex_drum_compact as original

ORDER = tuple(range(10)) + tuple(range(18, 42)) + tuple(range(10, 18))


def from_original(words):
    assert len(words) == original.WORDS
    return [words[i] for i in ORDER]


def to_original(words):
    assert len(words) >= original.WORDS
    result = [0] * original.WORDS
    for i, field in enumerate(ORDER):
        result[field] = words[i] & 0xffff
    return result
