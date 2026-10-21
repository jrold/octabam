#!/usr/bin/env python3
"""Execute guarded stock DELAY loop unrolls against their actual stock bytes."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/stock-delay-unroll'
ASSEMBLY=ROOT/'tools/harness/perky_cf/stock_delay_unroll.s'
BASE=ROOT/'out/perky/hybrid/cf-placement'

SEED=r'''
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
.globl mix_patch
mix_patch: jmp pk_stock_delay_mix16
 nop
.globl forward_patch
forward_patch: jmp pk_stock_delay_filter16_forward
 nop
.globl interleaved_patch
interleaved_patch: jmp pk_stock_delay_filter16_interleaved
 nop
'''

RUNNER=r'''
#include "machine.h"
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
 ot::Machine m;HybridPredictor predictor;std::map<std::string,unsigned> symbols;
 Target(const std::string&w,const std::string&image,bool patch):m(read(image)){
  m.mapRegion(0x45000000,0x10000);m.mapRegion(0x47000000,0x200000);
  auto code=read(w+"/kernel.bin");for(unsigned i=0;i<code.size();i++)m.write8(0x45000000+i,code[i]);
  std::ifstream nm(w+"/kernel.nm");std::string line;while(std::getline(nm,line)){std::istringstream f(line);unsigned a;char kind;std::string name;if(f>>std::hex>>a>>kind>>name)symbols[name]=a;}
  if(patch){unsigned entries[]={0x40003738,0x40003664,0x400036aa};const char*names[]={"mix_patch","forward_patch","interleaved_patch"};for(unsigned j=0;j<3;j++)for(unsigned i=0;i<8;i++)m.write8(entries[j]+i,m.read8(symbols.at(names[j])+i));}
 }
 uint64_t run(unsigned begin,unsigned end){uint64_t before=m.getCycles();m68k_set_reg(m.getCpuState(),M68K_REG_PC,begin);unsigned steps=0;while(m.pcFast()!=end){require(++steps<100000&&m.stepFast(),"target stopped at "+std::to_string(m.pcFast())+" "+m.why());}return m.getCycles()-before;}
 void call(const char*name){m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);m68k_set_reg(m.getCpuState(),M68K_REG_SP,0x47100000);m.write32(0x47100000,0x47200000);run(symbols.at(name),0x47200000);}
 Bytes bytes(unsigned at,unsigned n){Bytes b;for(unsigned i=0;i<n;i++)b.push_back(m.read8(at+i));return b;}
};
int main(int argc,char**argv){
 require(argc==3,"work image");std::string w=argv[1];HybridPredictor::selftest();
 Target original(w,argv[2],false),control(w,argv[2],false),candidate(w,argv[2],true);
 uint32_t seed=0xbad73591;auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
 std::ofstream csv(w+"/costs.csv");csv<<"kind,case,count,original,candidate,saved\n";
 unsigned comparisons=0;uint64_t saved[3]={},samples[3]={};
 for(unsigned kind=0;kind<3;kind++)for(unsigned c=0;c<1024;c++){
  uint32_t regs[16],emac[8];for(auto&v:regs)v=rnd();for(auto&v:emac)v=rnd();
  emac[0]=0xa0;unsigned n=c<256?1+c%32:16;
  int32_t step=int32_t(rnd()%200001)-100000;if(!step)step=1;
  regs[8]=0x47000000;regs[15]=0x47100000;
  if(kind==0){regs[2]=n;regs[9]=0x47010004;}
  else{regs[3]=uint32_t(step);regs[5]=uint32_t(step)*n;regs[13]=0x47010000;}
  uint16_t sr=0x2700|(rnd()&31);uint32_t memory[256];for(auto&v:memory)v=rnd();
  unsigned entry=kind==0?0x40003738:kind==1?0x40003664:0x400036aa;
  unsigned end=kind==0?0x4000377a:0x400036ee;
  std::array<uint32_t,17> expected{};Bytes expected_memory,expected_emac;uint64_t cycles[3];
  Target*targets[]={&original,&control,&candidate};
  for(unsigned which=0;which<3;which++){
   auto&t=*targets[which];t.predictor.load();
   for(unsigned i=0;i<128;i++){t.m.write32(0x47000000+4*i,memory[i]);t.m.write32(0x47010000+4*i,memory[128+i]);}
   for(unsigned i=0;i<8;i++)t.m.write32(0x47030000+4*i,emac[i]);t.call("seed_emac");
   m68k_set_reg(t.m.getCpuState(),M68K_REG_SR,sr);
   for(unsigned i=0;i<16;i++)m68k_set_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i),regs[i]);
   cycles[which]=t.run(entry,end);
   std::array<uint32_t,17> actual{};for(unsigned i=0;i<16;i++)actual[i]=m68k_get_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i));actual[16]=m68k_get_reg(t.m.getCpuState(),M68K_REG_SR);
   auto data=t.bytes(0x47000000,512);auto audio=t.bytes(0x47010000,512);data.insert(data.end(),audio.begin(),audio.end());
   t.call("read_emac");auto mac=t.bytes(0x47030100,32);t.predictor.save();
   if(!which){expected=actual;expected_memory=data;expected_emac=mac;}
   else{
    require(actual==expected,"register/architectural SR mismatch kind "+std::to_string(kind)+" case "+std::to_string(c));
    require(data==expected_memory,"complete audio/ring memory mismatch");require(mac==expected_emac,"full raw EMAC state mismatch");
   }
  }
  require(cycles[0]==cycles[1],"same-image independent predictor cycle mismatch");
  int64_t delta=int64_t(cycles[0])-int64_t(cycles[2]);csv<<kind<<','<<c<<','<<n<<','<<cycles[0]<<','<<cycles[2]<<','<<delta<<'\n';
  if(c>=512){saved[kind]+=delta;samples[kind]++;}comparisons++;
 }
 std::ofstream result(w+"/EXECUTION.json");result<<"{\"status\":\"PASS_ACTUAL_STOCK_DELAY_REGS_SR_EMAC_AUDIO_RING\",\"cases\":"<<comparisons<<",\"same_image_cycle_controls\":true,\"steady_saved_cycles\":[";
 for(unsigned k=0;k<3;k++)result<<(k?",":"")<<double(int64_t(saved[k]))/samples[k];result<<"]}\n";
 std::cout<<"PASS "<<comparisons<<" cases\n";
}
'''

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 WORK.mkdir(parents=True,exist_ok=True);commands=[]
 def run(args):
  args=list(map(str,args));commands.append(args);subprocess.run(args,cwd=ROOT,check=True)
 seed=WORK/'seed.s';seed.write_text(SEED)
 run(['m68k-elf-gcc','-mcpu=54455','-c',ASSEMBLY,'-o',WORK/'kernel.o'])
 run(['m68k-elf-gcc','-mcpu=54455','-c',seed,'-o',WORK/'seed.o'])
 run(['m68k-elf-gcc','-mcpu=54455','-nostdlib','-Ttext=0x45000000',WORK/'kernel.o',WORK/'seed.o','-o',WORK/'kernel.elf'])
 run(['m68k-elf-objcopy','-O','binary',WORK/'kernel.elf',WORK/'kernel.bin'])
 (WORK/'kernel.nm').write_bytes(subprocess.check_output(['m68k-elf-nm','-n',str(WORK/'kernel.elf')]))
 (WORK/'kernel.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump','-d',str(WORK/'kernel.elf')]))
 runner=WORK/'runner.cpp';runner.write_text(RUNNER)
 build=json.loads((BASE/'BUILD.json').read_text());original=str(ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp')
 command=next(c for c in build['commands'] if original in c);command=[str(runner) if v==original else v for v in command];command[command.index('-o')+1]=str(WORK/'runner');run(command)
 image=ROOT/'out/perky/hybrid/full-map-state-v4/probe/mainos_PKFM15.bin';run([WORK/'runner',WORK,image])
 result=json.loads((WORK/'EXECUTION.json').read_text());mix,forward,interleaved=result['steady_saved_cycles']
 result['profile_weighted_frame_saved_cycles']=8*mix+forward+7*interleaved
 result['profile_weighted_frame_saved_us']=result['profile_weighted_frame_saved_cycles']/264
 result['weights_basis']='Observed PKFM15 steady PCs:8 mix blocks,1 forward filter and7 interleaved filters per frame.'
 result['admission']='MEASURED_CANDIDATE' if result['profile_weighted_frame_saved_us']>1 else 'REJECT_BELOW_ONE_US_THRESHOLD'
 paths=[Path(__file__),ASSEMBLY,seed,runner,WORK/'runner',WORK/'kernel.elf',image,
        ROOT/'tools/emu/ot_emu/v4e.cpp',ROOT/'tools/harness/perky_cf/hybrid_cf_predictor.hpp']
 result.update(source_sha256={str(p):sha(p) for p in paths},commands=commands,
               limits=['Isolated actual-loop proof and measured model cycles; full eight-track stock ISR validation remains required before admission.'])
 (WORK/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
