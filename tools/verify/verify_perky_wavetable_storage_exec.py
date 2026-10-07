#!/usr/bin/env python3
"""Execute full Wavetable with mapped-address packed asset candidates.

Direct constant-time reads and two-cache decoding are compared to ARM/native.
Cache tags and miss timing are checked for the second-difference backend.
This is not an installed image: stock clearing, effect retirement, shared
loading and physical external-memory timing still need production qualification.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]
import wavetable_drum_compact as compact
import simple_drum_tables as packed
from build_wavetable_cached_source import source as cached_source, CACHE_A, CACHE_B
from build_wavetable_direct_source import source as direct_source
from build_wavetable_physical_bank import build
from build_wavetable_asset_bank import IDS
from verify_perky_wavetable_voice_exec import NATIVE
from verify_perky_simple_drum_envelope_exec import build_host, ASM, HOST
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals
from perky_noise_hat_dsp_support import audit_source, audit_binary

OUT = ROOT / 'out/perky/wavetable-cached'
FIX = ROOT / 'out/perky/engine-fixtures'
ASSETS = ROOT / 'out/perky/all-voice-assets'
SMALL = ROOT / 'out/perky/simple-drum-assets'
ORG = 0x2800


def equal(got, want, label):
    if got != want:
        raise AssertionError((label, [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:6]))


def assemble(encoding):
    build_host()
    OUT.mkdir(parents=True, exist_ok=True)
    wrapper = f'''pk_wavetable_cached_probe:
        move #>$200,r6
        move #>$3900,r5
        jsr pk_simple_base
        jsr pk_wavetable_voice
        move x:>${CACHE_A:x},a
        move a1,x:(r6+$3e)
        move x:>${CACHE_B:x},a
        move a1,x:(r6+$3f)
        rts
'''
    sample_wrapper = f'''pk_wavetable_sample_probe:
        move #>$200,r6
        move #>$3900,r5
        move #>${CACHE_A:x},r4
        do n7,pkwsp_done
        move x:(r6),x0
        move x:(r6+$1),y0
        move x:(r6+$2),y1
        jsr pkwt_fetch_wave
        move a1,x:(r0)+
        move a1,x:(r0)+
        move x:(r6),a
        add #>$1,a
        move a1,x:(r6)
pkwsp_done:
        nop
        rts
'''
    text = wrapper + sample_wrapper + (direct_source() if encoding == 'direct' else cached_source())
    audit_source(text)
    asm, binary, symbols = (OUT / f'voice.{ext}' for ext in ('asm', 'bin', 'sym'))
    asm.write_text(force_long_local_jsr(relativize_local_conditionals(text)))
    result = subprocess.run([str(ASM), '-in', str(asm), '-org', f'{ORG:x}', '-out', str(binary),
                             '-sym', str(symbols), '-list'], check=True, capture_output=True, text=True)
    audit_binary(result.stdout, binary, ORG)
    labels = {p[0]: int(p[1], 16) for p in map(str.split, symbols.read_text().splitlines()) if len(p) == 2}
    return binary, labels['pk_wavetable_cached_probe'], labels['pk_wavetable_sample_probe']


def main():
    global OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=Path(os.environ.get('PERKYBITS_SOURCE', '/Users/jrold/Downloads/perkybits')))
    ap.add_argument('--codec', choices=('direct', 'second-difference32'), default='direct')
    args = ap.parse_args()
    OUT = ROOT / ('out/perky/wavetable-physical-' + args.codec)
    manifest = json.loads((FIX / 'manifest.json').read_text())
    asset_manifest = json.loads((ASSETS / 'manifest.json').read_text())
    assert manifest['firmware_sha256'] == asset_manifest['firmware_sha256']
    for entry in asset_manifest['assets']:
        address = int(entry['address'], 16)
        if address in IDS:
            assert hashlib.sha256((ASSETS / f'asset_{address:08x}.bin').read_bytes()).hexdigest() == entry['raw_sha256']
    native_source = args.source / 'Source'
    assert hashlib.sha256((native_source / 'NativeV121Wavetable.cpp').read_bytes()).hexdigest() == manifest['source_sha256']['Source/NativeV121Wavetable.cpp']
    binary, entry, sample_entry = assemble(args.codec)
    bank, data = build(ASSETS, OUT / 'bank', args.codec)
    headers = {v['identity']: v['header'] for v in bank['assets']}
    wave_data = {i: (ASSETS / f'asset_{i:08x}.bin').read_bytes() for i in IDS}
    pitch, e1, e2 = ((SMALL / f'{name}.bin').read_bytes() for name in ('pitch', 'envelope1', 'envelope2'))
    env = packed.pack_u16(struct.unpack('<1024H', e1[:2048]))
    pitch_words = packed.pack_pitch_basis(struct.unpack('<4096H', pitch)).words
    data += 'Y c50 ' + ' '.join(f'{v:06x}' for v in env) + '\nY efb ' + ' '.join(f'{v:06x}' for v in pitch_words) + ' 000000\nX 3964 ffffff\n'

    def execute(raw, blocks, label):
        voice = compact.WavetableDrum.from_arm(raw)
        state, script, pcm, dump, meter = (OUT / f'case.{ext}' for ext in ('data', 'script', 'raw', 'state', 'meter'))
        state.write_text('X 200 ' + ' '.join(f'{v:06x}' for v in voice.words + [0] * 23)
                         + f'\nX {CACHE_A:x} ffffff\nX {CACHE_B:x} ffffff\n' + data)
        script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * blocks)
        subprocess.run([str(HOST), '-code', str(binary), '-org', f'{ORG:x}', '-entry', f'{entry:x}',
                        '-data', str(state), '-script', str(script), '-out', str(pcm), '-state', str(dump),
                        '-state-words', '64', '-meter', str(meter), '-cycle-meter', '1'],
                       check=True, capture_output=True, timeout=60)
        stereo = list(struct.unpack(f'<{32 * blocks}i', pcm.read_bytes()))
        equal(stereo[1::2], stereo[::2], label + ' stereo')
        costs = list(map(int, meter.read_text().split()))
        for block, line in enumerate(dump.read_text().splitlines()):
            want = voice.render(16, wave_data, pitch, e1, e2)
            equal(stereo[block * 32:(block + 1) * 32:2], want, f'{label}/{block} PCM')
            words = [int(v, 16) for v in line.split()]
            equal([v & 65535 for v in words[:41]], voice.words, f'{label}/{block} state')
            pointer = lambda off: voice.words[off] | voice.words[off + 1] << 16
            index = (pointer(2) >> 9) & 2047
            following = (index + 1) & 2047
            pending = index == 2047 and pointer(6) != pointer(8)
            a, b = (pointer(8), pointer(36)) if pending else (pointer(6), pointer(34))
            tags = [((headers[i] << 6) + following // 32) & 0xFFFFFF for i in (a, b)]
            if args.codec == 'second-difference32':
                equal(words[62:64], tags, f'{label}/{block} cache tags')
        return stereo[::2], voice.words, max(costs)

    # Every original sample runs through the same pointer directory and DSP
    # reader used by the complete renderer, including shared-window addresses.
    sample_costs = []
    for identity in IDS:
        state, script, pcm, meter = (OUT / f'samples.{ext}' for ext in ('data', 'script', 'raw', 'meter'))
        state.write_text(f'X 200 000000 {identity & 65535:06x} {identity >> 16:06x}\n'
                         + f'X {CACHE_A:x} ffffff\n' + data)
        script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * 128)
        subprocess.run([str(HOST), '-code', str(binary), '-org', f'{ORG:x}', '-entry', f'{sample_entry:x}',
                        '-data', str(state), '-script', str(script), '-out', str(pcm),
                        '-meter', str(meter), '-cycle-meter', '1'], check=True, capture_output=True, timeout=60)
        stereo = list(struct.unpack('<4096i', pcm.read_bytes()))
        equal(stereo[1::2], stereo[::2], f'{identity:x} all-sample stereo')
        equal(stereo[::2], list(struct.unpack('<2048h', wave_data[identity])), f'{identity:x} all samples')
        sample_costs.extend(map(int, meter.read_text().split()))
    report_cases = []
    for engine, offset in ((2, 0x2E8), (5, 0x31C)):
        for mode in range(1, 4):
            for corner in range(3):
                case = FIX / f'engine-{engine}-mode-{mode}-corner-{corner}'
                for before, after, audio in (
                    ('wrapper-window-before.bin', 'wrapper-window-after.bin', 'arm-pcm.bin'),
                    ('wrapper-window-after.bin', 'wrapper-window-continuation-after.bin', 'arm-pcm-continuation.bin'),
                ):
                    for name in (before, after, audio):
                        assert hashlib.sha256((case / name).read_bytes()).hexdigest() == manifest['files'][str((case / name).relative_to(FIX))]
                    raw = (case / before).read_bytes()[offset:offset + 0x150]
                    got, words, worst = execute(raw, 16, case.name + '/' + before)
                    equal(got, list(struct.unpack('<256h', (case / audio).read_bytes())), case.name + ' ARM PCM')
                    equal(words, compact.WavetableDrum.from_arm((case / after).read_bytes()[offset:offset + 0x150]).words, case.name + ' ARM state')
                    report_cases.append({'case': case.name + '/' + before, 'blocks': 16, 'worst_cycles': worst})

    template = (FIX / 'engine-2-mode-1-corner-1/wrapper-window-before.bin').read_bytes()[0x2E8:0x2E8 + 0x150]
    cases = []
    for i in range(240):
        rng = random.Random(0x574354 + i)
        v = compact.WavetableDrum.from_arm(template)
        v.words[0] = rng.choice((0, 1, 127, 255))
        v.words[1] = int(i % 19 == 0)
        phase = rng.choice((0, 0xFFFFF, 0x100000, 0xFFFFFFF0, rng.getrandbits(32)))
        v.words[2:4] = [phase & 65535, phase >> 16]
        for off in (6, 8, 34, 36):
            address = rng.choice(IDS)
            v.words[off:off + 2] = [address & 65535, address >> 16]
        v.words[38] = rng.choice((0, 255, 65535, rng.randrange(65536)))
        v.words[39] = rng.choice((0, 255, 65535, rng.randrange(65536)))
        v.words[40] = i % 3
        v.words[32:34] = [rng.randrange(4096), rng.randrange(4096)]
        for off in (10, 21):
            v.words[off] = rng.randrange(5)
            value = rng.choice((0, 0xFFFFF, rng.randrange(0x100000)))
            v.words[off + 5:off + 7] = [value & 65535, value >> 16]
            v.words[off + 10] = rng.choice((1, 6, 43, 428, 65535))
        cases.append(v.apply_to_arm(template))
    runner = OUT / 'native.cpp'
    runner.write_text(NATIVE.replace('IDS', ','.join(hex(i) for i in IDS)))
    exe = OUT / 'native'
    subprocess.run(['c++', '-std=c++20', '-O2', '-I' + str(native_source), str(runner),
                    str(native_source / 'NativeV121Wavetable.cpp'), '-o', str(exe)], check=True, capture_output=True)
    (OUT / 'native-input.bin').write_bytes(b''.join(cases))
    subprocess.run([str(exe), str(SMALL), str(ASSETS), str(OUT / 'native-input.bin'), str(OUT / 'native-output.bin')], check=True)
    results = (OUT / 'native-output.bin').read_bytes()
    for i, raw in enumerate(cases):
        got, words, worst = execute(raw, 1, f'native {i}')
        at = i * (32 + 0x150)
        equal(got, list(struct.unpack('<16h', results[at:at + 32])), f'native {i} PCM')
        equal(words, compact.WavetableDrum.from_arm(results[at + 32:at + 32 + 0x150]).words, f'native {i} state')
        report_cases.append({'case': f'native {i}', 'blocks': 1, 'worst_cycles': worst})
    report = {'schema': 'perky-wavetable-cached-dsp-v1', 'p_words': binary.stat().st_size // 3,
              'encoding': args.codec, 'cache_words': 0 if args.codec == 'direct' else 66, 'bank': bank, 'worst_cycles': max(v['worst_cycles'] for v in report_cases),
              'worst_original_cycles': max(v['worst_cycles'] for v in report_cases if v['case'].startswith('engine-')),
              'cases': report_cases, 'decoded_samples': len(IDS) * 2048,
              'sample_read_max_cycles': max(sample_costs), 'shipping_qualified': False}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"Wavetable {args.codec} DSP: PASS ({sum(v['blocks'] for v in report_cases)} blocks plus {report['decoded_samples']} samples; exact stereo PCM/state; {report['p_words']} P; {report['cache_words']} cache; original max {report['worst_original_cycles']}, all-case max {report['worst_cycles']} modeled cycles/16; physical installation pending)")


if __name__ == '__main__':
    main()
