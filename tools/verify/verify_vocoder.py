#!/usr/bin/env python3
"""VOCODER render gates, against the float reference (modules/vocoder/vocoder_ref.py).

Renders the module straight through dsp_host (the render-gate shape: the id and the
slots come from the manifest, and the entry points are checked against SEND's so an
absent module cannot pass as a passthrough). The modulator is synthetic and
deterministic: a 120 Hz glottal pulse train through three formant resonators, the
vowel changing every 200 ms, with noise bursts for consonants, so no audio file is
needed.

Gates:
  the law       -> INT at C3 and EXT with a chord carrier: the output matches the float
                   reference within -50 dB (error RMS re signal RMS) and 0.1 dB in level
  silence       -> silence in gives silence out, bit-exact, with CONS and DRY up
  pauses        -> 0.3 s after the voice stops the output is below -100 dBFS (the
                   48-bit envelopes decay; 24-bit ones stuck at -90 and leaked carrier)
  bands         -> a sine at a band's centre on L, noise as the EXT carrier: the output's
                   power at that band is 15 dB or more above its neighbours'
  NOTE          -> the INT carrier's pitch is NOTE's within 0.05 % (C1, C3, C6)
  NOTE clamp    -> a saved NOTE byte past C6 plays C6
  two per core  -> runs at r7 0x6500 and 0x6800 (FX2 of T2 T3 T6 T7) and is an exact dry
                   pass at every other FX2 and FX1 state block
  every knob    -> renders at both ends without dsp_host dying

    python3 tools/verify/verify_vocoder.py
"""
import importlib.util, math, pathlib, struct, subprocess, sys, tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); import toolpath  # noqa: E402,F401
import send_probe  # dispatch-table entry resolution
from remix import registry
from remix.schema import R7_ALLOC

ROOT = pathlib.Path(__file__).resolve().parents[2]
MOD = registry.by_name("vocoder")
SEND = registry.by_name("send")
K = MOD.knob_map()
MEM = f"out/dsp/_audition_{MOD.name}_A.mem"
HOST = "vendor/dsp56300/build/source/dsp_host/dsp_host"
FXID = MOD.menu.fx2_id
FRAMES = 15
TMP = pathlib.Path(tempfile.mkdtemp(prefix="vcgate_"))

_spec = importlib.util.spec_from_file_location("vocoder_ref", ROOT / "modules/vocoder/vocoder_ref.py")
REF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(REF)
FS = REF.FS

pathlib.Path(MEM).unlink(missing_ok=True)
subprocess.run([sys.executable, "tools/remix/audition.py", MOD.name, "out/dry/drums_110.wav"],
               capture_output=True)
if not pathlib.Path(MEM).exists():
    sys.exit(f"no {MEM} -- build it first:\n  python3 tools/remix/audition.py {MOD.name} out/dry/drums_110.wav")
init, proc = send_probe.entry_points(MEM, FXID)
if (init, proc) == send_probe.entry_points(MEM, SEND.menu.fx2_id):
    sys.exit(f"fx id 0x{FXID:02x} resolves to SEND's entry points -- {MOD.name} is NOT in this dump")
print(f"entries from dispatch tables: init=P:0x{init:04x} proc=P:0x{proc:04x}")

DEFAULTS = [(p.default or 0) for p in MOD.params]


def params(**kw):
    v = list(DEFAULTS)
    for name, val in kw.items():
        v[K[name]] = val
    return v


def q23f(x):
    """What dsp_host hands back for an untouched frame: the Q23 input as floats."""
    return np.asarray(q23(x), float) / (1 << 23)


def q23(x):
    return [max(-(1 << 23), min((1 << 23) - 1, int(round(s * (1 << 23))))) for s in x]


ALLOC = R7_ALLOC                  # r7 (0x6000 + 0x100 n) -> its base-table entry


def render(L, R, r7=5, **kw):
    """L, R: float arrays. Returns (L, R) floats from the module. r7 = dsp_host's state block,
    0x6000 + 0x100 r7: 5 (0x6500) is a core's second FX2 slot, VOCODER's home; it runs at 5 and 8
    only (the built-in two-per-core limit, off a core's first track)."""
    n = len(L) - len(L) % FRAMES
    li, ri = q23(L[:n]), q23(R[:n])
    fin, fout = TMP / "vc_in.raw", TMP / "vc_out.raw"
    fin.write_bytes(b"".join(struct.pack("<ii", a, b) for a, b in zip(li, ri)))
    cmd = [HOST, "-mem", MEM, "-init", f"{init:x}", "-proc", f"{proc:x}",
           "-inst", "1", "-r7", str(r7), "-alloc", str(ALLOC[r7]), "-inmask", "1", "-stereo",
           "-frames", str(FRAMES), "-blocks", str(n // FRAMES),
           "-in", str(fin), "-out", str(fout),
           "-params", ",".join(str(x) for x in params(**kw))]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"dsp_host failed for {kw}:\n{r.stdout}\n{r.stderr}")
    w = np.frombuffer(fout.read_bytes(), dtype="<i4").astype(float) / (1 << 23)
    return w[0::2][:n], w[1::2][:n]


FAILS = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


def db(x):
    return 20 * math.log10(max(float(np.sqrt(np.mean(np.asarray(x) ** 2))), 1e-30))


def speech_like(seconds=2.0, seed=5):
    """A 120 Hz glottal pulse train through three formants, vowels every 200 ms, noise bursts."""
    def lfilter(b, a, x):                            # a two-pole resonator (no scipy here)
        y = np.zeros(len(x)); y1 = y2 = 0.0
        for i, v in enumerate(x):
            y0 = b[0] * v - a[1] * y1 - a[2] * y2
            y[i] = y0; y2, y1 = y1, y0
        return y
    n = int(seconds * FS); rng = np.random.default_rng(seed)
    src = np.zeros(n); src[::int(FS / 120)] = 1.0
    vowels = ((730, 1090, 2440), (270, 2290, 3010), (300, 870, 2240), (530, 1840, 2480), (570, 840, 2410))
    out = np.zeros(n); seg = int(0.2 * FS)
    for i in range(0, n, seg):
        x = src[i:i + seg].copy()
        if (i // seg) % 3 == 2:                      # a consonant: noise
            x = rng.uniform(-0.3, 0.3, len(x))
        y = np.zeros_like(x)
        for f in vowels[(i // seg) % len(vowels)]:
            r = math.exp(-math.pi * 80 / FS); th = 2 * math.pi * f / FS
            y += lfilter([1 - r], [1, -2 * r * math.cos(th), r * r], x)
        out[i:i + seg] = y * np.hanning(len(y)) ** 0.25
    return out / np.max(np.abs(out)) * 0.5


v = speech_like()
z = np.zeros_like(v)

# ---- the law ---------------------------------------------------------------------------
for label, L, R, kw in (("INT, C3", v, v, dict(MODE=0, NOTE=24, LEVL=127)),
                        ("EXT, a chord carrier on R", v,
                         sum(REF._saw(len(v), REF.note_inc(s), REF.note_idt(s), 0) for s in (24, 27, 31)) / 3,
                         dict(MODE=1, LEVL=127))):
    oL, oR = render(L, R, **kw)
    ref = REF.vocode(L[:len(oL)], R[:len(oL)], mode=kw["MODE"], note=kw.get("NOTE", 24),
                     cons=DEFAULTS[K["CONS"]], dry=0, levl=127)
    err = db(oL - ref) - db(ref)
    lv = db(oL) - db(ref)
    check(f"the law, {label}: within {err:.1f} dB of the float reference, level {lv:+.3f} dB (output {db(oL):.1f} dBFS RMS)",
          err < -50 and abs(lv) < 0.1 and np.array_equal(oL, oR))

# ---- silence and pauses ---------------------------------------------------------------------
oL, _ = render(z[:44100], z[:44100], CONS=127, DRY=127, LEVL=127)
check("silence in, silence out (CONS and DRY up)", not np.any(oL))
vp = np.concatenate([v[:int(FS)], np.zeros(int(0.6 * FS))])
oL, _ = render(vp, vp, LEVL=127)
tail = db(oL[-int(0.3 * FS):])
check(f"0.3 s into a pause the output is {tail:.1f} dBFS", tail < -100)

# ---- bands ------------------------------------------------------------------------------------
rng = np.random.default_rng(9)
noise = rng.uniform(-0.9, 0.9, int(FS))
t = np.arange(int(FS)) / FS
worst = 99.0
for k in (1, 4, 7):
    fc = REF.CENTRES[k]
    oL, _ = render(0.5 * np.sin(2 * np.pi * fc * t), noise, MODE=1, LEVL=127, CONS=0)
    X = np.abs(np.fft.rfft(oL[4410:])) ** 2; fr = np.fft.rfftfreq(len(oL) - 4410, 1 / FS)
    p = lambda f: X[(fr > f / 1.1) & (fr < f * 1.1)].sum()
    sel = 10 * math.log10(p(fc) / max(p(REF.CENTRES[k - 1]), p(REF.CENTRES[k + 1])))
    worst = min(worst, sel)
check(f"bands: a centre sine keeps its band at least {worst:.1f} dB above the neighbours", worst > 15)

# ---- NOTE ---------------------------------------------------------------------------------------
noise3 = np.random.default_rng(11).uniform(-0.9, 0.9, int(3 * FS))
for step in (0, 24, 60):
    oL, _ = render(noise3, noise3, MODE=0, NOTE=step, LEVL=127, CONS=0)
    x = oL[4410:]; n = len(x)
    X = np.abs(np.fft.rfft(x * np.hanning(n), 4 * n)); fr = np.fft.rfftfreq(4 * n, 1 / FS)
    f0 = 440.0 * 2 ** ((REF.NOTE_LO + step - 69) / 12)
    h = max(1, math.ceil(400 / f0))                   # a harmonic inside the bands
    m = np.nonzero((fr > h * f0 * 0.99) & (fr < h * f0 * 1.01))[0]
    i = m[np.argmax(X[m])]
    a_, b_, c_ = np.log(X[i - 1:i + 2])               # parabolic interpolation of the peak
    fm = (fr[i] + 0.5 * (a_ - c_) / (a_ - 2 * b_ + c_) * (fr[1] - fr[0])) / h
    check(f"NOTE {REF.note_name(step)}: {fm:.3f} Hz (want {f0:.3f}; harmonic {h})", abs(fm / f0 - 1) < 5e-4)
a, _ = render(noise[:22050], noise[:22050], NOTE=99, LEVL=127)
b, _ = render(noise[:22050], noise[:22050], NOTE=60, LEVL=127)
check("a NOTE byte past C6 plays C6", np.array_equal(a, b))

# ---- two per core, built in: runs at r7 0x6500 and 0x6800 only, dry elsewhere -------------------
# Three on a core overran the MKII. The FX2 blocks are 0x6200 + 0x300 pos and the FX1 blocks
# 0x6100 + 0x300 pos (measured under the port, modules/send/README.md); dsp_host's -r7 n is
# 0x6000 + 0x100 n. A dry pass writes nothing, so its output is its input bit for bit.
src = noise[:22050]
runs, dry = [], []
for r7 in (5, 8, 2, 11, 1, 4, 7, 10):
    L, R = render(src, src, r7=r7, LEVL=127, CONS=127, DRY=0)
    (dry if np.array_equal(L, q23f(src)) and np.array_equal(R, q23f(src)) else runs).append(r7)
check("runs at FX2 positions 1 and 2 only (r7 0x6500, 0x6800): T2 T3 T6 T7",
      runs == [5, 8], f"(runs at {[hex(0x6000 + 0x100 * r) for r in runs]})")
check("an exact dry pass at FX2 positions 0 and 3 (T1 T4 T5 T8) and every FX1 slot",
      dry == [2, 11, 1, 4, 7, 10], f"(dry at {[hex(0x6000 + 0x100 * r) for r in dry]})")

# ---- every knob at both ends ---------------------------------------------------------------------
for name, hi in (("NOTE", 60), ("CONS", 127), ("DRY", 127), ("LEVL", 127), ("MODE", 1)):
    for val in (0, hi):
        render(v[:22050], v[:22050], **{name: val})
check("every knob at both ends renders", True)

if FAILS:
    sys.exit(f"verify_vocoder: {len(FAILS)} gate(s) failed")
print("verify_vocoder: OK")
