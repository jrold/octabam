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
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/hw'), str(ROOT / 'tools/harness')]

import blockdump as bd
import ot_project as otp
import recloop as rl
from ab_fixture import prepare

OUT = ROOT / 'out/perky/hw4-port'
FIXED = {0: 0, 1: 10, 4: 3, 5: 8}   # zero-based OT track -> engine id
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
        # One source upload contains four tracks: 672 16-bit host words.
        # Only local slot0 starts at the packet's recorded ColdFire address.
        # Resolve the requested track's byte address within the whole packet.
        for (direction, kind, payload_core, base), packets in classes.items():
            if (direction, kind, payload_core) != ('>', 0, core):
                continue
            delta = address - base
            if delta < 0 or delta % 2:
                continue
            offset = delta // 2
            for _frame, words in packets:
                if offset + 20 <= len(words) and words[offset] == 0x504B and words[offset+2] == 0x5931:
                    rows.append(words[offset:offset+168])
    return rows


def main():
    packet_window_selftest()
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

    # Activate the same signed voices once, then observe their settled tails
    # before the pattern's second trig. Without the initial trig FLEX never
    # calls the source and cannot calibrate this AMP continuation. Require the
    # last 1024 samples to be quiet and stable before using their stock DC bias.
    baseline_dump = OUT / 'stock-dirty.bin'
    baseline_cmd = list(cmd)
    baseline_cmd[baseline_cmd.index('--frames')+1] = '2600'
    baseline_cmd[baseline_cmd.index('--block-dump')+1] = str(baseline_dump)
    with (OUT / 'stock-dirty.log').open('w') as log:
        subprocess.run(baseline_cmd, cwd=ROOT, check=True, timeout=600,
                       stdout=log, stderr=subprocess.STDOUT)
    verify(log_path, dump, baseline_dump)


def packet_window_selftest():
    packets = {}
    for core, base in ((1, 0x80001c90), (0, 0x800021d0)):
        for ping in range(2):
            words = [0]*672
            for slot in (0, 1):
                start = 168*slot
                words[start:start+4] = [0x504b, 0, 0x5931, 1]
                words[start+19] = 10*core+slot
            packets[('>', 0, core, base+2688*ping)] = [(ping, words)]
    for track in range(8):
        rows = records_for_track(packets, track)
        if track % 4 < 2:
            assert len(rows) == 2 and all(len(row) == 168 for row in rows)
            assert {row[19] for row in rows} == {10*(1 if track < 4 else 0)+track%4}
        else:
            assert not rows, track


def verify(log_path, dump, baseline_dump):
    log = log_path.read_text()
    if 'ILLEGAL' in log:
        fail('emulator hit ILLEGAL')
    if not re.search(rf'frames run\s*:\s*{FRAMES}', log):
        fail(f'emulator did not complete {FRAMES} frames')
    classes = bd.classes(bd.read(dump))
    baseline = bd.classes(bd.read(baseline_dump))

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
        quiet_records = records_for_track(baseline, track)
        if not quiet_records or not any(row[3] & 0xffff for row in quiet_records):
            fail(f'T{track+1}: quiet-tail calibration never activated the signed source')
        quiet_l = rl.readback_audio(baseline, track+1)[-1024:]
        quiet_r = rl.readback_audio(baseline, track+1, True)[-1024:]
        if len(quiet_l) != 1024 or len(quiet_r) != 1024 or max(map(abs, quiet_l+quiet_r)) > 64:
            fail(f'T{track+1}: quiet calibration did not settle to the stock DC floor')
        bias = int(median(a-b for a,b in zip(quiet_l, quiet_r)))
        if max(abs(a-b-bias) for a,b in zip(quiet_l, quiet_r)) > 2:
            fail(f'T{track+1}: quiet stock stereo floor is not stable')
        stereo_error = max(abs(a-b-bias) for a,b in zip(tail_l, tail_r))
        if stereo_error > 2:
            fail(f'T{track+1}: L/R residual {stereo_error} exceeds measured stock bias {bias} + 2 LSB rounding')

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
        '(T1 Fold1, T2 Noise/Tone, T5 Fold2, T6 Karplus simultaneously; '
        'two voices/core; T3/T4/T7/T8 not PERKY)'
    )


if __name__ == '__main__':
    main()
