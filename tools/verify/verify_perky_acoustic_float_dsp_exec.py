#!/usr/bin/env python3
"""Execute Acoustic Hats' finite IEEE754 kernels on the DSP.

Compare bits to host IEEE754 operations, including signed zero, subnormals,
nearest/even ties, cancellation, and signed32 conversion boundaries. DSP
float-to-int inputs stay in the original renderer's defined signed32 domain.
"""
from pathlib import Path
import json
import math
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]
from dsp_u32 import Emitter
from resonant_dsp import PERKY
from acoustic_float_dsp import kernels
from verify_perky_slap_dsp_exec import assemble, HOST, ORG

OUT = ROOT / 'out/perky/acoustic-float-dsp'


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def value(raw):
    return struct.unpack('<f', struct.pack('<I', raw))[0]


def source():
    e = Emitter()
    e.lines.append('pk_acoustic_float_voice:')
    e.emit('move r5,a', 'add #>$80,a', 'move a1,r4')
    labels = [e.label() for _ in range(4)]
    for op, label in enumerate(labels):
        e.compare(e.state(0, 16), op, 'beq', label)
    e.emit('rts')
    for op, label in enumerate(labels):
        e.mark(label)
        if op == 0:
            e.assign(e.var('fp_int_in'), e.state(1))
            e.emit('jsr pk_acoustic_int_to_float')
        elif op == 1:
            e.assign(e.var('fp_bits_in'), e.state(1))
            e.emit('jsr pk_acoustic_float_decay')
        elif op == 2:
            e.assign(e.var('fp_add_a'), e.state(1))
            e.assign(e.var('fp_add_b'), e.state(3))
            e.emit('jsr pk_acoustic_float_add')
        else:
            e.assign(e.var('fp_bits_in'), e.state(1))
            e.emit('jsr pk_acoustic_float_to_int')
        e.assign(e.state(5), e.var('fp_int_out' if op == 3 else 'fp_bits_out'))
        e.emit('rts')
    kernels(e)
    return '\n'.join(e.lines) + '\n' + (PERKY / 'noise_tone_math.asm').read_text()


def cases():
    r = random.Random(0xF32)
    integers = [0, 1, -1, 32767, -32768, 0x7FFFFFFF, -0x80000000,
                0xFFFFFF, 0x1000001, 0x1000003, -0x1000001, -0x1000003]
    integers += [r.randrange(-0x80000000, 0x80000000) for _ in range(160)]
    result = [(0, n & 0xFFFFFFFF, 0, bits(f32(float(n)))) for n in integers]
    floats = [0, 0x80000000, 1, 2, 3, 0x7FFFFF, 0x800000, 0x800001,
              0x807FFFFF, 0x80800000, 0x3F800000, 0xBF800000, 0x7F7FFFFF, 0xFF7FFFFF]
    floats += [(r.randrange(2) << 31) | (r.randrange(255) << 23) | r.randrange(1 << 23) for _ in range(256)]
    result += [(1, raw, 0, bits(f32(value(raw) * value(0x3F7AE148)))) for raw in floats]
    pairs = [(0, 0x80000000), (0x80000000, 0x80000000), (1, 0x80000001),
             (0x800000, 0x807FFFFF), (0x3F800000, 0x33800000),
             (0x3F800001, 0x33800000), (0x3F800000, 0xBF7FFFFF)]
    for _ in range(256):
        raw = lambda: (r.randrange(2) << 31) | (r.randrange(200) << 23) | r.randrange(1 << 23)
        a = raw()
        b = a ^ 0x80000000 if r.randrange(5) == 0 else raw()
        pairs.append((a, b))
    result += [(2, a, b, bits(f32(value(a) + value(b)))) for a, b in pairs]
    floats = [0, 0x80000000, 1, 0x3F7FFFFF, 0xBF7FFFFF, 0x3F800000, 0xBF800000, 0x4EFFFFFF, 0xCEFFFFFF]
    floats += [(r.randrange(2) << 31) | (r.randrange(158) << 23) | r.randrange(1 << 23) for _ in range(160)]
    result += [(3, raw, 0, int(value(raw)) & 0xFFFFFFFF) for raw in floats]
    return result


def main():
    binary, entry = assemble(source, 'acoustic_float', OUT)
    script = OUT / 'case.script'
    script.write_text(' '.join(['0'] * 12 + ['-1']) + '\n')
    data, pcm, dump, meter = (OUT / f'case.{ext}' for ext in ('data', 'raw', 'state', 'meter'))
    worst = [0] * 4
    corpus = cases()
    for index, (op, a, b, want) in enumerate(corpus):
        words = [op, a & 65535, a >> 16, b & 65535, b >> 16, 0, 0]
        data.write_text('X 200 ' + ' '.join(f'{v:06x}' for v in words) + '\n')
        subprocess.run([str(HOST), '-code', str(binary), '-org', f'{ORG:x}', '-entry', f'{entry:x}',
                        '-data', str(data), '-script', str(script), '-out', str(pcm), '-state', str(dump),
                        '-state-words', '7', '-meter', str(meter), '-cycle-meter', '1'],
                       check=True, capture_output=True, timeout=60)
        final = [int(v, 16) & 65535 for v in dump.read_text().split()]
        got = final[5] | final[6] << 16
        assert got == want, (index, op, f'{a:08x}', f'{b:08x}', f'{got:08x}', f'{want:08x}')
        worst[op] = max(worst[op], int(meter.read_text().strip()))
    report = {'schema': 'perky-acoustic-float-dsp-v1', 'cases': len(corpus),
              'p_words': binary.stat().st_size // 3, 'worst_cycles_per_operation': worst}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Acoustic IEEE754 DSP: PASS ({len(corpus)} bit-exact operations; int conversion/0.98f multiply/add/truncation; worst cycles {worst})')


if __name__ == '__main__':
    main()
