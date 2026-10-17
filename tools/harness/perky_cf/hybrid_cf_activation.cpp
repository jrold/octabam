// First admission of T6 while T2 continues, with an independent T2-only control.
#include "hybrid_cf_observed_target.hpp"
using ProbeTarget=ObservedTarget;
using ProbeCost=ObservedCost;
int main(int argc,char**argv){
 if(argc!=3&&argc!=4)return 2;
 const bool splits=argc==4&&std::string(argv[3])=="splits";if(argc==4&&!splits)return 2;
 const unsigned warm=splits?32:64,frames=splits?40:128,split_cases=splits?17:1;
 HybridPredictor::selftest();const std::string image=argv[1],out=argv[2];
 ProbeTarget a(image,out+"/reference.nm"),b(image,out+"/candidate.nm");
 const uint32_t stride=a.symbols.at("pk_hybrid_voices").size/2;
 if((stride!=1974&&stride!=1984)||b.symbols.at("pk_hybrid_voices").size!=2*stride)throw std::runtime_error("unreviewed voice extent");
 const std::string names[]={"V1","V2","snare","bass","third"};
 std::ofstream csv(out+"/activation.csv");csv<<"profiler,T2,T6,activation_split,frame,baseline_T2_cycles,dual_T2_cycles,T6_cycles,baseline_T2_instructions,dual_T2_instructions,T6_instructions,baseline_code_bytes,dual_code_bytes,baseline_code_lines16,dual_code_lines16";
 for(auto label:{"baseline_T2","dual_T2","T6"})for(auto group:{"stack","state","PCM","source_RAM","instruction_stream","module_other","external_control_and_reservation"})csv<<','<<label<<'_'<<group<<"_read_bytes,"<<label<<'_'<<group<<"_write_bytes";
 for(auto group:{"stack","state","PCM","source_RAM","instruction_stream","module_other","external_control_and_reservation"})csv<<",baseline_"<<group<<"_lines16,dual_"<<group<<"_lines16";
 csv<<'\n';uint64_t state_checks=0,calls=0;
 auto state=[&](ProbeTarget&t){auto s=t.symbols.at("pk_hybrid_voices");return t.bytes(s.address,stride);};
 auto pcm=[&](ProbeTarget&t){return t.bytes(t.symbols.at("pk_hybrid_frame_pcm").address,32);};
 auto metadata=[&](ProbeTarget&t){std::vector<uint8_t> v;
  for(auto name:{"pk_hybrid_trigger_latch","pk_hybrid_frame_started","pk_hybrid_cf_ui_pending","pk_hybrid_cf_ui_bank","pk_hybrid_cf_ui_part","pk_hybrid_voice_generation"}){
   auto sym=t.symbols.at(name);if(sym.size%2)throw std::runtime_error("invalid per-voice metadata extent");
   auto bytes=t.bytes(sym.address,sym.size/2);v.insert(v.end(),bytes.begin(),bytes.end());
  }return v;};
 auto source_records=[&](ProbeTarget&t){auto v=t.bytes(0x80001c90+336,336);auto second=t.bytes(0x80001c90+0xa80+336,336);v.insert(v.end(),second.begin(),second.end());return v;};
 for(unsigned prof:{0u,1u})for(unsigned left=0;left<5;++left)for(unsigned right=0;right<5;++right)for(unsigned activation_split=0;activation_split<split_cases;++activation_split){
  for(auto*t:{&a,&b}){t->call("pk_hybrid_boot_init",{});t->m.write32(t->symbols.at("pk_hybrid_profiler_enable").address,prof);}
  for(unsigned frame=0;frame<frames;++frame){
   for(auto*t:{&a,&b})t->call("pk_hybrid_frame_begin",{});
   ProbeCost ac{},bc{},second{};
   auto accumulate=[](ProbeCost&d,const ProbeCost&s){d.cycles+=s.cycles;d.instructions+=s.instructions;d.stack=std::max(d.stack,s.stack);d.code_bytes.insert(s.code_bytes.begin(),s.code_bytes.end());for(unsigned i=0;i<7;++i){d.reads[i]+=s.reads[i];d.writes[i]+=s.writes[i];d.data_lines[i].insert(s.data_lines[i].begin(),s.data_lines[i].end());}};
   auto control=[&](ProbeTarget&t,unsigned which,unsigned track){unsigned algo=which<2?which:2,mode=which<2?((frame/32)%3):which-2;
    uint8_t values[]={uint8_t((31+frame*7)&127),uint8_t(96+frame%32),uint8_t(algo),uint8_t((frame*13)&127),uint8_t((frame*19)&127),uint8_t(mode)};
    for(unsigned k=0;k<6;++k)t.m.write16(0x80008000+2*k,uint16_t(values[k])<<8);t.m.write8(0x46104d0c+track,frame%3==0?16:0);};
   control(a,left,1);control(b,left,1);unsigned split=splits&&frame==warm?activation_split:frame%17;
   for(unsigned half=0;half<2;++half){std::vector<uint32_t>args={1u,half,half?split:0u,half?16u:split};
    for(auto*t:{&a,&b})t->m.write32(0x80001c80,0x80010000);
    auto x=a.call("pk_render",args),y=b.call("pk_render",args);accumulate(ac,x);accumulate(bc,y);calls+=2;
    if(state(a)!=state(b)||pcm(a)!=pcm(b)||metadata(a)!=metadata(b))throw std::runtime_error("T2 state/PCM changed by T6 activation");
    if(m68k_get_reg(a.m.getCpuState(),M68K_REG_D0)!=m68k_get_reg(b.m.getCpuState(),M68K_REG_D0))throw std::runtime_error("T2 callback return changed");
    if(a.bytes(0x80001c90+336+half*0xa80,336)!=b.bytes(0x80001c90+336+half*0xa80,336))throw std::runtime_error("T2 source record changed");++state_checks;
   }
   if(frame>=warm){auto saved=state(b),saved_pcm=pcm(b),saved_metadata=metadata(b),saved_source=source_records(b);control(b,right,5);
    for(unsigned half=0;half<2;++half){b.m.write32(0x80001c80,0x80010000);accumulate(second,b.call("pk_render",{5u,half,half?split:0u,half?16u:split}));++calls;
     if(state(b)!=saved||pcm(b)!=saved_pcm||metadata(b)!=saved_metadata||source_records(b)!=saved_source)throw std::runtime_error("T6 clobbered active T2 state/PCM");++state_checks;}
   }
   std::set<uint32_t> dual=bc.code_bytes;dual.insert(second.code_bytes.begin(),second.code_bytes.end());std::set<uint32_t> alines,blines;for(auto p:ac.code_bytes)alines.insert(p>>4);for(auto p:dual)blines.insert(p>>4);
   csv<<prof<<','<<names[left]<<','<<names[right]<<','<<(splits?activation_split:warm%17)<<','<<frame<<','<<ac.cycles<<','<<bc.cycles<<','<<second.cycles<<','<<ac.instructions<<','<<bc.instructions<<','<<second.instructions<<','<<ac.code_bytes.size()<<','<<dual.size()<<','<<alines.size()<<','<<blines.size();
   for(auto*c:{&ac,&bc,&second})for(unsigned i=0;i<7;++i)csv<<','<<c->reads[i]<<','<<c->writes[i];for(unsigned i=0;i<7;++i){auto lines=bc.data_lines[i];lines.insert(second.data_lines[i].begin(),second.data_lines[i].end());csv<<','<<ac.data_lines[i].size()<<','<<lines.size();}csv<<'\n';
  }
 }
 std::ofstream report(out+"/EXACT.json");report<<"{\"status\":\"PASS_T2_STATE_PCM_AND_SOURCE_UNCHANGED_THROUGH_SECOND_CF_ACTIVATION\",\"calls\":"<<calls<<",\"T2_exact_checks\":"<<state_checks<<",\"pairs\":25,\"profiler_modes\":2,\"activation_frame\":"<<warm<<",\"activation_splits\":"<<split_cases<<",\"frames_per_case\":"<<frames<<"}\n";
}
