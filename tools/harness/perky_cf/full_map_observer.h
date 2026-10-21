#pragma once
#include <array>
#include <map>
#include <vector>
#include <string>
#include <fstream>
#include <iterator>
#include <dlfcn.h>
#include "dsp56kEmu/memory.h"
namespace noise_hat_exact {
struct Observer {
 struct Frame{std::array<int32_t,16>pcm{};std::array<uint16_t,180>state{};std::array<uint16_t,6>side{};std::array<unsigned,60>writes{};std::array<unsigned,3>clock{};unsigned count=0,algo=0,hat_valid=0;};
 void*lib=nullptr;std::array<std::vector<uint8_t>,16>assets;
 using Init=void(*)(const uint8_t*const*);using Segment=int(*)(unsigned,unsigned,unsigned);using Prepare=int(*)(unsigned,const uint32_t*,unsigned);
 using PCM=void(*)(unsigned,int32_t*);using Hat=unsigned(*)(uint16_t*,uint16_t*,unsigned*);using Clock=void(*)(unsigned,unsigned*);
 Init init=nullptr;Segment segment=nullptr;Prepare prepare=nullptr;PCM pcm=nullptr;Hat hat=nullptr;Clock clock=nullptr;void(*start)()=nullptr;unsigned(*hat_valid)()=nullptr;
 unsigned prep_pc=0,seg_pc=0,frame_pc=0,output=0,owner=0,sequence=0,accept=0,mail=0,commit=0,generation=0;
 unsigned seg_ret=0,seg_sp=0,seg_tr=0,seg_begin=0,seg_end=0;
 unsigned frame_ret=0,frame_sp=0,split=0;bool initialized=false,event_seen=false;
 Frame current;std::map<unsigned,Frame>pending,feedback;
 std::array<int32_t,16>cf_expected{};std::array<uint64_t,4>frames{},pcm_errors{},significant{};
 std::array<unsigned,4>algorithms{},modes{};uint64_t state_frames=0,uninitialized_hat_frames=0,state_errors=0,side_errors=0,clock_errors=0,feedback_errors=0,feedback_checked=0,old_feedback=0,oracle_errors=0;
 std::vector<std::string>examples;
 std::array<unsigned,4>selected{},selected_mode{};std::map<std::string,uint64_t>combinations;
 unsigned env(const char*n){const char*p=std::getenv(n);if(!p)std::abort();return std::strtoul(p,nullptr,0);}
 template<class T>T fn(const char*n){auto p=dlsym(lib,n);if(!p)std::abort();return reinterpret_cast<T>(p);}
 Observer(){const char*p=std::getenv("FM_REFERENCE_LIBRARY");if(!p)return;lib=dlopen(p,RTLD_NOW|RTLD_LOCAL);if(!lib)std::abort();
  init=fn<Init>("fm_ref_init");segment=fn<Segment>("fm_ref_segment");prepare=fn<Prepare>("fm_ref_prepare");pcm=fn<PCM>("fm_ref_pcm");hat=fn<Hat>("fm_ref_hat");clock=fn<Clock>("fm_ref_clock");start=fn<void(*)()>("fm_ref_start");hat_valid=fn<unsigned(*)()>("fm_ref_hat_valid");
  prep_pc=env("FM_PREPARE");seg_pc=env("FM_SEGMENT");frame_pc=env("FM_FRAME");output=env("FM_OUTPUT");owner=env("FM_OWNER");sequence=env("FM_SEQUENCE");accept=env("FM_ACCEPT");mail=env("FM_MAIL");commit=env("FM_COMMIT");generation=env("FM_GENERATION");
  const char*names[]={"pitch","chromatic","envelope1","envelope2","w0","w1","w2","w3","m1","interp_a","interp_b","wt_base","wt_bank","closed","open","ride"};const uint8_t*ptr[16];
  for(unsigned i=0;i<16;i++){std::ifstream f(std::string(std::getenv("FM_ASSETS"))+"/"+names[i]+".bin",std::ios::binary);assets[i]={std::istreambuf_iterator<char>(f),{}};if(assets[i].empty())std::abort();ptr[i]=assets[i].data();}init(ptr);initialized=true;
 }
 void error(const char*kind,unsigned index,int32_t got,int32_t want){if(examples.size()<32)examples.push_back(std::string(kind)+":"+std::to_string(index)+":"+std::to_string(got)+"/"+std::to_string(want));}
 void check(unsigned tr,unsigned i,int32_t got,int32_t want){if(got!=want){pcm_errors[tr]++;error("PCM",tr*16+i,got,want);}if(got>64||got<-64)significant[tr]++;}
 template<class M>void step(M&m,unsigned pc){
  if(!initialized)return;auto sp=m.getA7();
  if(seg_ret&&pc==seg_ret&&sp==seg_sp+4){
   for(unsigned i=seg_begin;i<seg_end;i++)check(seg_tr,i,int32_t(m.peek32(output+64*seg_tr+4*i)),cf_expected[i]);
   if(seg_end==16)frames[seg_tr]++;seg_ret=0;
  }
  if(frame_ret&&pc==frame_ret&&sp==frame_sp+4){
   if(!event_seen)std::abort();
   if(m.peek32(owner)){pending[m.peek32(sequence)]=current;feedback[m.peek32(sequence)]=current;}
   else{for(unsigned i=0;i<16;i++)check(3,i,int32_t(m.peek32(output+192+4*i)),current.pcm[i]);frames[3]++;}
   frame_ret=0;
  }
  if(pc==accept){
   unsigned wire=m.peek32(mail+2)>>16,at=m.peek32(sp+4),n=m.peek32(sp+8);auto it=feedback.end();
   for(auto p=feedback.begin();p!=feedback.end();++p)if((p->first&65535)==wire){it=p;break;}
   if(it==feedback.end()||n>20)feedback_errors++;
   else{auto&f=it->second;if(n!=f.count)feedback_errors++;for(unsigned i=0;i<n;i++){
    if(i>=f.count){feedback_errors++;continue;}unsigned got=m.peek32(at+2*i)>>16,want=f.writes[3*i+2];
    if(got!=want){feedback_errors++;error("feedback",i,got,want);}if(f.writes[3*i]!=m.peek32(generation))old_feedback++;
   }feedback_checked++;feedback.erase(it);}
  }
  if(pc==frame_pc){
   current=Frame{};split=m.peek32(sp+4);frame_sp=sp;frame_ret=m.peek32(sp);event_seen=false;start();
   if(!segment(3,0,split))oracle_errors++;
  }
  if(pc==seg_pc){unsigned tr=m.peek32(sp+4);if(tr<3){
   seg_tr=tr;seg_begin=m.peek32(sp+8);seg_end=m.peek32(sp+12);seg_sp=sp;seg_ret=m.peek32(sp);
   if(!segment(tr,seg_begin,seg_end))oracle_errors++;pcm(tr,cf_expected.data());
  }}
  if(pc==prep_pc){
   unsigned tr=m.peek32(sp+4),at=m.peek32(sp+8);uint32_t input[10];for(unsigned i=0;i<10;i++)input[i]=m.peek32(at+4*i);
   if(tr>=4)std::abort();algorithms[tr]|=1u<<input[0];modes[tr]|=1u<<input[1];
   selected[tr]=input[0];selected_mode[tr]=input[1];
   if(!prepare(tr,input,m.peek32(generation)))oracle_errors++;
   if(tr==3&&frame_ret){
    std::string key;for(unsigned i=0;i<4;i++)key+=(i?":":"")+std::to_string(selected[i]);key+="/";for(unsigned i=0;i<4;i++)key+=(i?":":"")+std::to_string(selected_mode[i]);combinations[key]++;
    if(!segment(3,split,16))oracle_errors++;pcm(3,current.pcm.data());current.count=hat(current.state.data(),current.side.data(),current.writes.data());clock(3,current.clock.data());current.algo=input[0];current.hat_valid=hat_valid();event_seen=true;
   }
  }
 }
 template<class M>void dsp(M&m,unsigned pc){
  if(!initialized||pc!=commit)return;unsigned at=m.get(dsp56k::MemArea_X,0x209);if((m.get(dsp56k::MemArea_X,at)&65535)!=0x4e54)return;
  unsigned wire=m.get(dsp56k::MemArea_X,0x39f1)&65535;auto it=pending.end();for(auto p=pending.begin();p!=pending.end();++p)if((p->first&65535)==wire){it=p;break;}
  if(it==pending.end()){state_errors++;return;}auto&f=it->second;
  for(unsigned i=0;i<16;i++){int32_t got=m.get(dsp56k::MemArea_X,2*i);if(got&0x800000)got|=0xff000000;check(3,i,got,f.pcm[i]);}
  if(f.hat_valid)state_frames++;else uninitialized_hat_frames++;
  if(f.hat_valid)for(unsigned i=0;i<180;i++){unsigned got=m.get(dsp56k::MemArea_X,0x3800+i)&65535;if(got!=f.state[i]){state_errors++;error("state",i,got,f.state[i]);}}
  for(unsigned i=0;i<6;i++)if((m.get(dsp56k::MemArea_X,0x3970+i)&65535)!=f.side[i])side_errors++;
  if(f.algo==5)for(unsigned i=0;i<3;i++){unsigned got=m.get(dsp56k::MemArea_X,0x3a23+i);if(i==2){if(!f.clock[1])continue;if(got&0x800000)got|=0xff000000;}if(got!=f.clock[i])clock_errors++;}
  frames[3]++;pending.erase(it);
 }
 ~Observer(){
  if(!initialized)return;const char*path=std::getenv("FM_REPORT");if(!path)return;
  std::ofstream f(path);bool comma=false;
  auto array=[&](const char*name,const auto&values){f<<(comma?",":"")<<'"'<<name<<"\":[";bool item=false;for(auto value:values){f<<(item?",":"")<<value;item=true;}f<<']';comma=true;};
  f<<'{';array("source_frames",frames);array("PCM_mismatches",pcm_errors);array("source_significant",significant);array("algorithm_masks",algorithms);array("mode_masks",modes);
  f<<",\"resident_state_frames_checked\":"<<state_frames<<",\"uninitialized_hat_frames\":"<<uninitialized_hat_frames<<",\"DSP_state_mismatches\":"<<state_errors<<",\"DSP_side_mismatches\":"<<side_errors<<",\"DSP_clock_mismatches\":"<<clock_errors<<",\"feedback_mismatches\":"<<feedback_errors<<",\"feedback_frames\":"<<feedback_checked<<",\"old_generation_feedback_checked\":"<<old_feedback<<",\"oracle_errors\":"<<oracle_errors;
  f<<",\"combinations\":{";comma=false;for(auto&v:combinations){f<<(comma?",":"")<<'"'<<v.first<<"\":"<<v.second;comma=true;}
  f<<"},\"examples\":[";for(unsigned i=0;i<examples.size();i++)f<<(i?",":"")<<'"'<<examples[i]<<'"';f<<"]}\n";
 }
};inline Observer observer;
}
