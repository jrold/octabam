#!/usr/bin/env python3
"""Actual Slap EMAC RNG candidate vs frozen native full audio/object/RNG."""
import argparse,csv,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'out/perky/hybrid/cf-placement'
sys.path[:0]=[str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
import generate_cf_final as gcc
import generate_cf_slap_rng as candidate
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);a=p.parse_args();w=a.work.resolve();w.mkdir(parents=True,exist_ok=True)
 baseline=ROOT/'out/perky/hybrid/full-map-state-v4/slap-filter-block.c';commands=[]
 def run(command,log):
  command=list(map(str,command));commands.append(command)
  with (w/(log+'.log')).open('w') as out:subprocess.run(command,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
 manifest=json.loads((BASE/'BUILD.json').read_text());original=ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp';text=original.read_text()
 text=text.replace('compare(t,native,kind=="solo"||f==0||f+1==frames)','compare(t,native,true)')
 begin=text.index('    for(unsigned voice=0;voice<2;voice++)');end=text.index('    csv.close();',begin)
 text=text[:begin]+'''
    for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
        std::array<unsigned,4>a{9,9,8,5},m{1,2,mode,1};
        run("solo",4,a,m,128,corner,false);
        run("dense",4,a,m,128,corner,true);
        run("layout",15,a,m,64,corner,true);
    }
    t.call("slrng_mac_probe");
    require(t.m.read32(t.at("slrng_mac_checks"))==84&&t.m.read32(t.at("slrng_mac_failures"))==0,"Slap caller raw MACSR/ACC/extension preservation");
'''+text[end:]
 text=text.replace('\\"algorithm_layouts\\":81,\\"mode_rows\\":6','\\"algorithm_layouts\\":1,\\"mode_rows\\":3')
 runner=w/'runner.cpp';runner.write_text(text);command=list(next(c for c in manifest['commands'] if str(original) in c));command[command.index(str(original))]=str(runner);command[command.index('-o')+1]=str(w/'runner');run(command,'runner-build')
 helpers=('modules/perky/budget_transport.s','modules/perky/cf_synthesis_delay.s')
 for i,path in enumerate(helpers):run(['m68k-elf-gcc','-mcpu=54455','-c',ROOT/path,'-o',w/f'helper{i}.o'],f'helper{i}-build')
 flags=[*gcc.FLAGS,'-ffunction-sections','-fdata-sections','-I',ROOT/'modules/perky'];template=list(next(c for c in manifest['commands'] if '-nostdlib' in c));results={}
 for variant in ('baseline','emac'):
  d=w/variant;d.mkdir(exist_ok=True)
  for name in ('native.dylib','assets'):
   q=d/name
   if not q.exists():q.symlink_to(BASE/name,target_is_directory=name=='assets')
  source=candidate.transform(d,baseline) if variant=='emac' else d/'slap-baseline.c'
  if variant=='baseline':source.write_text(baseline.read_text())
  capture=(ROOT/'tools/harness/perky_cf/hybrid_cf_render_math.c').read_text().split('int bench_math_probe(void)')[0].replace('capture(', 'slrng_capture(')
  with source.open('a') as out:out.write('\n'+capture+'''
extern void placement_frame(void);
uint32_t slrng_mac_checks,slrng_mac_failures;
void slrng_mac_probe(void){
    static const uint32_t modes[]={0,0x20,0x40,0x60,0xb0,0xf0};
    uint32_t before[7],after[7];slrng_mac_checks=slrng_mac_failures=0;
    for(unsigned m=0;m<6;m++){
        __asm__ volatile("move.l #0,%%macsr\\n\\t"
            "move.l #0x12345678,%%acc0\\n\\tmove.l #0xfedcba98,%%acc1\\n\\t"
            "move.l #0x89abcdef,%%acc2\\n\\tmove.l #0x76543210,%%acc3\\n\\t"
            "move.l #0xdeadbeef,%%accext01\\n\\tmove.l #0xabcdef01,%%accext23\\n\\t"
            "move.l %0,%%macsr" :: "d"(modes[m]) : "cc","memory");
        slrng_capture(before);placement_frame();slrng_capture(after);
        for(unsigned k=0;k<7;k++){slrng_mac_checks++;if(before[k]!=after[k])slrng_mac_failures++;}
        if(pk_cf_slap_render(0,0,0,0,0)!=0)slrng_mac_failures++;
        slrng_capture(after);
        for(unsigned k=0;k<7;k++){slrng_mac_checks++;if(before[k]!=after[k])slrng_mac_failures++;}
    }
}
''')
  run(['m68k-elf-gcc',*flags,'-c',source,'-o',d/'slap.o'],variant+'-compile')
  command=[str(d/'slap.o') if v==str(BASE/'cf_slap.o') else str(d/'target.elf') if v==str(BASE/'target.elf') else v for v in template]+[str(w/f'helper{i}.o') for i in range(2)]
  command+=['-Wl,--undefined='+n for n in ('slrng_mac_probe','slrng_mac_checks','slrng_mac_failures')]
  run(command,variant+'-link');run(['m68k-elf-objcopy','-O','binary',d/'target.elf',d/'target.bin'],variant+'-binary')
  (d/'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm','-S',str(d/'target.elf')]));(d/'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump','-d',str(d/'target.elf')]))
  run([w/'runner',d,d/'assets'],variant+'-execute');groups={}
  for row in csv.DictReader((d/'costs.csv').open()):groups.setdefault(row['kind'],[]).append(int(row['cycles']))
  results[variant]=dict(execution=json.loads((d/'EXECUTION.json').read_text()),raw_MAC_register_checks=84,cost_cycles={k:dict(mean=sum(v)/len(v),maximum=max(v)) for k,v in groups.items()},source_sha256=sha(source),elf_sha256=sha(d/'target.elf'));print(variant,results[variant],flush=True)
 report=dict(status='PASS_EXACT_TARGET_NATIVE',scope='Standalone synthesis development; excludes stock ISR and DSP exchange',CPU_hz=264000000,results=results,commands=commands,input_sha256={str(q):sha(q) for q in (Path(__file__),Path(candidate.__file__),baseline,BASE/'native.dylib',runner,*[ROOT/q for q in helpers])})
 (w/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
