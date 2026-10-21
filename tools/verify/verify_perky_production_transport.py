#!/usr/bin/env python3
"""Final CF publication and EMAC resampling, against original bytes/math."""
import ctypes as C,hashlib,json,random,struct,subprocess
from pathlib import Path
import verify_perky_hybrid_runtime as rt
import unicorn.m68k_const as reg
ROOT=rt.ROOT;W=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class Clock(C.Structure):_fields_=[('phase',C.c_uint32),('have',C.c_uint32),('carry',C.c_int32)]
def main():
 out=W/'transport-gate';out.mkdir(exist_ok=True)
 source=out/'reference.c';source.write_text('#include "cf_native_clock.h"\nvoid reference(pk_cf_native_clock*c,const int16_t*d,unsigned n,int32_t*out){pk_cf_native_convert(c,d,n,out);}\nint proof(void){for(uint32_t n=0;n<=306179666u;n++)if(((uint64_t)n*233739717u>>35)!=n/147u)return 1;return 0;}\n')
 lib=out/'reference.dylib';subprocess.run(['cc','-O3','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(source),'-o',str(lib)],check=True);native=C.CDLL(str(lib));assert native.proof()==0
 image=W/'probe/mainos_PKNHG3.bin';elf=image.parent/'platform/runtime.elf'
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc
 if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
 # Load each verification function once. Never rewrite translated code.
 a=out/'canary.s';a.write_text('''.text
.globl seed
seed:
 move.l #0,%macsr
 move.l 8(%sp),%d0
 move.l %d0,%acc0
 move.l 12(%sp),%d0
 move.l %d0,%accext01
 move.l 4(%sp),%d0
 move.l %d0,%macsr
 rts
.globl readback
readback:
 move.l 4(%sp),%a0
 move.l %macsr,%d0
 move.l %d0,(%a0)+
 move.l #0,%macsr
 move.l %acc0,%d1
 move.l %d1,(%a0)+
 move.l %accext01,%d1
 move.l %d1,(%a0)+
 move.l %d0,%macsr
 rts
''')
 subprocess.run(['m68k-elf-gcc','-mcpu=54455','-nostdlib','-Wl,-Ttext=0x480e0000','-Wl,--entry=seed',str(a),'-o',str(out/'canary.elf')],check=True)
 subprocess.run(['m68k-elf-objcopy','-O','binary',str(out/'canary.elf'),str(out/'canary.bin')],check=True);u.mem_write(0x480e0000,(out/'canary.bin').read_bytes())
 sym={x[2]:int(x[0],16) for line in subprocess.check_output(['m68k-elf-nm',str(out/'canary.elf')],text=True).splitlines() if len(x:=line.split())==3}
 rng=random.Random(0x504b4733);canaries={getattr(reg,f'UC_M68K_REG_{p}{k}'):0x12340000+16*k for p,ks in (('D',range(2,8)),('A',range(2,7))) for k in ks}
 def call(name,args):
  for k,v in canaries.items():u.reg_write(k,v)
  rt.g.emu._call(u,s[name],args)
  assert all(u.reg_read(k)==v for k,v in canaries.items()),(name,'ABI')
 clocks=0
 for phase in range(147):
  for n in range(17):
   for kind in range(4):
    data=[-32768 if kind==0 else 32767 if kind==1 else (-32768 if i%2 else 32767) if kind==2 else rng.randrange(-32768,32768) for i in range(20)]
    clock=Clock(phase,kind&1,rng.randrange(-32768,32768));expected=(C.c_int32*16)();old=(clock.phase,clock.have,clock.carry)
    native.reference(C.byref(clock),(C.c_int16*20)(*data),n,expected)
    c,d,o=0x48000020,0x48001020,0x48002020
    u.mem_write(c,struct.pack('>IIi',*old));u.mem_write(d,struct.pack('>20h',*data));u.mem_write(o-16,b'\xa5'*(4*n+32))
    rt.g.emu._call(u,sym['seed'],((0,0x20,0x40,0x60,0x80,0xf0)[clocks%6],rng.randrange(1<<32),rng.randrange(1<<32)))
    rt.g.emu._call(u,sym['readback'],(0x48003000,));emac=bytes(u.mem_read(0x48003000,12))
    call('pk_nhb_native_convert_fast',(c,d,n,o))
    rt.g.emu._call(u,sym['readback'],(0x48003000,));assert bytes(u.mem_read(0x48003000,12))==emac,(phase,n,kind,'EMAC state')
    assert bytes(u.mem_read(c,12))==struct.pack('>IIi',clock.phase,clock.have,clock.carry),(phase,n,kind,'clock')
    assert bytes(u.mem_read(o-16,4*n+32))==b'\xa5'*16+b''.join((x&0xffffffff).to_bytes(4,'big') for x in expected[:n])+b'\xa5'*16,(phase,n,kind,'PCM/guard')
    clocks+=1
 packets=0
 for align in (0,2):
  for split in range(17):
   for k in range(32):
    values=[rng.randrange(1<<32) for _ in range(16)];at=0x48010020+align;src=0x48020020;u.mem_write(at-16,b'\xa5'*192);u.mem_write(src,b''.join(v.to_bytes(4,'big') for v in values))
    expected=[]
    for start,end in ((0,split),(split,16)):
     count=end-start;expected += [(count<<8)|count,0,0x04000000,0]
     for v in values[start:end]:expected += [(v<<8)&0xffffffff]*2
    call('pk_prod_pack',(at,src,split));assert bytes(u.mem_read(at-16,192))==b'\xa5'*16+b''.join(v.to_bytes(4,'big') for v in expected)+b'\xa5'*16
    packets+=1
 clears=0
 for align in (0,2):
  for n in range(129):
   at=0x48010020+align;u.mem_write(at-16,b'\xa5'*(4*n+32));call('pk_prod_clear',(at,n));assert u.reg_read(reg.UC_M68K_REG_D0)==at+4*n
   assert bytes(u.mem_read(at-16,4*n+32))==b'\xa5'*16+bytes(4*n)+b'\xa5'*16;clears+=1
 result=dict(status='PASS_EXACT_SOURCE_PACK_CLEAR_RESAMPLING_CLOCK_EMAC_AND_ABI',reciprocal_cases=306179667,source_clock_cases=clocks,packet_cases=packets,clear_cases=clears,image_sha256=sha(image),elf_sha256=sha(elf),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'modules/perky/production_resample.s',ROOT/'modules/perky/production_publish.s',ROOT/'modules/perky/cf_native_clock.h',source,a)})
 (W/'TRANSPORT_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],clocks,packets,clears)
if __name__=='__main__':main()
