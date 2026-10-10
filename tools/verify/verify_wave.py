#!/usr/bin/env python3
"""WAVE under dsp_host: pitch from the carrier, the chord, a pitch step, the
envelope, silence, eight instances, the instruction bound.

    python3 tools/verify/verify_wave.py [remix]   # make check: the remix just built

Renders the remix's own image (out/mainos_bus.bin), both payloads. Executed
instructions, not hardware cycles.
"""
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import toolpath  # noqa: F401,E402
import benchmark_reverbs as br  # noqa: E402
import send_probe  # noqa: E402
from remix import registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/wave_verify'
FR = 16
SR = 44100
C5 = 523.2511
INSTR_BOUND = 9500          # one instance, instructions a 16-sample block (measured 9,133 peak)
fails = []


def gate(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)
    if not ok:
        fails.append(name)


def sine(segments, n):
    """segments: [(start_sample, freq, amp)], each until the next."""
    out, phase = np.zeros(n), 0.0
    bounds = [s for s, _, _ in segments] + [n]
    for (s, f, a), e in zip(segments, bounds[1:]):
        t = np.arange(e - s)
        out[s:e] = a * np.sin(phase + 2 * math.pi * f * t / SR)
        phase += 2 * math.pi * f * (e - s) / SR
    return np.round(out * 8388607).astype(int).tolist()


class Host:
    def __init__(self, mems, mod):
        self.mems, self.mod = mems, mod

    def render(self, tag, knobs, inputs, positions, blocks, extra=(), timeout=600):
        eps = [send_probe.entry_points(self.mems[k // 4], self.mod.menu.fx2_id) for k in positions]
        out = OUT / f'{tag}.raw'
        cmd = [str(br.HOST), '-mem', str(self.mems[0]), '-memB', str(self.mems[1]),
               '-init', ','.join(f'{e[0]:x}' for e in eps), '-proc', ','.join(f'{e[1]:x}' for e in eps),
               '-inst', str(len(positions)), '-core', ','.join(str(k // 4) for k in positions),
               '-alloc', ','.join(str(1 + 2 * (k % 4)) for k in positions),
               '-r7', ','.join(str(2 + 3 * (k % 4)) for k in positions),
               '-audioidx', ','.join(str(k % 4) for k in positions),
               '-allocproc', 'end', '-frames', str(FR), '-blocks', str(blocks),
               '-out', str(out), '-meter', str(out.with_suffix('.meter'))]
        paths = []
        for j, x in enumerate(inputs):
            p = OUT / f'{tag}.in{j}.raw'
            br.raw(p, x)
            paths.append(str(p))
        cmd += ['-in', ','.join(paths)]
        for k in knobs:
            cmd += ['-params', ','.join(map(str, k))]
        cmd += list(extra)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise SystemExit(f'{tag}: dsp_host failed\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}')
        audio = [np.array(br.read_raw(Path(str(out) + (f'.i{j}' if j else ''))), dtype=np.int64).reshape(-1, 2)
                 for j in range(len(positions))]
        meter = np.array([[int(v) for v in line.split()] for line in out.with_suffix('.meter').read_text().splitlines()])
        return audio, meter


def peak_freqs(x, k, lo=40.0):
    """The k strongest spectral peaks (Hz), parabolic-interpolated."""
    n = 1 << 16
    seg = x[:n] * np.hanning(min(n, len(x)))
    sp = np.abs(np.fft.rfft(seg, n))
    lg = np.log(sp + 1e-12)
    peaks = [i for i in range(2, len(sp) - 1) if sp[i] > sp[i - 1] and sp[i] >= sp[i + 1] and i * SR / n > lo]
    peaks.sort(key=lambda i: -sp[i])
    out = []
    for i in peaks[:k]:
        d = (lg[i - 1] - lg[i + 1]) / (2 * (lg[i - 1] - 2 * lg[i] + lg[i + 1]))
        out.append(((i + d) * SR / n, sp[i]))
    return sorted(out)


def cents(f, ref):
    return 1200 * math.log2(f / ref)


def db(x):
    return 20 * math.log10(max(x, 1e-12))


def verify(mems):
    OUT.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(ROOT / 'modules/wave/generate.py'), '--check'],
                       capture_output=True, text=True)
    gate('wave.asm matches generate.py', r.returncode == 0, (r.stdout + r.stderr).strip())
    mod = registry.by_key('WAVE')
    host = Host(mems, mod)
    d = [p.default or 0 for p in mod.params]
    # page-2 defaults go in their delivered fields; dsp_host maps slots 6..11
    blocks = int(2.5 * SR / FR)
    n = blocks * FR
    settle = int(1.0 * SR)

    # 1. pitch: OCT -2 from three carriers
    for f in (C5 / 2, C5, C5 * 2):
        (a,), _ = host.render('pitch', [d], [sine([(0, f, .5)], n)], [4], blocks)
        got = peak_freqs(a[settle:, 0] / 2 ** 23, 1)[0][0]
        gate(f'carrier {f:.1f} Hz -> {f / 4:.2f} Hz at OCT -2', abs(cents(got, f / 4)) < 2,
             f'{got:.3f} Hz, {cents(got, f / 4):+.2f} cents')

    # 2. the MAJ chord: root, +4, +7, +12 semitones
    k = list(d); k[3] = 3
    (a,), _ = host.render('chord', [k], [sine([(0, C5, .5)], n)], [4], blocks)
    root = C5 / 4
    want = [root * 2 ** (s / 12) for s in (0, 4, 7, 12)]
    got = peak_freqs(a[settle:, 0] / 2 ** 23, 4)
    errs = [cents(g, w) for (g, _), w in zip(got, want)]
    levels = [db(m) for _, m in got]
    gate('MAJ: four partials at 0, +4, +7, +12', all(abs(e) < 3 for e in errs),
         ', '.join(f'{g:.2f}' for g, _ in got) + ' Hz')
    gate('MAJ: the four within 3 dB', max(levels) - min(levels) < 3, f'{max(levels) - min(levels):.2f} dB spread')

    # 3. a pitch step C5 -> G5 at 1.0 s; 10 ms later the new pitch is there
    step = int(1.0 * SR)
    (a,), _ = host.render('step', [d], [sine([(0, C5, .5), (step, C5 * 1.5, .5)], n)], [4], blocks)
    after = a[step + int(.010 * SR):, 0] / 2 ** 23
    got = peak_freqs(after, 1)[0][0]
    gate('pitch step: G5 carrier -> G3 within 10 ms', abs(cents(got, C5 * 1.5 / 4)) < 2,
         f'{got:.3f} Hz, {cents(got, C5 * 1.5 / 4):+.2f} cents')

    # 4. the envelope: half the carrier is half the output; a stop is silence
    stop = int(1.5 * SR)
    (a,), _ = host.render('env', [d], [sine([(0, C5, .5), (int(1.0 * SR), C5, .25), (stop, C5, 0)], n)], [4], blocks)
    x = a[:, 0] / 2 ** 23
    full = np.sqrt(np.mean(x[int(.6 * SR):int(.95 * SR)] ** 2))
    half = np.sqrt(np.mean(x[int(1.1 * SR):int(1.45 * SR)] ** 2))
    gate('envelope: carrier -6.02 dB -> output -6.02 dB', abs(db(half / full) + 6.02) < .3, f'{db(half / full):+.2f} dB')
    # two 2.9 ms one-poles: -79 dBFS at 30 ms (measured)
    tail = np.abs(x[stop + int(.060 * SR):]).max()
    gate('envelope: 60 ms after the carrier stops, below -90 dBFS', db(tail) < -90, f'{db(tail):.1f} dBFS')
    last = np.abs(a[stop + int(.5 * SR):, 0]).max()
    gate('envelope: 0.5 s after the carrier stops, exactly zero', last == 0, f'max {last} LSB')

    # 5. silence in: silence out, every sample
    (a,), _ = host.render('silence', [d], [[0] * n], [4], blocks)
    gate('silent carrier: every output sample zero', not np.any(a), f'max |x| = {np.abs(a).max()}')

    # 6. eight instances: together == alone, bit for bit; a different carrier each
    b8 = int(1.2 * SR / FR)
    n8 = b8 * FR
    ins = [sine([(0, C5 * 2 ** (j / 12), .3 + .05 * j)], n8) for j in range(8)]
    knobs8 = []
    for j in range(8):
        kk = list(d); kk[3] = j; kk[0] = 16 * j; kk[1] = 40 + 10 * j
        knobs8.append(kk)
    together, meter8 = host.render('eight', knobs8, ins, list(range(8)), b8)
    for j in range(8):
        (alone,), _ = host.render(f'solo{j}', [knobs8[j]], [ins[j]], [j], b8)
        gate(f'slot {j}: eight together == alone', np.array_equal(together[j], alone))

    # 8. a modulated knob word: the LFO leaves a non-zero byte in bits 8-15
    # (measured 21,011 of 21,088 stores under the port, 5 Oct 2026). OCT is
    # r6+4; dsp_host -pword writes the raw word after -params.
    tone = sine([(0, C5, .5)], n)
    ref = {}
    for oct_ in (1, 2, 4):
        k = list(d); k[4] = oct_
        (ref[oct_],), _ = host.render(f'oct{oct_}', [k], [tone], [4], blocks)
    f2 = peak_freqs(ref[2][settle:, 0] / 2 ** 23, 1)[0][0]
    f1 = peak_freqs(ref[1][settle:, 0] / 2 ** 23, 1)[0][0]
    gate('OCT 1 and OCT 2 clean words are an octave apart', abs(cents(f2, f1) - 1200) < 5, f'{f1:.2f} Hz, {f2:.2f} Hz')
    k = list(d); k[4] = 2
    (probe,), _ = host.render('pword_probe', [k], [tone], [4], blocks, extra=['-pword', '0:4=010000'])
    gate('dsp_host takes -pword (raw OCT word 0x010000 renders as OCT 1)', np.array_equal(probe, ref[1]))
    for oct_, word in ((4, 0x0400fe), (2, 0x0200fe), (4, 0x047f7f)):
        k = list(d); k[4] = oct_
        try:
            (a,), m = host.render(f'dirty{word:06x}', [k], [tone], [4], blocks,
                                  extra=['-pword', f'0:4={word:06x}'], timeout=120)
        except subprocess.TimeoutExpired:
            gate(f'OCT word {word:06x}: renders within 120 s', False, 'timeout')
            continue
        peak_i = int(m[:, 2].max())
        gate(f'OCT word {word:06x}: <= {INSTR_BOUND} instructions a block', peak_i <= INSTR_BOUND, f'peak {peak_i}')
        got = peak_freqs(a[settle:, 0] / 2 ** 23, 1)[0][0]
        want = peak_freqs(ref[oct_][settle:, 0] / 2 ** 23, 1)[0][0]
        gate(f'OCT word {word:06x}: pitch == the clean word\'s', abs(cents(got, want)) < 2,
             f'{got:.3f} Hz vs {want:.3f} Hz ({cents(got, want):+.1f} cents)')
        gate(f'OCT word {word:06x}: output == the clean word\'s, bit for bit', np.array_equal(a, ref[oct_]))
    k = list(d); k[3] = 3
    (cl,), _ = host.render('chrd_clean', [k], [tone], [4], blocks)
    (dt,), _ = host.render('chrd_dirty', [k], [tone], [4], blocks, extra=['-pword', '0:3=0300fe'])
    gate('CHRD word 0300fe: output == the clean word\'s, bit for bit', np.array_equal(cl, dt))

    # 7. instructions: one instance's peak block
    (_,), meter = host.render('meter', [d], [sine([(0, C5, .5)], n)], [4], blocks)
    peak = int(meter[:, 2].max())
    gate(f'one instance <= {INSTR_BOUND} instructions a block', peak <= INSTR_BOUND,
         f'peak {peak}, steady mean {meter[200:, 2].mean():.0f} ({peak / FR:.0f} a sample)')
    p8 = int(meter8[:, 1:3].max())
    print(f'  four instances on one core: peak {p8} instructions a block ({p8 / FR:.0f} a sample)')
    return not fails


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'wave'
    if 'WAVE' not in registry.remix(name).modules:
        print(f'[N/A] verify_wave: {name} does not carry WAVE')
        sys.exit(0)
    image = ROOT / 'out/mainos_bus.bin'
    if len(sys.argv) <= 1:
        subprocess.run([sys.executable, 'tools/build/build_bus.py'], cwd=ROOT, check=True,
                       env={**__import__('os').environ, 'REMIX': name, 'XBUS': '1', 'SPEC': '1'},
                       capture_output=True)
    OUT.mkdir(parents=True, exist_ok=True)
    mems = [send_probe.dump_mem(image, OUT / f'{name}_{p}.mem', p) for p in 'AB']
    ok = verify(mems)
    print('verify_wave:', 'every gate passed' if ok else f'{len(fails)} failed: {fails}')
    sys.exit(0 if ok else 1)
