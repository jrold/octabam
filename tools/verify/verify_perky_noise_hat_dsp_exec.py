#!/usr/bin/env python3
"""Execute all Noise Hat modes against local original ARM captures.

No reference bytes are checked into Git. Generate fixtures with
tools/perky/capture_engine_fixtures.py first, then pass the same firmware here.
Each 256-sample continuation runs as sixteen consecutive DSP blocks. Check
PCM, state and sidebands at every block against the compact oracle, then check
the final continuation directly against the original ARM capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]
import noise_hat_compact as hats  # noqa:E402
import noise_hat_pulse_compact as pulse  # noqa:E402
import simple_drum_tables as tables  # noqa:E402
import verify_noise_hat_compact as fixtures  # noqa:E402
import verify_perky_noise_hat_classic_synthetic_exec as classic_dsp  # noqa:E402
import verify_perky_noise_hat_pulse_synthetic_exec as pulse_dsp  # noqa:E402
from verify_perky_simple_drum_envelope_exec import build_host  # noqa:E402

OUT = ROOT / 'out/perky/noise-hat-arm-dsp'
BLOCKS = 16
FRAMES = 16


def require_equal(got, want, subject: str) -> None:
    if got != want:
        differences = [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b]
        raise SystemExit(f'Noise Hat ARM/DSP {subject}: mismatch {differences[:8]} '
                         f'(lengths {len(got)}/{len(want)})')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path)
    args = parser.parse_args()
    manifest = json.loads((fixtures.FIX / 'manifest.json').read_text())
    require_equal(hashlib.sha256(args.firmware.read_bytes()).hexdigest(),
                  manifest['firmware_sha256'], 'fixture firmware hash')
    build_host()
    OUT.mkdir(parents=True, exist_ok=True)
    envelope1, envelope2 = fixtures.tables(args.firmware)
    # The renderer clamps index to <=1023, plus its interpolation neighbour.
    env1_words = tables.pack_u16(struct.unpack('<1025H', envelope1[:2050]))
    env2_words = tables.pack_u16(struct.unpack('<1025H', envelope2[:2050]))
    script = OUT / 'blocks.script'
    script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * BLOCKS)
    binaries = {mode: classic_dsp.assemble(mode) for mode in (0, 1)}
    binaries[2] = pulse_dsp.assemble()
    worst = {mode: 0 for mode in range(3)}
    cases = []

    for panel_mode, mode in fixtures.PANEL_TO_FIRMWARE.items():
        for corner in range(3):
            tag = f'M{panel_mode}-corner-{corner}'
            case = fixtures.FIX / f'engine-10-mode-{panel_mode}-corner-{corner}'
            for path in case.glob('*.bin'):
                require_equal(hashlib.sha256(path.read_bytes()).hexdigest(),
                              manifest['files'][str(path.relative_to(fixtures.FIX))],
                              tag + ' fixture hash ' + path.name)
            rng_bytes = (case / 'rng-continuation-before.bin').read_bytes()
            rng = list(struct.unpack('<II', rng_bytes))
            rng_after = list(struct.unpack('<II', (case / 'rng-continuation-after.bin').read_bytes()))
            if mode == 2:
                voice = pulse.NoiseHatPulseStack.from_arm(
                    fixtures.pulse_state(case, 'wrapper-window-after.bin'))
                arm_final = pulse.NoiseHatPulseStack.from_arm(
                    fixtures.pulse_state(case, 'wrapper-window-continuation-after.bin'))
                state_words = pulse.PULSE_STACK_WORDS
                xwords = list(voice.words)
                ylines = ''
                dsp = pulse_dsp
            else:
                voice = hats.NoiseHatClassic.from_arm(
                    fixtures.classic_state(case, 'wrapper-window-after.bin'),
                    fixtures.hold_state(case, 'before'))
                arm_final = hats.NoiseHatClassic.from_arm(
                    fixtures.classic_state(case, 'wrapper-window-continuation-after.bin'),
                    fixtures.hold_state(case, 'after'))
                state_words = hats.RING_LEN
                xwords = [0] * state_words
                xwords[:hats.CLASSIC_WORDS] = voice.words
                sb = classic_dsp.SCRATCH_DUMP_OFF
                xwords[sb + 0x70:sb + 0x72] = voice.hold
                xwords[sb + 0x72:sb + 0x76] = [*classic_dsp.split_u32(rng[0]),
                                              *classic_dsp.split_u32(rng[1])]
                ylines = f'Y {classic_dsp.RING:x} ' + ' '.join(f'{v:06x}' for v in voice.ring) + '\n'
                dsp = classic_dsp
            initial_words = list(voice.words)
            data = OUT / f'{tag}.data'
            data.write_text(
                'X 200 ' + ' '.join(f'{v:06x}' for v in xwords) + '\n' + ylines
                + f'Y {dsp.ENV1_BASE:x} ' + ' '.join(f'{v:06x}' for v in env1_words) + '\n'
                + f'Y {dsp.ENV2_BASE:x} ' + ' '.join(f'{v:06x}' for v in env2_words) + '\n')
            binary, entry = binaries[mode]
            pcm, dump, meter = (OUT / f'{tag}.{ext}' for ext in ('raw', 'state', 'meter'))
            result = subprocess.run(
                [str(dsp.HOST), '-code', str(binary), '-org', f'{dsp.ORG:x}',
                 '-entry', f'{entry:x}', '-data', str(data), '-script', str(script),
                 '-out', str(pcm), '-state', str(dump), '-state-words', str(state_words),
                 '-meter', str(meter), '-cycle-meter', '1'],
                capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise SystemExit(f'{tag} DSP execution failed:\n{result.stdout[-2000:]}{result.stderr[-2000:]}')
            stereo = struct.unpack(f'<{BLOCKS * FRAMES * 2}i', pcm.read_bytes())
            got_pcm = list(stereo[::2])
            require_equal(list(stereo[1::2]), got_pcm, tag + ' stereo duplication')
            want_pcm = []
            states = dump.read_text().splitlines()
            assert len(states) == BLOCKS
            for block, line in enumerate(states):
                if mode == 2:
                    want_pcm.extend(voice.render(FRAMES, envelope1, envelope2))
                else:
                    want_pcm.extend(voice.render(FRAMES, mode, envelope1, envelope2, rng))
                words = [int(v, 16) for v in line.split()]
                require_equal([v & 0xffff for v in words[:len(voice.words)]],
                              voice.words, f'{tag} block {block} X state')
                if mode != 2:
                    require_equal([v & 0xffff for v in words[state_words:2 * state_words]],
                                  voice.ring, f'{tag} block {block} Y ring')
                    require_equal([v & 0xffff for v in words[sb + 0x70:sb + 0x72]],
                                  voice.hold, f'{tag} block {block} hold')
                    sideband = [v & 0xffff for v in words[sb + 0x72:sb + 0x76]]
                    require_equal([sideband[0] | sideband[1] << 16,
                                   sideband[2] | sideband[3] << 16],
                                  rng, f'{tag} block {block} global RNG')
            require_equal(got_pcm, want_pcm, tag + ' compact PCM')
            require_equal(got_pcm, list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes())),
                          tag + ' original ARM PCM')
            require_equal(voice.words, arm_final.words, tag + ' original ARM state')
            require_equal(rng, rng_after, tag + ' original ARM RNG')
            if mode != 2:
                require_equal(voice.ring, arm_final.ring, tag + ' original ARM ring')
                require_equal(voice.hold, arm_final.hold, tag + ' original ARM hold')
            if corner == 1:
                assert any(got_pcm), f'{tag}: all-zero fixture cannot prove active synthesis'
                assert voice.words != initial_words, f'{tag}: renderer state never advanced'
            cycles = list(map(int, meter.read_text().split()))
            assert len(cycles) == BLOCKS
            worst[mode] = max(worst[mode], max(cycles))
            cases.append(dict(panel_mode=panel_mode, firmware_mode=mode, corner=corner,
                              blocks=BLOCKS, max_modeled_cycles=max(cycles),
                              program_words=binary.stat().st_size // 3))
    report = dict(firmware_sha256=manifest['firmware_sha256'], pcm_samples=9 * BLOCKS * FRAMES,
                  cases=cases, worst_modeled_cycles=worst,
                  production_integrated=False, hardware_qualified=False)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Noise Hat original ARM/DSP: PASS ({report["pcm_samples"]} exact PCM samples; '
          f'144 continuation blocks, all X/Y/hold/RNG exact; worst modeled cycles {worst})')


if __name__ == '__main__':
    main()
