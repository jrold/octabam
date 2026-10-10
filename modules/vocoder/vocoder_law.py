"""VOCODER's constants and coefficient arithmetic, without numpy: the manifest builds the
P table from these, and vocoder_ref.py (the float reference) uses the same functions."""
import cmath
import math

FS = 44100.0
CENTRES = (200, 280, 400, 600, 900, 1300, 2000, 2800, 4000, 6000)
Q_BAND = 7.0
EMPH, TILT_DB = 0.9, 9.0
RELEASE_MS = 10.0                 # the envelope is a peak detector: instant attack
MAKEUP_SHIFT = 8
NOTE_LO, NOTE_HI = 24, 84                    # C1 .. C6, NOTE step 0 .. 60
K_BLEP = 11                                  # 1/du is held as 1/(du 2^11)
HP_FC, HP_Q = 4000.0, (0.5176, 0.7071, 1.9319)
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def chamberlin_bp(f, q):
    """Band-pass with the input scaled by q: B/X = f q (1 - z^-1) / (1 + (f^2 + f q - 2) z^-1 + (1 - f q) z^-2)."""
    return [f * q, -f * q], [1.0, f * f + f * q - 2.0, 1.0 - f * q]


def band_coefs():
    """Per band (f1, f2, W/2): the pair's tuning and the folded weight, halved to stay below 1."""
    q = 1.0 / Q_BAND
    out = []
    for k, fc in enumerate(CENTRES):
        f1, f2 = (2 * math.sin(math.pi * fc * r / FS) for r in (0.91, 1.10))
        z = cmath.exp(-1j * 2 * math.pi * fc / FS)
        g = 1.0
        for f in (f1, f2):
            b, a = chamberlin_bp(f, q)
            g *= abs((b[0] + b[1] * z) / (a[0] + a[1] * z + a[2] * z * z))
        emph = abs(1 - EMPH * z)
        tilt = 10 ** (-TILT_DB * k / (len(CENTRES) - 1) / 20)
        out.append((f1, f2, emph * tilt / (g * g) / 2))
    return out


def note_name(step):
    n = NOTE_LO + step
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


def note_inc(step):
    """The phase increment for NOTE step (a cycle is 2^24 of the 24-bit signed phase)."""
    f = 440.0 * 2 ** ((NOTE_LO + step - 69) / 12)
    return round(f / FS * (1 << 24))


def note_idt(step):
    """1/(du 2^11), du = inc / 2^24 the phase step as a fraction of a cycle (Q23 < 1)."""
    return (1 << 24) / note_inc(step) / (1 << K_BLEP)
