"""Resident inner state on A; existing source and readback DMA transport."""
import perky_noise_hat_offload as base
STATE=base.STATE;SCRATCH=base.SCRATCH;PCM=base.PCM;COUNT=base.COUNT;MODE=base.MODE
SAVED=base.SAVED;VECTOR=base.VECTOR;REGISTERS=base.REGISTERS
L=base.L;S=base.S
MAIL=0x39f0
ORIGINAL_SERVICE=base.service

def service():
    save=''.join(f' move {r},x:>${SAVED+i:x}\n' for i,r in enumerate(REGISTERS))
    restore=''.join(f' move x:>${SAVED+i:x},{r}\n' for i,r in reversed(list(enumerate(REGISTERS))))
    render=ORIGINAL_SERVICE()['render'].replace(' move #>$3800,r6',' move #>$3800,r6\n move x:>$39b1,a\n cmp #>2,a\n bne nhr_classic_base\n move #>$3879,r6\nnhr_classic_base:')
    irq='pknha_interrupt:\n rti\n'
    embed='nhr_embed:\n'+save+"""
 move x:>$39f0,a
 cmp #>$4e52,a
 bne nhr_padding_restore
 move #>$ffffff,m1
 move #>$ffffff,m4
 move #>2,n1
 move x:>$206,a
 sub #>$ff,a
 move a1,r1
 move #>$39f0,r4
 do #>24,nhr_padding_loop
 move x:(r4),a
 lsr #>8,a
 and #>$ff,a
 move a1,x0
 move x:(r1),a
 and #>$ffff00,a
 or x0,a
 move a1,x:(r1)+n1
 move x:(r4)+,a
 and #>$ff,a
 move a1,x0
 move x:(r1),a
 and #>$ffff00,a
 or x0,a
 move a1,x:(r1)+n1
nhr_padding_loop:
 nop
nhr_padding_restore:
"""+restore+' move x:>$415,a\n rts\n'
    return dict(irq=irq,embed=embed,render=render,frame=f'''nhr_source:
 move a,x:>$20e
'''+save+'''
 move x:>$418,a
 cmp #>$20,a
 bne nhr_restore
 move #>$ffffff,m4
 move x:>$209,r4
 move #>80,n4
 move x:(r4+n4),b
 and #>$ffff,b
 cmp #>$4e52,b
 bne nhr_restore
 move #>$ffffff,m0
 move #>$ffffff,m1
 move #>$ffffff,m2
 move #>$ffffff,m3
 move #>$ffffff,m4
 move #>$ffffff,m5
 move #>$ffffff,m6
 move #>$ffffff,m7
 move x:>$209,r4
 move #>81,n4
 move (r4)+n4
 move x:(r4)+,a
 and #>$ffff,a
 move a1,x:>$39f1
 clr a
 move a1,x:>$39b8
 move r4,x:>$39b2
 jsrl nhr_segment
 jsrl nhr_segment
 move #>$4e52,a
 move a1,x:>$39f0
 move x:>$39b8,a
 move a1,x:>$39f2
'''+'nhr_restore:\n'+restore+'''nhr_not_ours:
 rts
''',segment=f'''nhr_segment:
 move x:>$39b2,r4
 move x:(r4)+,a
 move a1,x:>$39b9
 and #>31,a
 move a1,x:>$39b0
 move x:>$39b9,a
 lsr #>5,a
 and #>3,a
 move a1,x:>$39b1
 move x:(r4)+,b
 and #>$ffff,b
 tst b
 beq nhr_patch_done
 do b,nhr_patch_loop
 move x:(r4)+,a
 and #>$ffff,a
 move a1,r1
 move x:(r4)+,a
 and #>$ffff,a
 move a1,x:(r1)
nhr_patch_loop:
 nop
nhr_patch_done:
 move r4,x:>$39b2
 move x:>$39b0,a
 tst a
 beq nhr_exit_segment
 jsrl pknha_render
 move #>$3980,r1
 move #>$39f4,a
 move x:>$39b8,x0
 add x0,a
 move a1,r2
 move x:>$39b0,b
 do b,nhr_capture_loop
 move x:(r1)+,a
 move (r1)+
 move a1,x:(r2)+
nhr_capture_loop:
 nop
 move x:>$39b8,a
 move x:>$39b0,x0
 add x0,a
 move a1,x:>$39b8
nhr_exit_segment:
 rts
''')

def build_program(work,asm):
    saved=base.service;base.service=service
    try:result=base.build_program(work,asm)
    finally:base.service=saved
    import json
    outputs,ledger,irq,*_=result
    entry=next(r['start'] for r in ledger if r['name']=='frame')
    _,syms=base.B.assemble_syms((work/'service.asm').read_text(),0x1000,'noise_hat_A',strict_layout=True)
    (work/'resident-symbols.json').write_text(json.dumps(dict(source_entry=entry,embed_entry=next(r['start'] for r in ledger if r['name']=='embed'),commit=entry+syms['nhr_restore']-syms['nhr_source'],
        short_irq_reference=None))+'\n')
    return result,entry
