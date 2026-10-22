#pragma once
// Diagnostic, read-only: attribute steady ISR cycles to the stock track being
// processed. Contexts are entered at the stock per-chunk dispatcher
// 0x400068e4(track, ping, start, end) and the per-track event routine
// 0x40005ff0(track, flags), and left at their own return. The eight-track
// DELAY routine 0x400031a0..0x4000385a is attributed through its loop counter
// at frame+112 (COLDFIRE_DELAY.md section 2). Everything else is "other".
// Within a context, stock and PERKY runtime code are kept apart.
// CF_TRACK_REPORT names the JSON report. Not an admission instrument.
// Measured on PKFM26 (modules/perky/hybrid/ORCHESTRATION_CF_QUALIFICATION.md):
// these contexts held 7.1 us/frame of stock and none of PERKY's runtime, and
// 0x40005ff0 was never entered, so they do not contain the per-chunk source
// path; full_map_stockpc_observer.h is the stock attribution that worked.
namespace full_map_track {
struct Observer {
 struct Ctx{unsigned ret,sp,kind,track;};
 std::vector<Ctx> stack;
 std::map<std::string,uint64_t> irq;
 uint64_t last_cycle=0,observed=0;unsigned last_pc=0;bool active=false,last_irq=false,enabled=false;
 unsigned delay_frame=0;
 std::map<std::string,uint64_t> calls;
 Observer(){enabled=std::getenv("CF_TRACK_REPORT")!=nullptr;}
 template<class M>void step(M&m,unsigned pc){
  if(!enabled)return;auto&h=hybrid_safety::observer;auto now=m.getCycles();auto sp=m.getA7();
  if(active&&last_irq){
   auto d=now-last_cycle;std::string key;
   const bool runtime=last_pc>=0x40c00000u;
   if(last_pc>=0x400031a0u&&last_pc<0x4000385au&&delay_frame)
    key="delay/T"+std::to_string((m.peek32(delay_frame+112)&7u)+1);
   else if(!stack.empty()){
    const auto&c=stack.back();
    key=std::string(c.kind?"event":"dispatch")+(runtime?"-runtime":"-stock")+"/T"+std::to_string((c.track&7u)+1);
   }else key=runtime?"runtime-outside":"stock-other";
   irq[key]+=d;
  }
  while(!stack.empty()&&pc==stack.back().ret&&sp==stack.back().sp+4)stack.pop_back();
  if(pc==0x400068e4u||pc==0x40005ff0u){
   Ctx c{m.peek32(sp),sp,pc==0x40005ff0u?1u:0u,m.peek32(sp+4)};stack.push_back(c);
   if(h.returns>=512)calls[std::string(c.kind?"event":"dispatch")+"/T"+std::to_string((c.track&7u)+1)]++;
  }
  if(pc==0x400031a4u)delay_frame=sp;            // after `lea -148(%sp),%sp`
  if(pc==0x40003858u)delay_frame=0;             // rts
  if(h.frames==h.returns)stack.clear();       // outside the frame ISR
  active=h.returns>=512;last_irq=h.frames>h.returns;last_cycle=now;last_pc=pc;observed=h.returns;
 }
 ~Observer(){if(!enabled)return;std::ofstream f(std::getenv("CF_TRACK_REPORT"));
  f<<"{\"completed_ISR\":"<<observed<<",\"exclude_first_ISR\":512,\"ISR\":{";bool s=false;
  for(auto&v:irq){f<<(s?",":"")<<'"'<<v.first<<"\":"<<v.second;s=true;}
  f<<"},\"calls\":{";s=false;for(auto&v:calls){f<<(s?",":"")<<'"'<<v.first<<"\":"<<v.second;s=true;}f<<"}}\n";
 }
};inline Observer observer;
}
