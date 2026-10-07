#!/usr/bin/env python3
"""Acoustic Hats compact gate against all nine original ARM continuations.

Checks every renderer-owned word, including exact IEEE754 filter history, the
firmware-global held sample, and round-tripping the compact state to ARM form.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]
import acoustic_hats_compact as hats
from extract_noise_tone_tables import parse_container, find_m7

FIX = ROOT / 'out/perky/engine-fixtures'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('firmware', type=Path)
    args = ap.parse_args()
    raw_image = args.firmware.read_bytes()
    manifest = json.loads((FIX / 'manifest.json').read_text())
    assert hashlib.sha256(raw_image).hexdigest() == manifest['firmware_sha256']
    segment = find_m7(parse_container(raw_image)[1])
    e1, e2 = segment.read(0x08022EA0, 4096), segment.read(0x080236A2, 4096)
    for mode in range(1, 4):
        for corner in range(3):
            case = FIX / f'engine-12-mode-{mode}-corner-{corner}'
            for path in case.glob('*.bin'):
                assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['files'][str(path.relative_to(FIX))]
            state = lambda name: (case / name).read_bytes()[0x2A80:0x2A80 + 0x10C]
            voice = hats.AcousticHats.from_arm(state('wrapper-window-after.bin'))
            address = hats.c.get_u32(voice.words, hats.SAMPLE_ADDRESS)
            length = hats.c.get_u32(voice.words, hats.SAMPLE_LENGTH)
            sample = segment.read(address, 2 * length)
            hold = list(struct.unpack('<i', (case / 'acoustic-hold-continuation-before.bin').read_bytes()))
            got = voice.render(256, sample, e1, e2, hold)
            want = list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes()))
            assert got == want, (mode, corner, 'PCM')
            after = state('wrapper-window-continuation-after.bin')
            assert voice.words == hats.AcousticHats.from_arm(after).words, (mode, corner, 'state')
            assert struct.pack('<i', hold[0]) == (case / 'acoustic-hold-continuation-after.bin').read_bytes(), (mode, corner, 'hold')
            assert hats.AcousticHats.from_arm(voice.apply_to_arm(after)).words == voice.words
    print('Acoustic Hats compact: PASS (9 original ARM continuation blocks; exact PCM/35-word state/IEEE754 history/global hold)')


if __name__ == '__main__':
    main()
