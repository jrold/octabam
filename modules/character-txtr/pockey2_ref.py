"""Airwindows Pockey2 (Chris Johnson, MIT, 2022) -- the float reference the
TXTR port is proven against (tools/verify/verify_character.py). A direct
transcription of Pockey2Proc.cpp's processReplacing at 44.1 kHz with the
dither left out; A = TXTR/128 (the hold), B = 1 - TXTR/128 (the resolution),
wet = 1."""
import math

PHI = 0.618033988749894848204586


def params(k: int):
    A, B = k / 128, 1 - k / 128
    freq = math.floor(pow(A, 3) * 32.0)
    rez_factor = int(pow(2, 4 + B * 12.0))
    return freq, rez_factor


def _enc(x):
    x = max(-1.0, min(1.0, x))
    if x > 0: return math.log(1.0 + 255 * abs(x)) / math.log(255)
    if x < 0: return -math.log(1.0 + 255 * abs(x)) / math.log(255)
    return x


def _dec(x):
    x = max(-1.0, min(1.0, x))
    if x > 0: return (pow(256, abs(x)) - 1.0) / 255
    if x < 0: return -(pow(256, abs(x)) - 1.0) / 255
    return x


class Pockey2:
    def __init__(self, k):
        self.freq, self.rez = params(k)
        self.position = 0
        self.held = [0.0, 0.0]; self.last = [0.0, 0.0]; self.prev = [0.0, 0.0]

    def frame(self, xs):
        coded = []
        for x in xs:
            y = _enc(x) * self.rez
            y = math.floor(y) if y > 0 else (-math.floor(-y) if y < 0 else y)
            coded.append(_dec(y / self.rez))
        blur = [max(0.0, PHI - abs(coded[c] - self.last[c])) for c in (0, 1)]
        if self.position < 1:
            self.position = self.freq
            self.held = list(coded)
        out = [self.held[c] * blur[c] + self.prev[c] * (1.0 - blur[c]) for c in (0, 1)]
        self.last = list(xs)
        self.prev = list(self.held)
        self.position -= 1
        return out

    def process(self, L, R):
        o = [self.frame((a, b)) for a, b in zip(L, R)]
        return [v[0] for v in o], [v[1] for v in o]
