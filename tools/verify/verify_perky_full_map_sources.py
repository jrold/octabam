#!/usr/bin/env python3
"""All 81 layouts through the actual CF image and final DSP source parser.

Direct calls establish correctness, not integrated scheduling or timing.
The reference starts from its own initializer and retains history thereafter.
"""
import argparse,ctypes as C,hashlib,itertools,json,os,struct,subprocess,sys
from pathlib import Path
import verify_perky_hybrid_runtime as rt
ROOT=rt.ROOT;W=Path(os.environ.get('PERKY_FULL_MAP_WORK',str(ROOT/'out/perky/hybrid/full-map'))).resolve()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
U16=C.c_uint16;U32=C.c_uint32;I32=C.c_int32
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--layouts',type=int,default=81);args=ap.parse_args()
 out=W/'source-gate';out.mkdir(exist_ok=True);vendor=ROOT/'vendor/dsp56300'
 bridge=out/'dsp.dylib';cmd=['c++','-O3','-shared','-fPIC','-DNDEBUG','-std=gnu++17','-DASMJIT_STATIC','-DDSP56300_DEBUGGER=0','-I'+str(vendor/'source'),'-I'+str(vendor/'source/asmjit/src'),str(ROOT/'tools/harness/perky_cf/full_map_dsp_bridge.cpp'),*[str(vendor/('build/source/'+s)) for s in ('dsp56kEmu/libdsp56kEmu.a','dsp56kBase/libdsp56kBase.a','asmjit/libasmjit.a')],'-lpthread','-o',str(bridge)]
 with (out/'compile.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
 dsp=C.CDLL(str(bridge));dsp.fm_dsp_open.argtypes=[C.c_char_p,C.c_char_p,U32];dsp.fm_dsp_open.restype=C.c_void_p
 dsp.fm_dsp_step.argtypes=[C.c_void_p,C.POINTER(U16),U32,C.POINTER(I32),C.POINTER(U16),C.POINTER(U16),C.POINTER(U32),C.POINTER(U16)]
 dsp.fm_dsp_error.restype=C.c_char_p;dsp.fm_dsp_close.argtypes=[C.c_void_p]
 entry=json.loads((W/'program/resident-symbols.json').read_text())['source_entry'];handle=dsp.fm_dsp_open(str(W/'import-gate/code.bin').encode(),str(W/'import-gate/initial.data').encode(),entry);assert handle,dsp.fm_dsp_error()
 fields={0:'fold1',1:'fold2',2:'karplus',3:'nt_m1',4:'res_snare',5:'nh',6:'sd',7:'cd',8:'slap',9:'wt',11:'nt_shared',12:'res_bass',13:'res_nt'}
 oracle=out/'oracle.c';oracle.write_text('''#include <stddef.h>
#include <string.h>
#include "cf_perky4.h"
extern pk4_engine placement_engine;extern unsigned char placement_ah_state[];
extern void pk_nha_codec(uint8_t*,unsigned,uint16_t*,int);
unsigned fm_raw(unsigned tr,unsigned algo,void*out){pk4_track*t=&placement_engine.tracks[tr];switch(algo){
'''+''.join(f'case {a}:memcpy(out,t->{f},sizeof(t->{f}));return sizeof(t->{f});\n' for a,f in fields.items())+'''case 10:memcpy(out,placement_ah_state,268);return 268;}return 0;}
void fm_side(unsigned tr,unsigned*out){out[0]=placement_engine.tracks[tr].rng_low;out[1]=placement_engine.tracks[tr].rng_high;out[2]=placement_engine.nh_hold[0];out[3]=placement_engine.nh_hold[1];}
void fm_hat(uint16_t*out){uint8_t*s=placement_engine.tracks[3].nh;pk_nha_codec(s,0,out,0);pk_nha_codec(s,1,out,0);pk_nha_codec(s+0x2c98,2,out+121,0);}
''')
 lib=out/'oracle.dylib';native_path=ROOT/'out/perky/hybrid/cf-placement/native.dylib'
 subprocess.run(['cc','-O3','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(oracle),str(ROOT/'modules/perky/cf_noise_hat_offload.c'),str(native_path),'-o',str(lib)],check=True)
 native=C.CDLL(str(native_path));oracle_lib=C.CDLL(str(lib));native.placement_prepare.argtypes=[U32,C.POINTER(U32),C.c_int]
 native.placement_segment.argtypes=[U32,U32,U32,U32];native.placement_bind.argtypes=[C.POINTER(C.c_void_p)]
 names=('pitch','chromatic','envelope1','envelope2','w0','w1','w2','w3','m1','interp_a','interp_b','wt_base','wt_bank','closed','open','ride')
 buffers=[C.create_string_buffer((ROOT/'out/perky/hybrid/cf-placement/assets'/f'{n}.bin').read_bytes()) for n in names];native.placement_bind((C.c_void_p*16)(*[C.addressof(b) for b in buffers]))
 output=(I32*64).in_dll(native,'placement_output');clock_ref=(U32*12).in_dll(native,'placement_clocks')
 version=json.loads((W/'BUILD.json').read_text()).get('version','PKFM1');image=W/'probe'/f'mainos_{version}.bin';elf=image.parent/'platform/runtime.elf';boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc
 if 'fma_ready' in s:
  for name in ('closed','open','ride'):u.mem_write(s['pk_placement_'+name],(ROOT/'out/perky/hybrid/cf-placement/assets'/f'{name}.bin').read_bytes())
  rt.w32(u,s['fma_ready'],0x41484f4b) # immutable fixture binding; actual card loader has its own whole-machine gate
 if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
 layout=out/'offsets.c';layout.write_text('#include <stddef.h>\n#include <stdio.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\nint main(void){'+''.join(f'printf("{a} %zu\\n",offsetof(pk4_track,{f}));' for a,f in fields.items())+'}\n')
 subprocess.run(['cc','-I'+str(ROOT/'modules/perky'),str(layout),'-o',str(out/'offsets')],check=True);offsets={int(a):int(b) for a,b in (line.split() for line in subprocess.check_output([str(out/'offsets')],text=True).splitlines())}
 stride=rt.word(u,s['placement_layout']);rng_off=rt.word(u,s['placement_layout']+28);hold_off=rt.word(u,s['placement_layout']+48)
 packet_at=0x48010000;expected_raw=C.create_string_buffer(12000);side=(U32*4)();hat=(U16*180)();pcm=(I32*16)();state=(U16*180)();ds=(U16*6)();dc=(U32*3)();mail=(U16*24)()
 family=((0,9,6),(1,9,7),(4,8,2),(5,3,10));pending=[];frames=0
 def call(name,values):rt.g.emu._call(u,s[name],values)
 def native_raw(tr,algo):n=oracle_lib.fm_raw(tr,algo,expected_raw);return expected_raw.raw[:n]
 def physical(algo,mode):return 11 if algo==3 and mode else 12 if algo==4 and mode==1 else 13 if algo==4 and mode==2 else algo
 transitions=[(v,a,b) for v in range(4) for a,b in itertools.permutations(range(3),2)] if args.layouts==81 else []
 for combo in range(args.layouts+len(transitions)):
  q=combo;algos=[]
  for f in family:algos.append(f[q%3]);q//=3
  transition=transitions[combo-args.layouts] if combo>=args.layouts else None
  if transition:algos=[9,9,8,5];v,a,b=transition;algos[v]=family[v][a]
  # A new Part begins at split zero. Later frames retain all histories.
  native.placement_init();rt.w32(u,s['pk_prod_generation'],combo+1)
  for mode_row in range(3):
   for frame in range(17):
    split=0 if mode_row==frame==0 else frame;trig=frame%4==0
    if transition:
     v,a,b=transition;algos[v]=family[v][a if frame%2==0 else b]
    if len(pending)>=3:u.mem_write(s['pk_nhr_mail'],pending.pop(0))
    inputs=[]
    for tr in range(4):
     p=[algos[tr],(mode_row+tr)%3,96+(frame%32),(frame*7+tr*31)%128,(frame*13+tr*17)%128,(frame*19+tr*11)%128,255,45,split,int(trig)];inputs.append((U32*10)(*p));u.mem_write(s['placement_inputs']+40*tr,b''.join(v.to_bytes(4,'big') for v in p))
     if tr<3:
      assert native.placement_segment(tr,0,split,0);call('placement_segment',(tr,0,split,0))
      assert native.placement_prepare(tr,inputs[-1],int(trig));call('placement_prepare',(tr,s['placement_inputs']+40*tr,int(trig)))
      assert native.placement_segment(tr,split,16,1);call('placement_segment',(tr,split,16,1))
      actual=struct.unpack('>16i',u.mem_read(s['placement_output']+64*tr,64));assert list(actual)==list(output[16*tr:16*(tr+1)]),(combo,mode_row,frame,tr,'PCM')
      a=physical(algos[tr],inputs[-1][1]);raw=native_raw(tr,a);actual=bytes(u.mem_read(s['placement_engine']+tr*stride+offsets[a],len(raw)));assert actual==raw,(combo,mode_row,frame,tr,'raw state',next((i for i,(a,b) in enumerate(zip(actual,raw)) if a!=b),None))
    assert native.placement_segment(3,0,split,0);assert native.placement_prepare(3,inputs[3],int(trig));assert native.placement_segment(3,split,16,1)
    call('pk_nhr_frame',(split,packet_at));assert rt.word(u,s['placement_status'])==1
    n=(U16*168)(*struct.unpack('>168H',u.mem_read(packet_at,336)));assert dsp.fm_dsp_step(handle,n,168,pcm,state,ds,dc,mail),dsp.fm_dsp_error()
    assert list(pcm)==list(output[48:64]),(combo,mode_row,frame,3,'PCM',list(pcm),list(output[48:64]),'CF buffer',struct.unpack('>16i',u.mem_read(s['placement_output']+192,64)))
    oracle_lib.fm_side(3,side);target=s['placement_engine']+3*stride
    assert [rt.word(u,target+rng_off),rt.word(u,target+rng_off+4)]==list(side[:2]),(combo,mode_row,frame,'CF RNG')
    assert list(ds)==[side[2],side[3],side[0]&65535,side[0]>>16,side[1]&65535,side[1]>>16],(combo,mode_row,frame,'DSP side')
    oracle_lib.fm_hat(hat);assert list(state)==list(hat),(combo,mode_row,frame,'Hat state',[(i,a,b) for i,(a,b) in enumerate(zip(state,hat)) if a!=b][:8])
    if algos[3]!=5:
     a=physical(algos[3],inputs[3][1]);raw=native_raw(3,a);at=s['placement_ah_state'] if a==10 else target+offsets[a];assert bytes(u.mem_read(at,len(raw)))==raw,(combo,mode_row,frame,'alternative raw')
    pending.append(struct.pack('>24H',*mail));call('pk_nhb_work',())
    assert rt.word(u,s['pk_nhr_failures'])==0,(combo,mode_row,frame,'transport failure')
    frames+=1
  print('scenario',combo+1,'/',args.layouts+len(transitions),'exact frames',frames,flush=True)
 dsp.fm_dsp_close(handle)
 result=dict(status='PASS_ACTUAL_IMAGE_ALL_LAYOUT_SOURCE_PCM_STATE_SHARED_RNG' if args.layouts==81 else 'PARTIAL_LAYOUT_DIAGNOSTIC',algorithm_layouts=args.layouts,directed_algorithm_transitions=transitions,mode_rows=3,splits=list(range(17)),frames=frames,CF_source_frames=3*frames,DSP_mixed_source_frames=frames,image_sha256=sha(image),elf_sha256=sha(elf),inputs={str(p):sha(p) for p in (W/'dsp-A.upload.bin',W/'import-gate/code.bin',native_path,bridge,lib)},source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__).resolve(),ROOT/'tools/harness/perky_cf/full_map_dsp_bridge.cpp',oracle)},limits=['Direct executed source calls with delayed feedback establish correctness, not full stock scheduling, timing, UI or hardware.','Reference starts from original initializers at each Part and retains histories thereafter.'])
 (W/'SOURCE_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
