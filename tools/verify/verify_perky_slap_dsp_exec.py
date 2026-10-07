#!/usr/bin/env python3
"""Execute Slap on DSP: exact PCM, state, full ring and RNG each block.

Default inputs are synthetic, so the module gate needs no proprietary assets.
--firmware adds all nine original ARM continuation captures (16 DSP blocks each).
This is renderer qualification; production controls/placement remain separate.
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]
import slap_compact as slap
import resonator_compact as c
import simple_drum_tables as tables
from build_slap_source import source
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals
from verify_perky_simple_drum_envelope_exec import ASM, HOST, build_host
from perky_noise_hat_dsp_support import audit_source, audit_binary
from verify_perky_noise_hat_classic_synthetic_exec import make_envelopes, make_env, make_filter
from extract_noise_tone_tables import parse_container, find_m7

OUT = ROOT / 'out/perky/slap-dsp'
FIX = ROOT / 'out/perky/engine-fixtures'
STATE = RING = 0x200
SCRATCH = 0x1400
SB = SCRATCH - STATE
ENV1, ENV2 = 0x2000, 0x2600
ORG = 0x2800
FRAMES = 16


def equal(got, want, label):
    if got != want:
        differences = [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b]
        raise AssertionError(f'{label}: {differences[:8]}, lengths {len(got)}/{len(want)}')


def assemble(builder=source, voice='slap', out=OUT):
    build_host()
    out.mkdir(parents=True, exist_ok=True)
    text = (f'pk_{voice}_probe:\n move #>${STATE:x},r6\n move #>${SCRATCH:x},r5\n'
            f' move #>${RING:x},r4\n jsr pk_{voice}_voice\n rts\n' + builder())
    text = text.replace('#>$0009a5,r1', f'#>${ENV1:06x},r1')
    text = text.replace('#>$000c51,r1', f'#>${ENV2:06x},r1')
    audit_source(text)
    text = force_long_local_jsr(relativize_local_conditionals(text))
    asm, binary, symbols = (out / f'voice.{ext}' for ext in ('asm', 'bin', 'sym'))
    asm.write_text(text)
    result = subprocess.run([str(ASM), '-in', str(asm), '-org', f'{ORG:x}',
                             '-out', str(binary), '-sym', str(symbols), '-list'],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout[-6000:] + result.stderr)
    audit_binary(result.stdout, binary, ORG)
    labels = {p[0]: int(p[1], 16) for p in map(str.split, symbols.read_text().splitlines()) if len(p) == 2}
    return binary, labels[f'pk_{voice}_probe']


def run(binary, entry, voice, rng, envelopes, blocks, tag, out=OUT):
    e1, e2 = envelopes
    env1 = tables.pack_u16(struct.unpack('<1025H', e1[:2050]))
    env2 = tables.pack_u16(struct.unpack('<1025H', e2[:2050]))
    live_words, ring_words = len(voice.words), len(voice.ring)
    dump_words = max(ring_words, SB + 128)
    xwords = [0] * dump_words
    xwords[:live_words] = voice.words
    xwords[SB + 0x72:SB + 0x76] = [rng[0] & 65535, rng[0] >> 16, rng[1] & 65535, rng[1] >> 16]
    data = out / 'case.data'
    data.write_text('X 200 ' + ' '.join(f'{v:06x}' for v in xwords) + '\n'
                    + 'Y 200 ' + ' '.join(f'{v:06x}' for v in voice.ring) + '\n'
                    + f'Y {ENV1:x} ' + ' '.join(f'{v:06x}' for v in env1) + '\n'
                    + f'Y {ENV2:x} ' + ' '.join(f'{v:06x}' for v in env2) + '\n')
    script = out / 'case.script'
    script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * blocks)
    pcm, dump, meter = (out / f'case.{ext}' for ext in ('raw', 'state', 'meter'))
    subprocess.run([str(HOST), '-code', str(binary), '-org', f'{ORG:x}', '-entry', f'{entry:x}',
                    '-data', str(data), '-script', str(script), '-out', str(pcm), '-state', str(dump),
                    '-state-words', str(dump_words), '-meter', str(meter), '-cycle-meter', '1'],
                   check=True, capture_output=True, timeout=60)
    stereo = list(struct.unpack(f'<{FRAMES * blocks * 2}i', pcm.read_bytes()))
    got = stereo[::2]
    equal(stereo[1::2], got, tag + ' stereo')
    lines = dump.read_text().splitlines()
    assert len(lines) == blocks
    for block, line in enumerate(lines):
        want = voice.render(FRAMES, e1, e2, rng)
        equal(got[block * FRAMES:(block + 1) * FRAMES], want, f'{tag} block {block} PCM')
        words = [int(v, 16) & 65535 for v in line.split()]
        equal(words[:live_words], voice.words, f'{tag} block {block} X')
        equal(words[dump_words:dump_words + ring_words], voice.ring, f'{tag} block {block} ring')
        limbs = words[SB + 0x72:SB + 0x76]
        equal([limbs[0] | limbs[1] << 16, limbs[2] | limbs[3] << 16], rng, f'{tag} block {block} RNG')
    return got, max(map(int, meter.read_text().split()))


def synthetic(index):
    r = random.Random(0x534C4150 + index)
    w = [0] * slap.WORDS
    w[slap.VELOCITY] = r.choice((0, 1, 127, 255))
    make_env(w, slap.AMP_ENV, r, index % 3)
    w[slap.ENV_RESET] = index & 1
    w[slap.NOISE:slap.NOISE + 3] = [r.randrange(4), r.randrange(4), r.randrange(65536)]
    make_filter(w, slap.FILTER, r)
    w[slap.COUNTERS:slap.COUNTERS + 4] = [r.choice((0, 1, 65535)) for _ in range(4)]
    w[slap.TAPS:slap.TAPS + 5] = [r.randrange(slap.RING_LEN) for _ in range(5)]
    w[slap.TAPS + 5:slap.TAPS + 10] = [r.randrange(65536) for _ in range(5)]
    w[slap.INDEX] = slap.RING_LEN - 1 if index % 3 == 0 else r.randrange(slap.RING_LEN)
    w[slap.MIX] = r.randrange(65536)
    return slap.Slap(w, [r.randrange(65536) for _ in range(slap.RING_LEN)]), [r.getrandbits(32), r.getrandbits(32)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path)
    args = ap.parse_args()
    binary, entry = assemble()
    e1, e2, _, _ = make_envelopes()
    cases = []
    for index in range(48):
        voice, rng = synthetic(index)
        _, worst = run(binary, entry, voice, rng, (e1, e2), 4, f'synthetic {index}')
        cases.append({'case': f'synthetic {index}', 'blocks': 4, 'worst_cycles': worst})
    if args.firmware:
        manifest = json.loads((FIX / 'manifest.json').read_text())
        equal(hashlib.sha256(args.firmware.read_bytes()).hexdigest(), manifest['firmware_sha256'], 'firmware hash')
        segment = find_m7(parse_container(args.firmware.read_bytes())[1])
        e1, e2 = segment.read(0x08022EA0, 4096), segment.read(0x080236A2, 4096)
        for mode in range(1, 4):
            for corner in range(3):
                case = FIX / f'engine-8-mode-{mode}-corner-{corner}'
                for path in case.glob('*.bin'):
                    equal(hashlib.sha256(path.read_bytes()).hexdigest(), manifest['files'][str(path.relative_to(FIX))], 'fixture hash')
                state = lambda name: (case / name).read_bytes()[0xc4:0xc4 + 0x2670]
                voice = slap.Slap.from_arm(state('wrapper-window-after.bin'))
                rng = list(struct.unpack('<II', (case / 'rng-continuation-before.bin').read_bytes()))
                got, worst = run(binary, entry, voice, rng, (e1, e2), 16, case.name)
                equal(got, list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes())), case.name + ' ARM PCM')
                final = slap.Slap.from_arm(state('wrapper-window-continuation-after.bin'))
                equal(voice.words, final.words, case.name + ' ARM X')
                equal(voice.ring, final.ring, case.name + ' ARM ring')
                equal(struct.pack('<II', *rng), (case / 'rng-continuation-after.bin').read_bytes(), case.name + ' ARM RNG')
                cases.append({'case': case.name, 'blocks': 16, 'worst_cycles': worst})
    report = {'schema': 'perky-slap-dsp-v1', 'p_words': binary.stat().st_size // 3,
              'x_words': slap.WORDS, 'scratch_words': 128, 'y_ring_words': slap.RING_LEN,
              'worst_cycles': max(v['worst_cycles'] for v in cases), 'cases': cases}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"Slap DSP: PASS ({sum(v['blocks'] for v in cases)} consecutive blocks; exact stereo PCM/state/full ring/RNG; {report['p_words']} P words; worst {report['worst_cycles']} modeled cycles/16)")


if __name__ == '__main__':
    main()
