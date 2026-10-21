#pragma once
#include <algorithm>
// Read-only instruction-cycle attribution. No target calls, writes or timers.
namespace noise_hat_exact {
struct Observer:nhb_profile_base::Observer {
 struct Frame{uint64_t number=0,cost=0;unsigned reset_mask=0,generation=0,old_owner=0,new_owner=0,split=0,mode=0,trigger=0,phase=0;std::map<std::string,uint64_t>cycles;std::map<unsigned,uint64_t>pcs;};
 std::map<unsigned,std::pair<unsigned,std::string>>ranges;
 std::map<std::string,uint64_t>aggregate;Frame current;std::vector<Frame>top,resets;
 std::vector<std::pair<unsigned,uint64_t>>trace;bool profiling=std::getenv("NHT_PROFILE_REPORT")!=nullptr;
 uint64_t seen_frames=0,seen_returns=0,seen_sum=0,last_cycle=0;unsigned last_pc=0;bool active=false;
 Observer(){if(const char*p=std::getenv("NHT_PROFILE_SYMBOLS")){std::ifstream f(p);unsigned lo,hi;std::string name;while(f>>std::hex>>lo>>hi>>name)ranges[lo]={hi,name};}}
 std::string bucket(unsigned pc){auto i=ranges.upper_bound(pc);if(i!=ranges.begin()){--i;if(pc<i->second.first)return i->second.second;}return pc<0x40c00000?"stock":"runtime-other";}
 template<class M>void step(M&m,unsigned pc){
  if(profiling){
   auto&h=hybrid_safety::observer;auto now=m.getCycles();
   if(active)trace.emplace_back(last_pc,now-last_cycle);
   if(h.returns>seen_returns){current.cost=h.isr_sum_cycles-seen_sum;seen_sum=h.isr_sum_cycles;seen_returns=h.returns;current.new_owner=m.peek32(owner);current.generation=m.peek32(generation);
    if(current.reset_mask||top.size()<64||current.cost>top.back().cost){
     for(auto&v:trace){current.cycles[bucket(v.first)]+=v.second;current.pcs[v.first]+=v.second;}
     uint64_t sum=0;for(auto&v:current.cycles)sum+=v.second;
     if(sum>current.cost)std::abort();current.cycles["entry-and-RTE"]+=current.cost-sum;
     if(current.reset_mask)resets.push_back(current);
     top.push_back(current);std::sort(top.begin(),top.end(),[](const Frame&a,const Frame&b){return a.cost>b.cost;});if(top.size()>64)top.pop_back();
    }active=false;
   }
   if(h.frames>seen_frames){seen_frames=h.frames;current=Frame{};current.number=h.frames;current.old_owner=m.peek32(owner);trace.clear();active=true;}
   last_pc=pc;last_cycle=now;
  }
  if(active&&pc==event){unsigned tr=m.peek32(m.getA7()+4);if(tr<4&&m.peek32(voices+4*tr)!=m.peek32(generation)){current.reset_mask|=1u<<tr;current.generation=m.peek32(generation);}}
  if(active&&pc==submit){current.split=m.peek32(m.getA7()+4);current.mode=m.peek32(inputs+4);current.trigger=m.peek32(inputs+36);current.phase=m.peek32(clocks);}
  nhb_profile_base::Observer::step(m,pc);
 }
 void write(std::ostream&f,const Frame&r){f<<"{\"frame\":"<<r.number<<",\"cycles\":"<<r.cost<<",\"old_owner\":"<<r.old_owner<<",\"new_owner\":"<<r.new_owner<<",\"source_split\":"<<r.split<<",\"panel_mode\":"<<r.mode<<",\"trigger\":"<<r.trigger<<",\"phase\":"<<r.phase<<",\"reset_mask\":"<<r.reset_mask<<",\"generation\":"<<r.generation<<",\"buckets\":{";bool comma=false;for(auto&v:r.cycles){f<<(comma?",":"")<<'"'<<v.first<<"\":"<<v.second;comma=true;}f<<"},\"top_PCs\":[";
  std::vector<std::pair<uint64_t,unsigned>>pcs;for(auto&v:r.pcs)pcs.emplace_back(v.second,v.first);std::sort(pcs.rbegin(),pcs.rend());for(unsigned i=0;i<std::min<size_t>(32,pcs.size());i++)f<<(i?",":"")<<'['<<pcs[i].second<<','<<pcs[i].first<<']';f<<"],\"synthesis_PCs\":[";unsigned emitted=0;for(auto&v:pcs){auto b=bucket(v.second);if(b=="pk_cf_slap_render"||b=="pk_cf_wt_render"||b=="pk_cf_nh_render"||b=="pk_cf_delay_block"||b.find("nh_block_")==0){f<<(emitted?",":"")<<'['<<v.second<<','<<v.first<<']';if(++emitted==64)break;}}f<<"]}";
 }
 ~Observer(){if(const char*p=std::getenv("NHT_PROFILE_REPORT")){std::ofstream f(p);f<<"{\"frames\":"<<seen_frames<<",\"returns\":"<<seen_returns<<",\"sum_cycles\":"<<seen_sum<<",\"top\":[";for(unsigned i=0;i<top.size();i++){if(i)f<<',';write(f,top[i]);}f<<"],\"reset_frames\":[";for(unsigned i=0;i<resets.size();i++){if(i)f<<',';write(f,resets[i]);}f<<"],\"aggregate\":{";bool comma=false;for(auto&v:aggregate){f<<(comma?",":"")<<'"'<<v.first<<"\":"<<v.second;comma=true;}f<<"}}\n";}}
};inline Observer observer;
}
