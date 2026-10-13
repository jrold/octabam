#!/usr/bin/env python3
"""The recorder loop under the port: what T2 plays back from R1.

  recloop.py DUMP [bpm] [rlen_steps]
Extracts T2's chain input (its 84-word record audio: what the FLEX voice plays)
and prints, per sequencer step, the level and the dominant frequency (from
zero crossings; `--audio-in tones` puts 500*(k+1) Hz on RX0 slot k, so the
frequency says WHICH input pair the recorder captured), then the largest
sample-to-sample jump in each pass relative to the tone's own slope -- a seam
click shows as a jump far above the slope.
"""
import sys, math, pathlib
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1])); import toolpath  # noqa: E402,F401  (every tools/ dir on sys.path)
import blockdump as bd

def words(w):
    out = []
    for i in range(0, len(w), 2):
        v = (w[i] << 8) | (w[i + 1] >> 8); out.append(v - (1 << 24) if v >= 1 << 23 else v)
    return out

UNITY_RATE = 0x40000


def is_header(rec, i):
    """A segment header at word i: (count, 0, rate, tag), count <= 16 output
    samples, rate a positive playback increment."""
    return (i + 4 <= len(rec) and rec[i + 1] == 0 and 0 < rec[i + 2] < 0x800000
            and 0 <= rec[i] <= 16)


def record_audio(rec, right=False):
    """One 84-word track record -> its source samples for the frame's 16
    output samples (L, or R).
    The record is a sequence of segments, each a 4-word header (count, 0,
    rate, tag) followed by the source stereo pairs that `count` output
    samples consume; the counts sum to 16 (measured: a THRU voice ships two
    empty headers then 16 pairs; a FLEX voice splits them, the split moving
    one sample per frame). `rate` is the segment's playback increment, the
    top 24 bits of the ColdFire long the builder stores at header +8
    (0x40003d16, from the pitch tables): 0x40000 is one source sample per
    output sample (0x04000000 = 2^26, the position unit, `lsrl #26` at
    0x40003d90; the empty header at 0x40003c28 carries it), so a segment
    holds count pairs at 0x40000 and about count * rate / 0x40000 pairs
    otherwise (0x20000: count 16 -> 8 pairs; count 4 -> 2). The pair count
    is taken from where the next header starts when one is within a pair
    of the estimate, a header at the same rate first."""
    # PK/Y1 is a generator command stream, not source PCM. `words()` has
    # combined its two 16-bit DSP halves and discarded the low eight bits.
    # Treating the signature as a sample fabricated a constant -16 dB input
    # on an idle PERKY track. Generator output is checked after DSP synthesis
    # by the PERKY source/port gates; it cannot be reconstructed from commands.
    if len(rec) >= 2 and rec[:2] == [0x504b00, 0x593100]:
        return []
    o = 1 if right else 0
    pairs = []; out = 0; i = 0
    while out < 16 and i + 4 <= len(rec):
        if is_header(rec, i):
            cnt, rate = rec[i], rec[i + 2]; i += 4
            n = (cnt * rate + UNITY_RATE // 2) // UNITY_RATE
            near = [m for m in (n, n - 1, n + 1) if m >= 0 and is_header(rec, i + 2 * m)]
            same = [m for m in near if rec[i + 2 * m + 2] == rate]
            n = (same or near or [n])[0]
            n = min(n, (len(rec) - i) // 2)
            pairs += [rec[i + 2 * k + o] for k in range(n)]; i += 2 * n
            out += cnt
            continue
        take = min(16 - out, (len(rec) - i) // 2)
        pairs += [rec[i + 2 * k + o] for k in range(take)]; i += 2 * take
        out += take
    return pairs

def track_audio(c, track, right=False):
    core = 0 if track >= 5 else 1; pos = (track - 1) % 4
    addrs = {1: (0x80001c90, 0x80002710), 0: (0x800021d0, 0x80002c50)}[core]
    rec = sorted(sum((c.get(('>', 0, core, a), []) for a in addrs), []))
    out = []
    for _, w in rec:
        ws = words(w); out += record_audio(ws[pos * 84:(pos + 1) * 84], right)
    return out

def readback_audio(c, track, right=False):
    """The track's slot of its core's 256-halfword read-back: the per-track
    chain OUTPUT before the master mix (32 words per track, (L,R) pairs)."""
    core = 0 if track >= 5 else 1; pos = (track - 1) % 4; o = 1 if right else 0
    addrs = {1: (0x80003190, 0x80003590), 0: (0x80003390, 0x80003790)}[core]
    rb = sorted(sum((c.get(('<', 1, core, a), []) for a in addrs), []))
    out = []
    for _, w in rb:
        ws = words(w); out += ws[pos * 32 + o: pos * 32 + 32: 2]
    return out

def db(x): return 20 * math.log10(x / 8388608) if x > 0 else -200

def main():
    dump = sys.argv[1]; bpm = float(sys.argv[2]) if len(sys.argv) > 2 else 128.0
    rlen = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    step = 60.0 / bpm / 4 * 44100                     # samples per 16th step
    c = bd.classes(bd.read(dump))
    for t in (1, 2):
        x = track_audio(c, t)
        print(f"T{t}: {len(x)} samples ({len(x) / step:.1f} steps of {step:.1f})")
        rows = []
        for s in range(int(len(x) / step)):
            seg = x[int(s * step): int((s + 1) * step)]
            if not seg: continue
            rms = math.sqrt(sum(v * v for v in seg) / len(seg))
            zc = sum(1 for i in range(1, len(seg)) if (seg[i - 1] < 0) != (seg[i] < 0))
            f = zc / 2 / (len(seg) / 44100)
            rows.append((s + 1, db(rms), f))
        print("   step: level dBFS / dominant Hz  " + "  ".join(f"{s}:{l:.0f}/{f:.0f}" for s, l, f in rows))
        # seams: largest jump per RLEN-step pass, relative to the median slope of that pass
        if any(l > -60 for _, l, _ in rows):
            for p in range(int(len(x) / (step * rlen))):
                a, b = int(p * step * rlen), int((p + 1) * step * rlen)
                seg = x[a:b]
                d = [abs(seg[i] - seg[i - 1]) for i in range(1, len(seg))]
                if not d or max(seg, key=abs) == 0: continue
                med = sorted(d)[len(d) // 2] or 1
                i = max(range(len(d)), key=lambda k: d[k])
                print(f"   pass {p + 1} (samples {a}..{b}): max jump {d[i]} at +{i + 1} = {d[i] / med:.1f}x the median slope")

if __name__ == '__main__':
    main()
