#!/usr/bin/env python3
"""Execute hybrid CF delay blocks and full renderers against original C."""
import csv,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'out/perky/hybrid/cf-synthesis-asm';BASE=ROOT/'out/perky/hybrid/cf-placement'
sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')]
import generate_cf_final as gcc
import generate_noise_hat_handoff_clock as clock
import generate_noise_hat_handoff_renderer as metallic
import generate_cf_synthesis_asm as synthesis
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 W.mkdir(exist_ok=True)
 for name in ('assets','native.dylib'):
  p=W/name
  if not p.exists():p.symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
 table=W/'table.h';clock.generate(table)
 engine=W/'engine.c';engine.write_text('#define NHB_CLOCK_TABLE "'+str(table)+'"\n#include "'+str(ROOT/'modules/perky/noise_hat_handoff_resample.h')+'"\n'+(ROOT/'tools/harness/perky_cf/placement_cf_engine.c').read_text()+'''
extern void pk_cf_delay_block(int32_t*,uint8_t*,int32_t*,uint32_t);
int32_t synthesis_state[12],synthesis_samples[24];struct{uint8_t prefix[0x3f8],ring[4806*2];}synthesis_storage;uint32_t synthesis_n,synthesis_kind;
extern __attribute__((weak)) void pk_cf_nh_delay_dispatch(uint8_t*,void*,int16_t*,uint32_t);
extern void pk_cf_nh_delay_block(void*,uint8_t*,int32_t*,uint32_t);
extern void pk_cf_slap_delay_block(void*,uint8_t*,int32_t*,uint32_t);
void synthesis_test(void){
 if(!synthesis_kind)pk_cf_delay_block(synthesis_state,synthesis_storage.ring,synthesis_samples,synthesis_n);
 else if(synthesis_kind==1){struct{uint16_t delay[5],gain[5];uint32_t index;int32_t mix;}q;for(unsigned k=0;k<5;k++){q.delay[k]=synthesis_state[2+k];q.gain[k]=synthesis_state[7+k];}q.index=synthesis_state[0];q.mix=synthesis_state[1];pk_cf_nh_delay_block(&q,synthesis_storage.ring,synthesis_samples,synthesis_n);synthesis_state[0]=q.index;}
 else if(synthesis_kind==2){struct{uint16_t index,mix,delay[5],gain[5];}q;for(unsigned k=0;k<5;k++){q.delay[k]=synthesis_state[2+k];q.gain[k]=synthesis_state[7+k];}q.index=synthesis_state[0];q.mix=synthesis_state[1];pk_cf_slap_delay_block(&q,synthesis_storage.ring,synthesis_samples,synthesis_n);synthesis_state[0]=q.index;}
 else{struct{uint16_t delay[5],gain[5];uint32_t index;int32_t mix;}q;int16_t data[24];for(unsigned k=0;k<5;k++){q.delay[k]=synthesis_state[2+k];q.gain[k]=synthesis_state[7+k];}q.index=synthesis_state[0];q.mix=synthesis_state[1];for(unsigned k=0;k<24;k++)data[k]=(int16_t)synthesis_samples[k];if(pk_cf_nh_delay_dispatch)pk_cf_nh_delay_dispatch(synthesis_storage.prefix,&q,data,synthesis_n);else{pk_cf_delay_block(synthesis_state,synthesis_storage.ring,synthesis_samples,synthesis_n);for(unsigned k=0;k<synthesis_n;k++)synthesis_samples[k]=(int16_t)synthesis_samples[k];return;}synthesis_state[0]=q.index;for(unsigned k=0;k<synthesis_n;k++)synthesis_samples[k]=data[k];}
}
''')
 sources=synthesis.generate(W);commands=[]
 def run(cmd):
  cmd=list(map(str,cmd));commands.append(cmd);subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for path,name in [(engine,'engine'),(Path(sources['hat']),'hat'),(Path(sources['slap']),'slap')]:
  run(['m68k-elf-gcc',*gcc.FLAGS,'-ffunction-sections','-fdata-sections','-I',ROOT/'modules/perky','-c',path,'-o',W/(name+'.o')])
 for path,name in [(ROOT/'modules/perky/noise_hat_handoff_resample.s','resample'),(ROOT/'modules/perky/cf_synthesis_delay.s','delay'),(ROOT/'modules/perky/noise_hat_delay_i16.s','i16')]:run(['m68k-elf-gcc','-mcpu=54455',*(['-Wa,--defsym,CF_SYNTHESIS_TEST=1'] if name in ('delay','i16') else []),'-c',path,'-o',W/(name+'.o')])
 build=json.loads((BASE/'BUILD.json').read_text());template=next(c for c in build['commands'] if '-nostdlib' in c)
 original=ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp';text=original.read_text();
 text=text.replace('    Cost call(const std::string&s){','    uint64_t fast_entries=0,generic_entries=0;\n    Cost call(const std::string&s){')
 text=text.replace('while(m.pcFast()!=end){require(++n','unsigned fast_pc=symbols.count("pk_cf_nh_fast_marker")?at("pk_cf_nh_fast_marker"):0xffffffff,generic_pc=at("pk_cf_nh_delay_block");while(m.pcFast()!=end){if(m.pcFast()==fast_pc)fast_entries++;if(m.pcFast()==generic_pc)generic_entries++;require(++n')
 start=text.index('    for(unsigned voice=0;voice<2;voice++)');end=text.index('    csv.close();',start)
 text=text[:start]+'''    uint32_t seed=0x693df71,checks=0;
    auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
    auto clip=[](int32_t v){return v>32767?32767:v<-32767?-32767:v;};
    auto mul=[](int32_t a,int32_t b){return int32_t(uint32_t(a)*uint32_t(b));};
    auto add=[](int32_t a,int32_t b){return int32_t(uint32_t(a)+uint32_t(b));};
    const uint32_t edges[]={0,1,32767,32768,65535,0x7fffffff,0x80000000,0xffffffff,0xffff8001};
    int16_t ring[4806];unsigned ring_at=t.at("synthesis_storage")+0x3f8;
    for(unsigned k=0;k<4806;k++){ring[k]=int16_t(rnd());t.m.write8(ring_at+2*k,uint8_t(ring[k]));t.m.write8(ring_at+2*k+1,uint8_t(uint16_t(ring[k])>>8));}
    for(unsigned c=0;c<24220;c++)for(unsigned kind=0;kind<4;kind++){
      unsigned n=c%21;int32_t state[12],samples[24],want[24];
      state[0]=c%4805;state[1]=int16_t(c%3==0?edges[c%9]:rnd());
      for(unsigned k=0;k<5;k++){state[2+k]=c%3==0?(c+k)%4805:rnd()%4805;state[7+k]=rnd()&65535;}
      if(c%4<=1){const int delay[]={573,1201,1538,3139,4804},gain[]={1,1,3,5,7};for(unsigned k=0;k<5;k++){state[2+k]=delay[k];state[7+k]=gain[k];}if(c%4==1)state[2+(c/4)%10]^=1;}
      if(c==10000||c==20000){for(unsigned k=0;k<4806;k++){ring[k]=c==10000?32767:-32768;t.m.write8(ring_at+2*k,uint8_t(ring[k]));t.m.write8(ring_at+2*k+1,uint8_t(uint16_t(ring[k])>>8));}}
      for(unsigned k=0;k<24;k++)samples[k]=want[k]=int32_t(c%3==0?edges[(c+k)%9]:rnd());
      if(c==10000||c==20000)for(unsigned k=0;k<24;k++)samples[k]=want[k]=c==10000?-32768:32767;
      if(kind==3)for(unsigned k=0;k<24;k++)samples[k]=want[k]=int16_t(samples[k]);
      unsigned sa=t.at("synthesis_state"),da=t.at("synthesis_samples");for(unsigned k=0;k<12;k++)t.m.write32(sa+4*k,uint32_t(state[k]));for(unsigned k=0;k<24;k++)t.m.write32(da+4*k,uint32_t(samples[k]));
      for(unsigned k=0;k<n;k++){
       int32_t stage=samples[k];unsigned ix=state[0];
       for(unsigned tap=0;tap<5;tap++){unsigned ri=ix>=unsigned(state[2+tap])?ix-state[2+tap]:4805+ix-state[2+tap];stage=clip(add(mul(stage,state[7+tap]-16),mul(state[7+tap],ring[ri]))>>4);}
       state[0]=(ix+1)%4805;ring[state[0]]=int16_t(stage);
       want[k]=add(mul(samples[k],4095-state[1]),mul(state[1],mul(stage,5)>>1))>>12;if(kind==3)want[k]=int16_t(want[k]);
      }
      t.m.write32(t.at("synthesis_n"),n);t.m.write32(t.at("synthesis_kind"),kind);
      for(unsigned k=0;k<6;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k),0x12340000+k);
      for(unsigned k=0;k<5;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k),0x47010000+16*k);
      t.call("synthesis_test");for(unsigned k=0;k<12;k++)require(t.m.read32(sa+4*k)==uint32_t(state[k]),"delay state mismatch");for(unsigned k=0;k<24;k++)require(t.m.read32(da+4*k)==uint32_t(want[k]),"delay PCM/guard mismatch");
      for(unsigned k=0;k<4806;k++)require(t.m.read8(ring_at+2*k)==uint8_t(ring[k])&&t.m.read8(ring_at+2*k+1)==uint8_t(uint16_t(ring[k])>>8),"delay full ring/guard mismatch");
      for(unsigned k=0;k<6;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k))==0x12340000+k,"delay D ABI");for(unsigned k=0;k<5;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k))==0x47010000+16*k,"delay A ABI");checks++;
    }
    for(unsigned voice=0;voice<4;voice++)for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
      std::array<unsigned,4>a{9,9,8,5},m{1,2,0,1};m[voice]=mode;
      run("solo",1u<<voice,a,m,128,corner,false);run("solo",1u<<voice,a,m,128,corner,true);run("layout",15,a,m,128,corner,true);
    }
    std::ofstream proof(work+"/DELAY.json");proof<<"{\\"fast_entries\\":"<<t.fast_entries<<",\\"generic_entries\\":"<<t.generic_entries<<",\\"cases\\":"<<checks<<",\\"status\\":\\"PASS_TARGET_PCM_STATE_ABI\\"}\\n";
'''+text[end:]
 runner=W/'runner.cpp';runner.write_text(text)
 cmd=list(next(c for c in build['commands'] if str(original) in c));cmd[cmd.index(str(original))]=str(runner);cmd[cmd.index('-o')+1]=str(W/'runner');run(cmd)
 baselinehat=W/'baseline-hat.c';metallic.generate(baselinehat);run(['m68k-elf-gcc',*gcc.FLAGS,'-ffunction-sections','-fdata-sections','-I',ROOT/'modules/perky','-c',baselinehat,'-o',W/'baseline-hat.o'])
 results={}
 for variant in ('baseline','assembly'):
  d=W/variant;d.mkdir(exist_ok=True)
  for name in ('assets','native.dylib'):
   p=d/name
   if not p.exists():p.symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
  replacements={str(BASE/'placement_cf_engine.o'):str(W/'engine.o'),str(BASE/'cf_noise_hat.o'):str(W/('hat.o' if variant=='assembly' else 'baseline-hat.o')),str(BASE/'target.elf'):str(d/'target.elf')}
  if variant=='assembly':replacements[str(BASE/'cf_slap.o')]=str(W/'slap.o')
  cmd=[replacements.get(v,v) for v in template]+[str(W/'resample.o'),str(W/'delay.o'),str(W/'i16.o')]+['-Wl,--undefined='+n for n in ('synthesis_state','synthesis_samples','synthesis_storage','synthesis_n','synthesis_kind','synthesis_test')];run(cmd)
  run(['m68k-elf-objcopy','-O','binary',d/'target.elf',d/'target.bin']);(d/'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm','-S',str(d/'target.elf')]));(d/'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump','-d',str(d/'target.elf')]))
  with (d/'execute.log').open('w') as f:subprocess.run([str(W/'runner'),str(d),str(d/'assets')],check=True,stdout=f,stderr=subprocess.STDOUT)
  groups={}
  for row in csv.DictReader((d/'costs.csv').open()):groups.setdefault(row['kind']+'-mask'+row['mask']+'-'+row['modes'],[]).append(int(row['cycles']))
  results[variant]=dict(execution=dict(json.loads((d/'EXECUTION.json').read_text()),algorithm_layouts=1,mode_rows=12),delay=json.loads((d/'DELAY.json').read_text()),groups={k:dict(mean=sum(v)/len(v),max=max(v)) for k,v in groups.items()},elf_sha256=sha(d/'target.elf'))
 paths=[Path(__file__),ROOT/'tools/perky/generate_cf_synthesis_asm.py',ROOT/'modules/perky/cf_synthesis_delay.s',ROOT/'modules/perky/noise_hat_delay_i16.s',engine,runner,W/'runner',*W.glob('*.o'),*W.glob('*.c'),table,ROOT/'modules/perky/cf_slap.c',ROOT/'modules/perky/cf_noise_hat.c',ROOT/'modules/perky/noise_hat_handoff_resample.h',ROOT/'modules/perky/noise_hat_handoff_resample.s',BASE/'native.dylib',*BASE.glob('*.o'),*sorted((BASE/'assets').glob('*.bin'))]
 report=dict(status='PASS_EXACT_DELAY_AND_COMBINED_RENDERERS',results=results,input_sha256={str(p):sha(p) for p in paths},commands=commands)
 (W/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
