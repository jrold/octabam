#!/usr/bin/env python3
"""The offset, in samples, between two channels of one recording, per click.

    tools/hw/usb_offset.py take.wav --ref 1 --ch 17     # MAIN L against T1 L, 20-channel take
    tools/hw/usb_offset.py --selftest

Channels are numbered from 1, as the USB stream and a DAW number them. The
recording is a PCM WAV (16, 24 or 32 bit), for example from `tools/rec`
(built from `tools/hw/rec.swift`), which records every input channel of
the device with nothing dropped.

The take is a short click on one track, a trig every bar or so, nothing
else playing. Every click is found on the reference channel (a sample
above --db below the channel's peak after --gap seconds of quiet), and
for each click the other channel's offset is taken two ways:

  xcorr  the lag, within +-MAXLAG samples, that maximises the normalised
         cross-correlation of the click (32 samples before its onset to
         2,048 after) with the other channel; corr is that maximum
         (1.0 = the same waveform at any gain);
  onset  the first sample on the other channel, within +-MAXLAG of the
         reference onset, above --db below the other channel's peak,
         minus the reference onset.

A positive offset means the other channel is LATER than the reference.
The two methods agree on a clean take; the summary is the median xcorr
lag over the clicks whose corr is at least --min-corr.
"""
import argparse
import os
import sys
import tempfile
import wave

import numpy as np

PRE = 32
POST = 2048


def load(path):
    w = wave.open(path)
    n, nch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
    raw = w.readframes(n)
    w.close()
    if sw == 2:
        x = np.frombuffer(raw, np.int16).astype(float) / 2 ** 15
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        x = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(x >= 1 << 23, x - (1 << 24), x) / float(1 << 23)
    elif sw == 4:
        x = np.frombuffer(raw, np.int32).astype(float) / 2 ** 31
    else:
        sys.exit(f"usb_offset: {path}: {8 * sw}-bit samples are not handled")
    return x.reshape(-1, nch), sr


def onsets(x, thr, gap):
    idx = np.flatnonzero(np.abs(x) > thr)
    if idx.size == 0:
        return idx
    keep = np.concatenate(([True], np.diff(idx) > gap))
    return idx[keep]


def xcorr_lag(ref, ch, o, maxlag):
    a, b = o - PRE, o + POST
    seg = ref[a:b]
    win = ch[a - maxlag:b + maxlag]
    c = np.correlate(win, seg, "valid")                  # c[k]: lag k - maxlag
    e = np.concatenate(([0.0], np.cumsum(win * win)))
    L = b - a
    energy = e[L:] - e[:-L]
    denom = np.sqrt(np.dot(seg, seg) * energy)
    corr = np.divide(c, denom, out=np.zeros_like(c), where=denom > 0)
    k = int(np.argmax(corr))
    return k - maxlag, float(corr[k])


def onset_lag(ch, o, thr, maxlag):
    win = np.abs(ch[o - maxlag:o + maxlag + 1])
    hit = np.flatnonzero(win > thr)
    return int(hit[0]) - maxlag if hit.size else None


def measure(x, sr, ref_ch, ch_ch, db, gap_s, maxlag):
    ref, ch = x[:, ref_ch - 1], x[:, ch_ch - 1]
    pr, pc = np.max(np.abs(ref)), np.max(np.abs(ch))
    if pr == 0 or pc == 0:
        return [], pr, pc
    k = 10 ** (-db / 20)
    rows = []
    for o in onsets(ref, pr * k, int(gap_s * sr)):
        if o - PRE - maxlag < 0 or o + POST + maxlag > len(ref):
            continue
        lag, corr = xcorr_lag(ref, ch, o, maxlag)
        rows.append((o, lag, corr, onset_lag(ch, o, pc * k, maxlag)))
    return rows, pr, pc


def report(path, ref_ch, ch_ch, db, gap_s, maxlag, min_corr):
    x, sr = load(path)
    n, nch = x.shape
    for c in (ref_ch, ch_ch):
        if not 1 <= c <= nch:
            sys.exit(f"usb_offset: {path} has {nch} channels; channel {c} is not one of them")
    print(f"{path}: {sr} Hz, {nch} channels, {n / sr:.2f} s; channel {ch_ch} against channel {ref_ch}")
    rows, pr, pc = measure(x, sr, ref_ch, ch_ch, db, gap_s, maxlag)
    if pr == 0 or pc == 0:
        sys.exit(f"usb_offset: channel {ref_ch if pr == 0 else ch_ch} is silent")
    print(f"  {'click':>5} {'time s':>8} {'xcorr':>6} {'corr':>6} {'onset':>6}")
    for i, (o, lag, corr, ol) in enumerate(rows, 1):
        print(f"  {i:>5} {o / sr:>8.3f} {lag:>6} {corr:>6.3f} {'-' if ol is None else ol:>6}")
    good = [lag for _, lag, corr, _ in rows if corr >= min_corr]
    if not good:
        sys.exit(f"usb_offset: no click with corr >= {min_corr} ({len(rows)} found)")
    good = np.array(good)
    print(f"offset: {int(np.median(good))} samples, channel {ch_ch} against channel {ref_ch}, positive = later "
          f"(median of {len(good)} of {len(rows)} clicks; min {good.min()}, max {good.max()})")
    return int(np.median(good))


def selftest():
    sr = 44100
    rng = np.random.default_rng(1)
    n = sr * 4
    click = rng.standard_normal(600) * np.exp(-np.arange(600) / 80.0)
    ok = True
    for delay in (16, 0, -32, 37):
        x = np.zeros((n, 20))
        for t in range(sr // 2, n - sr // 2, sr // 2):
            x[t:t + 600, 0] += 0.5 * click
            x[t + delay:t + delay + 600, 16] += 0.2 * click   # a lower gain, as MAIN carries
        x[:, 16] += 1e-5 * rng.standard_normal(n)
        pcm = (np.clip(x, -1, 1 - 2 ** -31) * 2 ** 31).astype("<i4")
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        w = wave.open(path, "wb")
        w.setnchannels(20)
        w.setsampwidth(4)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
        w.close()
        try:
            got = report(path, 1, 17, 20.0, 0.2, 2048, 0.9)
        finally:
            os.unlink(path)
        print(f"selftest delay {delay}: {'PASS' if got == delay else f'FAIL (got {got})'}\n")
        ok &= got == delay
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("wav", nargs="?")
    ap.add_argument("--ref", type=int, default=1, help="reference channel, from 1 (default 1: T1 L)")
    ap.add_argument("--ch", type=int, default=17, help="channel measured against it, from 1 (default 17: MAIN L)")
    ap.add_argument("--db", type=float, default=20.0, help="onset threshold, dB below each channel's peak (default 20)")
    ap.add_argument("--gap", type=float, default=0.2, help="seconds of quiet before a click (default 0.2)")
    ap.add_argument("--maxlag", type=int, default=2048, help="largest offset searched, samples (default 2048)")
    ap.add_argument("--min-corr", type=float, default=0.9, help="clicks below this corr are left out of the summary (default 0.9)")
    ap.add_argument("--selftest", action="store_true", help="synthetic 20-channel takes with known offsets")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not a.wav:
        ap.error("a .wav is needed (or --selftest)")
    report(a.wav, a.ref, a.ch, a.db, a.gap, a.maxlag, a.min_corr)


if __name__ == "__main__":
    main()
