#!/usr/bin/env python3
"""Paired actual-image Hat packets, plus CF external append capacity proof.

The Hat producer executes directly in each linked image. External append
capacity cases compile each exact header function into a separate CF probe;
its synthesis callback supplies declared PCM, so this part proves packet and
fallback semantics, not synthesis. Nominal full-image external PCM is covered
by the independent kernel and mixed-source gates.
"""
import argparse,hashlib,itertools,json,random,struct,subprocess,sys
from pathlib import Path
import verify_perky_hybrid_runtime as rt
ROOT=rt.ROOT
sys.path.insert(0,str(ROOT/'modules/perky'))
import generate_cf_final as gcc
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def body(text,name):
 start=text.index('static void '+name+'(');end=text.index('{',start)+1;level=1
 while level:level+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);a=p.parse_args();w=a.build.resolve();base=a.baseline.resolve();out=w/'packet-gate';out.mkdir(exist_ok=True)
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 machines=[];bindings=[]
 for d in (base,w):
  b=json.loads((d/'BUILD.json').read_text());image=d/'probe'/('mainos_'+b['version']+'.bin');elf=image.parent/'platform/runtime.elf';assert sha(image)==b['main_sha256'];r,s=rt.machine(image,elf,True)
  if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in r.uc.mem_regions()):r.uc.mem_map(0x48000000,0x100000)
  rt.g.emu._call(r.uc,s['placement_init']);rt.g.emu._call(r.uc,s['pk_nhb_reset']);machines.append((r.uc,s,rt.sizes(elf)));bindings.append(dict(image=str(image),image_sha256=sha(image),elf_sha256=sha(elf)))
 fields=('nhr_used','nht_issued','nht_committed','nht_ring_index','pk_nhr_failures','pk_nhr_initializations','pk_nht_pending_max','pk_nht_tap_words')
 rng=random.Random(0x5041434b);capacity=(0,2,120,150,165,167,168,169,0xffffffff);cases=fast_cases=fallback_cases=0
 engine_seeds=[bytes(u.mem_read(s['placement_engine'],sz['placement_engine'])) for u,s,sz in machines]
 engine_asset_offsets=[4*rt.word(u,s['placement_layout']) for u,s,_ in machines]
 for (u,s,_),offset in zip(machines,engine_asset_offsets):assert rt.word(u,s['placement_engine']+offset)==s['placement_assets']
 def canonical_engine(data,offset):return data[:offset]+data[offset+4:]
 assert canonical_engine(engine_seeds[0],engine_asset_offsets[0])==canonical_engine(engine_seeds[1],engine_asset_offsets[1]),'independent linked logical initializers differ'
 for mode,need,used,apply,trig in itertools.product(range(3),(0,1,17,20,21),capacity,range(2),range(2)):
  mute=int(used==0xffffffff or cases%11==0);building=cases%2;cache=bytes(rng.getrandbits(8) for _ in range(726));commands=bytes(rng.getrandbits(8) for _ in range(336));scratch=0x48060000;capture=0x48070000
  segment=[0,16,mode,need,trig,mute,-12345,0,9,int(cases%7==0),0]
  row=[]
  for i,(u,s,sz) in enumerate(machines):
   u.mem_write(s['placement_engine'],engine_seeds[i]);u.mem_write(s['budget_ctrl_cache'],cache);u.mem_write(s['budget_ctrl_valid'],struct.pack('>3I',*[int(cases%3!=0)]*3));u.mem_write(s['nhr_commands'],commands)
   u.mem_write(scratch,struct.pack('>2I',37,0)+struct.pack('>6Ii4I',*segment)*2);u.mem_write(capture,b'\x5a'*2048)
   values=dict(nhr_used=used,nht_issued=cases%700,nht_committed=0,nht_ring_index=cases%4805,pk_nhr_failures=7,pk_nhr_initializations=3,pk_nht_pending_max=0,pk_nht_tap_words=11,nhr_previous=scratch,nhb_building=capture if building else 0,nhs_state=1)
   for name,value in values.items():rt.w32(u,s[name],value)
   rt.g.emu._call(u,s['nhr_emit'],(mode,need,cases%2,trig,apply))
   assert rt.word(u,s['placement_engine']+engine_asset_offsets[i])==s['placement_assets']
   result=dict(scalars={name:rt.word(u,s[name]) for name in fields},commands=bytes(u.mem_read(s['nhr_commands'],336)),valid=bytes(u.mem_read(s['budget_ctrl_valid'],12)),cache=bytes(u.mem_read(s['budget_ctrl_cache'],726)),capture=bytes(u.mem_read(capture,2048)),engine=canonical_engine(bytes(u.mem_read(s['placement_engine'],sz['placement_engine'])),engine_asset_offsets[i]))
   row.append(result)
  assert row[0]==row[1],(cases,mode,need,used,apply,trig,'actual linked Hat packet/counter/state')
  if used<3:fast_cases+=1
  if used>=168:fallback_cases+=1;assert row[1]['scalars']['pk_nhr_failures']>7
  cases+=1
 # External path's exact old/new function bodies get independent CF code and
 # explicit capacity inputs, including corrupt ranges that remain checked.
 headers=(base/'full-map-transport.h',w/'full-map-transport-reserved.h');external=[];commands=[]
 prefix='''#include <stdint.h>
typedef struct {unsigned start,end,mode,need,reset,mute;int mix;unsigned ring_start,generation,epoch_reset,external;} nhr_segment;
typedef struct {unsigned dummy;} pk4_track;
struct {pk4_track tracks[4];} placement_engine;
typedef struct {nhr_segment segment;uint16_t words[121],side[6],carry_taps[5];unsigned apply,trig;} nhb_half;
struct {nhb_half half[2];} capture;typeof(capture)*nhb_building;
uint16_t nhr_commands[168];unsigned nhr_used,pk_nhr_failures,placement_status;
int32_t placement_output[4][32];nhr_segment test_segment;unsigned test_half,test_request,test_synthesis_return;uint16_t test_side[6];
static void nhr_put(unsigned v){if(nhr_used<168)nhr_commands[nhr_used++]=(uint16_t)v;else pk_nhr_failures++;}
static int placement_segment(unsigned tr,unsigned start,unsigned end,unsigned half){(void)tr;(void)start;(void)end;(void)half;return test_synthesis_return;}
static unsigned nhb_request_flag(unsigned half){return half?test_request:0;}
static void nhb_side(uint16_t*s,const pk4_track*t){(void)t;for(unsigned i=0;i<6;i++)s[i]=test_side[i];}
'''
 for i,path in enumerate(headers):
  d=out/('external-original' if not i else 'external-reserved');d.mkdir(exist_ok=True);source=d/'probe.c';source.write_text(prefix+body(path.read_text(),'fm_external')+'\nvoid ext_test(void){fm_external(&test_segment,test_half);}\n')
  argv=['m68k-elf-gcc',*gcc.FLAGS,'-c',str(source),'-o',str(d/'probe.o')];subprocess.run(argv,check=True);commands.append(argv)
  argv=['m68k-elf-ld','-Ttext=0x48080000','--entry=ext_test','-o',str(d/'probe.elf'),str(d/'probe.o')];subprocess.run(argv,check=True);commands.append(argv)
  subprocess.run(['m68k-elf-objcopy','-O','binary',str(d/'probe.elf'),str(d/'probe.bin')],check=True)
  u=machines[i][0];u.mem_write(0x48080000,(d/'probe.bin').read_bytes());symbols=rt.g.load_elf_symbols(d/'probe.elf');external.append((u,symbols))
 ext_cases=ext_fast=ext_fallback=0
 for start,end,used,half,building in itertools.product((0,7,16),(0,8,16),capacity,range(2),range(2)):
  if end<start and not(start==16 and end==8):continue
  segment=[start,end,2,0,0,0,0,0,0,1,1];side=[rng.randrange(65536) for _ in range(6)];pcm=[rng.randrange(-0x80000000,0x80000000) for _ in range(128)];initial=bytes(rng.getrandbits(8) for _ in range(336));rows=[]
  for u,s in external:
   u.mem_write(s['test_segment'],struct.pack('>6Ii4I',*segment));u.mem_write(s['test_side'],struct.pack('>6H',*side));u.mem_write(s['placement_output'],struct.pack('>128i',*pcm));u.mem_write(s['capture'],b'\xa5'*632);u.mem_write(s['nhr_commands'],initial)
   for name,value in dict(nhr_used=used,pk_nhr_failures=11,placement_status=1,test_half=half,test_request=2048,test_synthesis_return=int(start<=end),nhb_building=s['capture'] if building else 0).items():rt.w32(u,s[name],value)
   rt.g.emu._call(u,s['ext_test'])
   rows.append(dict(used=rt.word(u,s['nhr_used']),failures=rt.word(u,s['pk_nhr_failures']),status=rt.word(u,s['placement_status']),commands=bytes(u.mem_read(s['nhr_commands'],336)),capture=bytes(u.mem_read(s['capture'],632))))
  assert rows[0]==rows[1],(start,end,used,half,building,'external CF packet/fallback/capture')
  words=15+2*(end-start)
  if start<=end and used<=168 and words<=168-used:ext_fast+=1
  else:ext_fallback+=1
  ext_cases+=1
 report=dict(status='PASS_ACTUAL_HAT_AND_CF_EXTERNAL_PACKET_RESERVATION_FALLBACK',Hat_actual_image_cases=cases,Hat_bounded_capacity_rows=fast_cases,Hat_overcapacity_rows=fallback_cases,external_CF_cases=ext_cases,external_bounded_rows=ext_fast,external_checked_fallback_rows=ext_fallback,capacities=list(capacity),bindings=bindings,commands=commands,inputs={str(p):sha(p) for p in (Path(__file__).resolve(),*headers,*[out/n/'probe.c' for n in ('external-original','external-reserved')],*[out/n/'probe.elf' for n in ('external-original','external-reserved')])},limits=['External bounded/corrupt capacity proof executes independently linked exact function bodies with a declared-PCM callback; full-image synthesis/timing remain separate gates.'])
 (w/'PACKET_RESERVE_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
