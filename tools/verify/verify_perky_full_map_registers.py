#!/usr/bin/env python3
"""Final source/import/embed ABI, including every external-PCM split."""
import json,subprocess
from pathlib import Path
import measure_perky_full_map as f
import verify_perky_production_dsp_registers as g
ROOT=f.ROOT;W=f.W
def main():
 g.W=W;g.main();d=W/'register-gate';rows=[]
 values=(-1048576,-1,0,1,1048544)
 for split in range(17):
  for rotation in range(5):
   packet=[0x4e54,len(rows)+1]
   for start,end in ((0,split),(split,16)):
    packet += [end-start|1024,0,0]
    for i in range(start,end):
     v=values[(i+rotation)%5]&0xffffff;packet += [v>>16,v&65535]
   rows.append(packet)
 request=d/'external.requests';request.write_text(''.join(' '.join(f'{v:x}' for v in row)+'\n' for row in rows))
 symbols=json.loads((W/'program/resident-symbols.json').read_text())
 # A render leaves through the stock source tail at P:426, consumes the
 # JSR return, advances X:20b by 0x80, publishes n7=16 and puts SSH in x0.
 # Import uses ordinary RTS. Treating render as import executes unrelated
 # stock code with canary pointers and is an invalid harness stack shape.
 source=(d/'host.cpp').read_text()
 source=source.replace('((primitive||importing)?0x5002:0x426)','0x426')
 source=source.replace('dsp.regs().n[k].var!=before.n[k].var','dsp.regs().n[k].var!=(k==7?16:before.n[k].var)')
 source=source.replace('dsp.regs().x.var!=before.x.var','(dsp.regs().x.var>>24)!=(before.x.var>>24)')
 source=source.replace('if(!a.count("-embed")&&dsp.regs().a.var!=before.a.var)throw std::runtime_error("A register changed");','if(dsp.regs().a.var!=(0x2480ull<<32)||(dsp.regs().x.var&0xffffff)!=0x5002)throw std::runtime_error("stock source tail ABI changed");')
 source=source.replace('   dsp.regs().sp.var=0;','   mem.set(MemArea_X,0x20b,0x2400);\n   dsp.regs().sp.var=0;')
 target=d/'render-host.cpp';target.write_text(source)
 receipt=json.loads((W/'REGISTER_GATE.json').read_text());compile=receipt['commands'][0]
 compile=[str(target) if v==str(d/'host.cpp') else str(d/'render-host') if v==str(d/'host') else v for v in compile]
 subprocess.run(compile,check=True)
 cmd=[str(d/'render-host'),'-code',str(W/'import-gate/code.bin'),'-entry',f"{symbols['source_entry']:x}",'-data',str(W/'import-gate/initial.data'),'-requests',str(request),'-out',str(d/'external.bin'),'-kind','import']
 subprocess.run(cmd,check=True)
 p=W/'REGISTER_GATE.json';r=json.loads(p.read_text());r.update(status='PASS_FULL_MAP_SOURCE_IMPORT_EMBED_AND_EXTERNAL_PCM_REGISTERS',external_cases=len(rows),all_external_splits=list(range(17)));r['commands'].extend([compile,cmd]);r['render_tail_contract']='P:426; popped JSR return in x0; n7=16; X:20b += 0x80; A carries updated cursor; all other seeded registers preserved';r['source_sha256'][str(Path(__file__).relative_to(ROOT))]=f.c.sha(Path(__file__));p.write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()
