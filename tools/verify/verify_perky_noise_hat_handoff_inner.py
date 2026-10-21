#!/usr/bin/env python3
"""Original-author native stream vs inner shadow and one retained delay sample."""
import ctypes as C,hashlib,json,random,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/verify','tools/perky','tools/build','modules/perky','tools')]
import verify_noise_hat_compact as F
W=ROOT/'out/perky/hybrid/noise-hat-handoff'
U8=C.c_uint8;U16=C.c_uint16;I16=C.c_int16;U32=C.c_uint32
class RNG(C.Structure):_fields_=[('low',U32),('high',U32)]
class Tables(C.Structure):_fields_=[('a',C.POINTER(U8)),('b',C.POINTER(U8))]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'inner-gate';out.mkdir(exist_ok=True);wrapper=out/'carry.c';wrapper.write_text('#include "noise_hat_handoff_carry.h"\nint16_t carry(int16_t x,int mix,const uint16_t*t){return pk_nhb_delay_carry(x,mix,t);}\n')
 cmd=['cc','-O3','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(ROOT/'modules/perky/cf_noise_hat.c'),str(W/'noise-hat-inner.c'),str(ROOT/'modules/perky/cf_noise_hat_offload.c'),str(wrapper),'-o',str(out/'oracle.dylib')]
 subprocess.run(cmd,check=True);lib=C.CDLL(str(out/'oracle.dylib'));arg=[C.POINTER(U8),C.POINTER(I16),U32,C.c_uint,C.POINTER(Tables),C.POINTER(RNG),C.POINTER(U16)]
 full=lib.pk_cf_nh_render;inner=lib.pk_nhb_inner_renderer;full.argtypes=inner.argtypes=arg
 lib.carry.argtypes=[I16,C.c_int,C.POINTER(U16)];lib.carry.restype=I16;lib.pk_nha_codec.argtypes=[C.POINTER(U8),C.c_uint,C.POINTER(U16),C.c_int]
 env=F.tables(Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'));curves=[(U8*len(e)).from_buffer_copy(e) for e in env];tables=Tables(*curves);rows=[];rr=random.Random(0x4e4842)
 for panel,mode in F.PANEL_TO_FIRMWARE.items():
  for corner in range(3):
   case=F.FIX/f'engine-10-mode-{panel}-corner-{corner}';raw=(case/'wrapper-window-after.bin').read_bytes();initial=raw[0x2c98:0x2c98+0x160] if mode==2 else raw[:0x2dd8]
   a=(U8*len(initial)).from_buffer_copy(initial);b=(U8*len(initial)).from_buffer_copy(initial)
   seed=struct.unpack('<II',(case/'rng-continuation-before.bin').read_bytes());ra=RNG(*seed);rb=RNG(*seed);ha=(U16*2)(*struct.unpack('<HH',F.hold_state(case,'before')));hb=(U16*2)(*ha);samples=[]
   for block in range(80):
    n=rr.randrange(1,21);taps=[];want=[]
    for i in range(n):
     if mode<2:
      index=struct.unpack_from('<H',bytes(a),0x2982)[0];taps.append((U16*5)(*[struct.unpack_from('<H',bytes(a),0x3f8+2*((index-d)%4805))[0] for d in (573,1201,1538,3139,4804)]))
     p=(I16*1)();assert full(a,p,1,mode,C.byref(tables),C.byref(ra),ha);want.append(p[0]);samples.append(p[0])
    got=(I16*n)();assert inner(b,got,n,mode,C.byref(tables),C.byref(rb),hb)
    mix=struct.unpack_from('<h',initial,0x2dd4)[0] if mode<2 else 0
    post=[lib.carry(got[i],mix,taps[i]) if mode<2 and not initial[0xb8] else got[i] for i in range(n)]
    assert post==want,(panel,corner,block,'PCM')
    wa=(U16*121)();wb=(U16*121)();lib.pk_nha_codec(a,mode,wa,0);lib.pk_nha_codec(b,mode,wb,0)
    assert list(wa)==list(wb) and bytes(ra)==bytes(rb) and list(ha)==list(hb),(panel,corner,block,'state/RNG/hold')
   assert samples[:256]==list(struct.unpack('<256h',(case/'arm-pcm-continuation.bin').read_bytes()))
   rows.append(dict(panel=panel,corner=corner,blocks=80,native_samples=len(samples)))
 vectors=0
 for _ in range(8192):
  x=rr.randrange(-32768,32768);mix=rr.randrange(4096);taps=[rr.randrange(-32768,32768) for _ in range(5)];stage=x
  for g,t in zip((1,1,3,5,7),taps):stage=max(-32767,min(32767,(stage*(g-16)+g*t)>>4))
  expected=((x*(4095-mix)+mix*((stage*5)>>1))>>12)&65535
  assert lib.carry(x,mix,(U16*5)(*[t&65535 for t in taps]))&65535==expected;vectors+=1
 report=dict(status='PASS_AUTHOR_PCM_STATE_RNG_HOLD_AND_RETAINED_CARRY',cases=rows,native_samples=sum(r['native_samples'] for r in rows),arithmetic_vectors=vectors,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'modules/perky/noise_hat_handoff_carry.h',ROOT/'modules/perky/cf_noise_hat.c',W/'noise-hat-inner.c')},command=cmd)
 (W/'INNER_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
