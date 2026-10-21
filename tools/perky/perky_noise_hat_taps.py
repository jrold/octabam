"""Current-block Noise Hat: CF ring taps, A delay arithmetic and native clock."""
import json
import perky_noise_hat_resident as R
import source_clock as C
base=R.base
STATE=R.STATE;SCRATCH=R.SCRATCH;PCM=R.PCM;COUNT=R.COUNT;MODE=R.MODE
SAVED=R.SAVED;VECTOR=R.VECTOR;REGISTERS=R.REGISTERS;MAIL=R.MAIL;L=R.L;S=R.S

def service():
    parts=R.service()
    save=''.join(f' move {r},x:>${SAVED+i:x}\n' for i,r in enumerate(REGISTERS))
    restore=''.join(f' move x:>${SAVED+i:x},{r}\n' for i,r in reversed(list(enumerate(REGISTERS))))
    parts['render']=parts['render'].replace(' move #>$3980,r0\n','')
    parts['frame']='''nhr_source:
 move a,x:>$20e
'''+save+'''
 clr a
 move a1,x:>$39be
 move x:>$418,a
 cmp #>$20,a
 bne nhr_restore
 move #>$ffffff,m4
 move x:>$209,r4
 move x:(r4)+,a
 and #>$ffff,a
 cmp #>$4e54,a
 bne nhr_restore
'''+''.join(f' move #>$ffffff,m{i}\n' for i in range(8))+'''
 move x:(r4)+,a
 and #>$ffff,a
 move a1,x:>$39f1
 clr a
 move a1,x:>$39b8
 move a1,x:>$3a26
 move r4,x:>$39b2
 jsrl nhr_segment
 jsrl nhr_segment
 move #>$4e52,a
 move a1,x:>$39f0
 move x:>$39b8,a
 move a1,x:>$39f2
 move #>1,a
 move a1,x:>$39be
nhr_restore:
'''+restore+'''
 move x:>$39be,a
 tst a
 beq nht_pass
 move x:>$20b,a
 add #>$80,a
 move a1,x:>$20b
 move #>$10,n7
 move ssh,x0
 jmp $000426
nht_pass:
 move x:>$39c0,a2
 move x:>$39c1,a1
 move x:>$39c2,a0
 rts
'''
    parts['segment']='''nhr_segment:
 move x:>$39b2,r4
 move x:(r4)+,a
 and #>$ffff,a
 move a1,x:>$39b9
 and #>31,a
 move a1,x:>$39bb
 move x:>$39b9,a
 lsr #>5,a
 and #>3,a
 move a1,x:>$39b1
 move x:(r4)+,a
 and #>$ffff,a
 move a1,x:>$39bc
 move x:(r4)+,b
 and #>$ffff,b
 tst b
 beq nht_patches_done
 do b,nht_patches_loop
 move x:(r4)+,a
 and #>$ffff,a
 move a1,r1
 move x:(r4)+,a
 and #>$ffff,a
 move a1,x:(r1)
nht_patches_loop:
 nop
nht_patches_done:
 move r4,x:>$39b2
 move x:>$39b9,a
 jclr #7,a1,nht_no_reset
 jsrl pk_clock_reset
nht_no_reset:
 move x:>$39bb,a
 tst a
 beq nht_segment_exit
 move a1,n7
 jsrl pk_clock_prepare
 move n7,x:>$39b0
 move r0,x:>$39ba
 move x:>$39b9,a
 jclr #8,a1,nht_active
 clr a
 do n7,nht_muted_loop
 move a1,x:(r0)+
 move a1,x:(r0)+
nht_muted_loop:
 nop
 bra nht_convert
nht_active:
 jsrl pknha_render
 move x:>$39b1,a
 cmp #>2,a
 beq nht_convert
 jsrl nht_delay
nht_convert:
 jsrl pk_clock_finish
nht_segment_exit:
 rts
'''
    # The qualified adapter is relocated without changing its instructions.
    for key,text in (('clock_prepare',C.PREPARE),('clock_finish',C.FINISH)):
        for i in reversed(range(8)):text=text.replace(f'${C.BASE+i:x}',f'${0x3a23+i:x}')
        if key=='clock_finish':
            text=text.replace('        mpy y0,x0,a\n        move a1,x0','''        move x0,y1
        mpy y0,x0,a
        move a1,x0
        move x0,x:>$39bf
        move #>147,y0
        mpy y0,x0,b
        move n3,y0
        move y1,x0
        mpy y0,x0,a
        sub b,a
        asr a
        move a0,a
        move x:>$39bf,b
        tst a
        bge nht_remainder_positive
        sub #>1,b
        bra nht_quotient_ready
nht_remainder_positive:
        cmp #>147,a
        blt nht_quotient_ready
        add #>1,b
nht_quotient_ready:
        move b1,x0''')
        parts[key]=text
    parts['delay']='''nht_delay:
 move x:>$39ba,r0
 move x:>$39b2,r4
 move #>$39f4,a
 move x:>$39b8,x0
 add x0,a
 move a1,r2
 move x:>$39b0,b
 do b,nht_sample_loop
 move x:(r0),a
 move a1,x:>$39bd
 move #>$3a2b,r3
 do #>5,nht_stage_loop
 move a1,x0
 move x:(r3)+,a
 move a1,y1
 sub #>16,a
 move a1,y0
 mpy y0,x0,b
 move x:(r4)+,a
 and #>$ffff,a
 asl #>8,a,a
 move a1,a
 asr #>8,a,a
 move a1,x0
 move y1,y0
 mac y0,x0,b
 asr #>5,b,b
 move b0,a
 move #>$ff8001,x0
 cmp x0,a
 tlt x0,a
nht_stage_loop:
 nop
 move a1,x:(r2)+
 move a1,x0
 asl #>2,a,a
 add x0,a
 asr a
 move a1,x1
 move x:>$39bc,a
 move a1,y0
 move x1,x0
 mpy y0,x0,b
 move #>4095,a
 sub y0,a
 move a1,y0
 move x:>$39bd,x0
 mac y0,x0,b
 asr #>13,b,b
 move b0,a
 and #>$ffff,a
 asl #>8,a,a
 move a1,a
 asr #>8,a,a
 move a1,x:(r0)+
 move a1,x:(r0)+
nht_sample_loop:
 nop
 move r4,x:>$39b2
 move x:>$39b8,a
 move x:>$39b0,x0
 add x0,a
 move a1,x:>$39b8
 rts
'''
    for key in ('frame','segment'):
        parts[key]=parts[key].replace(' and #>$ffff,a\n',' and #>$ffff,a\n move a1,a\n').replace(' and #>$ffff,b\n',' and #>$ffff,b\n move b1,b\n')
    return parts

def build_program(work,asm):
    saved=base.service;base.service=service
    try:result=base.build_program(work,asm)
    finally:base.service=saved
    outputs,ledger,irq,*_=result
    entry=next(r['start'] for r in ledger if r['name']=='frame')
    _,syms=base.B.assemble_syms((work/'service.asm').read_text(),0x1000,'noise_hat_A',strict_layout=True)
    (work/'resident-symbols.json').write_text(json.dumps(dict(source_entry=entry,embed_entry=next(r['start'] for r in ledger if r['name']=='embed'),commit=entry+syms['nhr_restore']-syms['nhr_source'],short_irq_reference=None))+'\n')
    return result,entry
if __name__=='__main__':
    from pathlib import Path
    build_program(Path('out/perky/hybrid/noise-hat-taps/program'),Path('out/perky/hybrid/noise-hat-resident/probe/multi.asm'))
