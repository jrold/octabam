#pragma once
#include "cf_synthesis_observer.h"
namespace noise_hat_exact {
struct StreamFrame {
 std::array<int32_t,16>pcm{};std::array<uint16_t,180>state{};std::array<uint16_t,6>side{};
 std::array<uint32_t,4>clock{};std::array<uint16_t,4805>ring{};std::array<unsigned,60>write_records{};unsigned modes=0,writes=0,ordinal=0;
};
struct Observer:nhb_control_base::Observer {
 using Init=void(*)(const uint8_t*,const uint32_t*,const uint8_t*,const uint32_t*,const uint32_t*,unsigned,const uint8_t*,const uint8_t*,const uint8_t*,const uint8_t*);
 using Prefix=void(*)(unsigned,int32_t*);
 using Advance=void(*)(const uint8_t*,unsigned,unsigned,unsigned,int,unsigned,int32_t*,uint16_t*,uint16_t*,uint32_t*,uint16_t*);
 using Codec=void(*)(uint8_t*,unsigned,uint16_t*,int);
 Init init=nullptr;Prefix prefix=nullptr;Advance advance=nullptr;Codec codec=nullptr;
 unsigned engine=0,assets=0,layout=0,inputs=0,owner=0,sequence=0,output=0,clocks=0,produced=0,completed=0,blocking=0,work=0;uint64_t blocking_calls=0;
 unsigned ata=0;uint64_t ata_calls=0;
 unsigned frame_ret=0,frame_sp=0,old_mode=0,ordinal=0,frame_split=0;bool event_seen=false;
 unsigned event=0,voices=0,generation=0,epoch=0;uint64_t resets=0,old_epoch_writes=0;
 using Reset=void(*)();using Writes=unsigned(*)(unsigned*);Reset reset=nullptr;Writes writes=nullptr;
 bool initialized=false;
 std::array<uint16_t,4805>committed_ring{};unsigned model_ring_index=0;
 StreamFrame current;std::map<unsigned,StreamFrame>pending,feedback;
 uint64_t feedback_checked=0,feedback_errors_stream=0,retired_feedback=0;unsigned maximum_feedback_age=0;
 uint64_t cf_frames=0,dsp_frames=0,pcm_errors=0,dynamic_errors=0,clock_errors_stream=0,ring_errors_stream=0,transitions=0,worker_calls=0;
 unsigned previous_owner=1,max_queue=0;std::vector<std::string>stream_examples;
 Observer(){if(!ref)return;lifecycle_allow=false;
  auto env=[](const char*n){auto p=std::getenv(n);if(!p)std::abort();return unsigned(std::strtoul(p,nullptr,0));};
  engine=env("NHL_ENGINE");assets=env("NHL_ASSETS");layout=env("NHL_LAYOUT");inputs=env("NHB_INPUTS");owner=env("NHB_OWNER");sequence=env("NHB_SEQUENCE");output=env("NHB_OUTPUT");clocks=env("NHB_CLOCK");produced=env("NHB_PRODUCED");completed=env("NHB_COMPLETED");blocking=env("NHB_BLOCKING");work=env("NHB_WORK");
  event=env("NHP_EVENT");voices=env("NHP_VOICES");generation=env("NHP_GENERATION");
  reset=(Reset)dlsym(lib,"nhp_original_reset");writes=(Writes)dlsym(lib,"nhp_original_writes");if(!reset||!writes)std::abort();
  if(const char*p=std::getenv("NHB_ATA_FIX"))ata=std::strtoul(p,nullptr,0);
  init=(Init)dlsym(lib,"nhb_original_init");prefix=(Prefix)dlsym(lib,"nhb_original_prefix");advance=(Advance)dlsym(lib,"nhb_original_event");codec=(Codec)dlsym(lib,"pk_nha_codec");if(!init||!prefix||!advance||!codec)std::abort();
 }
 static unsigned mode(unsigned panel){return panel==0?1:panel==1?0:2;}
 void error(const char*kind,unsigned i,int32_t got,int32_t want){if(stream_examples.size()<24)stream_examples.push_back(std::string(kind)+":"+std::to_string(ordinal)+":"+std::to_string(i)+":"+std::to_string(got)+"/"+std::to_string(want));}
 bool dynamic(unsigned k)const {
  static const unsigned controls[]={1,6,11,12,15,16,21,22,27,28,33,34,39,40,45,46,81,86,91,92,97,104,107,121,126,131,132,161,162,163,164,165,166,167,168,169,170,171,172,175,176,179};
  for(auto v:controls)if(k==v)return false;return true;
 }
 template<class M>void state(M&m,const StreamFrame&f,bool dsp){
  if(dsp){
   for(unsigned k=0;k<180;k++)if(dynamic(k)||((f.modes&(k<81?1:k<121?2:4))!=0)){
    unsigned got=m.get(dsp56k::MemArea_X,0x3800+k)&65535;if(got!=f.state[k]){dynamic_errors++;error("state",k,got,f.state[k]);}}
   for(unsigned i=0;i<6;i++)if((m.get(dsp56k::MemArea_X,0x3970+i)&65535)!=f.side[i])dynamic_errors++;
   for(unsigned i=0;i<3;i++){int32_t got=m.get(dsp56k::MemArea_X,0x3a23+i);if(i==2&&got&0x800000)got|=0xff000000;
    if(i==2&&!f.clock[1])continue;if(uint32_t(got)!=f.clock[i]){clock_errors_stream++;error("clock",i,got,f.clock[i]);}}
  }
 }
 template<class M>void cf_state(M&m,const StreamFrame&f){
  auto offsets=((const unsigned*(*)())dlsym(lib,"nhl_offsets"))();unsigned tr=engine+3*offsets[0],raw=tr+offsets[1];
  std::vector<uint8_t>bytes(0x2df8);for(unsigned i=0;i<bytes.size();i++)bytes[i]=m.peek32(raw+i)>>24;
  uint16_t w[180]{};codec(bytes.data(),0,w,0);codec(bytes.data(),1,w,0);codec(bytes.data()+0x2c98,2,w+121,0);
  for(unsigned k=0;k<180;k++)if(w[k]!=f.state[k]){dynamic_errors++;error("CFstate",k,w[k],f.state[k]);}
  for(unsigned i=0;i<3;i++)if(m.peek32(clocks+4*i)!=f.clock[i]){clock_errors_stream++;error("CFclock",i,m.peek32(clocks+4*i),f.clock[i]);}
  if(m.peek32(tr+offsets[2])!=(unsigned(f.side[2])|(unsigned(f.side[3])<<16)))dynamic_errors++;
  if(m.peek32(tr+offsets[2]+4)!=(unsigned(f.side[4])|(unsigned(f.side[5])<<16)))dynamic_errors++;
  unsigned hp=engine+m.peek32(layout+48);for(unsigned i=0;i<2;i++)if((m.peek32(hp+2*i)>>16)!=f.side[i])dynamic_errors++;
  for(unsigned i=0;i<4805;i++){unsigned got=bytes[0x3f8+2*i]|(unsigned(bytes[0x3f9+2*i])<<8);if(got!=committed_ring[i]){ring_errors_stream++;error("CFring",i,got,committed_ring[i]);}}
  if((bytes[0x2982]|(unsigned(bytes[0x2983])<<8))!=f.clock[3])ring_errors_stream++;
 }
 template<class M>void step(M&m,unsigned pc){
  cf_synthesis_exact::observer.step(m,pc);
  if(!ref)return;auto sp=m.getA7();
  if(pc==event&&m.peek32(sp+4)==3&&m.peek32(voices+12)!=m.peek32(generation)){
   reset();committed_ring.fill(0);model_ring_index=0;resets++;epoch++;
  }
  if(pc==blocking)blocking_calls++;if(pc==work)worker_calls++;if(ata&&pc==ata)ata_calls++;
  if(frame_ret&&pc==frame_ret&&sp==frame_sp+4){
   if(!event_seen)std::abort();
   unsigned actual=m.peek32(owner);if(actual!=previous_owner){transitions++;previous_owner=actual;}
   unsigned q=m.peek32(produced)-m.peek32(completed);if(q>max_queue)max_queue=q;
   if(actual){pending[m.peek32(sequence)]=current;feedback[m.peek32(sequence)]=current;}
   else {
    for(unsigned i=0;i<16;i++){int32_t got=m.peek32(output+4*i);if(got!=current.pcm[i]){pcm_errors++;error("CFpcm",i,got,current.pcm[i]);}}
    for(unsigned i=0;i<current.writes;i++){
     auto*r=current.write_records.data()+3*i;if(r[0]==epoch)committed_ring[r[1]]=r[2];
    }
    cf_state(m,current);cf_frames++;
   }
   frame_ret=0;
  }
  if(pc==accept){
   unsigned wire=m.peek32(mail+2)>>16,at=m.peek32(sp+4),n=m.peek32(sp+8);auto it=feedback.end();
   for(auto p=feedback.begin();p!=feedback.end();++p)if((p->first&65535)==wire){it=p;break;}
   if(it==feedback.end()||n>20)feedback_errors_stream++;
   else {auto&f=it->second;unsigned age=ordinal-f.ordinal;if(age>maximum_feedback_age)maximum_feedback_age=age;if(!m.peek32(owner))retired_feedback++;if(n!=f.writes)feedback_errors_stream++;for(unsigned i=0;i<n;i++){
     if(i>=f.writes){feedback_errors_stream++;continue;}
     auto*r=f.write_records.data()+3*i;
     if((m.peek32(at+2*i)>>16)!=r[2])feedback_errors_stream++;
     if(r[0]==epoch)committed_ring[r[1]]=r[2];else old_epoch_writes++;
    }feedback_checked++;feedback.erase(it);}
  }
  if(pc==submit){
   ordinal++;auto offsets=((const unsigned*(*)())dlsym(lib,"nhl_offsets"))();
   if(m.peek32(layout)!=offsets[0])std::abort();unsigned tr=engine+3*offsets[0];
   if(!initialized){
    unsigned raw=tr+offsets[1],ctl=tr+offsets[6];std::vector<uint8_t>bytes(0x2df8);for(unsigned i=0;i<bytes.size();i++)bytes[i]=m.peek32(raw+i)>>24;
    uint32_t target[4];uint8_t tail[6];for(unsigned i=0;i<4;i++)target[i]=m.peek32(ctl+4*i);for(unsigned i=0;i<6;i++)tail[i]=m.peek32(ctl+16+i)>>24;
    unsigned hp=engine+m.peek32(layout+48);uint32_t side[4]={m.peek32(tr+offsets[2]),m.peek32(tr+offsets[2]+4),m.peek32(hp)>>16,m.peek32(hp+2)>>16};
    uint32_t clock[3]={m.peek32(clocks),m.peek32(clocks+4),m.peek32(clocks+8)};
    std::vector<uint8_t>table[4];unsigned sizes[]={8192,24,2050,2050};for(unsigned j=0;j<4;j++){table[j].resize(sizes[j]);unsigned a=m.peek32(assets+4*j);for(unsigned i=0;i<sizes[j];i++)table[j][i]=m.peek32(a+i)>>24;}
    for(unsigned i=0;i<4805;i++)committed_ring[i]=bytes[0x3f8+2*i]|(unsigned(bytes[0x3f9+2*i])<<8);
    model_ring_index=bytes[0x2982]|(unsigned(bytes[0x2983])<<8);
    old_mode=m.peek32(tr+offsets[4])>>24;
    init(bytes.data(),target,tail,side,clock,old_mode,table[0].data(),table[1].data(),table[2].data(),table[3].data());
    /* The oracle keeps these assets; host storage must outlive this call. */
    static std::vector<uint8_t>keep[4];for(unsigned j=0;j<4;j++)keep[j]=std::move(table[j]);initialized=true;
   }
   current=StreamFrame{};current.ordinal=ordinal;frame_split=m.peek32(sp+4);current.modes=frame_split?1u<<mode(old_mode):0;event_seen=false;
   prefix(frame_split,current.pcm.data());
   frame_sp=sp;frame_ret=m.peek32(sp);
  }
  if(frame_ret&&pc==prepare){
   uint8_t raw[4];unsigned at=m.peek32(sp+12);for(unsigned i=0;i<4;i++)raw[i]=m.peek32(at+i)>>24;
   unsigned selected=m.peek32(sp+16);current.modes|=1u<<mode(selected);old_mode=selected;
   advance(raw,selected,m.peek32(sp+20),m.peek32(sp+24),m.peek32(sp+28),frame_split,current.pcm.data(),current.state.data(),current.side.data(),current.clock.data(),current.ring.data());current.writes=writes(current.write_records.data());model_ring_index=current.clock[3];event_seen=true;
  }
  nhb_control_base::Observer::step(m,pc);
 }
 template<class M>void dsp(M&m,unsigned pc){
  if(!ref||pc!=commit)return;unsigned record=m.get(dsp56k::MemArea_X,0x209);if((m.get(dsp56k::MemArea_X,record)&65535)!=0x4e54)return;
  unsigned wire=m.get(dsp56k::MemArea_X,0x39f1)&65535;auto it=pending.end();for(auto p=pending.begin();p!=pending.end();++p)if((p->first&65535)==wire){it=p;break;}
  if(it==pending.end()){dynamic_errors++;return;}auto&f=it->second;
  for(unsigned i=0;i<16;i++){int32_t got=m.get(dsp56k::MemArea_X,2*i);if(got&0x800000)got|=0xff000000;
   if(std::abs(got)>64)source_significant++;if(std::abs(got)>source_peak)source_peak=std::abs(got);
   if(got!=f.pcm[i]){pcm_errors++;error("DSPpcm",i,got,f.pcm[i]);}}
  state(m,f,true);dsp_frames++;pending.erase(it);
 }
 ~Observer(){if(const char*p=std::getenv("NHP_REPORT")){std::ofstream f(p);f<<"{\"original_initializer_resets\":"<<resets<<",\"old_epoch_writes_checked_and_retired\":"<<old_epoch_writes<<"}\n";}if(ref)if(const char*p=std::getenv("NHR_EXACT_REPORT")){std::ofstream f(std::string(p)+".stream.json");f<<"{\"CF_frames\":"<<cf_frames<<",\"DSP_frames\":"<<dsp_frames<<",\"PCM_mismatches\":"<<pcm_errors<<",\"state_mismatches\":"<<dynamic_errors<<",\"clock_mismatches\":"<<clock_errors_stream<<",\"ring_mismatches\":"<<ring_errors_stream<<",\"feedback_frames\":"<<feedback_checked<<",\"feedback_mismatches\":"<<feedback_errors_stream<<",\"retired_feedback_jobs\":"<<retired_feedback<<",\"maximum_feedback_age_frames\":"<<maximum_feedback_age<<",\"blocking_RPC_calls\":"<<blocking_calls<<",\"worker_calls\":"<<worker_calls<<",\"PIO_first_sector_calls\":"<<ata_calls<<",\"ownership_transitions\":"<<transitions<<",\"maximum_worker_queue\":"<<max_queue<<",\"examples\":[";for(unsigned i=0;i<stream_examples.size();i++)f<<(i?",":"")<<'"'<<stream_examples[i]<<'"';f<<"]}\n";}}
};inline Observer observer;
}
