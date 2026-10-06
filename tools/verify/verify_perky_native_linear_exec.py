#!/usr/bin/env python3
"""Execute every synthetic linear-curve index, including quotient carries."""
import verify_perky_controlled_voice_exec as c


def main():
    c.build_host()
    c.OUT = c.ROOT / 'out/perky/native-linear'
    c.OUT.mkdir(parents=True, exist_ok=True)
    c.WRAPPER = '''
pk_controlled_voice_exec:
        move x:>$101,a
        asl #$7,a,a
        move x:>$100,x0
        add x0,a
        move a1,r3
        do n7,pknl_done
        move r3,x0
        jsrl pken_index_value
        move a1,x:(r0)+
        move a1,x:(r0)+
        move (r3)+
pknl_done:
        nop
        rts
'''
    s, init, tables = c.build_source_and_assets()
    binary, entry = c.assemble(s)
    blocks = []
    for start in range(0, 2048, 16):
        k = list(c.knob_row()); k[0] = start & 127; k[1] = start >> 7
        blocks.append((tuple(k), -1))
    audio, _, _ = c.run(binary, entry, 'all-indices', init, tables, blocks)
    expected = [round(i * 65535 / 2047) for i in range(2048)]
    assert c.flatten(audio) == expected
    print('PERKY native synthetic linear curve: PASS (all 2048 DSP indices exact)')

if __name__ == '__main__': main()
