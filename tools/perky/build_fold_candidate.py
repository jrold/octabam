#!/usr/bin/env python3
"""Compose the Fold Drum candidate, without emitting a hardware updater.

Production ColdFire controls and whole-seam gates are still required.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'modules/perky'))
import build_multi_payload as multi
import fold_drum_compact as fold
BASE_BUILD=multi.build

def build(out):
    BASE_BUILD(ROOT/'out/perky/simple-drum-assets',out)
    source=(out/'multi.asm').read_text()
    source=source.replace('        cmp #>$2,a\n        beq pks_simple_entry','        tst a\n        beq pks_fold_entry\n        cmp #>$2,a\n        beq pks_simple_entry',1)
    source=source.replace('pks_simple_entry:\n        jsrl pk_multi_simple_init', 'pks_fold_entry:\n        jsrl pk_multi_fold_init\n        bra pks_tone_common\npks_simple_entry:\n        jsrl pk_multi_simple_init\npks_tone_common:',1)
    # r4 still points at the tagged record before base-frequency preparation.
    source=source.replace('        move x:(r4+$11),a', '''        move x:(r4+$13),a
        and #>$ff,a
        tst a
        bne pksf_common_amp_gate
        move x:(r6+$1f),a
        move a1,x:(r6+$24)
        move #>$2b,a
        move a1,x:(r6+$1f)
        move x:(r4+$10),a
        and #>$ff,a
        cmp #>$2,a
        blt pksf_mode_increment
        clr a
        bra pksf_mode_prepared
pksf_mode_increment:
        add #>$1,a
pksf_mode_prepared:
        move a1,x:(r6+$22)
        move #>$22a0,a
        move a1,x:(r6+$8)
        bra pksf_skip_wave
pksf_common_amp_gate:
        move x:(r4+$11),a''',1)
    # Fold needs the common amplitude gate too, but no deferred mode-wave map.
    source=source.replace('        move a1,x:(r6+$8)\n        bra pksf_skip_wave','        move a1,x:(r6+$8)\n        move x:(r4+$11),a\n        and #>$1,a\n        move a1,x:(r6+$e)\n        bra pksf_skip_wave',1)
    source=source.replace('pksd_mode_ready:\n        move a1,x:(r6+$8)','pksd_mode_ready:\n        move a1,x:(r6+$8)\npksf_skip_wave:',1)
    source=source.replace('jsrl pk_simple_voice','jsrl pk_tone_candidate_voice')
    source=source.replace('pksd_retrigger:\n','pksd_retrigger:\n        jsrl pk_fold_candidate_trigger\n',1)
    source+=(ROOT/'modules/perky/fold_drum_voice.asm').read_text()
    source+='''
pk_tone_candidate_voice:
        move x:>$418,a
        lsr #$5,a
        move a1,n1
        move #>$38ee,r1
        move x:(r1+n1),a
        cmp #>$c,a
        beq pkfc_render_fold
        jsrl pk_simple_voice
        rts
pkfc_render_fold:
        jsrl pk_fold_voice
        rts
pk_fold_candidate_trigger:
        move x:>$418,a
        lsr #$5,a
        move a1,n1
        move #>$38ee,r1
        move x:(r1+n1),a
        cmp #>$c,a
        bne pkfc_trigger_done
        clr a
        move a1,x:(r6+$23)
pkfc_trigger_done:
        rts
'''
    raw=(ROOT/'out/perky/engine-fixtures/engine-1-mode-1-corner-0/wrapper-window-before.bin').read_bytes()[0xc4:0xc4+0xf4]
    words=fold.FoldDrum1.from_arm(raw).words
    words[10]=words[21]=0
    words[15]=words[16]=words[26]=words[27]=0
    source+='\npk_multi_fold_init:\n move x:>$418,a\n lsr #$5,a\n move a1,n1\n move #>$38ee,r1\n move x:(r1+n1),b\n cmp #>$c,b\n beq pkfc_initialized\n move #>$c,a\n move a1,x:(r1+n1)\n move r6,r1\n clr a\n do #>$3a,pkfc_zero\n move a1,x:(r1)+\npkfc_zero:\n nop\n'
    for i,value in enumerate(words):
        if value:source+=f' move #>${value:06x},a\n move a1,x:(r6+${i:x})\n'
    source+='pkfc_initialized:\n rts\n'
    source=multi.source.noise.force_long_local_jsr(multi.source.noise.relativize_local_conditionals(source))
    (out/'fold.asm').write_text(source)
    used=multi.source.noise.measure(source,out/'fold.asm')
    print(f'Fold candidate: {used}/2724 P words; no shipping CF transport yet')
    return source,words
if __name__=='__main__':build(ROOT/'out/perky/fold-multi')
