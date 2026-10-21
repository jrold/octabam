#!/usr/bin/env python3
"""Final-upload mixed PCM/Hat parser: all splits, poisoned wire and author PCM."""
import ctypes as C,hashlib,json,os,random,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/verify','tools/perky','modules/perky')]
import verify_perky_noise_hat_taps as g
from source_clock import Clock,coefficient_words
W=Path(os.environ.get('PERKY_FULL_MAP_WORK',str(ROOT/'out/perky/hybrid/full-map'))).resolve()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'mixed-gate';out.mkdir(exist_ok=True);host=W/'persistent-gate/taps_host'
 entry=json.loads((W/'program/resident-symbols.json').read_text())['source_entry'];code=W/'import-gate/code.bin'
 dll=C.CDLL(str(W/'persistent-gate/codec.dylib'));dll.pk_nha_codec.argtypes=[C.POINTER(g.U8),C.c_uint,C.POINTER(g.U16),C.c_int]
 dll.pk_nha_unused_renderer.argtypes=[C.POINTER(g.U8),C.POINTER(g.I16),g.U32,C.c_uint,C.POINTER(g.Tables),C.POINTER(g.RNG),C.POINTER(g.U16)]
 env=g.F.tables(Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'));curves=[(g.U8*len(e)).from_buffer_copy(e) for e in env];tables=g.Tables(*curves)
 environment=''.join(f'Y {a:x} '+' '.join(f'{v:x}' for v in g.T.pack_u16(struct.unpack('<1025H',e[:2050])))+'\n' for a,e in zip((0x9a5,0xc51),env))
 environment+='Y f3f '+' '.join(f'{v:x}' for v in coefficient_words())+'\nX 3a23 '+' '.join(['0']*8+['1','1','3','5','7'])+'\n'
 rnd=random.Random(0x464d5043);total=0;peak=0
 for panel,mode in g.F.PANEL_TO_FIRMWARE.items():
  for corner in range(3):
   case=g.F.FIX/f'engine-10-mode-{panel}-corner-{corner}';raw=(case/'wrapper-window-after.bin').read_bytes()
   initial=raw[0x2c98:0x2c98+0x160] if mode==2 else raw[:0x2dd8];ref=(g.U8*len(initial)).from_buffer_copy(initial)
   rng=g.RNG(*struct.unpack('<II',(case/'rng-continuation-before.bin').read_bytes()));hold=(g.U16*2)(*struct.unpack('<HH',g.F.hold_state(case,'before')))
   compact=(g.U16*121)();dll.pk_nha_codec(ref,mode,compact,0)
   first,count=(81,28) if mode==1 else (0,81 if mode==0 else 59);base=121 if mode==2 else 0
   state=[0xa5a5]*180
   for i in range(first,first+count):state[base+i]=compact[i]
   side=lambda:[hold[0],hold[1],rng.low&65535,rng.low>>16,rng.high&65535,rng.high>>16]
   data=out/'initial.data';data.write_text('X 3800 '+' '.join(f'{v:x}' for v in state)+'\nX 3970 '+' '.join(f'{v:x}' for v in side())+'\n'+environment)
   packets=[];expected=[]
   for frame in range(136):
    split=frame%17;hat_half=(frame//17)%2;packet=[0x4e54,frame+1];pcm=[];writes=[];clock=Clock()
    for half,n in enumerate((split,16-split)):
     external=half!=hat_half
     packet += [n|(1024 if external else (mode<<5)|128),0 if external or mode==2 else struct.unpack_from('<h',initial,0x2dd4)[0]&65535,6]
     for i,v in enumerate(side()):packet += [0x3970+i,v]
     if external:
      values=[rnd.choice((-1048576,-1,0,1,1048544,rnd.randrange(-1048576,1048576))) for _ in range(n)]
      for v in values:packet += [(v>>16)&255,v&65535]
      pcm+=values;continue
     # ALGO changes reset the source clock while preserving original engine
     # history and shared RNG. Every frame includes the other source family.
     native=[];need=clock.needed(n) if n else 0
     for _ in range(need):
      if mode<2:
       index=struct.unpack_from('<H',bytes(ref),0x2982)[0]
       for delay in (573,1201,1538,3139,4804):packet.append(struct.unpack_from('<H',bytes(ref),0x3f8+2*((index-delay)%4805))[0])
      sample=(g.I16*1)();assert dll.pk_nha_unused_renderer(ref,sample,1,mode,C.byref(tables),C.byref(rng),hold);native.append(sample[0])
      if mode<2:
       index=struct.unpack_from('<H',bytes(ref),0x2982)[0];writes.append(struct.unpack_from('<h',bytes(ref),0x3f8+2*index)[0])
     if n:pcm+=clock.render(native,n)
    dll.pk_nha_codec(ref,mode,compact,0)
    expected.append((pcm,writes,list(compact),side(),clock.phase,len(clock.tail),clock.tail[0] if clock.tail else None));packets.append(packet)
    assert len(packet)<=168;peak=max(peak,len(packet))
   request=out/'requests';request.write_text(''.join(' '.join(f'{v:x}' for v in p)+'\n' for p in packets));response=out/'response.bin'
   subprocess.run([str(host),'-code',str(code),'-entry',f'{entry:x}','-data',str(data),'-requests',str(request),'-out',str(response)],check=True)
   blob=response.read_bytes();assert len(blob)==len(packets)*504
   for frame,(pcm,writes,words,sides,phase,have,carry) in enumerate(expected):
    row=blob[frame*504:(frame+1)*504];actual=list(struct.unpack_from('<16i',row,8));assert actual==pcm,(panel,corner,frame,'PCM',actual,pcm)
    mail=struct.unpack_from('<24H',row,72);assert mail[:3]==(0x4e52,frame+1,len(writes));assert [v if v<32768 else v-65536 for v in mail[4:4+len(writes)]]==writes
    actual=struct.unpack_from('<180H',row,120);assert all(actual[base+i]==words[i] for i in range(first,first+count)),(panel,corner,frame,'state')
    assert list(struct.unpack_from('<6H',row,480))==sides,(panel,corner,frame,'side')
    actual=struct.unpack_from('<3I',row,492);assert actual[:2]==(phase,have),(panel,corner,frame,'clock',actual,(phase,have))
    if have:assert actual[2]&65535==carry&65535
   total+=len(expected)
 result=dict(status='PASS_FINAL_UPLOAD_MIXED_AUTHOR_HAT_AND_EXTERNAL_PCM',frames=total,all_splits=list(range(17)),hat_positions=['prefix','suffix'],maximum_packet_halfwords=peak,inputs={str(p):sha(p) for p in (W/'dsp-A.upload.bin',code,W/'program/resident-symbols.json')},source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))})
 (W/'MIXED_DSP_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],total,peak)
if __name__=='__main__':main()
