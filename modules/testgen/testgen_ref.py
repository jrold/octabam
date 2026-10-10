#!/usr/bin/env python3
"""Float reference for TESTGEN: the signals and the analysis that proves them.

    python3 modules/testgen/testgen_ref.py      # self-check on ideal signals
"""
import math
import numpy as np

FS = 44100.0                       # the Octatrack's rate
FREQS = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 440, 500, 630, 800, 1000,
         1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000]
# the ISO third-octave centres, and A 440 between 400 and 500


def level_lin(k):
    """LEVL 0..127 -> linear gain: 0 dBFS at 127, 0.5 dB steps."""
    return 10 ** (-(127 - k) * 0.5 / 20)


def freq_hz(k, fine=64):
    """FREQ step k (held at 20 kHz past the end), FINE 0..127 (64 = none): +-200 cents, 3.125 a step."""
    return FREQS[min(k, len(FREQS) - 1)] * 2 ** ((fine - 64) / 384)


def sine(f, n, level=1.0):
    return level * np.sin(2 * math.pi * f * np.arange(n) / FS)


def sweep(f1=20.0, f2=20000.0, T=4.0, level=1.0):
    """Exponential (Farina) sweep: phase = 2 pi f1 L (e^(t/L) - 1), L = T / ln(f2/f1)."""
    n = int(round(T * FS))
    t = np.arange(n) / FS
    L = T / math.log(f2 / f1)
    return level * np.sin(2 * math.pi * f1 * L * (np.exp(t / L) - 1.0)), L


def inverse_filter(f1, f2, T):
    """Farina's inverse: the time-reversed sweep, amplitude-weighted by -6 dB/octave."""
    s, L = sweep(f1, f2, T)
    t = np.arange(len(s)) / FS
    return s[::-1] * np.exp(-t / L)


# ---- what the module generates, exactly (the DSP's integer laws) ----------------
NOISE_A, NOISE_C, NOISE_M = 0x5DEECE66D, 11, 1 << 46         # x' = A x + C mod 2^46 (drand48's A)
NOISE_SEED_L = 0x2A5F31 << 23
NOISE_JUMP = 0x3243F6A8885                                      # R starts this many steps ahead of L
SWEEP_F2, SWEEP_GAP = 20000.0, 44100                            # end frequency, 1 s of silence
SWEEP_INC0 = 7609                                               # 20.0007 Hz, the start increment
IMPULSE_UNIT = 11025                                            # LEN step t: a period of (t+1)/4 s


def len_seconds(t):
    """LEN step t = LEN >> 3, 0..15 -> the sweep length in seconds."""
    return t + 1


def _jump(k):
    """The generator's map advanced k steps, as (multiplier, increment)."""
    a, c, ba, bc = 1, 0, NOISE_A, NOISE_C
    while k:
        if k & 1:
            a, c = (ba * a) % NOISE_M, (ba * c + bc) % NOISE_M
        ba, bc = (ba * ba) % NOISE_M, (ba * bc + bc) % NOISE_M
        k >>= 1
    return a, c


def noise_seed(channel):
    """The state each channel's generator restarts from: L's seed, and R's 0x3243f6a8885 steps on."""
    if channel == "L":
        return NOISE_SEED_L
    a, c = _jump(NOISE_JUMP)
    return (a * NOISE_SEED_L + c) % NOISE_M


def white_q23(n, channel="L"):
    """The module's WHITE before LEVL, exactly: each new state's top 23 bits, 2 x_hi - 2^23."""
    out = np.empty(n, np.int64)
    x = noise_seed(channel)
    for i in range(n):
        x = (NOISE_A * x + NOISE_C) % NOISE_M
        out[i] = 2 * (x >> 23) - (1 << 23)
    return out


def white(n, channel="L"):
    """Uniform in [-1, 1): the module's generator as a float."""
    return white_q23(n, channel) / float(1 << 23)


def pink(n, channel="L"):
    """Paul Kellet's economy pink filter (3 poles) on the module's white noise, scaled by 0.11."""
    w = white(n, channel)
    b0 = b1 = b2 = 0.0
    out = np.empty(n)
    for i, x in enumerate(w):
        b0 = 0.99765 * b0 + x * 0.0990460
        b1 = 0.96300 * b1 + x * 0.2965164
        b2 = 0.57000 * b2 + x * 1.0526913
        out[i] = b0 + b1 + b2 + x * 0.1848
    return out * 0.11


def sweep_d(t):
    """The sweep's per-sample growth (r - 1) * 2^35 for LEN step t, as the P table holds it."""
    n = len_seconds(t) * int(FS)
    ratio = SWEEP_F2 / (SWEEP_INC0 * FS / (1 << 24))
    return round((ratio ** (1.0 / n) - 1.0) * (1 << 35))


def sweep_phases(t, n_out):
    """The module's SWEEP phase law for LEN step t, exactly: (phase, on) per sample.

    inc is 48 bits (24 integer, 24 fraction); each sample the phase advances by
    its integer part and inc grows by floor(2 * inc_hi * d / 2^12) in fraction
    units (mpy, asr 12, add). Past the sweep's end, for SWEEP_GAP samples, the
    output is off and the phase and increment sit at their start values.
    """
    n_sw = len_seconds(t) * int(FS)
    d = sweep_d(t)
    period = n_sw + SWEEP_GAP
    ph = np.empty(n_out, np.int64)
    on = np.empty(n_out, bool)
    p, inc, k = 0, SWEEP_INC0 << 24, 0
    for i in range(n_out):
        ph[i], on[i] = p, k < n_sw
        hi = inc >> 24
        p = (p + hi) & 0xFFFFFF
        inc += (2 * hi * d) >> 12
        if k >= n_sw:
            p, inc = 0, SWEEP_INC0 << 24
        k = 0 if k + 1 == period else k + 1
    return ph, on


def sweep_dsp(t, n_out):
    """The module's SWEEP at full scale as a float (its sine is exact to within 3 LSB)."""
    ph, on = sweep_phases(t, n_out)
    return np.where(on, np.sin(2 * math.pi * ph / (1 << 24)), 0.0)


def impulse_positions(t, n_out):
    """Where the module's IMPULSE puts its samples: every (t+1)/4 s from sample 0."""
    return np.arange(0, n_out, (t + 1) * IMPULSE_UNIT)


def needle_period(inc):
    """NEEDLE's period in samples for a phase increment inc (a cycle is 2^24):
    round(2^24 / inc), the whole period nearest the set frequency, as the
    module's integer division computes it: (2^25 + inc) // (2 inc)."""
    return ((1 << 25) + inc) // (2 * inc)


def needle_positions(inc, n_out):
    """Where the module's NEEDLE puts its full-scale samples: every needle_period(inc) from sample 0.
    The train is strictly periodic, at FS / P Hz."""
    return np.arange(0, n_out, needle_period(inc))


def dc_q23(level_q23):
    """The module's DC: full scale times the level, every sample (IMPULSE with a period of one).
    level_q23 is the LEVEL table's entry; the product rounds (mpyr)."""
    return (((1 << 23) - 1) * level_q23 * 2 + (1 << 23)) >> 24


def thd_db(x, f, harmonics=9):
    """THD of a steady sine x at f, by a Blackman-Harris windowed FFT."""
    n = len(x)
    w = np.blackman(n)
    X = np.abs(np.fft.rfft(x * w))
    bins = lambda hz: int(round(hz * n / FS))
    def power(k):
        k0 = max(k - 4, 0)
        return float(np.sum(X[k0:k + 5] ** 2))
    p1 = power(bins(f))
    ph = sum(power(bins(f * h)) for h in range(2, harmonics + 1) if f * h < FS / 2)
    return 10 * math.log10(max(ph, 1e-30) / p1)


def deconvolve(y, f1=20.0, f2=20000.0, T=4.0):
    """Impulse response of the path that turned the sweep into y (linear part at the peak)."""
    inv = inverse_filter(f1, f2, T)
    n = len(y) + len(inv) - 1
    N = 1 << (n - 1).bit_length()
    h = np.fft.irfft(np.fft.rfft(y, N) * np.fft.rfft(inv, N), N)[:n]
    return h / np.max(np.abs(h))


def octave_slope_db(x, lo=40.0, hi=16000.0):
    """Level per octave band; returns the fitted slope (dB/octave) and the worst deviation from it."""
    X = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / FS)
    centres, levels = [], []
    c = lo
    while c <= hi:
        m = (f >= c / math.sqrt(2)) & (f < c * math.sqrt(2))
        levels.append(10 * math.log10(np.sum(X[m]) / max(np.sum(m), 1)))
        centres.append(math.log2(c))
        c *= 2
    p = np.polyfit(centres, levels, 1)
    dev = max(abs(l - np.polyval(p, c_)) for c_, l in zip(centres, levels))
    return float(p[0]), float(dev)


if __name__ == "__main__":
    ok = True
    s = sine(1000.0, 1 << 16)
    t = thd_db(s, 1000.0)
    print(f"ideal 1 kHz sine: THD {t:.1f} dB (the analysis floor)"); ok &= t < -120
    s3 = s + 1e-3 * sine(3000.0, 1 << 16)
    t3 = thd_db(s3, 1000.0)
    print(f"1 kHz sine with a -60 dB 3rd harmonic: THD {t3:.1f} dB (expect -60)"); ok &= abs(t3 + 60) < 0.5
    sw, _ = sweep(T=2.0)
    h = deconvolve(np.concatenate([sw, np.zeros(int(FS))]), T=2.0)
    pk = int(np.argmax(np.abs(h)))
    seg = h[pk - 4096:pk + 4096] * np.hanning(8192)            # the linear impulse response
    Hm = np.abs(np.fft.rfft(seg, 1 << 15)); fr = np.fft.rfftfreq(1 << 15, 1 / FS)
    band = (fr >= 40) & (fr <= 16000)
    db = 20 * np.log10(Hm[band] / np.median(Hm[band]))
    flat = float(np.max(np.abs(db)))
    print(f"sweep through an identity path: deconvolved response flat within {flat:.2f} dB, 40 Hz-16 kHz"); ok &= flat < 0.5
    sl, dev = octave_slope_db(pink(1 << 20))
    print(f"pink noise: slope {sl:+.2f} dB/octave, worst band deviation {dev:.2f} dB"); ok &= abs(sl + 3.0) < 0.3 and dev < 1.0
    sl, dev = octave_slope_db(white(1 << 20))
    print(f"white noise (the 46-bit generator): slope {sl:+.2f} dB/octave, worst band deviation {dev:.2f} dB"); ok &= abs(sl) < 0.3
    sd = sweep_dsp(0, 2 * int(FS) + SWEEP_GAP)
    h = deconvolve(sd[:2 * int(FS) + SWEEP_GAP], f1=SWEEP_INC0 * FS / (1 << 24), T=1.0)
    pk = int(np.argmax(np.abs(h)))
    seg = h[pk - 4096:pk + 4096] * np.hanning(8192)
    Hm = np.abs(np.fft.rfft(seg, 1 << 15))
    db = 20 * np.log10(Hm[band] / np.median(Hm[band]))
    flat = float(np.max(np.abs(db)))
    print(f"the module's 1 s sweep law through an identity path: flat within {flat:.2f} dB, 40 Hz-16 kHz"); ok &= flat < 0.5
    p = needle_period(380436)
    print(f"NEEDLE at FREQ 1 kHz: a period of {p} samples, {FS / p:.2f} Hz"); ok &= p == 44
    print(f"LEVL 127 = {20 * math.log10(level_lin(127)):.1f} dBFS, LEVL 0 = {20 * math.log10(level_lin(0)):.1f} dBFS; FREQ 18 = {freq_hz(18)} Hz, FREQ 14 = {freq_hz(14)} Hz")
    print("SELF-CHECK", "OK" if ok else "FAILED")
