#!/usr/bin/env python3
"""Execute authentic Noise/Tone modes and Resonant M3 against ARM captures.

The physically working PERKY2 synthetic-control path remains separate. Default
uses synthetic tables; --firmware adds all 12 original continuation cases.
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
import noise_tone_compact as shared
import noise_tone_wave2_compact as w2
import noise_tone_original_dsp as recipe
import resonator_compact as c
from noise_tone_word_model import WordRng
import simple_drum_tables as tables
from verify_perky_slap_dsp_exec import assemble, equal, FIX, SB, ENV1, ENV2, ORG, HOST
from verify_perky_noise_hat_classic_synthetic_exec import make_envelopes, make_env, make_filter
from extract_noise_tone_tables import parse_container, find_m7

OUT = ROOT / 'out/perky/noise-tone-original-dsp'
IDS = (0x080222A0, 0x080226A0, 0x080228A0, 0x080224A0)


def run(binary, entry, voice, rng, waves, envelopes, blocks, tag, scratch, kind):
    e1, e2 = envelopes
    dump_words = SB + scratch
    words = [0] * dump_words
    words[:len(voice.words)] = voice.words
    words[SB + 0x72:SB + 0x76] = [rng[0] & 65535, rng[0] >> 16, rng[1] & 65535, rng[1] >> 16]
    records = [('X', 0x200, words), ('Y', ENV1, tables.pack_u16(struct.unpack('<1025H', e1[:2050]))),
               ('Y', ENV2, tables.pack_u16(struct.unpack('<1025H', e2[:2050])))]
    if kind == 'shared':
        samples = [v for address in IDS for v in struct.unpack('<256H', waves[address])]
        records.append(('Y', 0x7A5, tables.pack_u16(samples)))
    else:
        identities = list(waves)
        assert 1 <= len(identities) <= 2
        if len(identities) == 1:
            identities *= 2
        words[SB + 0x76:SB + 0x78] = [0x4000, 0x5000]
        c.set_u32(words, SB + 0x78, identities[0])
        c.set_u32(words, SB + 0x7A, identities[1])
        for address, base in zip(identities, (0x4000, 0x5000)):
            records.append(('Y', base, struct.unpack('<2048H', waves[address])))
    out = OUT / kind
    data = out / 'case.data'
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
        if kind == 'shared':
            word_rng = WordRng.from_ints(*rng)
            want = shared.render_block(voice, 16, waves, word_rng, e1, e2)
            rng[:] = [word_rng.low.unsigned(), word_rng.high.unsigned()]
        else:
            want = voice.render(16, waves)
        equal(got[block * 16:(block + 1) * 16], want, f'{tag} block {block} PCM')
        words = [int(v, 16) & 65535 for v in line.split()]
        equal(words[:len(voice.words)], voice.words, f'{tag} block {block} X')
        if kind == 'shared':
            limbs = words[SB + 0x72:SB + 0x76]
            equal([limbs[0] | limbs[1] << 16, limbs[2] | limbs[3] << 16], rng, f'{tag} block {block} RNG')
    return got, max(map(int, meter.read_text().split()))


def synthetic(kind, index):
    r = random.Random(0x4E544F52 + index)
    if kind == 'shared':
        words = [0] * shared.WORDS_PER_VOICE
        words[0] = r.choice((0, 1, 127, 255))
        make_env(words, 1, r, index % 3)
        words[12:15] = [r.randrange(5), r.randrange(5), r.randrange(65536)]
        make_filter(words, 15, r)
        for osc in (23, 31):
            for offset in (4, 6): c.set_u32(words, osc + offset, r.choice(IDS))
            c.set_u32(words, osc, r.choice((0, 0xFFFFF, 0x100000, 0xFFFFFFFF)))
            c.set_u32(words, osc + 2, r.getrandbits(32))
        c.set_u32(words, shared.MIX, r.getrandbits(32) if index < 64 else (0, 1, 2047, 4094, 4095, 4096, 65535, 0xFFFFFFFF)[index % 8])
        voice = shared.CompactVoice(words)
        waves = {a: struct.pack('<256h', *[r.randint(-32768, 32767) for _ in range(256)]) for a in IDS}
    else:
        words = [0] * w2.WORDS
        words[0], words[1] = r.choice((0, 1, 127, 255)), int(index % 13 == 0)
        make_env(words, w2.ENV, r, 0)
        for field in (w2.PHASE, w2.INCREMENT, w2.OFFSET, w2.REDUCTION):
            c.set_u32(words, field, r.choice((0, 1, 0xFFFFF, 0x100000, 0x100001, r.getrandbits(32))))
        for field in (w2.CURRENT, w2.NEXT): c.set_u32(words, field, r.choice(IDS[:2]))
        voice = w2.NoiseToneWave2(words)
        waves = {a: struct.pack('<2048h', *[r.randint(-32768, 32767) for _ in range(2048)]) for a in IDS[:2]}
    return voice, [r.getrandbits(32), r.getrandbits(32)], waves


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path)
    args = ap.parse_args()
    e1, e2, _, _ = make_envelopes()
    report = {'schema': 'perky-original-noise-tone-dsp-v1', 'paths': {}}
    for kind, builder, target in (('shared', recipe.shared_source, 'original_noise_tone'),
                                  ('wave2', recipe.wave2_source, 'noise_tone_wave2')):
        source, scratch = builder()
        binary, entry = assemble(lambda: source, target, OUT / kind)
        cases = []
        for index in range(128 if kind == 'shared' else 64):
            voice, rng, waves = synthetic(kind, index)
            _, worst = run(binary, entry, voice, rng, waves, (e1, e2), 4, f'{kind} synthetic {index}', scratch, kind)
            cases.append({'case': f'synthetic {index}', 'blocks': 4, 'worst_cycles': worst})
        if args.firmware:
            manifest = json.loads((FIX / 'manifest.json').read_text())
            equal(hashlib.sha256(args.firmware.read_bytes()).hexdigest(), manifest['firmware_sha256'], 'firmware hash')
            segment = find_m7(parse_container(args.firmware.read_bytes())[1])
            e1, e2 = segment.read(0x08022EA0, 4096), segment.read(0x080236A2, 4096)
            targets = [(11, 1, 0x2B8C)] if kind == 'wave2' else [(11, 2, 0x2984), (11, 3, 0x2984), (7, 3, 0x3B68)]
            for engine, mode, offset in targets:
                for corner in range(3):
                    case = FIX / f'engine-{engine}-mode-{mode}-corner-{corner}'
                    for path in case.glob('*.bin'):
                        equal(hashlib.sha256(path.read_bytes()).hexdigest(), manifest['files'][str(path.relative_to(FIX))], 'fixture hash')
                    state = lambda name: (case / name).read_bytes()[offset:offset + 0x120]
                    cls = shared.CompactVoice if kind == 'shared' else w2.NoiseToneWave2
                    voice = cls.from_arm(state('wrapper-window-after.bin'))
                    rng = list(struct.unpack('<II', (case / 'rng-continuation-before.bin').read_bytes()))
                    if kind == 'shared':
                        waves = {a: segment.read(a, 512) for a in IDS}
                    else:
                        waves = {c.get_u32(voice.words, f): segment.read(c.get_u32(voice.words, f), 4096)
                                 for f in (w2.CURRENT, w2.NEXT)}
                    got, worst = run(binary, entry, voice, rng, waves, (e1, e2), 16, case.name, scratch, kind)
                    equal(got, list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes())), case.name + ' ARM PCM')
                    after = state('wrapper-window-continuation-after.bin')
                    equal(voice.words, cls.from_arm(after).words, case.name + ' ARM state')
                    equal(cls.from_arm(voice.apply_to_arm(after)).words, voice.words, case.name + ' roundtrip')
                    equal(struct.pack('<II', *rng), (case / 'rng-continuation-after.bin').read_bytes(), case.name + ' ARM RNG')
                    cases.append({'case': case.name, 'blocks': 16, 'worst_cycles': worst})
        result = {'p_words': binary.stat().st_size // 3, 'scratch_words': scratch,
                  'worst_cycles': max(v['worst_cycles'] for v in cases), 'cases': cases}
        report['paths'][kind] = result
        print(f"Original Noise/Tone {kind} DSP: PASS ({sum(v['blocks'] for v in cases)} consecutive blocks; exact stereo PCM/state/RNG; {result['p_words']} P words; worst {result['worst_cycles']} modeled cycles/16)", flush=True)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
