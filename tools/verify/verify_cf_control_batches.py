#!/usr/bin/env python3
"""Differential prepare-path proof for candidate control smoother batching."""
import argparse,ctypes as C,json,random,subprocess,sys
from pathlib import Path
import calibrate_perky_hybrid_budget as c
sys.path.insert(0,str(c.ROOT/'tools/perky'))
import generate_cf_control_batches as batches

WRAPPER=r'''
#include <string.h>
size_t cb_size(void){return sizeof(placement_engine)+sizeof(placement_ah_state)+sizeof(placement_ah_control)+sizeof(placement_clocks)+sizeof(placement_ah_hold)+sizeof(placement_ah_initialized);}
void cb_snapshot(uint8_t*out){
 memcpy(out,&placement_engine,sizeof(placement_engine));
 memset(out+offsetof(pk4_engine,assets),0,sizeof(placement_engine.assets));out+=sizeof(placement_engine);
#define CB_APPEND(value) memcpy(out,&value,sizeof(value));out+=sizeof(value)
 CB_APPEND(placement_ah_state);CB_APPEND(placement_ah_control);CB_APPEND(placement_clocks);CB_APPEND(placement_ah_hold);CB_APPEND(placement_ah_initialized);
#undef CB_APPEND
}
void cb_poison(unsigned tr,unsigned algo,uint32_t seed){
 pk4_track*t=&placement_engine.tracks[tr];uint8_t*s=0;pk4_control*control=0;
 switch(algo){
 case 0:s=t->fold1;control=&t->fold1_ctl;break;
 case 1:s=t->fold2;control=&t->fold2_ctl;break;
 case 6:s=t->sd;control=&t->sd_ctl;break;
 case 7:s=t->cd;control=&t->cd_ctl;break;
 case 8:s=t->slap;control=&t->slap_ctl;break;
 case 10:s=placement_ah_state;control=&placement_ah_control;break;
 default:return;
 }
 for(unsigned i=0;i<4;i++){seed=1664525u*seed+1013904223u;w32(s,0x1c+4*i,seed);seed=1664525u*seed+1013904223u;control->targets[i]=seed;}
}
unsigned cb_smoother_proof(void){
 uint8_t reference[128],candidate[128];uint32_t targets[4],seed=0x7fffffff;unsigned cases=0;
 for(unsigned n=14;n<=16;n++)for(int delta=-4095;delta<=4095;delta++){
  memset(reference,0xa5,sizeof(reference));memcpy(candidate,reference,sizeof(candidate));
  for(unsigned lane=0;lane<4;lane++){uint32_t value=delta>=0?(uint32_t)delta:0;targets[lane]=delta<0?(uint32_t)-delta:0;w32(reference,0x1c+4*lane,value);w32(candidate,0x1c+4*lane,value);}
  for(unsigned i=0;i<n;i++)common_smooth_only(reference,targets);common_smooth_many(candidate,targets,n);
  if(memcmp(reference,candidate,sizeof(reference)))return 0;cases++;
 }
 for(unsigned n=14;n<=16;n++)for(unsigned test=0;test<10000;test++){
  memset(reference,0x5a,sizeof(reference));memcpy(candidate,reference,sizeof(candidate));
  for(unsigned lane=0;lane<4;lane++){seed=1664525u*seed+1013904223u;uint32_t value=seed;seed=1664525u*seed+1013904223u;targets[lane]=seed;w32(reference,0x1c+4*lane,value);w32(candidate,0x1c+4*lane,value);}
  for(unsigned i=0;i<n;i++)common_smooth_only(reference,targets);common_smooth_many(candidate,targets,n);
  if(memcmp(reference,candidate,sizeof(reference)))return 0;cases++;
 }
 return cases;
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    baseline=args.baseline.resolve();settle=baseline/'cf_perky4_settle.c';assert settle.is_file()
    original=(c.ROOT/'tools/harness/perky_cf/placement_cf_engine.c').read_text()
    original=original.replace('#include "cf_perky4.c"','#include "'+str(settle)+'"')
    source=work/'placement-original.c';source.write_text(original)
    candidate=batches.transform(work,source)
    native=c.ROOT/'out/perky/hybrid/cf-placement/native.dylib';libs=[];commands=[]
    for name,path in (('reference',source),('candidate',candidate)):
        wrapper=work/(name+'.c');wrapper.write_text('#include "'+str(path)+'"\n'+WRAPPER)
        lib=work/(name+'.dylib')
        command=['cc','-O3','-std=c11','-shared','-fPIC','-I'+str(c.ROOT/'modules/perky'),str(wrapper),str(native),'-o',str(lib)]
        subprocess.run(command,check=True);commands.append(command);libs.append(C.CDLL(str(lib)))
    assets=c.ROOT/'out/perky/hybrid/cf-placement/assets'
    names=('pitch','chromatic','envelope1','envelope2','w0','w1','w2','w3','m1','interp_a','interp_b','wt_base','wt_bank','closed','open','ride')
    buffers=[C.create_string_buffer((assets/(name+'.bin')).read_bytes()) for name in names]
    pointers=(C.c_void_p*16)(*[C.addressof(value) for value in buffers])
    U32=C.c_uint32
    for lib in libs:
        lib.placement_bind.argtypes=[C.POINTER(C.c_void_p)];lib.placement_prepare.argtypes=[U32,C.POINTER(U32),C.c_int]
        lib.cb_size.restype=C.c_size_t;lib.cb_snapshot.argtypes=[C.c_void_p];lib.cb_poison.argtypes=[U32,U32,U32]
        lib.cb_smoother_proof.restype=U32
        assert lib.cb_smoother_proof()==54573
        lib.placement_bind(pointers);lib.placement_init()
    assert libs[0].cb_size()==libs[1].cb_size();size=libs[0].cb_size()
    snapshots=[C.create_string_buffer(size) for _ in libs]
    def check(label):
        for lib,snapshot in zip(libs,snapshots):lib.cb_snapshot(snapshot)
        assert snapshots[0].raw==snapshots[1].raw,(label,[(i,x,y) for i,(x,y) in enumerate(zip(snapshots[0].raw,snapshots[1].raw)) if x!=y][:12])
    check('initialized');rng=random.Random(0xc017ba7c);events=poisoned=0;previous={}
    for i in range(6000):
        tr=i%4;algo=(i//4)%11
        if algo==10:tr=3
        values=[algo,(i//44)%3,*[rng.randrange(256) for _ in range(4)],rng.randrange(1,256),rng.randrange(128),0,int(i%3!=0)]
        if i%5==0 and tr in previous:values=list(previous[tr]);values[9]=int(i%2==0)
        if i%7==0:
            seed=rng.getrandbits(32)
            for lib in libs:lib.cb_poison(tr,values[0],seed)
            poisoned+=1
        inputs=(U32*10)(*values)
        returns=[lib.placement_prepare(tr,inputs,values[9]) for lib in libs]
        assert returns==[1,1],(i,values,returns)
        check((i,tr,values));previous[tr]=values;events+=1
    result=dict(status='PASS_CONTROL_BATCHES_ALL_PREPARE_PATHS_AND_UNSIGNED_FALLBACK',prepare_events=events,
                poisoned_prepare_events=poisoned,bounded_delta_cases=24573,unsigned_fallback_cases=30000,
                compared='All engine/object/control/clock bytes; only native asset pointer canonicalized',
                commands=commands,inputs={str(p):c.sha(p) for p in (settle,source,candidate,native)},
                source_sha256={str(p.relative_to(c.ROOT)):c.sha(p) for p in (Path(__file__).resolve(),Path(batches.__file__).resolve())},
                limits=['Native compilation proves the control transformation; actual ColdFire source/lifecycle gates remain required.'])
    c.save(work/'RESULT.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
