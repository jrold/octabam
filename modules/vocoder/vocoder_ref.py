#!/usr/bin/env python3
"""Float reference for VOCODER: the law in the form the DSP computes it.

A ten-band channel vocoder after the Roland VP-330 (service notes, 21 Sept 1979: ten high-Q
band-pass filters, centres 200 Hz to 6 kHz, pre-emphasis before analysis and a de-emphasised
synthesis response, a high-consonant circuit). modules/vocoder/DESIGN.md has the reasons.

  modulator m = (L + R)/2 (MODE INT) or L (MODE EXT); carrier c = the internal 8' and 4'
    sawtooths at NOTE (INT) or R/2 (EXT)
  each band k: two Chamberlin band-pass sections, at fc x 0.91 and fc x 1.10, Q 7, the input
    scaled by q = 1/7 so each section peaks at the input's level; the same pair on m and on c
  envelope: v = (W_k / 2) |band_k(m)|; e = max(v, e (1 - ad)), ad for 10 ms: a peak
    detector, instant attack, as the VP-330's diodes; 48-bit
  out = LEVL limit(2^8 sum_k e_k band_k(c) + (CONS/32) hp6(m/2) + (DRY/128) m)
  W_k folds in the VP-330's pre-emphasis (1 - 0.9 z^-1 at fc), its de-emphasis (a 9 dB fall
    across the bands) and the pair's gain at fc (1/g^2), so the bass bands are not starved
    of level before the 24-bit filters
  hp6: the modulator at half level through three Chamberlin high-pass sections at 4 kHz
    (a 6th-order Butterworth: Q 0.518, 0.707, 1.932)
  sawtooths: polyBLEP, branch-free: corr = (1 - min(u/du, 1))^2 - (1 - min((1-u)/du, 1))^2

    python3 modules/vocoder/vocoder_ref.py      # self-check
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocoder_law import (FS, CENTRES, Q_BAND, EMPH, TILT_DB, RELEASE_MS,  # noqa: F401
                         MAKEUP_SHIFT, NOTE_LO, NOTE_HI, K_BLEP, HP_FC, HP_Q, NOTE_NAMES,
                         band_coefs, note_name, note_inc, note_idt)


def _saw(n, inc, idt, octave):
    """The DSP's sawtooth: signed 24-bit phase (a cycle is 2^24), polyBLEP, x2 for the 4' octave."""
    out = np.empty(n)
    p = 0
    for i in range(n):
        s = p << octave & 0xFFFFFF
        s = (s - (1 << 24) if s & 0x800000 else s) / (1 << 23)          # [-1, 1)
        u = s / 2 + 0.5
        it = idt / (1 << octave)
        ta = min(u * it * (1 << K_BLEP), 1.0)
        tb = min((1 - u) * it * (1 << K_BLEP), 1.0)
        out[i] = s + (1 - ta) ** 2 - (1 - tb) ** 2
        p = (p + inc) & 0xFFFFFF
    return out


def carrier_int(step, n):
    inc, idt = note_inc(step), note_idt(step)
    return 0.3 * _saw(n, inc, idt, 0) + 0.2 * _saw(n, inc, idt, 1)


def _svf_bp(x, f, q):
    low = band = 0.0
    y = np.empty_like(x)
    for i, v in enumerate(x):
        low += f * band
        band += f * (q * v - low - q * band)
        y[i] = band
    return y


def _svf_hp(x, f, q):
    low = band = 0.0
    y = np.empty_like(x)
    for i, v in enumerate(x):
        low += f * band
        h = v - low - q * band
        band += f * h
        y[i] = h
    return y


def vocode(L, R, mode=0, note=24, cons=48, dry=0, levl=100):
    """MODE 0 INT, 1 EXT; knob values as the panel gives them. Returns the mono output."""
    L = np.asarray(L, float); R = np.asarray(R, float); n = len(L)
    m = (L + R) / 2 if mode == 0 else L
    c = carrier_int(note, n) if mode == 0 else R / 2
    q = 1.0 / Q_BAND
    ad = 1 - math.exp(-1 / (FS * RELEASE_MS * 1e-3))
    acc = np.zeros(n)
    for f1, f2, w in band_coefs():
        a = _svf_bp(_svf_bp(m, f1, q), f2, q)
        b = _svf_bp(_svf_bp(c, f1, q), f2, q)
        e = np.empty(n); ev = 0.0
        for i, v in enumerate(w * np.abs(a)):
            ev = max(v, ev * (1 - ad))               # a peak detector: instant attack
            e[i] = ev
        acc += e * b
    hf = 2 * math.sin(math.pi * HP_FC / FS)
    hp = m / 2
    for qq in HP_Q:
        hp = _svf_hp(hp, hf, 1 / qq)
    y = np.clip(acc * (1 << MAKEUP_SHIFT) + (cons / 32.0) * hp + (dry / 128.0) * m, -1.0, 1.0 - 2 ** -23)
    lv = 1.0 if levl >= 127 else levl / 128.0
    return y * lv


if __name__ == "__main__":
    ok = True
    cf = band_coefs()
    print("f1", [round(x, 5) for x, _, _ in cf]); print("f2", [round(x, 5) for _, x, _ in cf])
    print("W/2", [round(w, 4) for _, _, w in cf]); ok &= all(0 < w < 1 for _, _, w in cf)
    print("NOTE", note_name(0), "..", note_name(60), "; C3 is step", [s for s in range(61) if note_name(s) == "C3"][0])
    ok &= all(note_idt(s) < 1 for s in range(61))
    # the sawtooth's aliasing: a C6 saw against an ideal band-limited one
    n = 1 << 15; s = _saw(n, note_inc(60), note_idt(60), 0)
    X = np.abs(np.fft.rfft(s * np.blackman(n))); fr = np.fft.rfftfreq(n, 1 / FS); f0 = note_inc(60) * FS / (1 << 24)
    harm = np.zeros_like(X, bool)
    for h in range(1, int(FS / 2 / f0) + 1):
        harm |= np.abs(fr - h * f0) < 15
    band = (fr > 100) & (fr < 7000)
    alias = 10 * math.log10(np.sum(X[band & ~harm] ** 2) / np.sum(X[band & harm] ** 2))
    print(f"C6 polyBLEP saw: aliased power 100 Hz-7 kHz {alias:.1f} dB under its harmonics"); ok &= alias < -40
    # a silent modulator gives silence; a steady vowel-like modulator gives the carrier
    t = np.arange(int(FS)) / FS
    y0 = vocode(np.zeros(len(t)), np.zeros(len(t)), cons=48)
    print("silence in, INT: peak", float(np.max(np.abs(y0)))); ok &= not np.any(y0)
    print("SELF-CHECK", "OK" if ok else "FAILED")
