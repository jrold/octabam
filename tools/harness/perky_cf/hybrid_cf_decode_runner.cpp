#include "machine.h"
#include "hybrid_cf_alignment.hpp"
#include "mc68k/Musashi/m68k.h"
#include "mc68k/cpuState.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <map>
#include <vector>
#include <algorithm>
#include <stdexcept>
static std::vector<uint8_t> read(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("read "+p);return {std::istreambuf_iterator<char>(f),{}};}
static void load(ot::Machine&m,const std::vector<uint8_t>&b,uint32_t a){for(unsigned i=0;i<b.size();i++)m.write8(a+i,b[i]);}
struct Cost {uint64_t cycles,instructions;uint32_t stack;};
const uint32_t SP=0x47100000, END=0x47200000;
static Cost call(ot::Machine&m,uint32_t pc){HybridAlignmentScope alignment_scope;m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);m68k_set_reg(m.getCpuState(),M68K_REG_SP,SP);m68k_set_reg(m.getCpuState(),M68K_REG_PC,pc);m.write32(SP,END);uint64_t before=m.getCycles(),n=0;uint32_t lo=SP;while(m.pcFast()!=END){if(++n>100000000||!m.stepFast())throw std::runtime_error("target call stopped: "+m.why()+" PC="+std::to_string(m.pcFast()));lo=std::min(lo,m68k_get_reg(m.getCpuState(),M68K_REG_SP));}if(m.getCycles()<before)throw std::runtime_error("cycles underflow");if(m68k_get_reg(m.getCpuState(),M68K_REG_SP)!=SP+4)throw std::runtime_error("stack ABI");return {m.getCycles()-before,n,SP-lo};}
int main(int argc,char**argv){if(argc!=3)return 2;std::string out=argv[1],ad=argv[2];std::map<std::string,uint32_t>s;std::ifstream nm(out+"/decode.nm");std::string line;while(getline(nm,line)){std::istringstream f(line);uint32_t a,z;char t;std::string n;if(f>>std::hex>>a>>z>>t>>n)s[n]=a;}ot::Machine m(read(out+"/decode.bin"));HybridAlignment alignment(m);hybrid_alignment=&alignment;auto packed=read(out+"/packed.pkr");load(m,packed,0x45000000);m.write32(s["packed_bytes"],packed.size());for(unsigned i=0;i<200704;i++)m.write8(0x45100000+i,0xa5);auto cost=call(m,s["bench_decode"]);std::vector<uint8_t> expected=read(ad+"/wt_base.bin"),bank=read(ad+"/wt_bank.bin");expected.insert(expected.end(),bank.begin(),bank.end());std::vector<uint8_t>got(expected.size());unsigned mismatches=0,swapped=0;for(unsigned i=0;i<got.size();i++){got[i]=m.read8(0x45100000+i);mismatches+=got[i]!=expected[i];swapped+=got[i]!=expected[i^1u];}std::ofstream raw(out+"/decoded-target.bin",std::ios::binary);raw.write((const char*)got.data(),got.size());std::ofstream report(out+"/decode-result.json");report<<"{\"status\":"<<m.read32(s["decode_status"])<<",\"bytes\":"<<got.size()<<",\"byte_mismatches\":"<<mismatches<<",\"byte_swapped_mismatches\":"<<swapped<<",\"cycles\":"<<cost.cycles<<",\"instructions\":"<<cost.instructions<<",\"stack_bytes\":"<<cost.stack<<"}\n";std::cout<<"target PKR1 decode: status="<<m.read32(s["decode_status"])<<" bytes="<<got.size()<<" exact_mismatches="<<mismatches<<" swapped_mismatches="<<swapped<<" cycles="<<cost.cycles<<" stack="<<cost.stack<<"\n";alignment.finish(out+"/decode-alignment.json");return mismatches?1:0;}
