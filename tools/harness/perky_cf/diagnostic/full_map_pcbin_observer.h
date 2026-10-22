#pragma once
// Diagnostic, read-only: steady ISR cycles by PC inside [CF_PCBIN_LO,
// CF_PCBIN_HI), attributed to the instruction that was executing (the last
// step's PC), with everything outside the range in one bucket. Per-instruction
// costs of runtime code under the real workload, where cf_cycle_bench sees
// only captured vectors. CF_PCBIN_REPORT names the JSON report. Not an
// admission instrument.
namespace full_map_pcbin {
struct Observer {
 std::map<unsigned,uint64_t> pcs;uint64_t outside=0;unsigned lo=0,hi=0;
 uint64_t last_cycle=0,observed=0;unsigned last_pc=0;bool active=false,last_irq=false,enabled=false;
 Observer(){const char*r=std::getenv("CF_PCBIN_REPORT");enabled=r!=nullptr;
  if(enabled){lo=std::strtoul(std::getenv("CF_PCBIN_LO"),nullptr,0);hi=std::strtoul(std::getenv("CF_PCBIN_HI"),nullptr,0);}}
 template<class M>void step(M&m,unsigned pc){
  if(!enabled)return;auto&h=hybrid_safety::observer;auto now=m.getCycles();
  if(active&&last_irq){auto d=now-last_cycle;if(last_pc>=lo&&last_pc<hi)pcs[last_pc]+=d;else outside+=d;}
  active=h.returns>=512;last_irq=h.frames>h.returns;last_cycle=now;last_pc=pc;observed=h.returns;
 }
 ~Observer(){if(!enabled)return;std::ofstream f(std::getenv("CF_PCBIN_REPORT"));
  f<<"{\"completed_ISR\":"<<observed<<",\"exclude_first_ISR\":512,\"outside\":"<<outside<<",\"pcs\":{";bool s=false;
  for(auto&v:pcs){char k[16];std::snprintf(k,sizeof k,"0x%08x",v.first);f<<(s?",":"")<<'"'<<k<<"\":"<<v.second;s=true;}f<<"}}\n";
 }
};inline Observer observer;
}
