#!/usr/bin/env python3
"""Persistent poisoned-wire DSP delay/clock proof against the original renderer."""
import ctypes as C,json,struct,subprocess,sys,hashlib,random,itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/perky','tools/build','modules/perky','tools/verify','tools')]
import perky_noise_hat_taps as N
import verify_noise_hat_compact as F
import simple_drum_tables as T
from source_clock import Clock,coefficient_words
U8=C.c_uint8;U16=C.c_uint16;I16=C.c_int16;U32=C.c_uint32
class RNG(C.Structure):_fields_=[('low',U32),('high',U32)]
class Tables(C.Structure):_fields_=[('a',C.POINTER(U8)),('b',C.POINTER(U8))]
WORK=ROOT/'out/perky/hybrid/noise-hat-taps'
def main():
 out=WORK/'persistent-gate';out.mkdir(parents=True,exist_ok=True)
 vendor=ROOT/'vendor/dsp56300';host=out/'taps_host'
 subprocess.run(['c++','-O3','-DNDEBUG','-std=gnu++17','-DASMJIT_STATIC','-DDSP56300_DEBUGGER=0','-I'+str(vendor/'source'),'-I'+str(vendor/'source/asmjit/src'),str(ROOT/'tools/harness/perky_cf/noise_hat_taps_host.cpp'),*[str(vendor/('build/source/'+s)) for s in ('dsp56kEmu/libdsp56kEmu.a','dsp56kBase/libdsp56kBase.a','asmjit/libasmjit.a')],'-lpthread','-o',str(host)],check=True)
 (records,ledger,irq,entry,brec,bledger),source=N.build_program(out/'program',ROOT/'out/perky/hybrid/noise-hat-resident/probe/multi.asm')
 flat=[0]*0x40000
 for a,w in [*[(a,w) for a,w in brec if a>=0x30000],*records]:flat[a:a+len(w)]=w
 code=out/'program.bin';code.write_bytes(b''.join(v.to_bytes(3,'little') for v in flat))
 lib=out/'codec.dylib';subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I'+str(ROOT/'modules/perky'),str(ROOT/'modules/perky/cf_noise_hat_taps.c'),'-o',str(lib)],check=True)
 dll=C.CDLL(str(lib));dll.pk_nha_codec.argtypes=[C.POINTER(U8),C.c_uint,C.POINTER(U16),C.c_int]
 dll.pk_nha_unused_renderer.argtypes=[C.POINTER(U8),C.POINTER(I16),U32,C.c_uint,C.POINTER(Tables),C.POINTER(RNG),C.POINTER(U16)]
 env=F.tables(Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'));curves=[(U8*len(e)).from_buffer_copy(e) for e in env];tables=Tables(*curves)
 environment=''.join(f'Y {a:x} '+' '.join(f'{v:x}' for v in T.pack_u16(struct.unpack('<1025H',e[:2050])))+'\n' for a,e in zip((0x9a5,0xc51),env))
 environment+='Y f3f '+' '.join(f'{v:x}' for v in coefficient_words())+'\nX 3a23 '+' '.join(['0']*8+['1','1','3','5','7'])+'\n'
 rows=[]
 for panel,mode in F.PANEL_TO_FIRMWARE.items():
  for corner in range(3):
   case=F.FIX/f'engine-10-mode-{panel}-corner-{corner}';raw=(case/'wrapper-window-after.bin').read_bytes()
   initial=raw[0x2c98:0x2c98+0x160] if mode==2 else raw[:0x2dd8]
   reference=(U8*len(initial)).from_buffer_copy(initial)
   rng=RNG(*struct.unpack('<II',(case/'rng-continuation-before.bin').read_bytes()));hold=(U16*2)(*struct.unpack('<HH',F.hold_state(case,'before')))
   compact=(U16*121)();dll.pk_nha_codec(reference,mode,compact,0);state=[0xa5a5]*180
   first,count=(81,28) if mode==1 else (0,81 if mode==0 else 59);base=121 if mode==2 else 0
   for i in range(first,first+count):state[base+i]=compact[i]
   side=[hold[0],hold[1],rng.low&65535,rng.low>>16,rng.high&65535,rng.high>>16]
   data=out/'initial.data';data.write_text('X 3800 '+' '.join(f'{v:x}' for v in state)+'\nX 3970 '+' '.join(f'{v:x}' for v in side)+'\n'+environment)
   clock=Clock();packets=[];expected=[];native_all=[]
   # 80 complete source frames: all split positions, > shortest feedback tap.
   # A separate CF ring receives feedback three frames later, like stock DMA.
   ring=bytearray(initial);pending=[];issued=committed=0;logical=struct.unpack_from('<H',ring,0x2982)[0] if mode<2 else 0;peak=0
   for frame in range(80):
    if len(pending)>=3:
     for at,value in pending.pop(0):struct.pack_into('<h',ring,0x3f8+2*at,value);committed+=1
    packet=[0x4e54,frame+1];sourcepcm=[];writes=[];frame_writes=[]
    split=frame%17
    for n in (split,16-split):
     need=clock.needed(n) if n else 0
     mix=struct.unpack_from('<h',initial,0x2dd4)[0] if mode<2 else 0
     velocity=0x3801 if mode==0 else 0x3851 if mode==1 else 0x3879
     packet += [n|(mode<<5),mix&65535,1,velocity,state[base+first] if mode==1 else state[base]]
     # Use the actual unchanged velocity, not the first compact word.
     packet[-1]=int(compact[81 if mode==1 else 1 if mode==0 else 0])
     native=[]
     for k in range(need):
      if mode<2:
       index=struct.unpack_from('<H',bytes(reference),0x2982)[0]
       assert index==logical
       peak=max(peak,issued-committed)
       for delay in (573,1201,1538,3139,4804):
        at=(logical-delay)%4805
        got=struct.unpack_from('<H',ring,0x3f8+2*at)[0];want=struct.unpack_from('<H',bytes(reference),0x3f8+2*at)[0]
        assert got==want,('uncommitted tap dependency',frame,k,delay)
        assert issued-committed<delay
        packet.append(got)
      sample=(I16*1)();assert dll.pk_nha_unused_renderer(reference,sample,1,mode,C.byref(tables),C.byref(rng),hold)
      native.append(sample[0]);native_all.append(sample[0])
      if mode<2:
       logical=(logical+1)%4805;value=struct.unpack_from('<h',bytes(reference),0x3f8+2*logical)[0]
       writes.append(value);frame_writes.append((logical,value));issued+=1
     if n:sourcepcm+=clock.render(native,n)
    pending.append(frame_writes)
    dll.pk_nha_codec(reference,mode,compact,0)
    expected.append((sourcepcm,writes,list(compact),[hold[0],hold[1],rng.low&65535,rng.low>>16,rng.high&65535,rng.high>>16],clock.phase,len(clock.tail),clock.tail[0] if clock.tail else None))
    assert len(packet)<=168,(panel,corner,frame,len(packet))
    packets.append(packet)
   # Original captured continuation remains the native PCM oracle.
   assert native_all[:256]==list(struct.unpack('<256h',(case/'arm-pcm-continuation.bin').read_bytes()))
   req=out/'requests';req.write_text(''.join(' '.join(f'{v:x}' for v in p)+'\n' for p in packets));response=out/'response.bin'
   subprocess.run([str(host),'-code',str(code),'-entry',f'{source:x}','-data',str(data),'-requests',str(req),'-out',str(response)],check=True)
   got=response.read_bytes();assert len(got)==len(packets)*504,(len(got),len(packets)*504)
   for i,e in enumerate(expected):
    record=got[i*504:(i+1)*504];pcm=struct.unpack_from('<16i',record,8);mail=struct.unpack_from('<24H',record,72);words=struct.unpack_from('<180H',record,120);sides=struct.unpack_from('<6H',record,480);phase,have,carry=struct.unpack_from('<3I',record,492)
    assert list(pcm)==e[0],(panel,corner,i,'PCM',list(pcm),e[0])
    assert mail[:3]==(0x4e52,i+1,len(e[1]))
    assert [v if v<32768 else v-65536 for v in mail[4:4+len(e[1])]]==e[1],(panel,corner,i,'feedback')
    assert all(words[base+k]==e[2][k] for k in range(first,first+count)),(panel,corner,i,'state')
    assert list(sides)==e[3],(panel,corner,i,'hold/RNG')
    assert (phase,have)==e[4:6]
    if have:assert (carry&65535)==(e[6]&65535)
   rows.append(dict(panel=panel,corner=corner,frames=len(packets),native_samples=len(native_all),max_packet_halfwords=max(map(len,packets)),peak_pending_writes=peak))
 # Exercise the actual DSP delay body at saturation and wrap boundaries.
 randomizer=random.Random(0x4e54)
 vectors=[(x,m,*taps) for x in (-32768,-32767,0,32767) for m in (0,1,2048,4095) for taps in itertools.product((-32768,32767),repeat=5)]
 vectors += [tuple([randomizer.randrange(-32768,32768),randomizer.randrange(4096)]+[randomizer.randrange(-32768,32768) for _ in range(5)]) for _ in range(2048)]
 req=out/'arithmetic.requests';req.write_text(''.join(' '.join(f'{v&65535:x}' for v in row)+'\n' for row in vectors));response=out/'arithmetic.response'
 delay=next(r['start'] for r in ledger if r['name']=='delay')
 subprocess.run([str(host),'-code',str(code),'-entry',f'{delay:x}','-data',str(data),'-requests',str(req),'-out',str(response),'-kind','arithmetic'],check=True)
 result=response.read_bytes();assert len(result)==len(vectors)*504
 for i,row in enumerate(vectors):
  x,m,*taps=row;stage=x
  for g,tap in zip((1,1,3,5,7),taps):stage=max(-32767,min(32767,(stage*(g-16)+g*tap)>>4))
  pcm=((x*(4095-m)+m*((stage*5)>>1))>>12)&65535
  actual=struct.unpack_from('<i',result,504*i+8)[0]&65535;feedback=struct.unpack_from('<H',result,504*i+72+8)[0]
  assert actual==pcm and feedback==(stage&65535),(i,row,actual,pcm,feedback,stage)
 report=dict(status='PASS_CURRENT_SOURCE_PCM_FEEDBACK_STATE_CLOCK',cases=rows,frames=sum(r['frames'] for r in rows),arithmetic_vectors=len(vectors),negative_boundary_test='actual production guard accepts 0/52/572 and refuses 573/574/UINT32_MAX',source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'tools/harness/perky_cf/noise_hat_taps_host.cpp',ROOT/'tools/perky/perky_noise_hat_taps.py')})
 guard=out/'ring-guard.c';guard.write_text('#include "noise_hat_taps_ring.h"\nint guard(unsigned p){return pk_nht_taps_ready(p); }\n')
 guardlib=out/'ring-guard.dylib';subprocess.run(['cc','-O3','-shared','-I'+str(ROOT/'modules/perky'),str(guard),'-o',str(guardlib)],check=True)
 g=C.CDLL(str(guardlib)).guard;g.argtypes=[U32]
 assert [g(p) for p in (0,52,572,573,574,0xffffffff)]==[1,1,1,0,0,0]
 (WORK/'PERSISTENT_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
