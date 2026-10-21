#!/usr/bin/env python3
"""Canary every saved register across actual A source/import and embed entries."""
import json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'register-gate';out.mkdir(exist_ok=True)
 original=(W/'import-gate/host.cpp').read_text()
 seed='''
   for(unsigned k=0;k<8;k++){dsp.regs().r[k].var=0x7345+17*k;dsp.regs().n[k].var=0xfedc+k;dsp.regs().m[k].var=0x1fff-k*0x100;}
   dsp.regs().m[1].var=0x1fff;
   // dsp.h stores its 56-bit accumulators left-aligned (g_aluShift=8).
   dsp.regs().a.var=0x7e123456a5a5a5ull<<8;dsp.regs().b.var=0x81fedcba123456ull<<8;
   dsp.regs().x.var=0xabcdef123456;dsp.regs().y.var=0x987654fedcba;
   dsp.regs().la.var=0x7521;dsp.regs().lc.var=0x123;
   if(a.count("-embed"))mem.set(MemArea_X,0x206,0x2700);
   auto before=dsp.regs();
'''
 original=original.replace('   dsp.regs().sp.var=0;',seed+'   dsp.regs().sp.var=0;')
 marker='   if(importing&&dsp.regs().m[1].var!=0x1fff)'
 checks=r'''
   for(unsigned k=0;k<8;k++)if(dsp.regs().r[k].var!=before.r[k].var||dsp.regs().n[k].var!=before.n[k].var||dsp.regs().m[k].var!=before.m[k].var)throw std::runtime_error("address/modulo/increment register changed "+std::to_string(k));
   if(dsp.regs().b.var!=before.b.var||dsp.regs().x.var!=before.x.var||dsp.regs().y.var!=before.y.var||dsp.regs().la.var!=before.la.var||dsp.regs().lc.var!=before.lc.var){std::cerr<<std::hex<<"B "<<dsp.regs().b.var<<"/"<<before.b.var<<" X "<<dsp.regs().x.var<<"/"<<before.x.var<<" Y "<<dsp.regs().y.var<<"/"<<before.y.var<<" LA "<<dsp.regs().la.var<<"/"<<before.la.var<<" LC "<<dsp.regs().lc.var<<"/"<<before.lc.var<<"\n";throw std::runtime_error("data/loop register changed");}
   if(!a.count("-embed")&&dsp.regs().a.var!=before.a.var)throw std::runtime_error("A register changed");
'''
 original=original.replace(marker,checks+marker);(out/'host.cpp').write_text(original)
 receipt=json.loads((W/'IMPORT_GATE.json').read_text());compile=receipt['commands'][0]
 compile=[str(out/'host.cpp') if x==str(W/'import-gate/host.cpp') else str(out/'host') if x==str(W/'import-gate/host') else x for x in compile]
 subprocess.run(compile,check=True)
 symbols=json.loads((W/'program/resident-symbols.json').read_text());commands=[]
 data=(W/'import-gate/initial.data').read_text()+'X 39f0 4e52\n';(out/'initial.data').write_text(data)
 for kind in ('source','embed'):
  command=[str(out/'host'),'-code',str(W/'import-gate/code.bin'),'-entry',f"{symbols['source_entry' if kind=='source' else 'embed_entry']:x}",'-data',str(out/'initial.data'),'-requests',str(W/'import-gate/requests'),'-out',str(out/(kind+'.bin')),'-kind','import']
  if kind=='embed':command+=['-embed','1']
  subprocess.run(command,check=True);commands.append(command)
 result=dict(status='PASS_SAVED_REGISTERS_SOURCE_IMPORT_AND_EMBED',cases=1536,commands=[compile,*commands],inputs={str(p):sha(p) for p in (W/'dsp-A.upload.bin',W/'program/resident-symbols.json')},source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))})
 (W/'REGISTER_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
