#!/usr/bin/env python3
"""Complete-map fixed rows with independent source streams and stock audio."""
import argparse,json,os,re
from pathlib import Path
import measure_perky_cf_placement_integrated as c
ROOT=c.ROOT;W=Path(os.environ.get('PERKY_FULL_MAP_WORK',str(ROOT/'out/perky/hybrid/full-map'))).resolve()
FAMILY=((0,9,6),(1,9,7),(4,8,2),(5,3,10))
ORIGINAL_STAGE=c.stage_fixture
def image_name():return json.loads((W/'BUILD.json').read_text()).get('version','PKFM1')
def stage(project,directory,kind,algos,modes,mask):
 otp=c.workload.otp;previous=otp._bank_write;set_fx=otp.set_fx
 def write(pdir,banknum,mutate,guard=True):
  def full(data):
   mutate(data)
   for part in range(otp.NPARTS_ALL):
    live=otp.PART_BASE+part*otp.PART_STRIDE+9
    for voice,track in enumerate((0,1,4,5)):
     at=live+48+30*track;data[at+2]=FAMILY[voice].index(algos[voice]);data[at+5]=modes[voice]
     data[live+60+30*track:live+63+30*track]=b'PK'+bytes((json.loads((W/'BUILD.json').read_text()).get('project_signature_version',1),))
   for pattern in range(4):
    for track in (0,1,4,5):
     at=otp.trac_off(pattern,track)+0x59
     for step in range(64):data[at+32*step+2]=data[at+32*step+5]=255
  return previous(pdir,banknum,full,guard=guard)
 def fx(pdir,slot,track,effect,**kw):
  if 'all fourteen' in str(json.loads((W/'BUILD.json').read_text()).get('memory',{}).get('retained_FX','')):
   layout=int(os.environ.get('PERKY_FULL_MAP_FX_LAYOUT','0'))
   replacements=({('fx2',2):'PLATE REV',('fx2',7):'COMPRESSOR'},
                 {('fx2',6):'PLATE REV',('fx2',3):'COMPRESSOR'},
                 {('fx1',1):'PLATE REV',('fx1',5):'COMPRESSOR',('fx2',2):'FILTER',('fx2',7):'PHASER'})[layout]
   replacement=replacements.get((slot,track))
   if replacement:
    effect=replacement;values=otp.module_defaults(c.workload.registry.modules()[effect]);kw.update(page=values[:6],page2=values[6:12])
  return set_fx(pdir,slot,track,effect,**kw)
 otp._bank_write=write;otp.set_fx=fx
 try:
  card=ORIGINAL_STAGE(project,directory,kind,algos,modes,mask)
  asset=W/'PERKYAH.DAT'
  if asset.exists():
   import emu_card,shutil
   tree=directory/'asset-tree';tree.mkdir(exist_ok=True)
   for name,data in emu_card.extract_image(card.read_bytes()).items():
    p=tree/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
   (tree/'PERKYAH.DAT').write_bytes(asset.read_bytes());card.write_bytes(emu_card.build_image(tree));shutil.rmtree(tree)
  return card
 finally:otp._bank_write=previous;otp.set_fx=set_fx
def environment(directory,syms):
 names=dict(FM_PREPARE='placement_prepare',FM_SEGMENT='placement_segment',FM_FRAME='pk_nhr_frame',FM_OUTPUT='placement_output',FM_OWNER='pk_nhb_owner',FM_SEQUENCE='pk_nhr_sequence',FM_ACCEPT='pk_nhr_accept',FM_MAIL='pk_nhr_mail',FM_GENERATION='pk_prod_generation')
 env={k:hex(syms[v]) for k,v in names.items()}
 env.update(FM_REFERENCE_LIBRARY=str(W/'observer/full-map-oracle.dylib'),FM_ASSETS=str(ROOT/'out/perky/hybrid/cf-placement/assets'),FM_REPORT=str(directory/'full-map-exact.json'),FM_COMMIT=hex(json.loads((W/'program/resident-symbols.json').read_text())['commit']))
 # The isolated port may skip the main idle spin only with an empty queue.
 env.update(NHB_PRODUCED=hex(syms['pk_nhb_produced']),NHB_COMPLETED=hex(syms['pk_nhb_completed']))
 return env
def program_checks():
 import ab_records as A
 peeks=['0:P:0,8192','1:P:0,8192'];expected={};appended=json.loads((W/'probe/p-records.json').read_text())
 for core,tag in enumerate(('A','B')):
  blob=(W/f'dsp-{tag}.upload.bin').read_bytes();rows,_=A.records(blob,A.BASE,len(blob));expected[core]={}
  for space,at,n,off in rows:
   if space or (at>=0x2000 and not any(at==a and n==len(words) for a,words in appended[tag])):continue
   expected[core].update({at+i:A.rd(blob,off+3*i) for i in range(n)})
   if at>=0x2000:peeks.append(f'{core}:P:{at:x},{n}')
 return peeks,expected
def loaded_program(log,expected):
 loaded={0:{},1:{}}
 for core,at,words in re.findall(r'core (\d+) P:(?:0x)?([0-9a-f]+): ([0-9a-f ]+)',log):
  loaded[int(core)].update({int(at,16)+i:int(v,16) for i,v in enumerate(words.split())})
 for core in (0,1):
  for at,value in expected[core].items():
   got=loaded[core].get(at)
   if at in ((0x58c,0x59b) if core==0 else (0x371,0x380)):assert value==0xffff and got in (0x3fff,0x5fff),(core,hex(at),got,value)
   else:assert got==value,(core,hex(at),got,value)
 return {str(core):len(expected[core]) for core in expected}
def live_program(m,expected):
 rows=[]
 for core,values in expected.items():
  addresses=sorted(values);i=0
  while i<len(addresses):
   at=addresses[i];j=i+1
   while j<len(addresses) and addresses[j]==addresses[j-1]+1 and j-i<4096:j+=1
   reply=m.proc.command(f'dsp peek {core} P {at:#x} {j-i}','dsp');words=reply.split()[1:];assert len(words)==j-i
   rows.append(f'core {core} P:{at:x}: '+ ' '.join(words));i=j
 return loaded_program('\n'.join(rows),expected)
def exact(r):
 return not any(r['PCM_mismatches']) and not any(r[k] for k in ('DSP_state_mismatches','DSP_side_mismatches','DSP_clock_mismatches','feedback_mismatches','oracle_errors'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--frames',type=int,default=4096);p.add_argument('--v3',type=int,choices=(4,8,2),default=8);p.add_argument('--v4',type=int,choices=(5,3,10),default=5);p.add_argument('--mode',type=int,choices=(0,1,2),default=1);a=p.parse_args()
 algos=[9,9,a.v3,a.v4];modes=[1,2,0,a.mode];name=f'FULL-WTWT-{a.v3}-{a.v4}-M{a.mode}'
 c.SCENARIOS[name]=(algos,modes,15);c.stage_fixture=stage
 directory=W/'integrated-results'/(name+'-static');syms=c.private.symbols(W/'probe/platform/runtime.elf')
 peeks,expected=program_checks();asset_dumps=[('fma_ready',4),('fma_status',4),('pk_placement_closed',20202),('pk_placement_open',172800),('pk_placement_ride',259106)] if 'fma_ready' in syms else []
 row=c.run(W,name,'static',a.frames,image_name=image_name(),extra_env=environment(directory,syms),extra_dumps=[(n,4) for n in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors','pk_nhb_produced','pk_nhb_completed','pk_prod_generation')]+asset_dumps,retain_audio_failure=True,extra_port_args=('--dsp-peek',';'.join(peeks)))
 finish_row(row,directory,expected,syms)
def finish_row(row,directory,expected=None,syms=None):
 if expected is None:_,expected=program_checks()
 if syms is None:syms=c.private.symbols(W/'probe/platform/runtime.elf')
 row['loaded_program_words_checked']=loaded_program((directory/'port.log').read_text(),expected)
 if 'fma_ready' in syms and 'card_assets_exact' not in row:
  assert int.from_bytes((directory/'fma_ready.bin').read_bytes(),'big')==0x41484f4b
  assert int.from_bytes((directory/'fma_status.bin').read_bytes(),'big')==2
  row['card_assets_exact']={}
  for n in ('closed','open','ride'):
   p=directory/('pk_placement_'+n+'.bin');want=(ROOT/'out/perky/hybrid/cf-placement/assets'/f'{n}.bin').read_bytes();assert p.read_bytes()==want,n
   row['card_assets_exact'][n]=c.sha(p);p.unlink()
 row['FX_layout']=int(os.environ.get('PERKY_FULL_MAP_FX_LAYOUT','0'))
 r=json.loads((directory/'full-map-exact.json').read_text());row['independent_source']=r
 row['transport']={n:int.from_bytes((directory/(n+'.bin')).read_bytes(),'big') for n in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors','pk_nhb_produced','pk_nhb_completed')}
 row['source_and_post_FX']['T6'].update(source_kind='mixed source PCM witnessed before AMP',source_significant=r['source_significant'][3])
 row['driver_sha256']=c.sha(Path(__file__).resolve());row['observer_environment']=environment(directory,syms)
 row['status']='PASS_EXACT_FULL_WORKLOAD_MODEL_SCOPE' if exact(r) and not row['audio_failures'] and row['full_ISR']['deadline_misses']==0 and row['transport']['pk_nhb_completed']>0 and not any(row['transport'][k] for k in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors')) else 'FAILED_FULL_WORKLOAD'
 (directory/'FULL_ROW.json').write_text(json.dumps(row,indent=2)+'\n');print(row['status'],row['full_ISR'],r,flush=True)
 assert row['status']=='PASS_EXACT_FULL_WORKLOAD_MODEL_SCOPE',directory
if __name__=='__main__':main()
