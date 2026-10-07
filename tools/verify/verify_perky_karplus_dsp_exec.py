#!/usr/bin/env python3
"""Execute exact Karplus DSP PCM/state/2K ring/RNG across consecutive blocks.

Synthetic gate requires no proprietary assets. --firmware adds all nine
original ARM continuation cases. Memory placement and controls are separate.
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]
import karplus_compact as karplus
import resonator_compact as c
from build_karplus_source import source
from verify_perky_slap_dsp_exec import assemble, run, equal, FIX
from verify_perky_noise_hat_classic_synthetic_exec import make_envelopes, make_env, make_filter
from extract_noise_tone_tables import parse_container, find_m7

OUT = ROOT / 'out/perky/karplus-dsp'


def synthetic(index):
    r = random.Random(0x4B415250 + index)
    w = [0] * karplus.WORDS
    w[karplus.VELOCITY] = r.choice((0, 1, 127, 255))
    w[karplus.MUTE] = int(index % 13 == 0)
    w[karplus.MODE] = index % 3
    make_env(w, karplus.AMP_ENV, r, index % 3)
    w[karplus.NOISE:karplus.NOISE + 3] = [r.randrange(4), r.randrange(4), r.randrange(65536)]
    make_filter(w, karplus.FILTER, r)
    w[karplus.EXCITE_TARGET] = r.choice((0, 1, 2, 65535))
    w[karplus.EXCITE_COUNT] = r.choice((0, 1, 2, 65535))
    c.set_u32(w, karplus.DELAY, r.choice((0, 1, 2047, 2048, 65535, 0xFFFFFFFF)))
    w[karplus.WRITE_INDEX] = r.choice((0, 2047, 2048, 65535))
    c.set_u32(w, karplus.AGE, r.choice((0, 0x8F, 0x90, 0xEF, 0xF0, 0x110, 0x111, 0x210, 0x211, 0xFFFFFFFF)))
    return karplus.Karplus(w, [r.randrange(65536) for _ in range(karplus.RING_LEN)]), [r.getrandbits(32), r.getrandbits(32)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path)
    args = ap.parse_args()
    binary, entry = assemble(source, 'karplus', OUT)
    e1, e2, _, _ = make_envelopes()
    cases = []
    for index in range(96):
        voice, rng = synthetic(index)
        _, worst = run(binary, entry, voice, rng, (e1, e2), 4, f'synthetic {index}', OUT)
        cases.append({'case': f'synthetic {index}', 'blocks': 4, 'worst_cycles': worst})
    if args.firmware:
        manifest = json.loads((FIX / 'manifest.json').read_text())
        equal(hashlib.sha256(args.firmware.read_bytes()).hexdigest(), manifest['firmware_sha256'], 'firmware hash')
        segment = find_m7(parse_container(args.firmware.read_bytes())[1])
        e1, e2 = segment.read(0x08022EA0, 4096), segment.read(0x080236A2, 4096)
        for mode in range(1, 4):
            for corner in range(3):
                case = FIX / f'engine-9-mode-{mode}-corner-{corner}'
                for path in case.glob('*.bin'):
                    equal(hashlib.sha256(path.read_bytes()).hexdigest(), manifest['files'][str(path.relative_to(FIX))], 'fixture hash')
                state = lambda name: (case / name).read_bytes()[0x2908:0x2908 + 0x10e0]
                voice = karplus.Karplus.from_arm(state('wrapper-window-after.bin'))
                rng = list(struct.unpack('<II', (case / 'rng-continuation-before.bin').read_bytes()))
                got, worst = run(binary, entry, voice, rng, (e1, e2), 16, case.name, OUT)
                equal(got, list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes())), case.name + ' ARM PCM')
                final = karplus.Karplus.from_arm(state('wrapper-window-continuation-after.bin'))
                equal(voice.words, final.words, case.name + ' ARM X')
                equal(voice.ring, final.ring, case.name + ' ARM ring')
                equal(struct.pack('<II', *rng), (case / 'rng-continuation-after.bin').read_bytes(), case.name + ' ARM RNG')
                cases.append({'case': case.name, 'blocks': 16, 'worst_cycles': worst})
    report = {'schema': 'perky-karplus-dsp-v1', 'p_words': binary.stat().st_size // 3,
              'x_words': karplus.WORDS, 'scratch_words': 128, 'y_ring_words': karplus.RING_LEN,
              'worst_cycles': max(v['worst_cycles'] for v in cases), 'cases': cases}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"Karplus DSP: PASS ({sum(v['blocks'] for v in cases)} consecutive blocks; exact stereo PCM/state/full ring/RNG; {report['p_words']} P words; worst {report['worst_cycles']} modeled cycles/16)")


if __name__ == '__main__':
    main()
