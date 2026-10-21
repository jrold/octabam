#!/usr/bin/env python3
"""Original ARM continuations and full raw state vs stage-transposed renderer."""
import ctypes as C,hashlib,json,random,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'out/perky/hybrid/noise-hat-handoff'
sys.path[:0]=[str(ROOT/p) for p in ('tools/verify','tools/perky','modules/perky','tools')]
import verify_noise_hat_compact as F
from verify_perky_noise_hat_handoff_inner import U8,U16,I16,U32,RNG,Tables
from generate_noise_hat_handoff_renderer import generate
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'renderer-gate';out.mkdir(exist_ok=True);source=W/'noise-hat-transposed.c';mapping=generate(source)
 obj=out/'original.o';subprocess.run(['cc','-O3','-fPIC','-Dpk_cf_nh_render=nhb_original_renderer','-I'+str(ROOT/'modules/perky'),'-c',str(ROOT/'modules/perky/cf_noise_hat.c'),'-o',str(obj)],check=True)
 libpath=out/'oracle.dylib';subprocess.run(['cc','-O3','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(source),str(obj),'-o',str(libpath)],check=True)
 lib=C.CDLL(str(libpath));arg=[C.POINTER(U8),C.POINTER(I16),U32,C.c_uint,C.POINTER(Tables),C.POINTER(RNG),C.POINTER(U16)]
 original=lib.nhb_original_renderer;candidate=lib.pk_cf_nh_render;original.argtypes=candidate.argtypes=arg
 firmware=Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img');env=F.tables(firmware);curves=[(U8*len(e)).from_buffer_copy(e) for e in env];tables=Tables(*curves);rng=random.Random(0x4e485254);rows=[];inputs={str(firmware):sha(firmware)}
 for panel,mode in F.PANEL_TO_FIRMWARE.items():
  for corner in range(3):
   case=F.FIX/f'engine-10-mode-{panel}-corner-{corner}'
   raw=(case/'wrapper-window-after.bin').read_bytes();initial=raw[0x2c98:0x2c98+0x160] if mode==2 else raw[:0x2dd8]
   a=(U8*len(initial)).from_buffer_copy(initial);b=(U8*len(initial)).from_buffer_copy(initial)
   seed=struct.unpack('<II',(case/'rng-continuation-before.bin').read_bytes());ra=RNG(*seed);rb=RNG(*seed);ha=(U16*2)(*struct.unpack('<HH',F.hold_state(case,'before')));hb=(U16*2)(*ha);samples=[];calls=0
   for block in range(160):
    n=block%25 if block<25 else rng.randrange(25);want=(I16*max(1,n))();got=(I16*max(1,n))()
    assert original(a,want,n,mode,C.byref(tables),C.byref(ra),ha)==candidate(b,got,n,mode,C.byref(tables),C.byref(rb),hb)==1
    assert list(want)==list(got) and bytes(a)==bytes(b) and bytes(ra)==bytes(rb) and list(ha)==list(hb),(panel,corner,block,n)
    samples.extend(list(got)[:n]);calls+=1
   assert samples[:256]==list(struct.unpack('<256h',(case/'arm-pcm-continuation.bin').read_bytes())),(panel,corner,'ARM PCM')
   for p in case.iterdir():
    if p.is_file():inputs[str(p)]=sha(p)
   rows.append(dict(panel=panel,corner=corner,calls=calls,native_samples=len(samples)))
 report=dict(status='PASS_ORIGINAL_ARM_PCM_FULL_RAW_STATE_RING_RNG_HOLD',cases=rows,calls=sum(r['calls'] for r in rows),native_samples=sum(r['native_samples'] for r in rows),mapping=mapping,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/perky/generate_noise_hat_handoff_renderer.py',ROOT/'modules/perky/cf_noise_hat.c',source)},input_sha256=inputs,oracle_sha256=sha(libpath))
 (W/'RENDERER_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],calls=report['calls'],native_samples=report['native_samples'])))
if __name__=='__main__':main()
