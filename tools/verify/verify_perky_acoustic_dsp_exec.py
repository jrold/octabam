#!/usr/bin/env python3
"""Acoustic Hats exact DSP renderer gate, with a logical sample bank only.

Default synthetic inputs cover playback end/hold/interpolation/mute/retrigger
history. --firmware adds all original ARM continuations. The large Y bank is
not physically mapped; no shipping asset-placement or timing claim is made.
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
import acoustic_dsp as recipe
import acoustic_hats_compact as h
import resonator_compact as c
import simple_drum_tables as tables
from verify_perky_slap_dsp_exec import assemble, equal, FIX, SB, ENV1, ENV2, ORG, HOST
from verify_perky_noise_hat_classic_synthetic_exec import make_envelopes, make_env
from extract_noise_tone_tables import parse_container, find_m7

OUT = ROOT / 'out/perky/acoustic-dsp'
SAMPLE_BASE = 0x10000


def run(binary, entry, voice, hold, sample, envelopes, blocks, tag, scratch):
    e1, e2 = envelopes
    dump_words = SB + scratch
    words = [0] * dump_words
    words[:h.WORDS] = voice.words
    c.set_u32(words, SB + 0x72, hold[0])
    words[SB + 0x74] = SAMPLE_BASE
    records = [('X', 0x200, words), ('Y', ENV1, tables.pack_u16(struct.unpack('<1025H', e1[:2050]))),
               ('Y', ENV2, tables.pack_u16(struct.unpack('<1025H', e2[:2050]))),
               ('Y', SAMPLE_BASE, struct.unpack(f'<{len(sample) // 2}H', sample))]
    data = OUT / 'case.data'
    data.write_text(''.join(f'{space} {address:x} ' + ' '.join(f'{v:06x}' for v in values) + '\n'
                            for space, address, values in records))
    script = OUT / 'case.script'
    script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * blocks)
    pcm, dump, meter = (OUT / f'case.{ext}' for ext in ('raw', 'state', 'meter'))
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
        want = voice.render(16, sample, e1, e2, hold)
        equal(got[block * 16:(block + 1) * 16], want, f'{tag} block {block} PCM')
        words = [int(v, 16) & 65535 for v in line.split()]
        equal(words[:h.WORDS], voice.words, f'{tag} block {block} X/IEEE754 history')
        held = c.s32(c.get_u32(words, SB + 0x72))
        equal(held, hold[0], f'{tag} block {block} global hold')
    return got, max(map(int, meter.read_text().split()))


def synthetic(index):
    r = random.Random(0x41434F55 + index)
    w = [0] * h.WORDS
    w[h.VELOCITY] = r.choice((0, 1, 127, 255))
    w[h.MUTE] = int(index % 11 == 0)
    make_env(w, h.AMP_ENV, r, index % 3)
    length = r.choice((1, 17, 65, 4096))
    c.set_u32(w, h.INDEX, r.choice((0, length - 1, length, r.randrange(length))))
    shift = r.choice((1, 4, 8, 12, 15))
    w[h.SHIFT] = shift
    c.set_u32(w, h.MASK, (1 << shift) - 1)
    c.set_u32(w, h.FRACTION, r.randrange(1 << shift))
    c.set_u32(w, h.INCREMENT, r.choice((0, 1, (1 << shift) - 1, 1 << shift, 2 << shift)))
    c.set_u32(w, h.HOLD_RELOAD, r.randrange(5))
    c.set_u32(w, h.HOLD, r.randrange(5))
    c.set_u32(w, h.SAMPLE_ADDRESS, 0x08012345)
    c.set_u32(w, h.SAMPLE_LENGTH, length)
    c.set_u32(w, h.FILTER_INT, r.randint(-32768, 32767))
    previous = r.choice((0, 0x80000000, 1, 0x80000001,
                         struct.unpack('<I', struct.pack('<f', r.uniform(-32768, 32767)))[0]))
    c.set_u32(w, h.FILTER_FLOAT, previous)
    w[h.FILTER_DIRTY] = index & 1
    sample = struct.pack(f'<{length}h', *[r.randint(-32768, 32767) for _ in range(length)])
    return h.AcousticHats(w), [r.randint(-16384, 16384)], sample


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path)
    args = ap.parse_args()
    source, scratch = recipe.source()
    binary, entry = assemble(lambda: source, 'acoustic', OUT)
    e1, e2, _, _ = make_envelopes()
    cases = []
    for index in range(64):
        voice, hold, sample = synthetic(index)
        _, worst = run(binary, entry, voice, hold, sample, (e1, e2), 4, f'synthetic {index}', scratch)
        cases.append({'case': f'synthetic {index}', 'blocks': 4, 'worst_cycles': worst})
    if args.firmware:
        manifest = json.loads((FIX / 'manifest.json').read_text())
        equal(hashlib.sha256(args.firmware.read_bytes()).hexdigest(), manifest['firmware_sha256'], 'firmware hash')
        segment = find_m7(parse_container(args.firmware.read_bytes())[1])
        e1, e2 = segment.read(0x08022EA0, 4096), segment.read(0x080236A2, 4096)
        for mode in range(1, 4):
            for corner in range(3):
                case = FIX / f'engine-12-mode-{mode}-corner-{corner}'
                for path in case.glob('*.bin'):
                    equal(hashlib.sha256(path.read_bytes()).hexdigest(), manifest['files'][str(path.relative_to(FIX))], 'fixture hash')
                state = lambda name: (case / name).read_bytes()[0x2A80:0x2A80 + 0x10C]
                voice = h.AcousticHats.from_arm(state('wrapper-window-after.bin'))
                address = c.get_u32(voice.words, h.SAMPLE_ADDRESS)
                length = c.get_u32(voice.words, h.SAMPLE_LENGTH)
                sample = segment.read(address, 2 * length)
                hold = list(struct.unpack('<i', (case / 'acoustic-hold-continuation-before.bin').read_bytes()))
                got, worst = run(binary, entry, voice, hold, sample, (e1, e2), 16, case.name, scratch)
                equal(got, list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes())), case.name + ' ARM PCM')
                equal(voice.words, h.AcousticHats.from_arm(state('wrapper-window-continuation-after.bin')).words, case.name + ' ARM state')
                equal(struct.pack('<i', hold[0]), (case / 'acoustic-hold-continuation-after.bin').read_bytes(), case.name + ' ARM hold')
                if corner == 1:
                    assert any(got), (case.name, 'active original fixture rendered silence')
                cases.append({'case': case.name, 'blocks': 16, 'asset_samples': length,
                              'asset_sha256': hashlib.sha256(sample).hexdigest(), 'worst_cycles': worst})
    report = {'schema': 'perky-acoustic-dsp-v1', 'p_words': binary.stat().st_size // 3,
              'x_words': h.WORDS, 'scratch_words': scratch, 'logical_sample_base': SAMPLE_BASE,
              'physical_assets_qualified': False, 'worst_cycles': max(v['worst_cycles'] for v in cases), 'cases': cases}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"Acoustic Hats DSP: PASS ({sum(v['blocks'] for v in cases)} consecutive blocks; exact stereo PCM/35-word state/IEEE754 history/hold; {report['p_words']} P words; {scratch} scratch; worst {report['worst_cycles']} modeled cycles/16; logical sample bank only)")


if __name__ == '__main__':
    main()
