#pragma once
// Diagnostic, read-only: steady ISR cycles by 256-byte stock PC bin, the
// remainder of the stock time that full_map_track_observer.h could not place
// in a per-track context. Runtime code (>= 0x40c00000) is one bucket.
// CF_STOCKPC_REPORT names the JSON report. Not an admission instrument.
namespace full_map_stockpc {
struct Observer {
 std::map<unsigned,uint64_t> bins;uint64_t runtime=0;
 uint64_t last_cycle=0,observed=0;unsigned last_pc=0;bool active=false,last_irq=false,enabled=false;
 Observer(){enabled=std::getenv("CF_STOCKPC_REPORT")!=nullptr;}
 template<class M>void step(M&m,unsigned pc){
  if(!enabled)return;auto&h=hybrid_safety::observer;auto now=m.getCycles();
  if(active&&last_irq){auto d=now-last_cycle;if(last_pc>=0x40c00000u)runtime+=d;else bins[last_pc&~0xffu]+=d;}
  active=h.returns>=512;last_irq=h.frames>h.returns;last_cycle=now;last_pc=pc;observed=h.returns;
 }
 ~Observer(){if(!enabled)return;std::ofstream f(std::getenv("CF_STOCKPC_REPORT"));
  f<<"{\"completed_ISR\":"<<observed<<",\"exclude_first_ISR\":512,\"runtime\":"<<runtime<<",\"bins\":{";bool s=false;
  for(auto&v:bins){char k[16];std::snprintf(k,sizeof k,"0x%08x",v.first);f<<(s?",":"")<<'"'<<k<<"\":"<<v.second;s=true;}f<<"}}\n";
 }
};inline Observer observer;
}
