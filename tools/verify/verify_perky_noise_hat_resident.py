#!/usr/bin/env python3
"""Persistent-state source-parser gate against all nine original ARM cases."""
import ctypes as C,json,struct,subprocess,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/perky','tools/build','modules/perky','tools/verify','tools')]
import perky_noise_hat_resident as N
import verify_noise_hat_compact as F
import simple_drum_tables as T
U8=C.c_uint8;U16=C.c_uint16;I16=C.c_int16;U32=C.c_uint32
class RNG(C.Structure):_fields_=[('low',U32),('high',U32)]
class Tables(C.Structure):_fields_=[('a',C.POINTER(U8)),('b',C.POINTER(U8))]
WORK=ROOT/'out/perky/hybrid/noise-hat-resident'
def main():
 out=WORK/'persistent-gate';out.mkdir(parents=True,exist_ok=True)
 vendor=ROOT/'vendor/dsp56300';host=out/'resident_host'
 subprocess.run(['c++','-O3','-DNDEBUG','-std=gnu++17','-DASMJIT_STATIC','-DDSP56300_DEBUGGER=0',
     '-I'+str(vendor/'source'),'-I'+str(vendor/'source/asmjit/src'),str(ROOT/'tools/harness/perky_cf/noise_hat_resident_host.cpp'),
     *[str(vendor/('build/source/'+s)) for s in ('dsp56kEmu/libdsp56kEmu.a','dsp56kBase/libdsp56kBase.a','asmjit/libasmjit.a')],'-lpthread','-o',str(host)],check=True)
 (records,ledger,irq,entry,brec,bledger),source=N.build_program(out/'program',WORK/'probe/multi.asm')
 flat=[0]*0x40000
 for a,w in [*[(a,w) for a,w in brec if a>=0x30000],*records]:flat[a:a+len(w)]=w
 code=out/'program.bin';code.write_bytes(b''.join(v.to_bytes(3,'little') for v in flat))
 lib=out/'codec.dylib';subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I'+str(ROOT/'modules/perky'),str(ROOT/'modules/perky/cf_noise_hat_resident.c'),'-o',str(lib)],check=True)
 dll=C.CDLL(str(lib));dll.pk_nha_codec.argtypes=[C.POINTER(U8),C.c_uint,C.POINTER(U16),C.c_int]
 dll.pk_nha_unused_renderer.argtypes=[C.POINTER(U8),C.POINTER(I16),U32,C.c_uint,C.POINTER(Tables),C.POINTER(RNG),C.POINTER(U16)]
 dll.pk_nhr_delay.argtypes=[C.POINTER(U8),C.POINTER(I16),C.c_uint,C.c_int]
 env=F.tables(Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'));curves=[(U8*len(e)).from_buffer_copy(e) for e in env];tables=Tables(*curves)
 environment=''.join(f'Y {a:x} '+' '.join(f'{v:x}' for v in T.pack_u16(struct.unpack('<1025H',e[:2050])))+'\n' for a,e in zip((0x9a5,0xc51),env))
 rows=[];total=0
 for panel,mode in F.PANEL_TO_FIRMWARE.items():
  for corner in range(3):
   case=F.FIX/f'engine-10-mode-{panel}-corner-{corner}';raw=(case/'wrapper-window-after.bin').read_bytes()
   initial=raw[0x2c98:0x2c98+0x160] if mode==2 else raw[:0x2dd8]
   reference=(U8*len(initial)).from_buffer_copy(initial);ring=(U8*len(initial)).from_buffer_copy(initial)
   rng=RNG(*struct.unpack('<II',(case/'rng-continuation-before.bin').read_bytes()));hold=(U16*2)(*struct.unpack('<HH',F.hold_state(case,'before')))
   compact=(U16*121)();dll.pk_nha_codec(reference,mode,compact,0);state=[0xa5a5]*180
   first,count=(81,28) if mode==1 else (0,81 if mode==0 else 59);base=121 if mode==2 else 0
   for i in range(first,first+count):state[base+i]=compact[i]
   side=[hold[0],hold[1],rng.low&65535,rng.low>>16,rng.high&65535,rng.high>>16]
   data=out/'initial.data';data.write_text('X 3800 '+' '.join(f'{v:x}' for v in state)+'\nX 3970 '+' '.join(f'{v:x}' for v in side)+'\n'+environment)
   lengths=[];remaining=256;i=0
   while remaining:n=min(remaining,(1,18,7,17,16,3,19)[i%7]);lengths.append(n);remaining-=n;i+=1
   req=out/'requests';req.write_text(''.join(f'{n} {mode}\n' for n in lengths));response=out/'response.bin'
   subprocess.run([str(host),'-code',str(code),'-entry',f'{source:x}','-data',str(data),'-requests',str(req),'-out',str(response)],check=True)
   got=response.read_bytes();assert len(got)==len(lengths)*(8+40+360+12)
   pcm=[];worst=0
   for i,n in enumerate(lengths):
    record=got[i*420:(i+1)*420];cycles=struct.unpack_from('<Q',record)[0];worst=max(worst,cycles)
    samples=(I16*n)(*struct.unpack_from('<20h',record,8)[:n]);words=struct.unpack_from('<180H',record,48);sides=struct.unpack_from('<6H',record,408)
    if mode<2:dll.pk_nhr_delay(ring,samples,n,struct.unpack_from('<h',initial,0x2dd4)[0])
    want=(I16*n)();assert dll.pk_nha_unused_renderer(reference,want,n,mode,C.byref(tables),C.byref(rng),hold)
    assert list(samples)==list(want),(panel,corner,i,'PCM')
    dll.pk_nha_codec(reference,mode,compact,0)
    assert all(words[base+k]==compact[k] for k in range(first,first+count)),(panel,corner,i,'resident state')
    assert list(sides)==[hold[0],hold[1],rng.low&65535,rng.low>>16,rng.high&65535,rng.high>>16],(panel,corner,i,'hold/RNG')
    pcm.extend(samples);total+=n
   captured=struct.unpack('<256h',(case/'arm-pcm-continuation.bin').read_bytes())
   assert tuple(pcm)==captured,(panel,corner,'original ARM PCM')
   final=(case/'wrapper-window-continuation-after.bin').read_bytes()
   final=final[0x2c98:0x2c98+0x160] if mode==2 else final[:0x2dd8]
   assert bytes(reference)==final,(panel,corner,'original ARM raw continuation')
   assert (rng.low,rng.high)==struct.unpack('<II',(case/'rng-continuation-after.bin').read_bytes())
   rows.append(dict(panel=panel,firmware_mode=mode,corner=corner,requests=len(lengths),native_samples=256,worst_source_cycles=worst))
 report=dict(status='PASS_PERSISTENT_SOURCE_PARSER_PCM_STATE_HOLD_RNG',cases=rows,native_samples=total,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'tools/harness/perky_cf/noise_hat_resident_host.cpp',ROOT/'tools/perky/perky_noise_hat_resident.py')})
 (WORK/'PERSISTENT_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
