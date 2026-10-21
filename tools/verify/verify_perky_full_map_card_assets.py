#!/usr/bin/env python3
"""Loader failure publication and chunk bounds with injected file operations.

Whole-machine rows separately execute the stock filesystem and compare every
decoded target byte. This gate tests malformed inputs without hardware writes.
"""
import ctypes as C,json,struct,subprocess,zlib
from pathlib import Path
import measure_perky_full_map as f
ROOT=f.ROOT;W=f.W
def main():
 d=W/'asset-gate';d.mkdir(exist_ok=True);asset=(W/'PERKYAH.DAT').read_bytes();crc=struct.unpack_from('>I',asset,12)[0]
 header=(ROOT/'modules/perky/full_map_card_assets.h').read_text()
 header=header.replace('(Open)0x40016864u','test_open').replace('(Read)0x40016564u','test_read').replace('(Close)0x4001677cu','test_close')
 header=header.replace('(*(volatile uint32_t*)0x46c8240eu)','mounted').replace('*(volatile uint32_t*)0x800065b8u','running')
 code='''#include <stdint.h>
#include <string.h>
static int test_open(void*,const char*,const char*,void*,unsigned);
static int test_read(void*,void*,unsigned);static int test_close(void*);
static unsigned mounted=1,running=0,offset,bytes,peak,opened,closed,reads;
static const uint8_t*file;
uint8_t pk_placement_closed[20202],pk_placement_open[172800],pk_placement_ride[259106];
'''+f'#define FMA_EXPECTED_CRC 0x{crc:08x}u\n'+header+'''
static int test_open(void*o,const char*p,const char*m,void*b,unsigned n){
 if(strcmp(p,"/PERKYAH.DAT")||strcmp(m,"r")||n!=4096)return -1;
 opened++;offset=0;return file?1:-1;
}
static int test_read(void*o,void*p,unsigned n){
 reads++;if(n>peak)peak=n;if(offset+n>bytes)return 0;
 memcpy(p,file+offset,n);offset+=n;
 if(p==fma_header){for(unsigned i=0;i<4;i++){const uint8_t*q=file+4*i;fma_header[i]=(unsigned)q[0]<<24|(unsigned)q[1]<<16|(unsigned)q[2]<<8|q[3];}}
 return 1;
}
static int test_close(void*o){closed++;return 1;}
int check(const uint8_t*p,unsigned n,unsigned transport,unsigned card,unsigned*out){
 file=p;bytes=n;mounted=card;running=transport;peak=opened=closed=reads=0;
 fma_ready=0x41484f4b;fma_status=-4;fma_retry=99;fma_reset();
 memset(fma_object,0xa5,sizeof(fma_object));memset(fma_header,0xa5,sizeof(fma_header));
 memset(pk_placement_closed,0xa5,sizeof(pk_placement_closed));memset(pk_placement_open,0xa5,sizeof(pk_placement_open));memset(pk_placement_ride,0xa5,sizeof(pk_placement_ride));
 for(unsigned i=0;i<200;i++){fma_tick();if(fma_status==2||fma_status<0)break;}
 out[0]=fma_ready;out[1]=opened;out[2]=closed;out[3]=peak;out[4]=reads;
 return fma_status;
}
'''
 source=d/'loader.c';source.write_text(code);lib=d/'loader.dylib';subprocess.run(['cc','-O2','-shared','-fPIC',str(source),'-o',str(lib)],check=True)
 dll=C.CDLL(str(lib));dll.check.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_void_p];cases=[]
 corrupt=bytearray(asset);corrupt[1000]^=1;badheader=bytearray(asset);badheader[4]^=1
 rows=[('valid',asset,0,1,2),('missing',None,0,1,-1),('unmounted',asset,0,0,0),('already-playing',asset,1,1,0),('short-header',asset[:15],0,1,-2),('bad-header',bytes(badheader),0,1,-2),('truncated',asset[:-1],0,1,-3),('CRC',bytes(corrupt),0,1,-4),('trailing-byte-does-not-change-assets',asset+b'x',0,1,2)]
 for name,data,running,mounted,want in rows:
  out=(C.c_uint*5)();status=dll.check(C.c_char_p(data) if data is not None else None,len(data or b''),running,mounted,out)
  assert status==want,(name,status,want);assert out[3]<=4096
  assert (out[0]==0x41484f4b)==(status==2),(name,list(out))
  if status==2:
   pos=16
   for symbol,n in (('pk_placement_closed',20202),('pk_placement_open',172800),('pk_placement_ride',259106)):
    assert bytes((C.c_ubyte*n).in_dll(dll,symbol))==asset[pos:pos+n];pos+=n
  if not mounted or running:assert out[1]==out[4]==0
  cases.append(dict(case=name,status=status,ready=out[0],open_calls=out[1],close_calls=out[2],maximum_read_bytes=out[3],read_calls=out[4]))
 r=dict(status='PASS_CARD_ASSET_LOADER_BYTES_PUBLICATION_CHUNK_BOUNDS_AND_FAILURES',cases=cases,asset_sha256=f.c.sha(W/'PERKYAH.DAT'),inputs={str(p):f.c.sha(p) for p in (Path(__file__),ROOT/'modules/perky/full_map_card_assets.h',source)},limits=['Injected native I/O; production logic unchanged. Whole-machine positive rows separately run actual stock filesystem and verify all target bytes.'])
 (W/'CARD_ASSET_GATE.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()
