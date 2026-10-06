#!/usr/bin/env python3
"""Enter the actual generated source seam for all slots and sample offsets.

Compare its PCM against the independently entered control/voice wrapper. The
low-P continuation calls our state dumper, then returns to the host; stock
AMP/FX itself is outside this focused gate.
"""
from pathlib import Path
import verify_perky_controlled_voice_exec as c

ROOT = c.ROOT
SLOT = 0
WRAPPER = r'''
pk_controlled_voice_exec:
        move #>$000500,r4
        move #>$000100,r1
        move #>$000508,r2
        do #$c,pkse_copy_controls
        move x:(r1)+,a
        move a1,x:(r2)+
pkse_copy_controls:
        nop
        move r4,x:>$209
        move x:>$10c,a
        move a1,x:>$20c
        clr b
        tst a
        blt pkse_flag_ready
        cmp #>$10,a
        bge pkse_flag_ready
        move #>$1,b
pkse_flag_ready:
        move b1,x:(r4+$3)
        jsrl pk_probe_source
        rts

pkse_finish:
        move x:>$20b,x0
        move #>$000200,r2
        do #$3a,pkse_copy_voice
        move x:(r6)+,a
        move a1,x:(r2)+
pkse_copy_voice:
        nop
        move x:>$38e8,a
        move a1,x:(r2)+
        move x:>$38e9,a
        move a1,x:(r2)+
        move x:>$38ea,a
        move a1,x:(r2)+
        move x:>$38eb,a
        move a1,x:(r2)+
        move x0,x:(r2)+
        move #>$1234,a
        move a1,x:(r2)+
        rts
'''


def main():
    # Establish reference PCM through the other entry path for each offset.
    c.build_host()
    source, state_init, tables = c.build_source_and_assets()
    binary, entry = c.assemble(source)
    knobs = c.knob_row()
    expected = {}
    for event in range(16):
        expected[event] = c.run(binary, entry, f'ref-event-{event}', state_init,
                                tables, [(knobs, event)])[0]
    expected[-1] = c.run(binary, entry, 'ref-no-event', state_init, tables,
                         [(knobs, -1)])[0]
    c.OUT = ROOT / 'out/perky/seam-exec'
    c.OUT.mkdir(parents=True, exist_ok=True)
    c.WRAPPER = WRAPPER
    source, state_init, tables = c.build_source_and_assets()
    source = source.replace('jmp     $000426', 'jmp     $000400')
    binary, entry = c.assemble(source)
    labels = {f[0]: int(f[1], 16) for line in binary.with_suffix('.sym').read_text().splitlines()
              if len(f := line.split()) == 2}
    finish = labels['pkse_finish']

    def write_data(path, state_init, table_words):
        path.write_text(
            'X 3800 ' + ' '.join(f'{v:06x}' for v in state_init) + '\n'
            + 'X 3900 ' + ' '.join(['000000'] * 100) + '\n'
            + 'X 500 00504b 000000 005931 000000\n'
            + f'X 418 {SLOT:06x}\nX 20b 004080\n'
            + f'P 400 0bf080 {finish:06x} 00000c\n'
            + f'Y {c.TABLE_Y:x} ' + ' '.join(f'{v:06x}' for v in table_words) + '\n')
        return state_init[-4:]
    c.write_data = write_data
    global SLOT
    for SLOT in (0, 0x20, 0x40, 0x60):
        for event in (-1, *range(16)):
            audio, states, _ = c.run(binary, entry, f'slot-{SLOT:x}-event-{event}',
                                      state_init, tables, [(knobs, event)])
            assert audio == [[sample << 8 for sample in block] for block in expected[event]], (SLOT, event, 'seam PCM differs')
            assert states[0][62:64] == [0x4100, 0x1234], (SLOT, event, 'continuation')
    SLOT = 0x80
    audio, states, _ = c.run(binary, entry, 'invalid-slot', state_init, tables,
                              [(knobs, 0)])
    assert not any(audio[0])
    # A stale dirty latch must reset on slot0. Additional signed slots are
    # explicitly cleared without entering the costly renderer.
    original_write = c.write_data
    def occupied(path, state_init, table_words):
        rng = original_write(path, state_init, table_words)
        with path.open('a') as f: f.write('X 38ed 000001\n')
        return rng
    c.write_data = occupied
    SLOT = 0
    audio, _, _ = c.run(binary, entry, 'dirty-latch-reset', state_init, tables, [(knobs, 0)])
    assert audio == [[sample << 8 for sample in block] for block in expected[0]]
    SLOT = 0x20
    audio, _, _ = c.run(binary, entry, 'excess-voice', state_init, tables, [(knobs, 0)])
    assert not any(audio[0]), 'second admitted voice exceeded the per-core limit'

    # An unsigned slot0 must also clear the latch before a later PERKY track.
    c.WRAPPER = WRAPPER.replace('        jsrl pk_probe_source', """
        clr a
        move a1,x:>$418
        move a1,x:>$500
        jsrl pk_probe_source
        move #>$00504b,a
        move a1,x:>$500
        move #>$20,a
        move a1,x:>$418
        jsrl pk_probe_source""")
    source, _, _ = c.build_source_and_assets()
    source = source.replace('jmp     $000426', 'jmp     $000400')
    binary, entry = c.assemble(source)
    labels = {f[0]: int(f[1], 16) for line in binary.with_suffix('.sym').read_text().splitlines()
              if len(f := line.split()) == 2}
    finish = labels['pkse_finish']
    audio, _, _ = c.run(binary, entry, 'unsigned-slot0-reset', state_init, tables, [(knobs, 0)])
    assert audio == [[sample << 8 for sample in block] for block in expected[0]]
    print('PERKY actual source seam: PASS (all slots/trigger offsets, exact PCM, '
          'ring advance, continuation, invalid/excess voices silent, dirty latch '
          'reset on signed and unsigned slot0)')


if __name__ == '__main__':
    main()
