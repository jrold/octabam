#!/usr/bin/env python3
"""Full raw-state differential for batched Noise Hat controls and continued PCM."""
import ctypes as C,hashlib,json,random,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-fast'
U8=C.c_uint8;U16=C.c_uint16;U32=C.c_uint32;I16=C.c_int16
class RNG(C.Structure):_fields_=[('low',U32),('high',U32)]
class Tables(C.Structure):_fields_=[('a',C.POINTER(U8)),('b',C.POINTER(U8))]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=WORK/'controls-gate';out.mkdir(parents=True,exist_ok=True)
 wrapper=ROOT/'tools/harness/perky_cf/noise_hat_controls_oracle.c';libs=[]
 for tag,source in (('original',ROOT/'modules/perky/cf_perky4.c'),('batched',WORK/'cf_perky4_settle.c')):
  path=out/(tag+'.c');path.write_text(wrapper.read_text().replace('#include "cf_perky4.c"','#include "'+str(source)+'"'))
  lib=out/(tag+'.dylib');subprocess.run(['cc','-O3','-std=c11','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(path),str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),'-o',str(lib)],check=True)
  d=C.CDLL(str(lib));d.nhf_reference.argtypes=[C.POINTER(U8),C.POINTER(U32),C.POINTER(U8),C.POINTER(U8),U32,U32,U32,C.c_int,C.POINTER(U8),C.POINTER(U8)];libs.append(d)
 assets=ROOT/'out/perky/hybrid/cf-placement/assets'
 pitch=(U8*8192).from_buffer_copy((assets/'pitch.bin').read_bytes());chrom=(U8*24).from_buffer_copy((assets/'chromatic.bin').read_bytes())
 env=[(U8*len(v)).from_buffer_copy(v) for v in [(assets/'envelope1.bin').read_bytes(),(assets/'envelope2.bin').read_bytes()]];tables=Tables(*env)
 renderer=C.CDLL(str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'));renderer.pk_cf_nh_render.argtypes=[C.POINTER(U8),C.POINTER(I16),U32,U32,C.POINTER(Tables),C.POINTER(RNG),C.POINTER(U16)]
 rand=random.Random(0x4e4846);calls=samples=0;cases=[]
 for case in sorted((ROOT/'out/perky/engine-fixtures').glob('engine-10-mode-*-corner-*')):
  if not (case/'wrapper-window-after.bin').exists():continue
  initial=(case/'wrapper-window-after.bin').read_bytes()[:0x2dd8]
  states=[(U8*len(initial)).from_buffer_copy(initial) for _ in libs];targets=[(U32*4)() for _ in libs];tails=[(U8*6)() for _ in libs]
  rngs=[RNG(1,0),RNG(1,0)];holds=[(U16*2)(),(U16*2)()]
  for step in range(192):
   mode=(step//7)%3;raw=(U8*4)(*[rand.randrange(128) for _ in range(4)]) if step%4 else (U8*4)(0,127,0,127)
   if step%9==0:raw=(U8*4)(*tails[0][:4]) # unchanged controls are part of the stream
   vel=(0,1,127,255)[step%4];note=(0,45,63,127,255)[step%5];trig=(step%3==0)
   # Exercise nonstandard but in-bounds smoother/attack/config words. Both
   # full states receive exactly the same mutation before the next update.
   if step%11==0:
    for b in (0,0xc4,0x318,0x2c98):
     for k in range(4):
      value=rand.getrandbits(32) if step%22==0 else rand.randrange(4096)
      packed=struct.pack('<I',value)
      for s in states:
       for j,v in enumerate(packed):s[b+0x1c+4*k+j]=v
     for at in (0x0a,0x8c,0x8e,0x90,0x92):
      value=rand.randrange(65536);packed=struct.pack('<H',value)
      for s in states:
       for j,v in enumerate(packed):s[b+at+j]=v
   for d,s,t,tail in zip(libs,states,targets,tails):d.nhf_reference(s,t,tail,raw,mode,vel,note,trig,pitch,chrom)
   assert bytes(states[0])==bytes(states[1]),(case.name,step,'raw control state',next(i for i,(a,b) in enumerate(zip(states[0],states[1])) if a!=b))
   assert list(targets[0])==list(targets[1]) and bytes(tails[0])==bytes(tails[1]),(case.name,step,'control history')
   n=(0,1,7,16,19)[step%5];outputs=[]
   for s,r,h in zip(states,rngs,holds):
    pcm=(I16*max(1,n))();fw=(1,0,2)[mode];ptr=C.cast(C.byref(s,0x2c98),C.POINTER(U8)) if fw==2 else s
    assert renderer.pk_cf_nh_render(ptr,pcm,n,fw,C.byref(tables),C.byref(r),h)
    outputs.append(list(pcm)[:n])
   assert outputs[0]==outputs[1] and bytes(states[0])==bytes(states[1]),(case.name,step,'PCM/dynamic state/ring')
   assert bytes(rngs[0])==bytes(rngs[1]) and bytes(holds[0])==bytes(holds[1])
   calls+=1;samples+=n
  cases.append(case.name)
 assert len(cases)==15
 result=dict(status='PASS_RAW_CONTROLS_PCM_STATE_RING_RNG',cases=cases,control_calls=calls,native_samples=samples,
  source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),wrapper,ROOT/'modules/perky/cf_noise_hat_controls.h',ROOT/'modules/perky/cf_perky4.c',WORK/'cf_perky4_settle.c',ROOT/'tools/perky/build_noise_hat_fast_probe.py')},
  scope='Complete 11736-byte object, control history, PCM, dynamic state/ring/hold/RNG; repeated triggers, mode/note changes, arbitrary 32-bit smoother values and 16-bit envelope configs. Target execution is checked separately by the live observer.')
 (WORK/'CONTROLS_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
