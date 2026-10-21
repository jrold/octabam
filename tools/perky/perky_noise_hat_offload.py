"""Opt-in DSP-A Noise Hat inner service, reusing original qualified kernels.

ColdFire owns the authentic ring and raw objects. The service exchanges the
active compact limb, hold/RNG and native PCM. No extra DSP ring is allocated.
"""
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools','tools/build','tools/perky','modules/perky','tools/verify')]
os.environ.setdefault('REMIX','perky-machine')
import all_fx_layout as L
import build_bus as B
import perky_dsp_b_specialization as S
import perky_emit_shards as E
from build_noise_tone_synth_source import force_long_local_jsr,relativize_local_conditionals
from perky_noise_hat_dsp_support import audit_source,audit_binary

STATE=0x3800
SCRATCH=0x3900
PCM=0x3980
COUNT=0x39b0
MODE=0x39b1
PENDING=0x39b2
SAVED=0x39c0
VECTOR=0x2c
REGISTERS=('a2','a1','a0','b2','b1','b0','x0','x1','y0','y1',
           *('r'+str(i) for i in range(8)),*('n'+str(i) for i in range(8)),
           *('m'+str(i) for i in range(8)),'la','lc')


def service():
    save=''.join(f' move {r},x:>${SAVED+i:x}\n' for i,r in enumerate(REGISTERS))
    restore=''.join(f' move x:>${SAVED+i:x},{r}\n' for i,r in reversed(list(enumerate(REGISTERS))))
    return {
      'irq': 'pknha_interrupt:\n'+save+'''
 move #>$ffffff,m0
 move #>$ffffff,m1
 move #>$ffffff,m2
 move #>$ffffff,m3
 move #>$ffffff,m4
 move #>$ffffff,m5
 move #>$ffffff,m6
 move #>$ffffff,m7
 jsrl pknha_receive
 jsrl pknha_render
 jsrl pknha_send
'''+restore+' rti\n',
      'wire': f'''pknha_receive:
 jsrl pknha_rx
 move a1,x:>${MODE:x}
 jsrl pknha_rx
 move a1,x:>${COUNT:x}
 jsrl pknha_rx
 move a1,x:>${PENDING:x}
 jsrl pknha_rx
 move a1,x:>${PENDING+1:x}
 jsrl pknha_active
 do b,pknha_load_done
 jsrl pknha_rx
 move a1,x:(r1)+
pknha_load_done:
 nop
 move #>${SCRATCH+0x70:x},r1
 do #>6,pknha_side_load
 jsrl pknha_rx
 move a1,x:(r1)+
pknha_side_load:
 nop
 rts
pknha_send:
 move x:>${MODE:x},a
 asl #>5,a,a
 add #>$4e4800,a
 move x:>${COUNT:x},x0
 add x0,a
 jsrl pknha_tx
 jsrl pknha_active
 do b,pknha_store_done
 move x:(r1)+,a
 jsrl pknha_tx
pknha_store_done:
 nop
 move #>${SCRATCH+0x70:x},r1
 do #>6,pknha_side_store
 move x:(r1)+,a
 jsrl pknha_tx
pknha_side_store:
 nop
 move #>${PCM:x},r1
 move x:>${COUNT:x},b
 do b,pknha_pcm_store
 move x:(r1)+,a
 move (r1)+
 jsrl pknha_tx
pknha_pcm_store:
 nop
 move #>$4e4844,a
 jsrl pknha_tx
 move x:>${PENDING:x},a
 tst a
 beq pknha_wire_finished
 move x:>${PENDING+1:x},a
 jsrl pknha_tx
pknha_wire_finished:
 rts
pknha_active:
 move #>${STATE:x},r1
 move #>81,b
 move x:>${MODE:x},a
 tst a
 beq pknha_address_done
 cmp #>2,a
 beq pknha_pulse_address
 move #>${STATE+81:x},r1
 move #>28,b
 bra pknha_address_done
pknha_pulse_address:
 move #>59,b
pknha_address_done:
 rts
pknha_rx:
 jclr #0,x:<<$ffffc3,pknha_rx
 movep x:<<$ffffc6,a1
 rts
pknha_tx:
 jclr #1,x:<<$ffffc3,pknha_tx
 movep a1,x:<<$ffffc7
 rts
''',
      'render': f'''pknha_render:
 move #>${STATE:x},r6
 move #>${SCRATCH:x},r5
 move #>${PCM:x},r0
 move x:>${COUNT:x},n7
 move x:>${MODE:x},a
 cmp #>2,a
 beq pknha_pulse_go
 move r6,x:>${SCRATCH+0x76:x}
 do n7,pknha_classic_done
 move x:>${SCRATCH+0x76:x},r6
 move x:>${MODE:x},a
 tst a
 bne pknha_white_go
 jsrl pk_noise_hat_classic_inner0
 bra pknha_inner_done
pknha_white_go:
 jsrl pk_noise_hat_classic_inner1
pknha_inner_done:
 move a1,x:(r0)+
 move a1,x:(r0)+
pknha_classic_done:
 nop
 rts
pknha_pulse_go:
 jsrl pk_noise_hat_pulse_voice
 rts
'''}


def sources():
    parts=service()
    for n in ('noise_hat_classic_mode0','noise_hat_classic_mode1','noise_hat_pulse_voice',
              'noise_hat_phase','noise_hat_filter','noise_hat_envelope'):
        parts[n]=(ROOT/'modules/perky'/(n+'.asm')).read_text()
    math=(ROOT/'modules/perky/noise_tone_math.asm').read_text()
    parts['add']=math[math.index('pk_u32_add:'):math.index('pk_u32_sub:')]
    parts['multiply']=math[math.index('pk_u32_mul_low:'):math.index('pk_mul16:')]
    return {n:force_long_local_jsr(relativize_local_conditionals(t)) for n,t in parts.items()}


def build_program(work,oscillator_asm):
    """Fit A's service beside the specialized single B oscillator portfolio."""
    work.mkdir(parents=True,exist_ok=True)
    bp,_,bd,bfinal,bsyms=S.emit(oscillator_asm,'B')
    records,ledger,_=S.plan(oscillator_asm,'B')
    records=[(a,w) for a,w in records if a!=S.SWAP_ORG]
    ledger=[r for r in ledger if r['name']!='experimental context exchange']
    external=bfinal(bsyms['pk_noise_step'])
    assert external>=0x30000,'shared helper cannot call private B code'
    parts=sources()
    parts={n:re.sub(r'\bpk_noise_step\b',f'${external:06x}',t) for n,t in parts.items()}
    source=''.join(f'; ===== BEGIN {n} =====\n{t}\n; ===== END {n} =====\n' for n,t in parts.items())
    audit_source(source)
    mono,syms=B.assemble_syms(source,0x1000,'noise_hat_A',strict_layout=True)
    pieces=E.slice_pieces(source,len(mono),syms)
    spans=[(a,b-48 if i==0 else b) for i,(a,b) in enumerate(L.local_p_spans('A'))]
    for lo,hi in L.SAFE_SHARED_P_SPANS:
        cursor=lo
        for a,w in sorted(records):
            if a<lo or a>=hi:continue
            if cursor<a:spans.append((cursor,a))
            cursor=a+len(w)
        if cursor<hi:spans.append((cursor,hi))
    placed=L.place_program_shards_two_space([L.ProgramShard(n,b-a) for n,a,b,_,_ in pieces],spans)
    destinations={p.name:p.start for p in placed}
    def final(addr):
        for n,a,b,_,_ in pieces:
            if a<=addr<b:return destinations[n]+addr-a
        return addr
    outputs=[];allocation=[]
    for n,a,b,t,_ in pieces:
        rewritten=E.rewrite(t,syms,final)
        words,labels=B.assemble_syms(rewritten,destinations[n],'hat_'+n,strict_layout=True)
        assert len(words)==b-a,(n,len(words),b-a)
        binary=work/(n+'.bin');binary.write_bytes(b''.join(w.to_bytes(3,'little') for w in words))
        # build_bus has a mnemonic round-trip audit for its assembler output;
        # retain a separate disassembly at every final PC too.
        import subprocess
        dis=subprocess.check_output([str(B.DISASM),'-in',str(binary),'-pc',f'{destinations[n]:x}','-le','-nops'],text=True)
        (work/(n+'.dis')).write_text(dis)
        outputs.append((destinations[n],words))
        allocation.append(dict(name=n,start=destinations[n],length=len(words)))
    (work/'service.asm').write_text(source)
    return outputs,allocation,final(syms['pknha_interrupt']),final(syms['pknha_render']),records,ledger
