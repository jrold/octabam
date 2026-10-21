#!/usr/bin/env python3
"""Execute stock packed-source mixer versus guarded unroll in local CF targets."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


RUNNER = r'''
#include "machine.h"
#include "hybrid_cf_alignment.hpp"
#include "hybrid_cf_predictor.hpp"
#include "mc68k/Musashi/m68k.h"
#include "mc68k/cpuState.h"
#include <array>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>
using Bytes=std::vector<uint8_t>;
static Bytes read(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error(p);return {std::istreambuf_iterator<char>(f),{}};}
static void require(bool ok,const std::string&s){if(!ok)throw std::runtime_error(s);}
struct Target{
 ot::Machine m;HybridAlignment alignment;HybridPredictor predictor;std::map<std::string,unsigned> symbols;bool patched;
 Target(const std::string&w,const std::string&image,bool patch):m(read(image)),alignment(m),patched(patch){
  m.mapRegion(0x45000000,0x10000);m.mapRegion(0x47000000,0x400000);
  auto code=read(w+"/kernel.bin");for(unsigned i=0;i<code.size();i++)m.write8(0x45000000+i,code[i]);
  std::ifstream nm(w+"/kernel.nm");std::string line;while(std::getline(nm,line)){std::istringstream f(line);unsigned a;char kind;std::string name;if(f>>std::hex>>a>>kind>>name)symbols[name]=a;}
  if(patch)for(unsigned i=0;i<12;i++)m.write8(0x4000cc02+i,m.read8(symbols.at("entry_patch")+i));
 }
 uint64_t run(unsigned begin,unsigned end,unsigned bounded=0){hybrid_alignment=&alignment;HybridAlignmentScope scope;uint64_t before=m.getCycles();m68k_set_reg(m.getCpuState(),M68K_REG_PC,begin);unsigned steps=0,bodies=0;bool started=false;unsigned body=patched?symbols.at("pk_stock_source_mix_fallback_body"):0x4000cc02;
  while(m.pcFast()!=end){if(bounded&&m.pcFast()==body){if(started&&++bodies==bounded)break;started=true;}require(++steps<100000&&m.stepFast(),"target stopped "+m.why());}return m.getCycles()-before;}
 void call(const char*name){m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);m68k_set_reg(m.getCpuState(),M68K_REG_SP,0x47100000);m.write32(0x47100000,0x47200000);run(symbols.at(name),0x47200000);}
 Bytes bytes(unsigned at,unsigned n){Bytes b;for(unsigned i=0;i<n;i++)b.push_back(m.read8(at+i));return b;}
};
int main(int argc,char**argv){
 require(argc==3,"work image");std::string w=argv[1];HybridPredictor::selftest();
 Target original(w,argv[2],false),control(w,argv[2],false),candidate(w,argv[2],true);
 uint32_t seed=0x37e8cb61;auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
 std::ofstream csv(w+"/costs.csv");csv<<"case,count,mode,alias,original,candidate,saved,bounded\n";
 const unsigned modes[]={0,0x20,0x40,0x60,0x80,0xa0,0xb0,0xc0};const int offsets[]={-64,-4,0,2,4,16,64,0x8000};
 int64_t saved6=0,saved9=0;unsigned samples6=0,samples9=0,fast_cases=0,fallback_cases=0,bounded_cases=0;
 for(unsigned c=0;c<4096;c++){
  unsigned n=c<1024?1+c%32:c%16==0?0:c%16==1?0xffffffffu:c%16==2?0x80000000u:c%2?6:9;
  unsigned bounded=(n==0||int32_t(n)<0)?16:0;unsigned mode=modes[(c/32)%8];int offset=offsets[(c/8)%8];
  uint32_t regs[16],emac[8];for(auto&v:regs)v=rnd();for(auto&v:emac)v=rnd();emac[0]=mode|(rnd()&0xf00);emac[1]=rnd()&0xffff;
  regs[1]=n;regs[9]=0x47000100+offset;regs[11]=0x47000100;regs[15]=0x47100000;if(c%3==0)regs[7]=0x80000012;
  uint16_t sr=0x2700|(rnd()&31);std::vector<uint32_t> memory(0x10000/4);for(auto&v:memory)v=rnd();
  if(c%11==0)for(auto&v:memory)v=0;if(c%11==1)for(auto&v:memory)v=0x80000000;if(c%11==2)for(auto&v:memory)v=0x7fffffff;
  std::array<uint32_t,17> expected{};Bytes expected_memory,expected_emac;uint64_t cycles[3];Target*targets[]={&original,&control,&candidate};
  for(unsigned which=0;which<3;which++){
   auto&t=*targets[which];t.predictor.load();for(unsigned i=0;i<memory.size();i++)t.m.write32(0x47000000+4*i,memory[i]);
   for(unsigned i=0;i<8;i++)t.m.write32(0x47030000+4*i,emac[i]);t.call("seed_emac");
   m68k_set_reg(t.m.getCpuState(),M68K_REG_SR,sr);for(unsigned i=0;i<16;i++)m68k_set_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i),regs[i]);
   cycles[which]=t.run(0x4000cc02,0x4000cc26,bounded);std::array<uint32_t,17> actual{};for(unsigned i=0;i<16;i++)actual[i]=m68k_get_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i));actual[16]=m68k_get_reg(t.m.getCpuState(),M68K_REG_SR);
   auto data=t.bytes(0x47000000,0x10000);t.call("read_emac");auto mac=t.bytes(0x47030100,32);t.predictor.save();
   if(!which){expected=actual;expected_memory=data;expected_emac=mac;}else{
    if(actual!=expected)for(unsigned i=0;i<17;i++)if(actual[i]!=expected[i])std::cerr<<"reg "<<i<<" got "<<std::hex<<actual[i]<<" expected "<<expected[i]<<std::dec<<'\n';
    require(actual==expected,"register/full CCR mismatch case "+std::to_string(c));require(data==expected_memory,"full source/destination/unused memory mismatch case "+std::to_string(c));require(mac==expected_emac,"full raw EMAC mismatch case "+std::to_string(c));
   }
  }
  require(cycles[0]==cycles[1],"same-image independent predictor cycles mismatch");int64_t delta=int64_t(cycles[0])-int64_t(cycles[2]);csv<<c<<','<<n<<','<<mode<<','<<offset<<','<<cycles[0]<<','<<cycles[2]<<','<<delta<<','<<bounded<<'\n';
  if(n==6||n==9)fast_cases++;else fallback_cases++;if(bounded)bounded_cases++;
  if(c>=2048&&mode==0xb0){if(n==6){saved6+=delta;samples6++;}if(n==9){saved9+=delta;samples9++;}}
 }
 original.alignment.finish(w+"/original-alignment.json");control.alignment.finish(w+"/control-alignment.json");candidate.alignment.finish(w+"/candidate-alignment.json");
 std::ofstream result(w+"/EXECUTION.json");result<<"{\"status\":\"PASS_ACTUAL_STOCK_SOURCE_MIX_REGS_CCR_EMAC_ALL_MEMORY\",\"cases\":4096,\"fast_cases\":"<<fast_cases<<",\"fallback_cases\":"<<fallback_cases<<",\"bounded_unterminated_fallback_cases\":"<<bounded_cases<<",\"same_image_cycle_controls\":true,\"mean_saved_cycles_6\":"<<double(saved6)/samples6<<",\"mean_saved_cycles_9\":"<<double(saved9)/samples9<<",\"samples6\":"<<samples6<<",\"samples9\":"<<samples9<<"}\n";
 std::cout<<"PASS4096cases\n";
}
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/stock-source-mix-v1')
    parser.add_argument('--image',type=Path,default=ROOT/'out/perky/hybrid/full-map-packet-reserve-v2/probe/mainos_PKFM17.bin')
    args=parser.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    genpath=ROOT/'tools/perky/generate_stock_source_mix_unroll.py';gen=module('source_mix_generator',genpath);generated=gen.generate(work)
    emac=module('stock_emac_proof',ROOT/'tools/verify/verify_stock_envelope_fusion.py')
    image=args.image.resolve();blob=image.read_bytes();assert blob[gen.SITE['address']-gen.BASE:gen.SITE['end']-gen.BASE]==gen.expected_span()
    commands=[]
    def run(command):
        command=list(map(str,command));commands.append(command);subprocess.run(command,cwd=ROOT,check=True)
    seed=work/'seed.s';seed.write_text(emac.SEED.replace('pk_stock_envelope_fusion','pk_stock_source_mix_unroll'))
    run(['m68k-elf-gcc','-mcpu=54455','-c',generated['path'],'-o',work/'kernel.o']);run(['m68k-elf-gcc','-mcpu=54455','-c',seed,'-o',work/'seed.o'])
    run(['m68k-elf-gcc','-mcpu=54455','-nostdlib','-Ttext=0x45000000',work/'kernel.o',work/'seed.o','-o',work/'kernel.elf']);run(['m68k-elf-objcopy','-O','binary',work/'kernel.elf',work/'kernel.bin'])
    for suffix,tool,flags in [('nm','m68k-elf-nm',['-n']),('dis','m68k-elf-objdump',['-d'])]:(work/f'kernel.{suffix}').write_bytes(subprocess.check_output([tool,*flags,str(work/'kernel.elf')]))
    runner=work/'runner.cpp';runner.write_text(RUNNER);build=json.loads((ROOT/'out/perky/hybrid/cf-placement/BUILD.json').read_text());oldsource=str(ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp');command=next(c for c in build['commands'] if oldsource in c);command=[str(runner) if v==oldsource else v for v in command];command[command.index('-o')+1]=str(work/'runner');run(command);run([work/'runner',work,image])
    result=json.loads((work/'EXECUTION.json').read_text());paths=[Path(__file__),genpath,Path(emac.__file__),seed,runner,work/'runner',work/'kernel.elf',image,ROOT/'tools/emu/ot_emu/v4e.cpp',ROOT/'tools/harness/perky_cf/hybrid_cf_predictor.hpp']
    result.update(source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},commands=commands,generator=generated,
                  limits=['Actual stock loop and separately linked helper; full combined image qualification remains required.',
                          'Zero/negative loop counts preserve the original nonterminating recurrence for16bodies; no early return is introduced.'])
    (work/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
