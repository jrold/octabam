"""Sample-accurate pre-trig/post-trig control and engine routing.

The optional prefix tuple occupies unused source PCM words, not packet-header
fields. Marker A5 lives in its reserved parameter byte. Legacy diagnostic
records without that marker use the current tuple for both segments.
"""
import re

FRAME='''pk_three_frame:
        clr a
        move a1,x:>$39b3
        move a1,x:>$39bc
        move r4,x:>$39ba
        move x:(r4+$3),a
        and #>$ffff,a
        move a1,x:>$39bb
        tst a
        beq p3fm_suffix
        move x:>$20c,a
        tst a
        ble p3fm_suffix
        cmp #>$10,a
        bge p3fm_suffix
        move a1,x:>$39bc
        move a1,n7
        clr a
        move a1,x:>$39bd
        move x:(r4+$1e),a
        and #>$ff,a
        cmp #>$a5,a
        bne p3fm_prefix
        move r4,a
        add #>$c,a
        move a1,r4
p3fm_prefix:
        jsrl pk_three_segment
p3fm_suffix:
        move x:>$39ba,r4
        move x:>$39bb,a
        move a1,x:>$39bd
        move #>$10,a
        move x:>$39bc,x0
        sub x0,a
        move a1,n7
        jsrl pk_three_segment
        rts
'''

SEGMENT='''pk_three_segment:
        move n7,x:>$39be
        move #>$3900,r5
        move #>$ffffff,m0
        move #>$ffffff,m1
        move #>$ffffff,m2
        move #>$ffffff,m3
        move #>$ffffff,m4
        move #>$ffffff,m5
        move #>$ffffff,m6
        move x:(r4+$13),a
        and #>$ff,a
        move a1,x:>$39bf
        tst a
        beq p3sg_init_one
        cmp #>$3,a
        beq p3sg_init_two
        cmp #>$2,a
        bne p3sg_silent
        jsrl pk_multi_simple_init
        bra p3sg_common
p3sg_init_one:
        jsrl pk_multi_fold_init
p3sg_common:
        jsrl pk_three_common_controls
        bra p3sg_base
p3sg_init_two:
        jsrl pk_multi_fold2_init
        jsrl pk_fold2_apply_controls
p3sg_base:
        jsrl pk_simple_base
        move x:>$39bf,a
        cmp #>$3,a
        bne p3sg_event
        move x:>$3975,a
        move a1,x:(r6+$4)
        clr a
        move a1,x:(r6+$5)
p3sg_event:
        move x:>$39bd,a
        tst a
        beq p3sg_render
        move x:>$39bf,a
        cmp #>$3,a
        beq p3sg_hitfoldtwo
        jsrl pk_clock_reset
        jsrl pk_three_common_trigger
        bra p3sg_render
p3sg_hitfoldtwo:
        jsrl pk_three_fold2_trigger
p3sg_render:
        move x:>$39be,n7
        jsrl pk_clock_prepare
        move x:>$39bf,a
        tst a
        beq p3sg_voice_one
        cmp #>$3,a
        beq p3sg_voice_two
        jsrl pk_simple_voice
        bra p3sg_finish
p3sg_voice_one:
        jsrl pk_fold_voice
        bra p3sg_finish
p3sg_voice_two:
        jsrl pk_fold2_voice
p3sg_finish:
        jsrl pk_clock_finish
        rts
p3sg_silent:
        move x:>$39b3,a
        asl a
        move a1,r0
        move x:>$39be,a
        asl a
        move a1,b
        clr a
        do b,p3sg_zeros
        move a1,x:(r0)+
p3sg_zeros:
        nop
        move x:>$39b3,a
        move x:>$39be,x0
        add x0,a
        move a1,x:>$39b3
        rts
'''

TRIGGER='''pk_three_common_trigger:
        move #>$1,a
        move a1,x:(r6+$a)
        move a1,x:(r6+$11)
        move a1,x:(r6+$15)
        move a1,x:(r6+$1c)
        clr a
        move a1,x:(r6+$f)
        move a1,x:(r6+$10)
        move a1,x:(r6+$12)
        move a1,x:(r6+$1a)
        move a1,x:(r6+$1b)
        move a1,x:(r6+$1d)
        move x:>$39bf,a
        tst a
        bne p3ct_finish
        clr a
        move a1,x:(r6+$23)
p3ct_finish:
        rts
'''


def compose(source,piece):
    begin=source.index('pks_tone_common:')
    ctrl=source.index('        move x:(r4+$8),a',begin)
    end=source.index('pksf_skip_wave:',ctrl)+len('pksf_skip_wave:\n')
    common='pk_three_common_controls:\n'+source[ctrl:end]+'        rts\n'
    source,count=re.subn(r'pks_voice_ready:.*?(?=; ===== END synth_seam_glue.asm =====)',
                         'pks_voice_ready:\n        jsrl pk_three_frame\n        bra pks_continue\n',source,flags=re.S)
    assert count==1
    for name in ('pk_three_controls','pk_tone_candidate_voice'):
        source,count=re.subn(r'; ===== BEGIN '+name+r' =====.*?; ===== END '+name+r' =====\n?', '',source,flags=re.S)
        assert count==1,name
    return source+piece('pk_three_common_controls',common)+piece('pk_three_common_trigger',TRIGGER)+piece('pk_three_frame',FRAME)+piece('pk_three_segment',SEGMENT)
