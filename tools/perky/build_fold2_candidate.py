#!/usr/bin/env python3
"""Compose hidden Fold Drum 2 into the PERKY4 DSP seam.

This is not a hardware-image builder.  It consumes the locally qualified ARM
trigger plan, preserves PERKY4's visible browser, and gives engine 3 an exact
production-record/control/event/render path for emulator qualification.  The
current PERKY4 2,724-word donor is already nearly full; physical P placement is
a later, explicit effect-reclamation gate.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'modules/perky'));sys.path.insert(0,str(ROOT/'tools/perky'))
import build_fold_candidate as fold1
import fold_drum2_compact as fold2
import fold2_trigger_plan_source as trigger

PLAN=ROOT/'out/perky/fold2-trigger-plan.json'
FIX=ROOT/'out/perky/engine-fixtures'
SHADOW_X=0x3975


def once(source:str,old:str,new:str,what:str)->str:
    if source.count(old)!=1:raise RuntimeError(f'{what}: expected one anchor, found {source.count(old)}')
    return source.replace(old,new,1)


def build(out:Path):
    source,_=fold1.build(out)
    _plan,ops=trigger.load_plan(PLAN)

    # Engine 3 remains hidden from the ColdFire/browser tables; this only makes
    # a production-form PK/Y1 record carrying catalog byte 3 executable here.
    source=once(source,
        '        tst a\n        beq pks_fold_entry\n        cmp #>$2,a',
        '        tst a\n        beq pks_fold_entry\n        cmp #>$3,a\n        beq pks_fold2_entry\n        cmp #>$2,a',
        'Fold2 dispatcher')

    # Fold2 owns its control/event path rather than falling through Simple's
    # mode/wave preparation.  It rejoins only at pks_continue after rendering.
    fold2_entry='''pks_fold2_entry:
        jsrl pk_multi_fold2_init
        jsrl pk_fold2_apply_controls
        move #>$3900,r5
        move #>$ffffff,m0
        move #>$ffffff,m1
        move #>$ffffff,m2
        move #>$ffffff,m3
        move #>$ffffff,m4
        move #>$ffffff,m5
        move #>$ffffff,m6
        move #$0,r0
        move #>$10,a
        move a1,x:>$38ec
        move x:(r4+$3),a
        and #>$ffff,a
        tst a
        beq pkf2_event_ready
        move x:>$20c,a
        tst a
        blt pkf2_event_ready
        cmp #>$10,a
        bge pkf2_event_ready
        move a1,x:>$38ec
pkf2_event_ready:
        jsrl pk_simple_base
        move x:>$38ec,a
        cmp #>$10,a
        beq pkf2_full
        tst a
        beq pkf2_retrigger
        move a1,n7
        jsrl pk_fold2_voice
pkf2_retrigger:
        jsrl pk_fold2_candidate_trigger
        move #>$3900,r5
        move #>$10,a
        move x:>$38ec,x0
        sub x0,a
        move a1,n7
        jsrl pk_fold2_voice
        bra pks_continue
pkf2_full:
        move #>$10,n7
        jsrl pk_fold2_voice
        bra pks_continue
'''
    source=once(source,'pks_simple_entry:\n',fold2_entry+'pks_simple_entry:\n','Fold2 seam insertion')

    # Local fixture-derived initialization is emitted only into out/*.asm; no
    # original firmware state is committed.  Marker $d distinguishes Fold2
    # from Fold1's $c and the Simple/Noise overlays.
    case=FIX/'engine-4-mode-1-corner-0'
    raw=(case/'wrapper-window-before.bin').read_bytes()[0xc4:0xc4+0x134]
    words=fold2.FoldDrum2.from_arm(raw).words
    init='''\npk_multi_fold2_init:
        move x:>$418,a
        lsr #$5,a
        move a1,n1
        move #>$38ee,r1
        move x:(r1+n1),b
        cmp #>$d,b
        beq pkf2_initialized
        move #>$d,a
        move a1,x:(r1+n1)
        move r6,r1
        clr a
        do #>$3a,pkf2_zero
        move a1,x:(r1)+
pkf2_zero:
        nop
'''
    for i,value in enumerate(words):
        if value:init+=f'        move #>${value:06x},a\n        move a1,x:(r6+${i:x})\n'
    init+='pkf2_initialized:\n        rts\n'

    trigger_source=trigger.emit_routine(ops,label='pk_fold2_candidate_trigger',
                                        snapshot_reg='r5',snapshot_address=SHADOW_X)
    source+='\n'+(ROOT/'modules/perky/fold_drum2_seam.asm').read_text()
    source+='\n'+(ROOT/'modules/perky/fold_drum2_voice.asm').read_text()
    source+='\n'+trigger_source+init
    source=fold1.multi.source.noise.force_long_local_jsr(
        fold1.multi.source.noise.relativize_local_conditionals(source))
    out.mkdir(parents=True,exist_ok=True)
    (out/'fold2.asm').write_text(source)
    print('Fold2 hidden candidate: wrote production-form source; browser unchanged; P placement not claimed')
    print(f'Fold2 trigger shadow candidate: X:${SHADOW_X:04x}..${SHADOW_X+trigger.WORDS-1:04x}')
    return source,words

if __name__=='__main__':build(ROOT/'out/perky/fold2-candidate')
