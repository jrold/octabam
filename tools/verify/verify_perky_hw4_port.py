#!/usr/bin/env python3
"""Full-image emulator audition gate for fixed-engine PERKY HW4.

Requires OT_PROJECT and PERKY_HW4_IMAGE.  Runs all four admitted tracks in one
sequencer session and proves transport engine identity plus nontrivial stereo
post-chain audio.  This is an emulator/full-image gate, not a physical-hardware
or sonic-parity claim.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/hw'), str(ROOT / 'tools/harness')]

import blockdump as bd
import ot_project as otp
import recloop as rl
from ab_fixture import prepare

OUT = ROOT / 'out/perky/hw4-port'
FIXED = {0: 0, 1: 8, 4: 3, 5: 10}   # zero-based OT track -> engine id
FRAMES = 16000


def fail(message):
    raise AssertionError('PERKY HW4 port: ' + message)


def configure(project):
    fixture = prepare(project, OUT / 'project')
    for bank in fixture.glob('bank*.work'):
        def mutate(data):
            for part in range(8):
                base = otp.PART_BASE + part * otp.PART_STRIDE + 9
                for track, engine in FIXED.items():
                    data[base + 0x22 + track] = 1
                    data[base + 60 + 30 * track:base + 63 + 30 * track] = b'PK\x01'
                    params = [64, 64, 64, 64, 0, 0, 0, 0, 0, 0, 0, engine]
                    for slot, value in enumerate(params):
                        off = (0x2a if slot < 6 else 0x1da) + 30 * track + 6 + slot % 6
                        data[base + off] = value
                    data[base + track] = 0
                    data[base + 8 + track] = 0
            for track in FIXED:
                at = otp.trac_off(0, track)
                data[at:at + 8] = (1).to_bytes(8, 'big')
        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def records_for_track(classes, track):
    core = 1 if track < 4 else 0
    local = track & 3
    base = 0x80001C90 + (0 if core else 0x540)
    rows = []
    for address in (base, base + 0xA80):
        for _frame, words in classes.get(('>', 0, core, address), []):
            offset = 168 * local
            record = words[offset:offset + 24]
            if len(record) >= 20 and record[0] == 0x504B and record[2] == 0x5931:
                rows.append(record)
    return rows


def main():
    project = os.environ.get('OT_PROJECT')
    if not project:
        raise SystemExit('PERKY HW4 port requires OT_PROJECT=<saved stock project fixture>')
    image_src = Path(os.environ.get('PERKY_HW4_IMAGE', ROOT / 'out/mainos_perky_hw4.bin'))
    if not image_src.exists():
        fail(f'missing image {image_src}')

    OUT.mkdir(parents=True, exist_ok=True)
    fixture = configure(project)
    card = OUT / 'card.img'
    subprocess.run([
        sys.executable, str(ROOT / 'tools/emu/ot_emu/stage_card.py'),
        str(fixture), 'OCTABAM', 'RIG', '--tree', str(OUT / 'tree'), '--out', str(card),
    ], cwd=ROOT, check=True)
    image = OUT / 'image.bin'
    shutil.copy2(image_src, image)
    dump, log_path = OUT / 'blocks.bin', OUT / 'port.log'
    cmd = [
        os.environ.get('PERKY_EMU', str(ROOT / 'out/emu/ot_emu')),
        '--image', str(image), '--card', str(card), '--set', 'OCTABAM', '--project', 'RIG',
        '--load-ms', '90000', '--sequencer', '--internal-clock', '--bank', '0',
        '--frames', str(FRAMES), '--dsp', '--dsp-dirty', '123', '--main-level', '64',
        '--block-dump', str(dump),
    ]
    with log_path.open('w') as log:
        log.write(' '.join(cmd) + '\n'); log.flush()
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=600, stdout=log, stderr=subprocess.STDOUT)

    log = log_path.read_text()
    if 'ILLEGAL' in log: fail('emulator hit ILLEGAL')
    if not re.search(rf'frames run\s*:\s*{FRAMES}', log):
        fail(f'emulator did not complete {FRAMES} frames')
    classes = bd.classes(bd.read(dump))

    for track, engine in FIXED.items():
        records = records_for_track(classes, track)
        if not records: fail(f'T{track+1}: no PK/Y1 records')
        if not any((row[3] & 0xffff) == 1 for row in records):
            fail(f'T{track+1}: no trigger-bearing PK/Y1 record')
        if not any(row[19] == engine for row in records):
            observed = sorted({row[19] for row in records})
            fail(f'T{track+1}: expected engine {engine}, observed {observed}')

        left = rl.readback_audio(classes, track + 1)
        right = rl.readback_audio(classes, track + 1, True)
        if not left or not right: fail(f'T{track+1}: no post-chain audio')
        tail = left[2048:]
        significant = [v for v in tail if abs(v) > 100]
        if len(significant) < 16:
            fail(f'T{track+1}/engine {engine}: only {len(significant)} significant samples')
        if len(set(significant)) < 5:
            fail(f'T{track+1}/engine {engine}: output lacks variation')
        if len(left) != len(right): fail(f'T{track+1}: stereo length mismatch')
        stereo_error = max(abs(a - b) for a, b in zip(left[2048:], right[2048:]))
        if stereo_error > 4:
            fail(f'T{track+1}: stereo mismatch {stereo_error} LSB')
        print(
            f'PASS T{track+1}: engine {engine}, {len(significant)} significant samples, '
            f'{len(set(significant))} distinct, peak {max(map(abs,left))}'
        )

    print('PERKY HW4 full-image port: PASS (T1 Fold1, T2 Karplus, T5 Fold2, T6 Noise/Tone simultaneously)')


if __name__ == '__main__':
    main()
