#pragma once
// Read-only attribution; keeps both the IRQ and real background worker visible.
namespace full_map_spike {
struct Observer {
 std::map<unsigned,std::pair<unsigned,std::string>> ranges;
 std::map<std::string,uint64_t> irq,background;
 std::map<unsigned,uint64_t> irq_pc,background_pc;
 std::map<std::string,uint64_t> cur;uint64_t cur_total=0,spikes=0,threshold=0;std::vector<uint64_t> spike_totals;
 uint64_t last_cycle=0,observed=0,last_returns=0;unsigned last_pc=0;
 bool enabled=false,active=false,last_irq=false;
 Observer(){if(const char*p=std::getenv("CF_SPIKE_SYMBOLS")){
  std::ifstream f(p);unsigned lo,hi;std::string name;
  while(f>>std::hex>>lo>>hi>>name)ranges[lo]={hi,name};enabled=true;
  if(const char*t=std::getenv("CF_SPIKE_THRESHOLD"))threshold=std::strtoull(t,nullptr,0);
 }}
 std::string bucket(unsigned pc){auto i=ranges.upper_bound(pc);if(i!=ranges.begin()){
  --i;if(pc<i->second.first)return i->second.second;}
  return pc<0x40c00000?"stock":"runtime-other";
 }
 template<class M>void step(M&m,unsigned pc){
  if(!enabled)return;auto&h=hybrid_safety::observer;auto now=m.getCycles();
  if(active&&last_irq){auto d=now-last_cycle;cur[bucket(last_pc)]+=d;cur_total+=d;}
  if(h.returns!=last_returns){
   if(active&&cur_total>threshold){for(auto&v:cur)irq[v.first]+=v.second;spikes++;spike_totals.push_back(cur_total);}
   cur.clear();cur_total=0;
  }
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
 ~Observer(){if(!enabled)return;const char*p=std::getenv("CF_SPIKE_REPORT");if(!p)return;
  std::ofstream f(p);f<<"{\"completed_ISR\":"<<observed<<",\"spikes\":"<<spikes<<",\"threshold\":"<<threshold<<",\"spike_totals\":[";
  for(size_t i=0;i<spike_totals.size()&&i<4096;i++)f<<(i?",":"")<<spike_totals[i];
  f<<"],\"exclude_first_ISR\":512,\"ISR\":";
  sums(f,irq);f<<",\"background\":";sums(f,background);
  f<<",\"ISR_PCs\":";pcs(f,irq_pc);f<<",\"background_PCs\":";pcs(f,background_pc);f<<"}\n";
 }
};inline Observer observer;
}
