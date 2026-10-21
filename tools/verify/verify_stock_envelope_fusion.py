#!/usr/bin/env python3
"""Compare a guarded stock background fusion with actual PKFM17 target code."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


SEED = r'''
.text
.globl seed_emac
seed_emac:
 move.l #0,%macsr
 move.l 0x47030008,%d0
 move.l %d0,%acc0
 move.l 0x4703000c,%d0
 move.l %d0,%acc1
 move.l 0x47030010,%d0
 move.l %d0,%acc2
 move.l 0x47030014,%d0
 move.l %d0,%acc3
 move.l 0x47030018,%d0
 move.l %d0,%accext01
 move.l 0x4703001c,%d0
 move.l %d0,%accext23
 move.l 0x47030004,%d0
 move.l %d0,%mask
 move.l 0x47030000,%d0
 move.l %d0,%macsr
 rts
.globl read_emac
read_emac:
 move.l %macsr,%d0
 move.l %d0,0x47030100
 move.l %mask,%d0
 move.l %d0,0x47030104
 move.l #0,%macsr
 move.l %acc0,%d0
 move.l %d0,0x47030108
 move.l %acc1,%d0
 move.l %d0,0x4703010c
 move.l %acc2,%d0
 move.l %d0,0x47030110
 move.l %acc3,%d0
 move.l %d0,0x47030114
 move.l %accext01,%d0
 move.l %d0,0x47030118
 move.l %accext23,%d0
 move.l %d0,0x4703011c
 rts
.globl entry_patch
entry_patch:
 jmp pk_stock_envelope_fusion
 .rept 3
 nop
 .endr
'''

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
 ot::Machine m;HybridAlignment alignment;HybridPredictor predictor;std::map<std::string,unsigned> symbols;
 Target(const std::string&w,const std::string&image,bool patch):m(read(image)),alignment(m){
  m.mapRegion(0x45000000,0x10000);m.mapRegion(0x47000000,0x400000);m.mapRegion(0x80006000,0x6000);
  auto code=read(w+"/kernel.bin");for(unsigned i=0;i<code.size();i++)m.write8(0x45000000+i,code[i]);
  std::ifstream nm(w+"/kernel.nm");std::string line;while(std::getline(nm,line)){std::istringstream f(line);unsigned a;char kind;std::string name;if(f>>std::hex>>a>>kind>>name)symbols[name]=a;}
  if(patch)for(unsigned i=0;i<12;i++)m.write8(0x400984d2+i,m.read8(symbols.at("entry_patch")+i));
 }
 uint64_t run(unsigned begin,unsigned end){hybrid_alignment=&alignment;HybridAlignmentScope scope;uint64_t before=m.getCycles();m68k_set_reg(m.getCpuState(),M68K_REG_PC,begin);unsigned steps=0;while(m.pcFast()!=end){require(++steps<200000&&m.stepFast(),"target stopped at "+std::to_string(m.pcFast())+" "+m.why());}return m.getCycles()-before;}
 void call(const char*name){m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);m68k_set_reg(m.getCpuState(),M68K_REG_SP,0x47100000);m.write32(0x47100000,0x47200000);run(symbols.at(name),0x47200000);}
 Bytes bytes(unsigned at,unsigned n){Bytes b;for(unsigned i=0;i<n;i++)b.push_back(m.read8(at+i));return b;}
};
int main(int argc,char**argv){
 require(argc==3,"work image");std::string w=argv[1];HybridPredictor::selftest();
 Target original(w,argv[2],false),control(w,argv[2],false),candidate(w,argv[2],true);
 uint32_t seed=0x6ce273a1;auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
 std::ofstream csv(w+"/costs.csv");csv<<"case,count,mode,object,fast,original,candidate,saved\n";
 unsigned comparisons=0,fast_cases=0,fallback_cases=0;int64_t saved768=0;unsigned samples768=0;
 const unsigned modes[]={0,0x20,0x40,0x80,0xa0,0xc0};
 for(unsigned c=0;c<4096;c++){
  uint32_t regs[16],emac[8];for(auto&v:regs)v=rnd();for(auto&v:emac)v=rnd();
  unsigned n=c<1025?c:c%8==0?0xffffffffu:c%8==1?0x80000000u:c%8==2?0:768;
  unsigned mode=modes[c%6];emac[0]=mode|(rnd()&0xf00);
  unsigned object=c%7==0?0x80006940:c%7==1?0x80006a00:c%7==2?0x80006940+4*(rnd()%300):0x47010000;
  bool fast=n>0&&n<=768&&!(object+44>=0x8000695c&&object+44<0x8000796c);
  regs[10]=object;regs[15]=0x47100000;uint16_t sr=0x2700|(rnd()&31);
  std::vector<uint32_t> scratch(0x6000/4);for(auto&v:scratch)v=rnd();uint32_t object_data[32],stack[32];for(auto&v:object_data)v=rnd();for(auto&v:stack)v=rnd();
  if(c%11==0)for(auto&v:scratch)v=0;if(c%11==1)for(auto&v:scratch)v=0x80000000;if(c%11==2)for(auto&v:scratch)v=0x7fffffff;
  std::array<uint32_t,17> expected{};Bytes expected_memory,expected_emac;uint64_t cycles[3];
  Target*targets[]={&original,&control,&candidate};
  for(unsigned which=0;which<3;which++){
   auto&t=*targets[which];t.predictor.load();
   for(unsigned i=0;i<scratch.size();i++)t.m.write32(0x80006000+4*i,scratch[i]);
   for(unsigned i=0;i<32;i++){t.m.write32(object+4*i,object_data[i]);t.m.write32(0x47100000+4*i,stack[i]);}
   t.m.write32(0x47100000+48,n);for(unsigned i=0;i<8;i++)t.m.write32(0x47030000+4*i,emac[i]);t.call("seed_emac");
   m68k_set_reg(t.m.getCpuState(),M68K_REG_SR,sr);for(unsigned i=0;i<16;i++)m68k_set_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i),regs[i]);
   cycles[which]=t.run(0x400984d2,0x40098534);
   std::array<uint32_t,17> actual{};for(unsigned i=0;i<16;i++)actual[i]=m68k_get_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i));actual[16]=m68k_get_reg(t.m.getCpuState(),M68K_REG_SR);
   auto data=t.bytes(0x80006000,0x6000);for(auto [a,size]:{std::pair<unsigned,unsigned>{object,128},{0x47100000,128}}){auto q=t.bytes(a,size);data.insert(data.end(),q.begin(),q.end());}
   t.call("read_emac");auto mac=t.bytes(0x47030100,32);t.predictor.save();
   if(!which){expected=actual;expected_memory=data;expected_emac=mac;}
   else{
    if(actual!=expected){for(unsigned i=0;i<17;i++)if(actual[i]!=expected[i])std::cerr<<"reg "<<i<<" got "<<std::hex<<actual[i]<<" expected "<<expected[i]<<std::dec<<'\n';}
    require(actual==expected,"register/full CCR mismatch case "+std::to_string(c));
    require(data==expected_memory,"complete scratch/object/stack mismatch case "+std::to_string(c));
    require(mac==expected_emac,"full raw EMAC mismatch case "+std::to_string(c));
   }
  }
  require(cycles[0]==cycles[1],"same-image independent predictor cycle mismatch");
  int64_t delta=int64_t(cycles[0])-int64_t(cycles[2]);csv<<c<<','<<n<<','<<mode<<','<<object<<','<<fast<<','<<cycles[0]<<','<<cycles[2]<<','<<delta<<'\n';
  if(c>=2048&&n==768&&fast&&mode==0xa0){saved768+=delta;samples768++;}comparisons++;if(fast)fast_cases++;else fallback_cases++;
 }
 original.alignment.finish(w+"/original-alignment.json");control.alignment.finish(w+"/control-alignment.json");candidate.alignment.finish(w+"/candidate-alignment.json");
 std::ofstream result(w+"/EXECUTION.json");result<<"{\"status\":\"PASS_ACTUAL_STOCK_SPAN_REGS_CCR_EMAC_ALL_MEMORY\",\"cases\":"<<comparisons<<",\"fast_cases\":"<<fast_cases<<",\"fallback_cases\":"<<fallback_cases<<",\"same_image_cycle_controls\":true,\"mean_saved_cycles_768_fractional\":"<<double(saved768)/samples768<<",\"samples_768_fractional\":"<<samples768<<"}\n";
 std::cout<<"PASS "<<comparisons<<" cases\n";
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, default=ROOT/'out/perky/hybrid/stock-common-v1')
    parser.add_argument('--image', type=Path, default=ROOT/'out/perky/hybrid/full-map-packet-reserve-v2/probe/mainos_PKFM17.bin')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    genpath = ROOT/'tools/perky/generate_stock_envelope_fusion.py'
    gen = module('envelope_generator', genpath)
    generated = gen.generate(work)
    image = args.image.resolve()
    blob = image.read_bytes()
    assert blob[gen.SITE['address']-gen.BASE:gen.SITE['end']-gen.BASE] == gen.expected_span()
    commands = []

    def run(command):
        command = list(map(str, command)); commands.append(command)
        subprocess.run(command, cwd=ROOT, check=True)

    seed = work/'seed.s'; seed.write_text(SEED)
    run(['m68k-elf-gcc', '-mcpu=54455', '-c', generated['path'], '-o', work/'kernel.o'])
    run(['m68k-elf-gcc', '-mcpu=54455', '-c', seed, '-o', work/'seed.o'])
    run(['m68k-elf-gcc', '-mcpu=54455', '-nostdlib', '-Ttext=0x45000000', work/'kernel.o', work/'seed.o', '-o', work/'kernel.elf'])
    run(['m68k-elf-objcopy', '-O', 'binary', work/'kernel.elf', work/'kernel.bin'])
    for suffix, tool, flags in [('nm','m68k-elf-nm',['-n']), ('dis','m68k-elf-objdump',['-d'])]:
        (work/f'kernel.{suffix}').write_bytes(subprocess.check_output([tool,*flags,str(work/'kernel.elf')]))
    runner = work/'runner.cpp'; runner.write_text(RUNNER)
    build = json.loads((ROOT/'out/perky/hybrid/cf-placement/BUILD.json').read_text())
    oldsource = str(ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp')
    command = next(c for c in build['commands'] if oldsource in c)
    command = [str(runner) if v == oldsource else v for v in command]
    command[command.index('-o')+1] = str(work/'runner'); run(command)
    run([work/'runner', work, image])
    result = json.loads((work/'EXECUTION.json').read_text())
    paths = [Path(__file__), genpath, seed, runner, work/'runner', work/'kernel.elf', image,
             ROOT/'tools/emu/ot_emu/v4e.cpp', ROOT/'tools/harness/perky_cf/hybrid_cf_predictor.hpp']
    result.update(source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  commands=commands, generator=generated,
                  limits=['Actual stock span and separately linked CF helper, not yet an integrated full image.',
                          'Model cycle saving per invocation does not establish the invocation frequency or hardware saving.'])
    (work/'RESULT.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
