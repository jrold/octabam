#!/usr/bin/env python3
"""Run actual linked NT/AH/Slap kernels against frozen native object/audio/RNG.

This loads the final CF image and calls its linked functions. The independent
native initializer supplies only initial objects; histories remain separate.
Production scheduling and hardware timing are qualified elsewhere.
"""
import argparse,ctypes as C,hashlib,json,random,struct
from pathlib import Path
import verify_perky_hybrid_runtime as rt
ROOT=rt.ROOT
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Wave(C.Structure):_fields_=[('address',C.c_uint32),('table',C.c_void_p)]
class NT(C.Structure):_fields_=[('envelope1',C.c_void_p),('envelope2',C.c_void_p),('waves',Wave*4)]
class Fold(C.Structure):_fields_=[('pitch',C.c_void_p),('envelope1',C.c_void_p),('envelope2',C.c_void_p),('waves',Wave*4)]
class Sample(C.Structure):_fields_=[('address',C.c_uint32),('data',C.c_void_p),('bytes',C.c_uint32)]
class AH(C.Structure):_fields_=[('envelope1',C.c_void_p),('envelope2',C.c_void_p),('samples',Sample*3)]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);a=p.parse_args();w=a.build.resolve();out=w/'kernel-gate';out.mkdir(exist_ok=True)
 b=json.loads((w/'BUILD.json').read_text());image=w/'probe'/('mainos_'+b['version']+'.bin');elf=image.parent/'platform/runtime.elf';assert sha(image)==b['main_sha256']
 base=ROOT/'out/perky/hybrid/cf-placement';native_path=base/'native.dylib';oracle_path=ROOT/'out/perky/hybrid/full-map-state-v4/source-gate/oracle.dylib'
 native=C.CDLL(str(native_path));oracle=C.CDLL(str(oracle_path));native.placement_prepare.argtypes=[C.c_uint32,C.c_void_p,C.c_int];native.placement_bind.argtypes=[C.c_void_p];oracle.fm_raw.argtypes=[C.c_uint32,C.c_uint32,C.c_void_p]
 names=('pitch','chromatic','envelope1','envelope2','w0','w1','w2','w3','m1','interp_a','interp_b','wt_base','wt_bank','closed','open','ride')
 assets=[(base/'assets'/(n+'.bin')).read_bytes() for n in names];buffers=[C.create_string_buffer(v) for v in assets];pointers=[C.addressof(v) for v in buffers];native.placement_bind((C.c_void_p*16)(*pointers))
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000);r,s=rt.machine(image,elf,True);u=r.uc
 if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
 raw_at,data_at,side_at,tables_at=0x48000000,0x48010000,0x48011000,0x48012000
 addresses=[];at=0x48020000
 for data in assets:addresses.append(at);u.mem_write(at,data+b'\x00\x00');at=(at+len(data)+7)&~3
 waves=(Wave*4)(*[Wave(0x080222a0+512*i,pointers[4+i]) for i in range(4)])
 nt=NT(pointers[2],pointers[3],waves);fold=Fold(pointers[0],pointers[2],pointers[3],waves)
 ah=AH(pointers[2],pointers[3],(Sample*3)(*[Sample(addr,pointers[13+i],len(assets[13+i])) for i,addr in enumerate((0x080cbef0,0x080a1bf0,0x080627cc))]))
 raw_table={
 'nt':struct.pack('>10I',addresses[2],addresses[3],*[v for i in range(4) for v in (0x080222a0+512*i,addresses[4+i])]),
 'slap':struct.pack('>11I',addresses[0],addresses[2],addresses[3],*[v for i in range(4) for v in (0x080222a0+512*i,addresses[4+i])]),
 'ah':struct.pack('>11I',addresses[2],addresses[3],*[v for i,addr in enumerate((0x080cbef0,0x080a1bf0,0x080627cc)) for v in (addr,addresses[13+i],len(assets[13+i]))])}
 rng=random.Random(0x534b4552);n_values=(0,1,2,16,17,18,19,20,21,39,41);results={};seed=C.create_string_buffer(12000)
 for name,generic,physical,tr,table,modes in [('nt',3,11,3,nt,(1,2)),('ah',10,10,3,ah,(0,1,2)),('slap',8,8,2,fold,(0,1,2))]:
  symbol={'nt':'pk_cf_nt_shared_render','ah':'pk_cf_ah_render','slap':'pk_cf_slap_render'}[name];fn=getattr(native,symbol);fn.argtypes=[C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p,C.c_void_p];fn.restype=C.c_int
  calls=samples=0
  for mode in modes:
   for corner in (0,64,127):
    for edge in range(8):
     native.placement_init();params=(C.c_uint32*10)(generic,mode,corner,corner,corner,corner,255,45,0,1);assert native.placement_prepare(tr,params,1)
     size=oracle.fm_raw(tr,physical,seed);state=bytearray(seed.raw[:size])
     def put(o,v):state[o:o+4]=struct.pack('<I',v&0xffffffff)
     if edge:
      if name=='ah':
       put(0xc4,(0,1,0xffffffff,10)[edge%4]);put(0xfc,(0,1,2,100000)[edge%4]);put(0xc8,rng.randrange(4096));put(0xdc,edge%4);put(0x100,rng.getrandbits(32));put(0x104,(rng.getrandbits(32)&0x807fffff)|((1+edge*31)<<23));state[0x108]=3 if edge%3==0 else 0;state[0xb8]=int(edge%7==0)
      else:
       for offset in (0xac,0xb0,0xb4):put(offset,rng.choice((0,1,0xffffffff,0x80000000,0x7fffffff,32767,0xffff8000)))
     reference=C.create_string_buffer(bytes(state),size);u.mem_write(raw_at,bytes(state));u.mem_write(tables_at,raw_table[name]);side=(C.c_int32*1)(rng.randrange(-0x80000000,0x80000000)) if name=='ah' else (C.c_uint32*2)(rng.getrandbits(32),rng.getrandbits(32))
     u.mem_write(side_at,struct.pack('>i',side[0]) if name=='ah' else struct.pack('>2I',*side))
     for n in n_values:
      pcm=C.create_string_buffer(b'\xa5'*132,132);u.mem_write(data_at,b'\xa5'*132)
      expected=fn(reference,pcm,n,C.byref(table),side);rt.g.emu._call(u,s[symbol],(raw_at,data_at,n,tables_at,side_at));actual=int(u.reg_read(__import__('unicorn.m68k_const',fromlist=['UC_M68K_REG_D0']).UC_M68K_REG_D0))
      assert actual==expected,(name,mode,corner,edge,n,'return')
      assert bytes(u.mem_read(raw_at,size))==reference.raw,(name,mode,corner,edge,n,'complete raw state')
      want=struct.pack('>'+str(n)+'h',*struct.unpack('<'+str(n)+'h',pcm.raw[:2*n]))+b'\xa5'*(132-2*n)
      assert bytes(u.mem_read(data_at,132))==want,(name,mode,corner,edge,n,'PCM/guard')
      assert bytes(u.mem_read(side_at,4 if name=='ah' else 8))==(struct.pack('>i',side[0]) if name=='ah' else struct.pack('>2I',*side)),(name,mode,corner,edge,n,'hold/RNG')
      calls+=1;samples+=n
     before=bytes(u.mem_read(raw_at,size));rt.g.emu._call(u,s[symbol],(raw_at,data_at,0,0,side_at));assert u.reg_read(__import__('unicorn.m68k_const',fromlist=['UC_M68K_REG_D0']).UC_M68K_REG_D0)==0 and bytes(u.mem_read(raw_at,size))==before
  results[name]=dict(calls=calls,native_samples=samples,modes=list(modes),counts=list(n_values),edge_rows=8,invalid_table_return_and_state=True,symbol=symbol,address=s[symbol])
 report=dict(status='PASS_ACTUAL_LINKED_KERNEL_NATIVE_PCM_FULLSTATE_RNG_HOLD',results=results,image_sha256=sha(image),elf_sha256=sha(elf),inputs={str(p):sha(p) for p in (Path(__file__).resolve(),native_path,oracle_path,*[base/'assets'/(n+'.bin') for n in names])},generated_sources={str(w/name):sha(w/name) for name in ('noise-tone-native20.c','acoustic-hats-native-state.c','slap-rng-emac.c')},limits=['Direct linked-kernel calls establish exact audio/state, not full-machine scheduling or silicon timing.'])
 (w/'KERNEL_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
