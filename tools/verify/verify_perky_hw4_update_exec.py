#!/usr/bin/env python3
"""Execute raw triggers plus mandatory Fold2/Karplus updates on DSP56300.

Uses the candidate's shared trigger emitters, Fold2 pitch decoder and frozen
Karplus update emitter. Compares every compact word with the original updated
ARM objects, retaining allocation guards. Full ARM-object update arithmetic is
independently checked by verify_perky_hw4_control_update.py.
"""
from pathlib import Path
import struct
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/verify'), str(ROOT/'tools/perky'), str(ROOT/'modules/perky')]
import verify_perky_controlled_voice_exec as host
import fold2_trigger_plan_source as fold_trigger
import karplus_trigger_plan_source as karplus_trigger
import karplus_prepared_update_source as karplus_update
import fold_drum2_compact as fold
import karplus_compact as karplus
import simple_drum_tables as tables
FIX = ROOT/'out/perky/engine-fixtures'
OUT = ROOT/'out/perky/hw4-update-exec'


def main():
    pitch = (ROOT/'out/perky/simple-drum-assets/pitch.bin').read_bytes()
    packed = tables.pack_pitch_basis(struct.unpack('<4096H', pitch)).words
    _, fold_ops = fold_trigger.load_plan(ROOT/'out/perky/fold2-trigger-plan.json')
    _, karplus_ops = karplus_trigger.load_plan(ROOT/'out/perky/karplus-trigger-plan.json')
    host.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    host.HOST.parent.mkdir(parents=True, exist_ok=True)
    host.build_host()
    rows, routines = [], ''
    for engine, offset, size, model in ((4, 0xc4, 0x134, fold.FoldDrum2), (9, 0x2908, 0x10e0, karplus.Karplus)):
        for mode in range(1, 4):
            for corner in range(3):
                case = FIX/f'engine-{engine}-mode-{mode}-corner-{corner}'
                for phase, pre, post in (
                    ('first_trigger', 'wrapper-window-pre-trigger.bin', 'wrapper-window-before.bin'),
                    ('active_retrigger', 'wrapper-window-retrigger-pre.bin', 'wrapper-window-retrigger-before.bin'),
                ):
                    before = model.from_arm((case/pre).read_bytes()[offset:offset+size]).words
                    want = model.from_arm((case/post).read_bytes()[offset:offset+size]).words
                    record = [0]*12
                    if engine == 4:
                        for i, word in enumerate((32, 20, 44, 33)):
                            record[2*i:2*i+2] = [want[word] >> 8, want[word] & 255]
                        record[8] = (2, 0, 1)[want[42]]
                        record[9] = want[14]
                        calls = '        jsr pk_fold2_raw\n        move #>$4f8,r4\n        jsr pk_fold2_apply_controls\n        move #>$3900,r5\n        jsr pk_fold2_apply_pitch\n'
                    else:
                        values, _fixed = karplus_update.context_values(case, phase)
                        # Only the middle-corner fixed point is a shipping specialization.
                        if corner == 1:
                            assert values == karplus_update.prepared_values(case)
                        label = f'pku_prep_{len(rows):02d}'
                        routines += karplus_update.emit_routine(values, label)
                        calls = f'        jsr pk_karplus_raw_{phase}\n        jsr {label}\n'
                    n = len(rows)
                    routines += f'pku_entry_{n:02d}:\n'+calls+'        rts\n'
                    rows.append((before, want, tuple(record)))
    source = 'pk_controlled_voice_exec:\n        move #>$200,r6\n        move x:>$280,a\n'
    for n in range(len(rows)):
        source += f'        cmp #>${n:x},a\n        beq pku_entry_{n:02d}\n'
    source += '        rts\n'+routines
    source += fold_trigger.emit_routine(fold_ops, label='pk_fold2_raw', snapshot_address=0x300)
    for phase in ('first_trigger', 'active_retrigger'):
        source += karplus_trigger.emit_routine(karplus_ops[phase], label=f'pk_karplus_raw_{phase}', snapshot_address=0x300)
    source += (ROOT/'modules/perky/fold_drum2_seam.asm').read_text()
    source += (ROOT/'modules/perky/simple_drum_delta.asm').read_text()
    source = host.source_builder.force_long_local_jsr(host.source_builder.relativize_local_conditionals(source))
    binary, entry = host.assemble(source)
    selection = 0
    current_record = [0]*12
    def write_data(path, state, _tables):
        path.write_text('X 100 '+' '.join(['000000']*13)+'\n'+
            'X 200 '+' '.join(f'{v:06x}' for v in state)+'\n'+
            'X 500 '+' '.join(f'{v:06x}' for v in current_record)+'\n'+
            f'X 280 {selection:06x}\nX 300 '+' '.join(['000000']*64)+'\n'+
            'X 3900 '+' '.join(['000000']*128)+'\nX 3964 ffffff\n'+
            'Y efb '+' '.join(f'{v:06x}' for v in (*packed, 0))+'\n')
        return []
    host.write_data = write_data
    for n, (before, want, record) in enumerate(rows):
        selection = n
        current_record = record
        initial = before + [0x5a5a]*(64-len(before))
        _, states, _ = host.run(binary, entry, f'case-{n:02d}', initial, [], [(record, -1)])
        expected = want + initial[len(before):]
        if states[0] != expected:
            differences = [(i, a, b) for i, (a, b) in enumerate(zip(states[0], expected)) if a != b]
            raise AssertionError(f'case {n}: trigger/update state differences {differences}')
    print(f'HW4 trigger + mandatory update DSP gate: PASS ({len(rows)} complete compact states; original ARM oracle; allocation guards)')


if __name__ == '__main__':
    main()
