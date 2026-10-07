#!/usr/bin/env python3
"""Execute resonant bass/snare DSP against compact and original ARM oracles.

No claim of realtime or production qualification. Default uses synthetic
tables; --firmware adds original ARM continuations for both resonant paths.
Panel M3's reused Noise/Tone path is covered by separate Noise/Tone gates.
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
import resonator_compact as c
import resonant_dsp as recipe
import resonant_bass_compact as bass
import resonant_snare_compact as snare
import simple_drum_tables as tables
from verify_perky_slap_dsp_exec import assemble, equal, FIX, SB, ENV1, ENV2, ORG, HOST
from verify_perky_noise_hat_classic_synthetic_exec import make_envelopes, make_env
from extract_noise_tone_tables import parse_container, find_m7

OUT = ROOT / 'out/perky/resonant-dsp'


def run(binary, entry, voice, rng, table_data, blocks, tag, scratch_words, out):
    e1, e2, ia, ib = table_data
    dump_words = SB + scratch_words
    words = [0] * dump_words
    words[:len(voice.words)] = voice.words
    words[SB + 0x72:SB + 0x76] = [rng[0] & 65535, rng[0] >> 16, rng[1] & 65535, rng[1] >> 16]
    data = out / 'case.data'
    records = [('X', 0x200, words), ('Y', ENV1, tables.pack_u16(struct.unpack('<1025H', e1[:2050]))),
               ('Y', ENV2, tables.pack_u16(struct.unpack('<1025H', e2[:2050]))),
               ('Y', recipe.INTERP_A, struct.unpack('<257H', ia)),
               ('Y', recipe.INTERP_B, struct.unpack('<257H', ib))]
    data.write_text(''.join(f'{space} {address:x} ' + ' '.join(f'{v:06x}' for v in values) + '\n'
                            for space, address, values in records))
    script = out / 'case.script'
    script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * blocks)
    pcm, dump, meter = (out / f'case.{ext}' for ext in ('raw', 'state', 'meter'))
    subprocess.run([str(HOST), '-code', str(binary), '-org', f'{ORG:x}', '-entry', f'{entry:x}',
                    '-data', str(data), '-script', str(script), '-out', str(pcm), '-state', str(dump),
                    '-state-words', str(dump_words), '-meter', str(meter), '-cycle-meter', '1'],
                   check=True, capture_output=True, timeout=60)
    stereo = list(struct.unpack(f'<{16 * blocks * 2}i', pcm.read_bytes()))
    got = stereo[::2]
    equal(stereo[1::2], got, tag + ' stereo')
    lines = dump.read_text().splitlines()
    assert len(lines) == blocks
    for block, line in enumerate(lines):
        want = voice.render(16, e1, e2, ia, ib, rng)
        equal(got[block * 16:(block + 1) * 16], want, f'{tag} block {block} PCM')
        words = [int(v, 16) & 65535 for v in line.split()]
        equal(words[:len(voice.words)], voice.words, f'{tag} block {block} X')
        limbs = words[SB + 0x72:SB + 0x76]
        equal([limbs[0] | limbs[1] << 16, limbs[2] | limbs[3] << 16], rng, f'{tag} block {block} RNG')
    return got, max(map(int, meter.read_text().split()))


def synthetic(family, index):
    r = random.Random(0x5245534F + index)
    model, cls = (bass, bass.ResonantBass) if family == 'bass' else (snare, snare.ResonantSnare)
    w = [0] * model.WORDS
    w[0] = r.choice((0, 1, 127, 255))
    make_env(w, model.AMP_ENV, r, index % 3)
    w[model.NOISE:model.NOISE + 3] = [r.randrange(4), r.randrange(4), r.randrange(65536)]
    resonators = (bass.TONE_RES, bass.NOISE_RES) if family == 'bass' else (snare.RES1, snare.RES2, snare.RES3)
    for base in resonators:
        w[base + c.RES_DIRTY] = index & 1
        w[base + c.RES_PITCH_A] = r.randrange(65536)
        w[base + c.RES_PITCH_B] = r.randrange(65536)
        for field in (c.RES_COEFF_A, c.RES_COEFF_B):
            c.set_u32(w, base + field, r.randrange(65536))
        c.set_u32(w, base + c.RES_MOD, r.choice((0, 1, 65535, 0xFFFFFFFF)))
        w[base + c.RES_BYPASS] = r.randrange(2)
        for field in (c.RES_POSITION, c.RES_VELOCITY):
            c.set_u32(w, base + field, r.randint(-32767, 32767))
    decays = (bass.DECAY_A, bass.DECAY_B, bass.DECAY_C, bass.DECAY_LEVEL) if family == 'bass' else (snare.DECAY_A, snare.DECAY_B, snare.DECAY_C, snare.DECAY_D)
    for base in decays:
        for field in (c.DECAY_MUL, c.DECAY_VALUE):
            c.set_u32(w, base + field, r.getrandbits(32))
        c.set_u32(w, base + c.DECAY_COUNT, r.choice((0, 1, 2, 0xFFFFFFFF)))
        c.set_u32(w, base + c.DECAY_SIGN, r.choice((0, 0x80000000, 0xFFFFFFFF, 32767)))
        c.set_u32(w, base + c.DECAY_MIN, r.randint(-65536, 65536))
    if family == 'bass':
        w[bass.PITCH] = r.randrange(65536)
        c.set_u32(w, bass.RESONATOR_STATE, r.getrandbits(32))
        c.set_u32(w, bass.RESONATOR_COEFF, r.getrandbits(32))
    else:
        c.set_u32(w, snare.MIX_FIRST, r.getrandbits(32))
        c.set_u32(w, snare.MIX_SECOND, r.getrandbits(32))
    return cls(w), [r.getrandbits(32), r.getrandbits(32)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path)
    args = ap.parse_args()
    e1, e2, _, _ = make_envelopes()
    ia = struct.pack('<257H', *[(i * 257 + i * i) & 65535 for i in range(257)])
    ib = struct.pack('<257H', *[(65535 - i * 251) & 65535 for i in range(257)])
    synthetic_tables = e1, e2, ia, ib
    report = {'schema': 'perky-resonant-dsp-v1', 'families': {}}
    for family, model, cls, panel, offset, size in (
        ('bass', bass, bass.ResonantBass, 2, 0x39E8, 0x178),
        ('snare', snare, snare.ResonantSnare, 1, 0x2734, 0x1D4),
    ):
        out = OUT / family
        text, scratch = recipe.source(family)
        binary, entry = assemble(lambda: text, 'resonant_' + family, out)
        cases = []
        for index in range(32):
            voice, rng = synthetic(family, index)
            _, worst = run(binary, entry, voice, rng, synthetic_tables, 4, f'{family} synthetic {index}', scratch, out)
            cases.append({'case': f'synthetic {index}', 'blocks': 4, 'worst_cycles': worst})
        if args.firmware:
            manifest = json.loads((FIX / 'manifest.json').read_text())
            equal(hashlib.sha256(args.firmware.read_bytes()).hexdigest(), manifest['firmware_sha256'], 'firmware hash')
            segment = find_m7(parse_container(args.firmware.read_bytes())[1])
            original_tables = tuple(segment.read(address, length) for address, length in
                                    ((0x08022EA0, 4096), (0x080236A2, 4096), (0x0803237C, 514), (0x08032178, 514)))
            for corner in range(3):
                case = FIX / f'engine-7-mode-{panel}-corner-{corner}'
                for path in case.glob('*.bin'):
                    equal(hashlib.sha256(path.read_bytes()).hexdigest(), manifest['files'][str(path.relative_to(FIX))], 'fixture hash')
                state = lambda name: (case / name).read_bytes()[offset:offset + size]
                voice = cls.from_arm(state('wrapper-window-after.bin'))
                rng = list(struct.unpack('<II', (case / 'rng-continuation-before.bin').read_bytes()))
                got, worst = run(binary, entry, voice, rng, original_tables, 16, case.name, scratch, out)
                equal(got, list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes())), case.name + ' ARM PCM')
                equal(voice.words, cls.from_arm(state('wrapper-window-continuation-after.bin')).words, case.name + ' ARM X')
                equal(struct.pack('<II', *rng), (case / 'rng-continuation-after.bin').read_bytes(), case.name + ' ARM RNG')
                cases.append({'case': case.name, 'blocks': 16, 'worst_cycles': worst})
        result = {'p_words': binary.stat().st_size // 3, 'x_words': model.WORDS,
                  'scratch_words': scratch, 'worst_cycles': max(v['worst_cycles'] for v in cases), 'cases': cases}
        report['families'][family] = result
        print(f"Resonant {family} DSP: PASS ({sum(v['blocks'] for v in cases)} blocks; exact stereo PCM/state/RNG; {result['p_words']} P words; {scratch} scratch; worst {result['worst_cycles']} modeled cycles/16)", flush=True)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
