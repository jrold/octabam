#!/usr/bin/env python3
"""Full-image emulator audition gate for fixed-engine PERKY HW4.

Requires OT_PROJECT and PERKY_HW4_IMAGE. Runs all four admitted tracks in one
sequencer session and proves transport engine identity plus nontrivial stereo
post-chain audio. This is an emulator/full-image gate, not a physical-hardware
or sonic-parity claim; isolated native/ARM gates remain authoritative for each
engine's exact renderer/trigger behavior.
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
BLOCKED = tuple(track for track in range(8) if track not in FIXED)
FRAMES = 32000


def fail(message):
    raise AssertionError('PERKY HW4 port: ' + message)


def record_addresses(track):
    # Exact production writer in control.c/control_hw4_candidate.c:
    #   0x80001c90 + ping*0xa80 + 336*track
    base = 0x80001C90 + 336 * track
    return base, base + 0xA80


def configure(project):
    fixture = prepare(project, OUT / 'project')
    for bank in fixture.glob('bank*.work'):
        def mutate(data):
            for part in range(8):
                base = otp.PART_BASE + part * otp.PART_STRIDE + 9
                for track in range(8):
                    data[base + 0x22 + track] = 1  # underlying FLEX donor
                    sig = base + 60 + 30 * track
                    data[sig:sig + 3] = b'PK\x01' if track in FIXED else b'\x00\x00\x00'

                    params = [64, 64, 64, 64, 0, 0, 0, 0, 0, 0, 0, 0]
                    if track in FIXED:
                        params[11] = FIXED[track]
                    for slot, value in enumerate(params):
                        off = (0x2a if slot < 6 else 0x1da) + 30 * track + 6 + slot % 6
                        data[base + off] = value
                    data[base + track] = 0      # FX1 NONE
                    data[base + 8 + track] = 0  # FX2 NONE

            # One trig at step zero on every admitted HW4 voice and none on
            # the other tracks. Pattern looping provides later retriggers.
            for track in range(8):
                at = otp.trac_off(0, track)
                data[at:at + 8] = ((1 if track in FIXED else 0).to_bytes(8, 'big'))

        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def records_for_track(classes, track):
    core = 1 if track < 4 else 0
    rows = []
    for address in record_addresses(track):
        for _frame, words in classes.get(('>', 0, core, address), []):
            if len(words) >= 20 and words[0] == 0x504B and words[2] == 0x5931:
                rows.append(words)
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
        log.write(' '.join(cmd) + '\n')
        log.flush()
        subprocess.run(
            cmd, cwd=ROOT, check=True, timeout=600,
            stdout=log, stderr=subprocess.STDOUT,
        )

    verify(log_path, dump)


def verify(log_path, dump):
    log = log_path.read_text()
    if 'ILLEGAL' in log:
        fail('emulator hit ILLEGAL')
    if not re.search(rf'frames run\s*:\s*{FRAMES}', log):
        fail(f'emulator did not complete {FRAMES} frames')
    classes = bd.classes(bd.read(dump))

    for track, engine in FIXED.items():
        records = records_for_track(classes, track)
        if not records:
            fail(f'T{track+1}: no PK/Y1 records at production track-record address')
        if not any((row[3] & 0xffff) == 1 for row in records):
            fail(f'T{track+1}: no trigger-bearing PK/Y1 record')
        observed = sorted({row[19] for row in records if len(row) >= 20})
        if observed != [engine]:
            fail(f'T{track+1}: expected only engine {engine}, observed {observed}')

        left = rl.readback_audio(classes, track + 1)
        right = rl.readback_audio(classes, track + 1, True)
        if not left or not right:
            fail(f'T{track+1}: no post-chain audio')
        if len(left) != len(right):
            fail(f'T{track+1}: stereo length mismatch')
        tail_l, tail_r = left[4096:], right[4096:]
        stereo_error = max((abs(a - b) for a, b in zip(tail_l, tail_r)), default=0)
        if stereo_error > 4:
            fail(f'T{track+1}: mono-source stereo mismatch {stereo_error} LSB')

        significant = [v for v in tail_l if abs(v) > 100]
        if len(significant) < 16:
            fail(f'T{track+1}/engine {engine}: only {len(significant)} significant samples')
        if len(set(significant)) < 5:
            fail(f'T{track+1}/engine {engine}: output lacks variation')
        print(
            f'PASS T{track+1}: engine {engine}, {len(significant)} significant samples, '
            f'{len(set(significant))} distinct, peak {max(map(abs, left))}'
        )

    for track in BLOCKED:
        if records_for_track(classes, track):
            fail(f'T{track+1}: non-HW4 track unexpectedly published a PK/Y1 record')

    print(
        'PERKY HW4 full-image port: PASS '
        '(T1 Fold1, T2 Karplus, T5 Fold2, T6 Noise/Tone simultaneously; '
        'two voices/core; T3/T4/T7/T8 not PERKY)'
    )


if __name__ == '__main__':
    main()
