#!/usr/bin/env python3
"""Check actual placed DSP kernels through the production CF codec and ring.

The transport callback executes DSP instructions, never a host renderer. Full
raw objects/hold/RNG and native PCM are compared against original ARM captures
and the independently qualified complete CF renderer.
"""
import ctypes as C
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools','tools/perky','tools/verify','modules/perky')]
import perky_noise_hat_offload as N
import build_bus as B
import simple_drum_tables as tables
import verify_noise_hat_compact as fixtures
from verify_perky_simple_drum_envelope_exec import HOST,build_host

WORK=ROOT/'out/perky/hybrid/noise-hat-offload'
U16=C.c_uint16;U8=C.c_uint8;I16=C.c_int16;U32=C.c_uint32
class RNG(C.Structure):_fields_=[('low',U32),('high',U32)]
class Tables(C.Structure):_fields_=[('a',C.POINTER(U8)),('b',C.POINTER(U8))]
CALL=C.CFUNCTYPE(C.c_int,C.c_uint,C.POINTER(U16),U32,C.POINTER(U16),C.POINTER(I16))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--wire',action='store_true');args=parser.parse_args()
    WORK.mkdir(parents=True,exist_ok=True);build_host()
    records,ledger,irq,entry,brec,bledger=N.build_program(WORK/'program',ROOT/'out/perky/hybrid/dsp-b-feasibility/multi.asm')
    flat=[0]*0x40000
    for a,w in [*[(a,w) for a,w in brec if a>=0x30000],*records]:flat[a:a+len(w)]=w
    wrapper,syms=B.assemble_syms(f'''pknhat_probe:
 jsrl ${entry:x}
 move #>${N.PCM:x},r1
 move #>0,r0
 move x:>${N.COUNT:x},b
 asl b
 do b,pknhat_capture
 move x:(r1)+,a
 move a1,x:(r0)+
pknhat_capture:
 nop
 rts
''',0x5000,'hat_test')
    flat[0x5000:0x5000+len(wrapper)]=wrapper
    code=WORK/'kernels-test.bin';code.write_bytes(b''.join(v.to_bytes(3,'little') for v in flat))
    host=HOST;call_entry=syms['pknhat_probe']
    if args.wire:
        host=WORK/'rpc_host';vendor=ROOT/'vendor/dsp56300'
        subprocess.run(['c++','-O3','-DNDEBUG','-std=gnu++17','-DASMJIT_STATIC','-DDSP56300_DEBUGGER=0',
            '-I'+str(vendor/'source'),'-I'+str(vendor/'source/asmjit/src'),
            str(ROOT/'tools/harness/perky_cf/noise_hat_rpc_host.cpp'),
            *[str(vendor/('build/source/'+s)) for s in ('dsp56kEmu/libdsp56kEmu.a','dsp56kBase/libdsp56kBase.a','asmjit/libasmjit.a')],
            '-lpthread','-o',str(host)],check=True)
        call_entry=irq
    lib=WORK/'codec.dylib'
    subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I',str(ROOT/'modules/perky'),
        str(ROOT/'modules/perky/cf_noise_hat_offload.c'),'-o',str(lib)],check=True)
    dll=C.CDLL(str(lib));function_args=[C.POINTER(U8),C.POINTER(I16),U32,C.c_uint,
        C.POINTER(Tables),C.POINTER(RNG),C.POINTER(U16)]
    dll.pk_cf_nh_offload.argtypes=function_args;dll.pk_nha_unused_renderer.argtypes=function_args
    env=fixtures.tables(Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'))
    curves=[(U8*len(e)).from_buffer_copy(e) for e in env];cfg=Tables(*curves)
    packed=[tables.pack_u16(struct.unpack('<1025H',e[:2050])) for e in env]
    environment=''.join(f'Y {a:x} '+' '.join(f'{v:x}' for v in w)+'\n' for a,w in zip((0x9a5,0xc51),packed))
    calls=0;worst={0:0,1:0,2:0};errors=[]
    @CALL
    def exchange(mode,state,n,side,pcm):
        nonlocal calls
        try:
            x=[0xa5a5]*(N.SAVED+len(N.REGISTERS)-N.STATE)
            begin,count=(81,28) if mode==1 else (0,81 if mode==0 else 59)
            for i in range(begin,begin+count):x[i]=state[i]
            x[N.COUNT-N.STATE]=n;x[N.MODE-N.STATE]=mode
            for i in range(6):x[N.SCRATCH+0x70-N.STATE+i]=side[i]
            data=WORK/'request.data';data.write_text(f'X {N.STATE:x} '+' '.join(f'{v:x}' for v in x)+'\n'+environment)
            script=WORK/'request.script';script.write_text(' '.join(['0']*12+['-1'])+'\n')
            output=WORK/'response.raw';dump=WORK/'response.state';meter=WORK/'response.cycles'
            command=[str(host),'-code',str(code),'-org','0','-entry',f'{call_entry:x}',
                '-data',str(data),'-script',str(script),'-out',str(output),'-state',str(dump),
                '-statebase',f'{N.STATE:x}','-state-words',str(len(x)),'-frames',str(n),
                '-meter',str(meter),'-cycle-meter','1']
            if args.wire and calls==0:
                negative=subprocess.run(command,env=dict(os.environ,PK_NHA_IRQ_CLOCK='0'),capture_output=True,text=True)
                assert negative.returncode!=0 and 'wire stalled' in negative.stderr,'missing peripheral-clock negative control'
                (WORK/'wire-clock-negative.log').write_text(negative.stderr)
            subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
            result=[int(v,16) for v in dump.read_text().split()][:len(x)]
            for i in range(begin,begin+count):state[i]=result[i]&65535
            for i in range(6):side[i]=result[N.SCRATCH+0x70-N.STATE+i]&65535
            stereo=struct.unpack('<'+'i'*(2*n),output.read_bytes());assert stereo[::2]==stereo[1::2]
            for i,v in enumerate(stereo[::2]):pcm[i]=v
            calls+=1;worst[mode]=max(worst[mode],int(meter.read_text()))
            return 1
        except Exception as e:errors.append(str(e)+' '+str(getattr(e,'stderr',b'')));return 0
    C.c_void_p.in_dll(dll,'pk_nha_exchange').value=C.cast(exchange,C.c_void_p).value
    samples=0;cases=0
    for panel,mode in fixtures.PANEL_TO_FIRMWARE.items():
        for corner in range(3):
            case=fixtures.FIX/f'engine-10-mode-{panel}-corner-{corner}'
            raw=(case/'wrapper-window-after.bin').read_bytes()
            initial=raw[0x2c98:0x2c98+0x160] if mode==2 else raw[:0x2dd8]
            current=(U8*len(initial)).from_buffer_copy(initial);reference=(U8*len(initial)).from_buffer_copy(initial)
            rng0=struct.unpack('<II',(case/'rng-continuation-before.bin').read_bytes())
            rng=RNG(*rng0);ref_rng=RNG(*rng0)
            hold0=struct.unpack('<HH',fixtures.hold_state(case,'before'))
            hold=(U16*2)(*hold0);ref_hold=(U16*2)(*hold0)
            rendered=[]
            # Irregular lengths exercise 17/18 native workload and block cuts.
            remaining=256;block=0
            while remaining:
                n=min(remaining,(1,18,7,17,16,3,19)[block%7]);remaining-=n;block+=1
                got=(I16*n)();want=(I16*n)()
                assert dll.pk_cf_nh_offload(current,got,n,mode,C.byref(cfg),C.byref(rng),hold),errors
                assert dll.pk_nha_unused_renderer(reference,want,n,mode,C.byref(cfg),C.byref(ref_rng),ref_hold)
                assert list(got)==list(want),(panel,corner,block,'PCM')
                assert bytes(current)==bytes(reference),(panel,corner,block,'raw state')
                assert (rng.low,rng.high)==(ref_rng.low,ref_rng.high)
                assert list(hold)==list(ref_hold)
                rendered.extend(got);samples+=n
            arm=list(struct.unpack('<256h',(case/'arm-pcm-continuation.bin').read_bytes()))
            assert rendered==arm,(panel,corner,'original ARM PCM')
            final=(case/'wrapper-window-continuation-after.bin').read_bytes()
            final=final[0x2c98:0x2c98+0x160] if mode==2 else final[:0x2dd8]
            assert bytes(current)==final,(panel,corner,'original ARM raw state')
            assert (rng.low,rng.high)==struct.unpack('<II',(case/'rng-continuation-after.bin').read_bytes())
            if mode<2:assert bytes(hold)==fixtures.hold_state(case,'after')
            cases+=1
    report=dict(status='PASS_IRQ_WIRE_CF_CODEC_RING_ARM_EXACT' if args.wire else 'PASS_PLACED_KERNEL_CF_CODEC_RING_ARM_EXACT',cases=cases,native_samples=samples,
        DSP_calls=calls,maximum_kernel_cycles=worst,irq_entry=irq,render_entry=entry,
        A_program_words=sum(r['length'] for r in ledger),A_program=ledger,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),ROOT/'modules/perky/cf_noise_hat_offload.c',ROOT/'tools/perky/perky_noise_hat_offload.py',ROOT/'tools/harness/perky_cf/noise_hat_rpc_host.cpp')},
        limitations=['Host word pacing excludes ColdFire execution; integrated timing is a separate gate.'])
    (WORK/('WIRE_EXACT.json' if args.wire else 'EXACT.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
