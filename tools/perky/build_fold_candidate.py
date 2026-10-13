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
import fold_drum2_compact as fold2
BASE_BUILD=multi.build

def build(out):
    BASE_BUILD(ROOT/'out/perky/simple-drum-assets',out)
    source=(out/'multi.asm').read_text()
    # Engine bytes: 0 Fold Drum 1, 2 Simple, 3 Fold Drum 2 (the free HW4 catalogue
    # ids). Fold2 gets its OWN entry and its OWN init rather than a branch inside
    # Fold1's, because the established shape is one init per engine routed by the
    # engine byte -- and a Fold2 record that called no init would be silent.
    source=source.replace('        cmp #>$2,a\n        beq pks_simple_entry','        tst a\n        beq pks_fold_entry\n        cmp #>$3,a\n        beq pks_fold2_entry\n        cmp #>$2,a\n        beq pks_simple_entry',1)
    source=source.replace('pks_simple_entry:\n        jsrl pk_multi_simple_init', 'pks_fold_entry:\n        jsrl pk_multi_fold_init\n        bra pks_tone_common\npks_fold2_entry:\n        jsrl pk_multi_fold2_init\n        bra pks_tone_common\npks_simple_entry:\n        jsrl pk_multi_simple_init\npks_tone_common:',1)
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
    # Fold Drum 2, on its own engine marker ($0d), kept DISTINCT from Fold 1's $0c so
    # the staged boundary holds: marker $0c must still produce Fold1's exact behaviour,
    # because this branch was byte-identical to the physically-tested PERKY4 card at
    # 41227ef3. Two-word relative branches, so pass-1/pass-2 sizing cannot drift.
    source+=(ROOT/'modules/perky/fold_drum2_voice.asm').read_text()
    source+='''
pk_tone_candidate_voice:
        move x:>$418,a
        lsr #$5,a
        move a1,n1
        move #>$38ee,r1
        move x:(r1+n1),a
        cmp #>$c,a
        beq pkfc_render_fold
        cmp #>$d,a
        beq pkfc2_render_fold
        ; NOTE the label names: pkfc2_* deliberately shares no prefix with
        ; pkfc_* -- dsp_asm resolves labels by PREFIX, so a name like
        ; pkfc_render_fold2 (prefix of pkfc_render_fold) can branch to the
        ; wrong address and land in hyperspace with no diagnostic, which is
        ; the warmz/warmz2 failure AGENTS.md records. tools/verify/
        ; verify_perky_3algo_label_prefix would have caught this.
        jsrl pk_simple_voice
        rts
pkfc_render_fold:
        jsrl pk_fold_voice
        rts
pkfc2_render_fold:
        jsrl pk_fold2_voice
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
    # Fold Drum 2's authored state, from ITS template -- slice 0x134, Fold2's object
    # size, NOT Fold1's 0xf4 -- and its own 24 nonzero words (Fold1 has 19).
    raw2=(ROOT/'out/perky/engine-fixtures/engine-4-mode-1-corner-0/wrapper-window-before.bin').read_bytes()[0xc4:0xc4+0x134]
    words2=fold2.FoldDrum2.from_arm(raw2).words
    words2[10]=words2[21]=0
    source+='\npk_multi_fold_init:\n move x:>$418,a\n lsr #$5,a\n move a1,n1\n move #>$38ee,r1\n move x:(r1+n1),b\n cmp #>$c,b\n beq pkfc_initialized\n move #>$c,a\n move a1,x:(r1+n1)\n move r6,r1\n clr a\n do #>$3a,pkfc_zero\n move a1,x:(r1)+\npkfc_zero:\n nop\n'
    for i,value in enumerate(words):
        if value:source+=f' move #>${value:06x},a\n move a1,x:(r6+${i:x})\n'
    source+='pkfc_initialized:\n rts\n'
    # Fold 2's own init. THE LABEL NAMES MATTER: pkfc2_* deliberately shares NO PREFIX
    # with pkfc_*. dsp_asm resolves labels by prefix, so pkfc_zero2 would assemble as
    # pkfc_zero's address with a stray "2" and branch into hyperspace -- the failure
    # AGENTS.md records as a host SIGSEGV with no diagnostic.
    source+='pk_multi_fold2_init:\n move x:>$418,a\n lsr #$5,a\n move a1,n1\n move #>$38ee,r1\n move x:(r1+n1),b\n cmp #>$d,b\n beq pkfc2_initialized\n move #>$d,a\n move a1,x:(r1+n1)\n move r6,r1\n clr a\n do #>$3a,pkfc2_zero\n move a1,x:(r1)+\npkfc2_zero:\n nop\n'
    for i,value in enumerate(words2):
        if value:source+=f' move #>${value:06x},a\n move a1,x:(r6+${i:x})\n'
    source+='pkfc2_initialized:\n rts\n'
    source=multi.source.noise.force_long_local_jsr(multi.source.noise.relativize_local_conditionals(source))
    (out/'fold.asm').write_text(source)
    used=multi.source.noise.measure(source,out/'fold.asm')
    print(f'Fold candidate: {used}/{multi.source.noise.FULL_DONOR_WORDS} P words; no shipping CF transport yet')
    return source,words
if __name__=='__main__':build(ROOT/'out/perky/fold-multi')
