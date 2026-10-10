#!/usr/bin/env python3
"""Core 0's MAIN-gain arithmetic, as payload A runs it (docs/firmware/
STEM_REC.md 18.2-18.3), for STEM REC's stems after the fader.

    python3 tools/verify/stems_gain.py validate

Every value is a 24-bit DSP word held as a signed int. mpy is the DSP's
fractional multiply (a*b*2, the top 24 bits of 48: floor(a*b / 2^23));
lim24 is the limiting move to memory. A page is the 64 halfwords the
ColdFire hands core 0 through X:$205: per slot k four words at 4k (cue
send, level, MAIN table index, split), the MAIN level at 0x29.

The hook (modules/stems/stems.s) does the same arithmetic on the ColdFire;
verify_stems compares the hook with core 0, and `validate` this model."""
import re

NSLOTS = 8          # the tracks; slots 8 and 9 are the inputs, recorded raw
PAGES, NPAGES, PAGE, SENT = 0x80005460, 4, 0x80, 0x80004804   # four level pages (STEM_REC.md 18.1)
WATCH = re.compile(r"\s*\[\s*([\d.]+)\] \[(0x[0-9a-f]+)\] <- (0x[0-9a-f]+|0) \((\d)\)")


def sext24(v):
    v &= 0xffffff
    return v - 0x1000000 if v & 0x800000 else v


def lim24(v):
    return max(-0x800000, min(0x7fffff, v))


def mpy(a, b):
    return (a * b) >> 23


def target(w1, w2, w29, table):
    """One slot's MAIN target: P:0xf5-0x10a (w1 times 0x80, the low word
    kept, squared), then P:0x115-0x130 (the MAIN level squared, times
    T[w2], times the slot's square)."""
    x = sext24(w1 << 8)
    w1sq = lim24(mpy(x, x))
    m = sext24((w29 & 0xff) << 16)
    m2 = lim24(mpy(m, m))
    idx = sext24(w2 << 8) >> 15
    t = table[idx] if 0 <= idx < len(table) else 0
    return lim24(mpy(w1sq, lim24(mpy(m2, t))))


class Mirror:
    """The MAIN chain of P:0x203-0x237 for each track slot. state[k] =
    [split, increment, gain], zero at boot as payload A uploads X:0x3dd."""

    def __init__(self, table):
        self.table = table
        self.state = [[0, 0, 0] for _ in range(NSLOTS)]

    def step(self, page):
        out = []
        for k in range(NSLOTS):
            sp, inc, cur = self.state[k]
            s = page[4 * k + 3] & 15
            tgt = target(page[4 * k + 1], page[4 * k + 2], page[0x29], self.table)
            m = min(s, sp)
            g = []
            for _ in range(m):
                g.append(cur)
                cur += inc
            g += [cur] * (s - m)
            inc = lim24((tgt - cur) >> 4)
            for _ in range(16 - s):
                g.append(cur)
                cur += inc
            self.state[k] = [s, inc, cur]
            out.append(g)
        return out


def stem24(g, x24):
    """One track's share of MAIN for one sample: the mixdown's product,
    times 4 (asl #2), limited (P:0x259-0x28f)."""
    return lim24((g * x24) >> 21)


def main24(gains, xs):
    return lim24(sum(g * x for g, x in zip(gains, xs)) >> 21)


def sent_pages(log, mark=None):
    """Every page channel 0 sent, in order, from a --watch-mem log of the
    sent index and the page ring (the port's line: `[sample] [addr] <- value
    (bytes) at pc ...`). The index is written once per core, so a repeat of
    the same value is the same frame; a page is taken when the index moves
    past it, with every write of its frame in it. The fourth frame writes
    4, then 0: the 4 is the increment before its wrap, never sent.

    With `mark`, the address of a long a test seam writes once a frame (also
    in the watch), returns (pages, marks): each value written there, with
    the index among the pages of the page being sent at that moment."""
    ring, out, cur, marks = bytearray(NPAGES * PAGE), [], None, []
    for line in log.splitlines():
        m = WATCH.match(line)
        if not m:
            continue
        addr, val, nb = int(m.group(2), 16), int(m.group(3), 0), int(m.group(4))
        if addr == SENT:
            if val < NPAGES and val != cur:
                if cur is not None:
                    p = ring[cur * PAGE:(cur + 1) * PAGE]
                    out.append([int.from_bytes(p[i:i + 2], "big") for i in range(0, PAGE, 2)])
                cur = val
        elif addr == mark:
            marks.append((val, len(out)))
        elif PAGES <= addr < PAGES + NPAGES * PAGE:
            o = addr - PAGES
            ring[o:o + nb] = (val & ((1 << 8 * nb) - 1)).to_bytes(nb, "big")
    return (out, marks) if mark is not None else out


def dsp_peeks(log, space, addr):
    """The words of one --dsp-peek line, sign-extended. The port prints the
    address with %#07x, which writes address 0 as 0000000, not 0x00000."""
    for m in re.finditer(rf"core 0 {space}:(0x[0-9a-f]+|0+):((?: [0-9a-f]{{6}})+)", log):
        if int(m.group(1), 16) == addr:
            return [sext24(int(w, 16)) for w in m.group(2).split()]
    return []


def validate(fixture="out/stems_fixture_thru1.json", frames=260):
    """One port run with T1's LEVEL stepped at frames 60 (64), 61 (100),
    90 (20) and 120 (127) -- two steps one frame apart cut a ramp -- every
    page write and sent index logged. Every sent page replayed through
    Mirror must leave core 0's ramp state (X:0x3dd: split, MAIN increment,
    MAIN gain) as the DSP has it. The run can end inside core 0's frame,
    so either of the model's last two frames may be the DSP's. The last
    frame's MAIN gains (Y:0x4a + 20j + k, j >= 2) are counted, not gated:
    by the run's end other code has reused Y:0x80-0x9f, samples 3 and 4
    (STEM_REC.md 18.3)."""
    import json
    import pathlib
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[2]
    fx = json.loads((root / fixture).read_text())
    mover = (root / "out/stems_runs/lv_mover.txt").read_text().split()
    args = [str(root / "out/emu/ot_emu"), "--image", str(root / "out/mainos_bus.bin"), "--card", fx["card"],
            "--set", fx["set"], "--project", fx["project"], "--sequencer", "--internal-clock",
            "--frames", str(frames), "--load-ms", "20000", "--dsp", "--main-level", "64",
            "--pre-roll", "40", "--poke-trig", "2", "--audio-in", fx["audio_in"],
            "--watch-mem", f"0x{SENT:x},4;0x{PAGES:x},{NPAGES * PAGE}",
            "--dsp-peek", "0:X:0x3dd,50;0:Y:0x40,320"]
    steps = ((60, 64), (61, 100), (90, 20), (120, 127))
    if mover[0] == "poke":
        for f, v in steps:
            args += ["--step", f"{f}:poke:{mover[1]}={v}"]
    else:
        mid = root / "out/stems_runs/gainval_midi.txt"
        mid.write_text("".join(f"{f} B0 2E {v:02X}\n" for f, v in steps))
        args += ["--midi", str(mid)]
    r = subprocess.run(args, capture_output=True, text=True)
    log = r.stdout + r.stderr
    (root / "out/stems_runs/gainval.log").write_text(log)
    img = (root / "out/raw/section_3_MAIN_OS.bin").read_bytes()
    off = 0x400ea18a - 0x40000400
    table = [int.from_bytes(img[off + 3 * i:off + 3 * i + 3], "little") for i in range(258)]
    pages = sent_pages(log)
    mirror, gains, states = Mirror(table), [], []
    for p in pages:
        gains.append(mirror.step(p))
        states.append([list(s) for s in mirror.state])
    x, y = dsp_peeks(log, "X", 0x3dd), dsp_peeks(log, "Y", 0x40)
    if len(x) != 50 or len(y) != 320 or len(pages) < 200:
        print(f"incomplete run: {len(pages)} pages, {len(x)} X words, {len(y)} Y words")
        return False
    dsp_state = [[x[5 * k], x[5 * k + 2], x[5 * k + 4]] for k in range(8)]
    dsp_main = [[y[20 * j + 10 + k] for j in range(2, 16)] for k in range(8)]
    # The run can end inside core 0's per-slot loop: each slot may be at the
    # model's last frame or the one before.
    back = [next((b for b in (1, 2) if dsp_state[k] == states[-b][k]), None) for k in range(8)]
    for k in range(8):
        b = back[k] or 1
        same = sum(d == g for d, g in zip(dsp_main[k], gains[-b][k][2:16]))
        print(f"T{k + 1}: core 0 state {[f'{w:06x}' for w in dsp_state[k]]}  "
              f"model -{b} {[f'{w:06x}' for w in states[-b][k]]}  "
              f"MAIN gains j=2..15: {same}/14 equal (not gated)")
    if all(b is not None for b in back):
        print(f"the model equals core 0 in every track slot: {len(pages)} pages replayed")
        return True
    print("MISMATCH")
    print("core 0 : T1 MAIN gains j=2..5", [f"{w:06x}" for w in dsp_main[0][:4]])
    for b in (1, 2):
        print(f"model -{b}: T1 MAIN gains j=2..5", [f"{w:06x}" for w in gains[-b][0][2:6]])
    return False


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["validate"]:
        sys.exit(0 if validate() else 1)
    print(__doc__)
