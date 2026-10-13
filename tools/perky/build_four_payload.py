#!/usr/bin/env python3
"""Compose PERKY4 from the unchanged PERKY3R clock and renderer sources.

Only local qualification inputs are emitted. No flash wrapper is produced.
The fourth wave uses 172 dormant voice-overlay X words and 84 internal low-Y
padding words. This is valid only with T1/T5 admission (position zero/core).
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'modules/perky'), str(ROOT/'tools/perky')]
import build_three_payload as three
import complex_drum_compact as complex_ref
import complex_drum_production as state


def build(out, *, native_clock=True):
    assert native_clock, 'PERKY4 uses the qualified 48 kHz native clock'
    out = Path(out)
    source, fresh = three.build(out, native_clock=True)
    source = re.sub(r'(?m)^p3site\d{5}:\n', '', source)
    source = source.replace('pks_voice_ready:\n', '''pks_voice_ready:
        ; The fourth-wave X asset occupies dormant position-1..3 overlays.
        ; Refuse tagged diagnostic records outside T1/T5 before any init.
        move x:>$418,a
        tst a
        bne pks_silence
''', 1)
    # The common control and trigger ABI is the first 34 words of this overlay.
    source = source.replace('        cmp #>$2,a\n        bne p3sg_silent',
        '        cmp #>$5,a\n        beq p4sg_init\n        cmp #>$2,a\n        bne p3sg_silent', 1)
    source = source.replace('p3sg_init_one:',
        'p4sg_init:\n        jsrl pk_multi_complex_init\n        bra p3sg_common\np3sg_init_one:', 1)
    source = source.replace('        jsrl pk_simple_voice\n        bra p3sg_finish',
        '        cmp #>$5,a\n        bne p4sg_simple\n        jsrl pk_complex_production_voice\n        bra p3sg_finish\np4sg_simple:\n        jsrl pk_simple_voice\n        bra p3sg_finish', 1)
    # Complex has no amplitude gate at maximum DECAY. Original MODE 1/0/2
    # selects 22a0/24a0/28a0; phase-wrap owns the actual oscillator switch.
    source = source.replace('pksf_common_amp_gate:\n',
        'pksf_common_amp_gate:\n        move x:>$39bf,a\n        cmp #>$5,a\n        bne p4sg_gate\n        clr a\n        move a1,x:(r6+$e)\n        bra p4sg_wave\np4sg_gate:\n', 1)
    source = source.replace('        move #>$0802,a\n        move a1,x:(r6+$9)',
        'p4sg_wave:\n        move #>$0802,a\n        move a1,x:(r6+$9)', 1)
    source = source.replace('pksd_mode1:\n        move #>$26a0,a',
        'pksd_mode1:\n        move x:>$39bf,a\n        cmp #>$5,a\n        bne p4sg_mode_simple\n        move #>$24a0,a\n        bra pksd_mode_ready\np4sg_mode_simple:\n        move #>$26a0,a', 1)
    # Restore authentic fourth-wave dispatch; retain the three direct Y reads.
    source = source.replace('        bra     pksdo_unknown_wave',
        '        cmp     #>$24a0,a\n        beq     p4osc_fourth\n        bra     pksdo_unknown_wave', 1)
    source = source.replace('pksdo_unknown_wave:',
        'p4osc_fourth:\n        move #>$300,a\n        move a1,x:(r5+$59)\n        bra pksdo_have_wave\npksdo_unknown_wave:', 1)
    source = source.replace('pksdo_read_s16:\n', '''pksdo_read_s16:
        move x0,a
        cmp #>$300,a
        blt p4osc_direct
        sub #>$300,a
        cmp #>$ac,a
        bge p4osc_y_tail
        move a1,n1
        move #>$383a,r1
        move x:(r1+n1),a
        btst #15,a1
        bcc p4osc_return
        sub #>$10000,a
p4osc_return:
        rts
p4osc_y_tail:
        sub #>$ac,a
        move a1,n1
        move #>$ea5,r1
        move y:(r1+n1),a
        rts
p4osc_direct:
''', 1)
    # Reuse qualified native renderer arithmetic, with a control-rate base
    # frequency cache and Simple-compatible state geometry. No +0x64 scratch.
    voice = (ROOT/'modules/perky/complex_drum_voice.asm').read_text()
    voice = voice[:voice.index('; Prepared raw pitch')]
    voice = voice.replace('pk_complex_voice:', 'pk_complex_production_voice:')
    voice = voice.replace('(r6+$12)', '(r6+$a)').replace('(r6+$1d)', '(r6+$15)')
    voice = voice.replace('(r6+$a),r7', '(r6+$22),r7')
    begin = voice.index('        move    x:(r6+$28),a')
    end = voice.index('        move    x:(r5+$62),y0', begin)
    voice = voice[:begin] + voice[end:]
    voice = voice.replace('(r6+$29)', '(r6+$21)').replace('x:(r5+$64)', 'x:(r6+$34)')
    voice = voice.replace('        move    #>$2000,b\n        and     y0,b\n', '')
    voice = voice.replace('''        move    b1,x1
        move    y0,a
        lsr     #$d,a
        move    a1,y1
        move    #>$d,b
        sub     y1,b
        move    b1,x0
        move    x1,b
''', '''        move    y0,a
        lsr     #$d,a
        neg a
        add #>$d,a
        move a1,x0
''')
    # Original renderer's final int16 clamp, independently reference-gated.
    needle = '        move    a0,a\n        move    a1,x:(r0)+'
    voice = voice.replace(needle, '''        move    a0,a
        cmp #>$7fff,a
        ble p4cv_lower
        move #>$7fff,a
p4cv_lower:
        cmp #>$ff8000,a
        bge p4cv_output
        move #>$ff8000,a
p4cv_output:
        move    a1,x:(r0)+''', 1)
    source += three.piece('complex_drum_production_voice', voice)
    raw = (ROOT/'out/perky/engine-fixtures/engine-6-mode-1-corner-0/wrapper-window-pre-trigger.bin').read_bytes()[0x1f8:0x338]
    init_words = state.from_original(complex_ref.CompactComplexDrum.from_arm(raw).words)
    # Engine initialization preserves native pre-trigger state, including the
    # modulation increment; controls are subsequently applied by the seam.
    init = '''pk_multi_complex_init:
        move x:>$38ee,b
        cmp #>$e,b
        beq p4in_ready
        move #>$e,a
        move a1,x:>$38ee
        jsrl pk_clock_reset
        move r6,r1
        clr a
        do #>$3a,p4in_zero
        move a1,x:(r1)+
p4in_zero:
        nop
'''
    for i, value in enumerate(init_words):
        if value:
            init += f'        move #>${value:06x},a\n        move a1,x:(r6+${i:x})\n'
    init += 'p4in_ready:\n        rts\n'
    source += three.piece('pk_multi_complex_init', init)
    # Initializers clear first and then install independent constants. Load
    # each distinct value once; group its stores without changing any final
    # state or condition-code dependency. This is specific to this profile.
    for name in ('simple', 'fold', 'fold2', 'complex'):
        pattern = (r'(; ===== BEGIN pk_multi_'+name+r'_init =====.*?)'
                   r'((?:\s*move #>\$[0-9a-f]+,a\n\s*move a1,x:\(r6\+\$[0-9a-f]+\)\n)+)'
                   r'(.*?; ===== END pk_multi_'+name+r'_init =====)')
        def group(match):
            values = {}
            for value, field in re.findall(r'move #>\$([0-9a-f]+),a\n\s*move a1,x:\(r6\+\$([0-9a-f]+)\)', match[2]):
                values.setdefault(value, []).append(field)
            body = ''.join('        move #>$'+v+',a\n'+''.join('        move a1,x:(r6+$'+f+')\n' for f in fields)
                           for v, fields in values.items())
            return match[1]+'\n'+body+match[3]
        source, count = re.subn(pattern, group, source, flags=re.S)
        assert count == 1, (name, 'initializer constant-store census')
    source = three.historical.multi.source.noise.force_long_local_jsr(source)
    lines = []; branch = 0
    for line in source.splitlines():
        if re.match(r'^\s*b(?:ra|cc|cs|eq|ne|ge|gt|le|lt|pl|mi|vc|vs|hs|lo)\s+[A-Za-z_]', line):
            lines.append(f'p3site{branch:05d}:'); branch += 1
        lines.append(line)
    source = '\n'.join(lines)+'\n'
    (out/'multi.asm').write_text(source)
    (out/'four.asm').write_text(source)
    # Original extracted asset only; no embedded waveform in Git.
    wave = struct.unpack('<256h', (ROOT/'out/perky/simple-drum-assets/wave_080224a0.bin').read_bytes())
    x = [int(v,16) for v in (out/'state_init.words').read_text().split()]
    x[58:230] = [v & 0xffff for v in wave[:172]]
    y = [int(v,16) for v in (out/'tables.words').read_text().split()]
    y[0xea5-0x7a5:0xea5-0x7a5+84] = [v & 0xffffff for v in wave[172:]]
    layout = json.loads((out/'layout.json').read_text())
    for name, words in (('state_init',x), ('tables',y)):
        blob = b''.join(v.to_bytes(3,'little') for v in words)
        (out/f'{name}.bin').write_bytes(blob)
        (out/f'{name}.words').write_text('\n'.join(f'{v:06x}' for v in words)+'\n')
        if name == 'tables': layout['sha256'] = hashlib.sha256(blob).hexdigest()
        else: layout['x_init']['sha256'] = hashlib.sha256(blob).hexdigest()
    layout['complex_wave'] = {'asset':'wave_080224a0.bin','sha256':hashlib.sha256(struct.pack('<256h',*wave)).hexdigest(),
                              'segments':[['x',0x383a,172],['y',0xea5,84]],'admitted_core_position':0}
    layout['free_y_words'] = [[0xef9,0xefb]]
    (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    return source, fresh


if __name__ == '__main__': build(ROOT/'out/perky/four')
