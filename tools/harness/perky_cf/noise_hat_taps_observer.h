#pragma once
#include <cstdlib>
#include <dlfcn.h>
#include <fstream>
#include <vector>
#include <cstdint>
#include <map>
#include <array>
#include "dsp56kEmu/memory.h"
namespace noise_hat_exact {
struct RNG{uint32_t low,high;};struct Tables{const uint8_t*a,*b;};
struct Frame{std::vector<int32_t>pcm;std::vector<int16_t>writes;std::array<uint16_t,180>state{};std::array<uint16_t,6>side{};std::array<uint16_t,4805>ring{};unsigned index=0,modes=0;};
struct Observer{
 using Ref=int(*)(const uint8_t*,unsigned,unsigned,const Tables*,const RNG*,const uint16_t*,int,int,int16_t*,uint16_t*);
 using Ring=unsigned(*)(uint16_t*);
 void*lib=nullptr;Ref ref=nullptr;Ring ring=nullptr;unsigned entry=0,accept=0,submit=0,commit=0,mail=0;
 unsigned seq=0,split=0,stage=0,phase=0,have=0,classic=0;int16_t carry=0;
 uint32_t return_pc=0,return_sp=0;std::array<uint16_t,4805>committed_ring{};unsigned committed_index=0;bool ring_pending=false;
 std::map<unsigned,Frame>frames;std::vector<uint8_t>curve[2];
 uint64_t calls=0,samples=0,source_frames=0,source_errors=0,state_errors=0,feedback_frames=0,feedback_errors=0,clock_errors=0,ring_frames=0,ring_errors=0,source_significant=0;int32_t source_peak=0;
 std::vector<std::string>examples;
 Observer(){const char*p=std::getenv("NHR_EXACT_LIBRARY");if(!p)return;lib=dlopen(p,RTLD_NOW);if(!lib)std::abort();ref=(Ref)dlsym(lib,"pk_nhr_oracle");ring=(Ring)dlsym(lib,"pk_nht_ring");if(!ref||!ring)std::abort();
  entry=std::strtoul(std::getenv("NHR_EXPECT"),nullptr,0);accept=std::strtoul(std::getenv("NHR_ACCEPT"),nullptr,0);submit=std::strtoul(std::getenv("NHR_FRAME"),nullptr,0);commit=std::strtoul(std::getenv("NHR_DSP_COMMIT"),nullptr,0);mail=std::strtoul(std::getenv("NHR_MAIL"),nullptr,0);}
 template<class M>void step(M&m,uint32_t pc){
  if(!ref)return;auto sp=m.getA7();
  if(return_pc&&pc==return_pc&&sp==return_sp+4){
   if(ring_pending&&classic){for(unsigned i=0;i<4805;i++)if(uint16_t((m.peek32(classic+0x3f8+2*i)>>24)|((m.peek32(classic+0x3f9+2*i)>>24)<<8))!=committed_ring[i])ring_errors++;
    uint16_t hi=m.peek32(classic+0x2982)>>24,lo=m.peek32(classic+0x2983)>>24;if((hi|(lo<<8))!=committed_index)ring_errors++;ring_frames++;ring_pending=false;}
   return_pc=0;
  }
  if(pc==submit){seq++;frames[seq]=Frame{};split=m.peek32(sp+4);stage=split?0:1;return_sp=sp;return_pc=m.peek32(sp);return;}
  if(pc==accept){unsigned at=m.peek32(sp+4),n=m.peek32(sp+8),tag=m.peek32(mail)>>16,number=m.peek32(mail+2)>>16;auto found=frames.find(number);
   if(tag!=0x4e52||found==frames.end()){feedback_errors++;return;}auto&f=found->second;
   if(n!=f.writes.size())feedback_errors++;
   for(unsigned i=0;i<n;i++)if(i>=f.writes.size()||int16_t(m.peek32(at+2*i)>>16)!=f.writes[i])feedback_errors++;
   committed_ring=f.ring;committed_index=f.index;ring_pending=f.modes&3;feedback_frames++;return;
  }
  if(pc!=entry)return;
  unsigned raw=m.peek32(sp+4),n=m.peek32(sp+8),mode=m.peek32(sp+12),tp=m.peek32(sp+16),rp=m.peek32(sp+20),hp=m.peek32(sp+24);int init=m.peek32(sp+28),trig=m.peek32(sp+32);
  std::vector<uint8_t>control(mode==2?0x160:0x2dd8);for(unsigned i=0;i<control.size();i++)control[i]=m.peek32(raw+i)>>24;
  if(mode<2)classic=raw;
  if(curve[0].empty())for(unsigned j=0;j<2;j++){curve[j].resize(2050);unsigned a=m.peek32(tp+4*j);for(unsigned i=0;i<2050;i++)curve[j][i]=m.peek32(a+i)>>24;}
  Tables tables{curve[0].data(),curve[1].data()};RNG rng{m.peek32(rp),m.peek32(rp+4)};uint16_t hold[]{uint16_t(m.peek32(hp)>>16),uint16_t(m.peek32(hp+2)>>16)},state[127]{};
  std::vector<int16_t>native(n);if(!ref(control.data(),n,mode,&tables,&rng,hold,init,trig,native.data(),state))std::abort();
  auto&f=frames[seq];if(mode<2){f.index=ring(f.ring.data());if(!control[0xb8])for(unsigned i=0;i<n;i++)f.writes.push_back(int16_t(f.ring[(f.index+4805+1-n+i)%4805]));}
  unsigned outn=stage?16-split:split;stage++;if(trig){phase=0;have=0;carry=0;}
  unsigned end=phase+160*outn,needed=end/147+(end%147>=13)-have;if(needed!=n)clock_errors++;
  std::vector<int16_t>data;if(have)data.push_back(carry);data.insert(data.end(),native.begin(),native.end());unsigned at=0;
  for(unsigned k=0;k<outn;k++){if(at>=data.size()||(phase&&at+1>=data.size())){clock_errors++;break;}int32_t a=data[at],b=phase?data[at+1]:a;int64_t product=int64_t(b-a)*32*phase;int32_t delta=product<0?-int32_t((-product+146)/147):int32_t(product/147);f.pcm.push_back(a*32+delta);unsigned pos=phase+160;at+=pos/147;phase=pos%147;}
  have=phase>=13;carry=have&&at<data.size()?data[at]:0;
  unsigned first=mode==1?81:0,count=mode==0?81:mode==1?28:59,base=mode==2?121:0;
  for(unsigned i=first;i<first+count;i++)f.state[base+i]=state[i];if(mode==1)for(unsigned i=0;i<6;i++)f.side[i]=state[121+i];f.modes|=1u<<mode;samples+=n;calls++;
 }
 template<class M>void dsp(M&m,unsigned pc){
  if(!ref||pc!=commit)return;unsigned record=m.get(dsp56k::MemArea_X,0x209);if((m.get(dsp56k::MemArea_X,record)&65535)!=0x4e54)return;
  unsigned number=m.get(dsp56k::MemArea_X,0x39f1);auto it=frames.find(number);if(it==frames.end()){state_errors++;return;}auto&f=it->second;
  if(f.pcm.size()!=16)clock_errors++;
  for(unsigned i=0;i<16;i++){int32_t got=m.get(dsp56k::MemArea_X,2*i);if(got&0x800000)got|=0xff000000;if(std::abs(got)>64)source_significant++;if(std::abs(got)>source_peak)source_peak=std::abs(got);if(i>=f.pcm.size()||got!=f.pcm[i]){source_errors++;if(examples.size()<8)examples.push_back(std::to_string(number)+":"+std::to_string(i)+":"+std::to_string(got)+"/"+std::to_string(i<f.pcm.size()?f.pcm[i]:0));}}
  for(unsigned mode=0;mode<3;mode++)if(f.modes&(1u<<mode)){unsigned first=mode==1?81:0,count=mode==0?81:mode==1?28:59,base=mode==2?121:0;for(unsigned i=first;i<first+count;i++)if((m.get(dsp56k::MemArea_X,0x3800+base+i)&65535)!=f.state[base+i])state_errors++;}
  if(f.modes&2)for(unsigned i=0;i<6;i++)if((m.get(dsp56k::MemArea_X,0x3970+i)&65535)!=f.side[i])state_errors++;
  source_frames++;while(frames.size()>8)frames.erase(frames.begin());
 }
 ~Observer(){if(const char*p=std::getenv("NHR_EXACT_REPORT")){std::ofstream f(p);f<<"{\"requests\":"<<calls<<",\"native_samples\":"<<samples<<",\"source_frames\":"<<source_frames<<",\"source_PCM_mismatches\":"<<source_errors<<",\"source_significant\":"<<source_significant<<",\"source_peak\":"<<source_peak<<",\"state_mismatches\":"<<state_errors<<",\"feedback_frames\":"<<feedback_frames<<",\"feedback_mismatches\":"<<feedback_errors<<",\"clock_mismatches\":"<<clock_errors<<",\"ring_frames\":"<<ring_frames<<",\"ring_mismatches\":"<<ring_errors<<",\"examples\":[";for(unsigned i=0;i<examples.size();i++)f<<(i?",":"")<<'"'<<examples[i]<<'"';f<<"]}\n";}}
};inline Observer observer;
}
