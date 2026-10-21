#pragma once
// Read-only attribution; keeps both the IRQ and real background worker visible.
namespace full_map_count {
struct Observer {
 std::map<unsigned,std::pair<unsigned,std::string>> ranges;
 std::map<std::string,uint64_t> irq,background;
 std::map<unsigned,uint64_t> irq_pc,background_pc;
 std::map<unsigned,uint64_t> entries;std::map<unsigned,std::string> entry_names;
 uint64_t last_cycle=0,observed=0,last_returns=0;unsigned last_pc=0;
 bool enabled=false,active=false,last_irq=false;
 Observer(){if(const char*p=std::getenv("CF_COUNT_SYMBOLS")){
  std::ifstream f(p);unsigned lo,hi;std::string name;
  while(f>>std::hex>>lo>>hi>>name){ranges[lo]={hi,name};if(name.find('@')==std::string::npos){entry_names[lo]=name;entries[lo]=0;}}enabled=true;
 }}
 std::string bucket(unsigned pc){auto i=ranges.upper_bound(pc);if(i!=ranges.begin()){
  --i;if(pc<i->second.first)return i->second.second;}
  return pc<0x40c00000?"stock":"runtime-other";
 }
 template<class M>void step(M&m,unsigned pc){
  if(!enabled)return;auto&h=hybrid_safety::observer;auto now=m.getCycles();
  if(active){auto d=now-last_cycle;auto&sum=last_irq?irq:background;
   auto&pcs=last_irq?irq_pc:background_pc;sum[bucket(last_pc)]+=d;pcs[last_pc]+=d;
  }
  if(h.returns>=512){auto e=entries.find(pc);if(e!=entries.end())e->second++;}
  active=h.returns>=512;last_irq=h.frames>h.returns;last_cycle=now;last_pc=pc;
  observed=h.returns;last_returns=h.returns;
 }
 void sums(std::ostream&f,const std::map<std::string,uint64_t>&r){
  bool sep=false;f<<'{';for(auto&v:r){f<<(sep?",":"")<<'"'<<v.first<<"\":"<<v.second;sep=true;}f<<'}';
 }
 void pcs(std::ostream&f,const std::map<unsigned,uint64_t>&r){
  std::vector<std::pair<uint64_t,unsigned>>v;for(auto&p:r)v.push_back({p.second,p.first});
  std::sort(v.rbegin(),v.rend());f<<'[';for(unsigned i=0;i<std::min<size_t>(128,v.size());i++)
   f<<(i?",":"")<<'['<<v[i].second<<','<<v[i].first<<']';f<<']';
 }
 ~Observer(){if(!enabled)return;const char*p=std::getenv("CF_COUNT_REPORT");if(!p)return;
  std::ofstream f(p);f<<"{\"completed_ISR\":"<<observed<<",\"exclude_first_ISR\":512,\"ISR\":";
  sums(f,irq);f<<",\"background\":";sums(f,background);
  f<<",\"entries\":{";{bool s=false;for(auto&e:entries)if(e.second){f<<(s?",":"")<<'"'<<entry_names[e.first]<<"\":"<<e.second;s=true;}}f<<"}";
  f<<",\"ISR_PCs\":";pcs(f,irq_pc);f<<",\"background_PCs\":";pcs(f,background_pc);f<<"}\n";
 }
};inline Observer observer;
}
