#!/usr/bin/env python3
"""Execute the CF converter assembly against the original complete C adapter."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'out/perky/hybrid/noise-hat-asm';BASE=ROOT/'out/perky/hybrid/cf-placement'
sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')]
import generate_cf_final as gcc
import generate_noise_hat_handoff_clock as clock
import generate_noise_hat_handoff_renderer as renderer
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 W.mkdir(exist_ok=True)
 for n in ('assets','native.dylib'):
  p=W/n
  if not p.exists():p.symlink_to(BASE/n,target_is_directory=(BASE/n).is_dir())
 table=W/'table.h';clock.generate(table)
 header=W/'resample.h';header.write_text((ROOT/'modules/perky/noise_hat_handoff_resample.h').read_text())
 engine=W/'engine.c';engine.write_text('#define NHB_CLOCK_TABLE "'+str(table)+'"\n#include "'+str(header)+'"\n'+(ROOT/'tools/harness/perky_cf/placement_cf_engine.c').read_text()+'''
pk_cf_native_clock nhb_test_clock;int16_t nhb_test_data[20];int32_t nhb_test_out[16];uint32_t nhb_test_n;
void nhb_test_convert(void){pk_nhb_native_convert_fast(&nhb_test_clock,nhb_test_data,nhb_test_n,nhb_test_out);}
''')
 hat=W/'hat.c';renderer.generate(hat);commands=[]
 def run(c):
  c=list(map(str,c));commands.append(c);subprocess.run(c,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for source,name in ((engine,'engine'),(hat,'hat')):run(['m68k-elf-gcc',*gcc.FLAGS,'-ffunction-sections','-fdata-sections','-I',ROOT/'modules/perky','-c',source,'-o',W/(name+'.o')])
 asm=ROOT/'modules/perky/noise_hat_handoff_resample.s';run(['m68k-elf-gcc','-mcpu=54455','-c',asm,'-o',W/'resample.o'])
 build=json.loads((BASE/'BUILD.json').read_text());link=next(c for c in build['commands'] if '-nostdlib' in c)
 command=[str(W/'engine.o') if v==str(BASE/'placement_cf_engine.o') else str(W/'hat.o') if v==str(BASE/'cf_noise_hat.o') else str(W/'target.elf') if v==str(BASE/'target.elf') else v for v in link]
 command += [str(W/'resample.o'),*['-Wl,--undefined='+n for n in ('nhb_test_clock','nhb_test_data','nhb_test_out','nhb_test_n','nhb_test_convert')]];run(command)
 run(['m68k-elf-objcopy','-O','binary',W/'target.elf',W/'target.bin']);(W/'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm','-S',str(W/'target.elf')]))
 (W/'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump','-d',str(W/'target.elf')]))
 original=ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp';text=original.read_text();start=text.index('    for(unsigned voice=0;voice<2;voice++)');end=text.index('    csv.close();',start)
 text=text[:start]+'''    for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
     std::array<unsigned,4>a{9,9,8,5},m{1,2,0,mode};
     run("solo",8,a,m,128,corner,false);run("solo",8,a,m,128,corner,true);run("layout",15,a,m,128,corner,true);
    }
    uint32_t seed=0x83ab1391,checks=0;
    for(unsigned phase=0;phase<147;phase++)for(unsigned have=0;have<2;have++)for(unsigned n=0;n<=16;n++)for(unsigned kind=0;kind<8;kind++){
     int16_t data[20];int32_t want[16];pk_cf_native_clock c{phase,have,-123};
     for(unsigned k=0;k<20;k++){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;data[k]=kind==0?-32768:kind==1?32767:kind==2?(k&1?-32768:32767):int16_t(seed);}
     pk_cf_native_convert(&c,data,n,want);
     unsigned at=t.at("nhb_test_clock");t.m.write32(at,phase);t.m.write32(at+4,have);t.m.write32(at+8,uint32_t(-123));t.m.write32(t.at("nhb_test_n"),n);
     for(unsigned k=0;k<20;k++)t.m.write16(t.at("nhb_test_data")+2*k,uint16_t(data[k]));
     for(unsigned k=0;k<6;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k),0x12340000+k);
     for(unsigned k=0;k<5;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k),0x47010000+16*k);
     t.call("nhb_test_convert");
     require(t.m.read32(at)==c.phase&&t.m.read32(at+4)==c.have&&t.m.read32(at+8)==uint32_t(c.carry),"CF assembly clock mismatch");
     for(unsigned k=0;k<n;k++)require(t.m.read32(t.at("nhb_test_out")+4*k)==uint32_t(want[k]),"CF assembly PCM mismatch");
     for(unsigned k=0;k<6;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k))==0x12340000+k,"CF assembly D ABI");
     for(unsigned k=0;k<5;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k))==0x47010000+16*k,"CF assembly A ABI");checks++;
    }
    std::ofstream cfproof(work+"/ASM_CLOCK.json");cfproof<<"{\\"cases\\":"<<checks<<",\\"status\\":\\"PASS_TARGET_PCM_CLOCK_CALLEE_REGISTERS\\"}\\n";
'''+text[end:]
 text='#include "'+str(ROOT/'modules/perky/cf_native_clock.h')+'"\n'+text
 runner=W/'runner.cpp';runner.write_text(text)
 template=next(c for c in build['commands'] if str(original) in c);command=list(template);command[command.index(str(original))]=str(runner);command[command.index('-o')+1]=str(W/'runner');run(command)
 with (W/'execute.log').open('w') as f:subprocess.run([str(W/'runner'),str(W),str(W/'assets')],check=True,stdout=f,stderr=subprocess.STDOUT)
 proof=json.loads((W/'ASM_CLOCK.json').read_text());assert proof['cases']==39984
 execution=json.loads((W/'EXECUTION.json').read_text());execution['algorithm_layouts']=1;execution['mode_rows']=3
 paths=[Path(__file__),asm,engine,hat,table,header,runner,W/'runner',ROOT/'modules/perky/cf_native_clock.h',ROOT/'tools/perky/generate_noise_hat_handoff_clock.py',ROOT/'tools/perky/generate_noise_hat_handoff_renderer.py',BASE/'native.dylib',*BASE.glob('*.o'),*sorted((BASE/'assets').glob('*.bin'))]
 report=dict(status='PASS_TARGET_ASSEMBLY_CLOCK_PCM_ABI_AND_COMBINED_SOURCE',clock=proof,execution=execution,target_elf_sha256=sha(W/'target.elf'),input_sha256={str(p):sha(p) for p in paths},commands=commands)
 (W/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],clock=proof,execution=execution)))
if __name__=='__main__':main()
