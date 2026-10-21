#pragma once
#include <algorithm>
#include <sstream>
// Included after the exact source witness and existing safety observer.
namespace noise_hat_exact {
struct Observer:nht_exact_base::Observer {
 struct Frame{uint64_t number=0,cost=0;std::map<std::string,uint64_t>cycles;std::map<unsigned,uint64_t>pcs;};
 std::map<unsigned,std::pair<unsigned,std::string>>ranges;
 std::map<std::string,uint64_t>aggregate;Frame current,worst;std::vector<Frame>misses;
 uint64_t seen_frames=0,seen_returns=0,seen_sum=0,last_cycle=0;unsigned last_pc=0;bool active=false;
 Observer(){if(const char*p=std::getenv("NHT_PROFILE_SYMBOLS")){std::ifstream f(p);unsigned lo,hi;std::string name;while(f>>std::hex>>lo>>hi>>name)ranges[lo]={hi,name};}}
 std::string bucket(unsigned pc){auto i=ranges.upper_bound(pc);if(i!=ranges.begin()){--i;if(pc<i->second.first)return i->second.second;}return pc<0x40c00000?"stock":"runtime-other";}
 template<class M>void step(M&m,unsigned pc){
  if(std::getenv("NHT_PROFILE_REPORT")){
   auto&h=hybrid_safety::observer;auto now=m.getCycles();
   if(active){auto d=now-last_cycle;current.cycles[bucket(last_pc)]+=d;current.pcs[last_pc]+=d;}
   if(h.returns>seen_returns){current.cost=h.isr_sum_cycles-seen_sum;seen_sum=h.isr_sum_cycles;seen_returns=h.returns;
    uint64_t sum=0;for(auto&v:current.cycles){sum+=v.second;aggregate[v.first]+=v.second;}
    if(sum>current.cost)std::abort();current.cycles["entry-and-RTE"]+=current.cost-sum;aggregate["entry-and-RTE"]+=current.cost-sum;
    if(current.cost>worst.cost)worst=current;if(current.cost*44100ull>16ull*264000000)misses.push_back(current);active=false;
   }
   if(h.frames>seen_frames){seen_frames=h.frames;current=Frame{};current.number=h.frames;active=true;}
   last_pc=pc;last_cycle=now;
  }
  nht_exact_base::Observer::step(m,pc);
 }
 static void write(std::ostream&f,const Frame&r){f<<"{\"frame\":"<<r.number<<",\"cycles\":"<<r.cost<<",\"buckets\":{";bool comma=false;for(auto&v:r.cycles){f<<(comma?",":"")<<'"'<<v.first<<"\":"<<v.second;comma=true;}f<<"},\"top_PCs\":[";
  std::vector<std::pair<uint64_t,unsigned>>top;for(auto&v:r.pcs)top.emplace_back(v.second,v.first);std::sort(top.rbegin(),top.rend());for(unsigned i=0;i<std::min<size_t>(32,top.size());i++)f<<(i?",":"")<<'['<<top[i].second<<','<<top[i].first<<']';f<<"]}";
 }
 ~Observer(){if(const char*p=std::getenv("NHT_PROFILE_REPORT")){std::ofstream f(p);f<<"{\"frames\":"<<seen_frames<<",\"returns\":"<<seen_returns<<",\"sum_cycles\":"<<seen_sum<<",\"worst\":";write(f,worst);f<<",\"misses\":[";for(unsigned i=0;i<misses.size();i++){if(i)f<<',';write(f,misses[i]);}f<<"],\"aggregate\":{";bool comma=false;for(auto&v:aggregate){f<<(comma?",":"")<<'"'<<v.first<<"\":"<<v.second;comma=true;}f<<"}}\n";}}
};inline Observer observer;
}
