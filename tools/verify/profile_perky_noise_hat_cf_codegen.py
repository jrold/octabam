#!/usr/bin/env python3
"""Compare unchanged Hat C code generation under an exact native CF witness."""
import csv,hashlib,json,subprocess,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'out/perky/hybrid/noise-hat-codegen';BASE=ROOT/'out/perky/hybrid/cf-placement'
sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')];import generate_cf_final as generator
import generate_noise_hat_handoff_renderer as renderer
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 W.mkdir(exist_ok=True)
 original=ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp';text=original.read_text();start=text.index('    for(unsigned voice=0;voice<2;voice++)');end=text.index('    csv.close();',start)
 text=text[:start]+'''    for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
     std::array<unsigned,4>a{9,9,8,5},m{1,2,0,mode};
     run("solo",8,a,m,128,corner,false);run("solo",8,a,m,128,corner,true);
     run("layout",15,a,m,128,corner,true);
    }
'''+text[end:]
 text=text.replace('algorithm_layouts\\\":81','algorithm_layouts\\\":1').replace('mode_rows\\\":6','mode_rows\\\":3')
 source=W/'runner.cpp';source.write_text(text)
 build=json.loads((BASE/'BUILD.json').read_text());template=next(c for c in build['commands'] if str(original) in c)
 cmd=list(template);cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(W/'runner');subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 transposed=W/'transposed.c';renderer.generate(transposed)
 variants={'transpose':[],'baseline':[],'no-unroll':['-fno-unroll-loops','-fno-peel-loops'],'O2':['-O2'],'Os':['-Os'],'no-pressure':['-fno-sched-pressure']};results=[]
 link=next(c for c in build['commands'] if '-nostdlib' in c)
 for name,options in variants.items():
  d=W/name;d.mkdir(exist_ok=True)
  for n in ('assets','native.dylib'):
   p=d/n
   if not p.exists():p.symlink_to(BASE/n,target_is_directory=(BASE/n).is_dir())
  obj=d/'cf_noise_hat.o';compile=['m68k-elf-gcc',*generator.FLAGS,*options,'-ffunction-sections','-fdata-sections','-I',str(ROOT/'modules/perky'),'-c',str(transposed if name=='transpose' else ROOT/'modules/perky/cf_noise_hat.c'),'-o',str(obj)]
  subprocess.run(compile,check=True)
  command=[str(obj) if v==str(BASE/'cf_noise_hat.o') else str(d/'target.elf') if v==str(BASE/'target.elf') else v for v in link];subprocess.run(command,check=True)
  subprocess.run(['m68k-elf-objcopy','-O','binary',str(d/'target.elf'),str(d/'target.bin')],check=True)
  (d/'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm','-S',str(d/'target.elf')]))
  with (d/'execute.log').open('w') as f:subprocess.run([str(W/'runner'),str(d),str(d/'assets')],check=True,stdout=f,stderr=subprocess.STDOUT)
  rows=list(csv.DictReader((d/'costs.csv').open()));groups={}
  for r in rows:
   key=r['kind']+'-'+r['modes'];g=groups.setdefault(key,[]);g.append(int(r['cycles']))
  result=dict(name=name,options=options,groups={k:dict(max=max(v),mean=sum(v)/len(v)) for k,v in groups.items()},execution=json.loads((d/'EXECUTION.json').read_text()),elf_sha256=sha(d/'target.elf'),source_sha256=sha(ROOT/'modules/perky/cf_noise_hat.c'),compiled_source_sha256=sha(transposed if name=='transpose' else ROOT/'modules/perky/cf_noise_hat.c'),inputs={str(p):sha(p) for p in [Path(__file__),source,W/'runner',ROOT/'tools/perky/generate_noise_hat_handoff_renderer.py',BASE/'native.dylib',*BASE.glob('*.o'),*sorted((BASE/'assets').glob('*.bin'))]},commands=[compile,command])
  (d/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result);print(json.dumps(result),flush=True)
 (W/'RESULTS.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
