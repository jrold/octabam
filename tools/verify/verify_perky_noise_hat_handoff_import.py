#!/usr/bin/env python3
"""Exercise the actual DSP import parser, with poisoned wire upper bytes."""
import json,random,struct,subprocess,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/perky','tools/build','tools')]
import ab_records as A
W=ROOT/'out/perky/hybrid/noise-hat-handoff'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'import-gate';out.mkdir(exist_ok=True)
 original=ROOT/'tools/harness/perky_cf/noise_hat_taps_host.cpp'
 source=original.read_text().replace('const bool primitive=', 'const bool importing=a.count("-kind")&&a.at("-kind")=="import";\n   const bool primitive=')
 source=source.replace('dsp.regs().sp.var=0;', 'dsp.regs().m[1].var=0x1fff;\n   dsp.regs().sp.var=0;')
 source=source.replace('primitive?0x5002:0x426','(primitive||importing)?0x5002:0x426')
 source=source.replace('   if(dsp.regs().sp.var!=0)', '   if(importing&&dsp.regs().m[1].var!=0x1fff)throw std::runtime_error("import did not restore modulo register");\n   if(dsp.regs().sp.var!=0)')
 (out/'host.cpp').write_text(source)
 vendor=ROOT/'vendor/dsp56300';host=out/'host'
 cmd=['c++','-O3','-DNDEBUG','-std=gnu++17','-DASMJIT_STATIC','-DDSP56300_DEBUGGER=0','-I'+str(vendor/'source'),'-I'+str(vendor/'source/asmjit/src'),str(out/'host.cpp'),*[str(vendor/('build/source/'+s)) for s in ('dsp56kEmu/libdsp56kEmu.a','dsp56kBase/libdsp56kBase.a','asmjit/libasmjit.a')],'-lpthread','-o',str(host)]
 subprocess.run(cmd,check=True)
 blob=(W/'dsp-A.upload.bin').read_bytes();records,_=A.records(blob,A.BASE,len(blob));flat=[0]*0x40000;data=[];state=[0]*180;side=[0]*6
 for space,at,n,off in records:
  words=[A.rd(blob,off+3*i) for i in range(n)]
  if space==0:
   assert at+n<=len(flat);flat[at:at+n]=words
  else:
   data.append(('X' if space==1 else 'Y')+f' {at:x} '+' '.join(f'{v:x}' for v in words)+'\n')
   for i,v in enumerate(words):
    if space==1 and 0x3800<=at+i<0x3800+180:state[at+i-0x3800]=v&65535
    if space==1 and 0x3970<=at+i<0x3976:side[at+i-0x3970]=v&65535
 (out/'code.bin').write_bytes(b''.join(v.to_bytes(3,'little') for v in flat));(out/'initial.data').write_text(''.join(data))
 rng=random.Random(0x4e4842);packets=[];expected=[]
 for i in range(768):
  mode=i%3;first,count=(81,28) if mode==1 else (0,81 if mode==0 else 59);base=121 if mode==2 else 0
  phase=(0,12,13,146,rng.randrange(147))[i%5];carry=(-32768,-1,0,32767,rng.randrange(-32768,32768))[i%5]
  words=[rng.randrange(65536) for _ in range(count)];state[base+first:base+first+count]=words
  packet=[0]*80+[0x4e43,0x3800+base+first,count,phase,carry&65535]+words
  if mode==1:side=[rng.randrange(65536) for _ in range(6)];packet+=side
  assert len(packet)<=168;packets.append(packet);expected.append((state.copy(),side.copy(),phase,int(phase>=13),carry&0xffffff))
 (out/'requests').write_text(''.join(' '.join(f'{v:x}' for v in p)+'\n' for p in packets))
 entry=json.loads((W/'program/resident-symbols.json').read_text())['source_entry']
 run=[str(host),'-code',str(out/'code.bin'),'-entry',f'{entry:x}','-data',str(out/'initial.data'),'-requests',str(out/'requests'),'-out',str(out/'response.bin'),'-kind','import']
 subprocess.run(run,check=True);response=(out/'response.bin').read_bytes();assert len(response)==504*len(expected)
 for i,(state,side,phase,have,carry) in enumerate(expected):
  row=response[504*i:504*(i+1)];assert struct.unpack_from('<24H',row,72)[0]==0
  assert list(struct.unpack_from('<180H',row,120))==state,(i,'state')
  assert list(struct.unpack_from('<6H',row,480))==side,(i,'side')
  assert struct.unpack_from('<3I',row,492)==(phase,have,carry),(i,'clock',struct.unpack_from('<3I',row,492),(phase,have,carry))
 result=dict(status='PASS_POISONED_PERSISTENT_IMPORT_STATE_CLOCK_MODULO_STACK',cases=len(expected),maximum_packet_halfwords=max(map(len,packets)),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),original,ROOT/'tools/perky/perky_noise_hat_handoff.py')},input_sha256={str(p.relative_to(ROOT)):sha(p) for p in (W/'dsp-A.upload.bin',W/'program/resident-symbols.json')},commands=[cmd,run],hardware_validated=False)
 (W/'IMPORT_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
