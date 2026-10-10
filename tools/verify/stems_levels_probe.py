#!/usr/bin/env python3
"""STEM REC piece 5, probes 1-2: the level words the ColdFire hands core 0.

    python3 tools/verify/stems_levels_probe.py one|thru|thru1 [--poke ADDR=VAL@FRAME ...]
    python3 tools/verify/stems_levels_probe.py trace

Runs the port on a fixture card and prints, at the run's end: the page
indexes 0x80004800 (written) and 0x80004804 (sent by channel 0), the four
level pages at 0x80005460 (and the page after them, which is not one), the DSP's copy at X:0x4800, core 0's targets
(Y:0x00-0x13), its ramp state (X:0x3dd, five words a slot), whether the
table words at 0x400ea18a still equal the image's (with a known string of
the image beside them, to tell memory reused from memory not mapped), and which instructions
write a page's MAIN level halfword (0x29). Facts only: the assertions are
verify_stems' (docs/firmware/STEM_REC.md section 18).

`trace` runs the one-THRU fixture with the hook's trace seam on and
prints what the hook sees each frame, against stems_gain's model
(STEM_REC.md 18.5)."""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMU = ROOT / "out/emu/ot_emu"
IMAGE = ROOT / "out/mainos_bus.bin"
STOCK = ROOT / "out/raw/section_3_MAIN_OS.bin"
BASE = 0x40000400
PAGES, NPAGES, PAGE = 0x80005460, 4, 0x80   # four level pages; the index passes 4 and wraps inside one frame
TABLE = 0x400ea18a                      # X:0x6c00's words in the image, 3 bytes LE
NAME_FMT = 0x400b77bb                   # "%02d%02d%02d-%02d%02d", read by STEM REC at run time
WORK = ROOT / "out/stems_runs"
TRACE_N, TRACE_B = 64, 64               # stems.s: the trace seam's frames, and bytes a frame
WATCH = re.compile(r"\s*\[\s*([\d.]+)\] \[(0x[0-9a-f]+)\] <- (0x[0-9a-f]+|0) \((\d)\) at pc (0x[0-9a-f]+)")


def table_words(img, n=258):
    off = TABLE - BASE
    return [int.from_bytes(img[off + 3 * i:off + 3 * i + 3], "little") for i in range(n)]


def peeks(log, space, addr):
    """The words of one --dsp-peek line. The port prints the address with
    %#07x, which writes address 0 as 0000000, not 0x00000."""
    for m in re.finditer(rf"core 0 {space}:(0x[0-9a-f]+|0+):((?: [0-9a-f]{{6}})+)", log):
        if int(m.group(1), 16) == addr:
            return [int(w, 16) for w in m.group(2).split()]
    return []


def run(fixture_json, frames=300, extra=()):
    fx = json.loads(pathlib.Path(fixture_json).read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    tag = pathlib.Path(fixture_json).stem
    sram, tab, idx = WORK / f"lv_{tag}.sram", WORK / f"lv_{tag}.tab", WORK / f"lv_{tag}.idx"
    fmt = WORK / f"lv_{tag}.fmt"
    w29 = ";".join(f"0x{PAGES + p * PAGE + 2 * 0x29:x},2" for p in range(NPAGES))
    args = [str(EMU), "--image", str(IMAGE), "--card", fx["card"], "--set", fx["set"],
            "--project", fx["project"], "--sequencer", "--internal-clock", "--frames", str(frames),
            "--load-ms", "20000", "--dsp", "--main-level", "64", "--pre-roll", "40", "--poke-trig", "2",
            "--mem-dump", f"0x80004800,8={idx};0x{PAGES:x},{(NPAGES + 1) * PAGE}={sram};"
                          f"0x{TABLE:x},{258 * 3}={tab};0x{NAME_FMT:x},24={fmt}",
            "--dsp-peek", "0:X:0x4800,48;0:Y:0x0,20;0:X:0x3dd,50",
            "--watch-mem", w29, *extra]
    if fx.get("audio_in"):
        args += ["--audio-in", fx["audio_in"]]
    r = subprocess.run(args, capture_output=True, text=True)
    log = r.stdout + r.stderr
    (WORK / f"lv_{tag}.log").write_text(log)
    ib = idx.read_bytes() if idx.exists() else b"\0" * 8
    tb = tab.read_bytes() if tab.exists() else b""
    return {"pages": sram.read_bytes() if sram.exists() else b"",
            "write_idx": int.from_bytes(ib[0:4], "big"), "sent_idx": int.from_bytes(ib[4:8], "big"),
            "dsp_x4800": peeks(log, "X", 0x4800), "dsp_targets": peeks(log, "Y", 0),
            "dsp_state": peeks(log, "X", 0x3dd),
            "table_ok": [int.from_bytes(tb[3 * i:3 * i + 3], "little") for i in range(258)]
                        == table_words(STOCK.read_bytes()),
            "w29_writers": {m.group(5) for m in map(WATCH.match, log.splitlines()) if m},
            "image_string": fmt.read_bytes().split(b"\0")[0] if fmt.exists() else b"",
            "exit": r.returncode}


def syms():
    out = subprocess.run(["m68k-elf-nm", str(ROOT / "out/platform/runtime/runtime.elf")],
                         capture_output=True, text=True).stdout
    return {p[2]: int(p[0], 16) for p in (line.split() for line in out.splitlines()) if len(p) == 3}


def sext(v):
    return v - 0x1000000 if v & 0x800000 else v


def wav_pos(vals, ch, k):
    """The WAV sample p with ch[p + 16f + k] == vals[f] for every traced
    frame f, or None: where a column of 16-bit samples sits in the input."""
    for p in (q for q in range(len(ch) - 16 * len(vals) - k) if ch[q + k] == vals[0]):
        if all(ch[p + 16 * f + k] == v for f, v in enumerate(vals)):
            return p
    return None


def trace(fixture_json, start=60):
    """The hook's view for TRACE_N frames from `start`, against the model
    (STEM_REC.md 18.5). T1's LEVEL moves inside the window (64, then 100
    a frame later, 20, 127), so only one gain lag fits; the watch takes
    stems_trace too, so each traced frame is placed among the pages core
    0 received. For each traced frame with sound: which mirrored frame's
    gains (`lag` frames before the page being sent then) and which
    read-back long (the half PING names, the other, either one frame
    older) give MAIN's first L sample. T1 must sound alone."""
    sys.path.insert(0, str(ROOT / "tools/verify"))
    import stems_gain as sg
    s = syms()
    fx = json.loads(pathlib.Path(fixture_json).read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    buf = WORK / "lv_trace.buf"
    mover = (WORK / "lv_mover.txt").read_text().split()
    if mover[0] != "poke":
        sys.exit("trace moves T1's LEVEL with a poke: lv_mover.txt names none")
    args = [str(EMU), "--image", str(IMAGE), "--card", fx["card"], "--set", fx["set"],
            "--project", fx["project"], "--sequencer", "--internal-clock",
            "--frames", str(start + TRACE_N + 16), "--load-ms", "20000", "--dsp", "--main-level", "64",
            "--pre-roll", "40", "--poke-trig", "2", "--audio-in", fx["audio_in"],
            "--step", f"{start}:poke:0x{s['stems_trace'] + 3:x}=1",
            "--mem-dump", f"0x{s['stems_trace_buf']:x},{TRACE_N * TRACE_B}={buf}",
            "--watch-mem", f"0x{sg.SENT:x},4;0x{PAGES:x},{NPAGES * PAGE};0x{s['stems_trace']:x},4"]
    for f, v in ((start + 8, 64), (start + 9, 100), (start + 30, 20), (start + 45, 127)):
        args += ["--step", f"{f}:poke:{mover[1]}={v}"]
    r = subprocess.run(args, capture_output=True, text=True)
    log = r.stdout + r.stderr
    (WORK / "lv_trace.log").write_text(log)
    raw = buf.read_bytes()
    rows = [[int.from_bytes(raw[TRACE_B * f + 4 * i:TRACE_B * f + 4 * i + 4], "big") for i in range(16)]
            for f in range(TRACE_N)]
    pages, marks = sg.sent_pages(log, mark=s["stems_trace"])
    newest = {v - 2: n for v, n in marks}    # stems_trace counts on once frame v - 2 is recorded
    mirror = sg.Mirror(table_words(STOCK.read_bytes()))
    gains = [mirror.step(pg) for pg in pages]
    print(f"exit {r.returncode}; {len(pages)} pages; traced frames placed: {len(newest)}")
    print("frame ping wr sent page  T1:this   T1:other  MAIN-L    MAIN-R    MAIN-L15  in-idx    "
          "A         B         C         D         A-last    A(-1)     T1:oth15")
    found = {}
    for f, row in enumerate(rows):
        n = newest.get(f)
        print(f"{f:5d} {row[0]:4d} {row[1]:2d} {row[2]:4d} {-1 if n is None else n:4d}  "
              + "  ".join(f"{w:08x}" for w in row[3:16]))
        if f < 1 or not row[5] or n is None:
            continue
        want = sext(row[5] >> 8)
        cands = {"this": row[3], "other": row[4], "this-1": rows[f - 1][3], "other-1": rows[f - 1][4]}
        for lag in range(4):
            if not 0 <= n - lag < len(gains):
                continue
            g = gains[n - lag][0][0]
            for name, x in cands.items():
                if sg.stem24(g, sext(x >> 8)) == want:
                    found[(lag, name)] = found.get((lag, name), 0) + 1
        # sample 15: MAIN complete at hook time, and the model's gain index
        if n - 2 >= 0 and n - 2 < len(gains) and rows[f][7]:
            ok15 = sg.stem24(gains[n - 2][0][15], sext(rows[f - 1][15] >> 8)) == sext(rows[f][7] >> 8)
            found[("sample 15", "lag 2, other-1")] = found.get(("sample 15", "lag 2, other-1"), 0) + ok15
    print("matches of MAIN's first L sample, by (gain lag, sample):",
          sorted(found.items(), key=lambda kv: -kv[1]))
    if pages:
        print("the input slots' words (AB, CD) on the last page:",
              " ".join(f"{w:04x}" for w in pages[-1][32:40]))
    # Where each input column sits in the WAV (channels 0-3 are inputs C, D,
    # A, B), and T1 (THRU on A|B), over the traced frames.
    import array
    import wave
    with wave.open(fx["audio_in"]) as w:
        data = array.array("h", w.readframes(w.getnframes()))
    chans = {"C": data[0::4], "D": data[1::4], "A": data[2::4], "B": data[3::4]}

    def top16(v):
        return (v >> 16) - 0x10000 if v & 0x80000000 else v >> 16
    for col, name, ch, k in ((9, "A, page idx", "A", 0), (10, "B, page idx", "B", 0),
                             (11, "C, page idx", "C", 0), (12, "D, page idx", "D", 0),
                             (13, "A last, page idx", "A", 15), (14, "A, page idx-1", "A", 0),
                             (3, "T1 this", "A", 0),
                             (4, "T1 other", "A", 0)):
        pos = wav_pos([top16(r[col]) for r in rows], chans[ch], k)
        print(f"{name}: " + ("not one run of the WAV" if pos is None
                             else f"WAV {ch} from sample {pos} at traced frame 0"))


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "one"
    if which == "trace":
        trace(ROOT / "out/stems_fixture_thru1.json")
        return
    fx = ROOT / {"one": "out/stems_fixture.json", "thru": "out/stems_fixture_thru.json",
                 "thru1": "out/stems_fixture_thru1.json"}[which]
    extra = []
    for a in sys.argv[2:]:
        if a.startswith("--poke"):
            continue
        if a.startswith("midi:"):
            extra += ["--midi", a[5:]]
            continue
        what, frame = a.split("@")
        extra += ["--step", f"{frame}:poke:{what}"]
    res = run(fx, extra=extra)
    print(f"exit {res['exit']}  write_idx {res['write_idx']}  sent_idx {res['sent_idx']}")
    for p in range(NPAGES + 1):
        pg = res["pages"][p * PAGE:(p + 1) * PAGE]
        print(f"page {p}: " + " ".join(f"{int.from_bytes(pg[i:i + 2], 'big'):04x}" for i in range(0, 0x58, 2)))
    print("X:0x4800 ", " ".join(f"{w:06x}" for w in res["dsp_x4800"]))
    print("Y targets", " ".join(f"{w:06x}" for w in res["dsp_targets"]))
    print("X:0x3dd  ", " ".join(f"{w:06x}" for w in res["dsp_state"]))
    print(f"table words unchanged at run end: {res['table_ok']}; the image's name format reads {res['image_string']!r}")
    print(f"writers of a page's MAIN level halfword: {sorted(res['w29_writers'])}")


if __name__ == "__main__":
    main()
