#pragma once
// Read-only differential at each actual Slap renderer call. Unlike the Hat
// migration witness, this checks a pure renderer given its actual entry state.
namespace cf_synthesis_exact {
struct Tables {
 const uint8_t*pitch=nullptr,*envelope1=nullptr,*envelope2=nullptr;
 struct Wave{uint32_t address;const uint8_t*table;}waves[4]{};
};
struct Rng{uint32_t low,high;};
struct Observer {
 using Render=int(*)(uint8_t*,int16_t*,uint32_t,const Tables*,Rng*);
 void*library=nullptr;Render reference=nullptr;
 unsigned render=0,ret=0,entry_sp=0,raw=0,dst=0,rng_at=0,count=0;
 unsigned table_addresses[2]{};std::vector<uint8_t>curves[2];
 std::array<uint8_t,0x2670>expected{};std::array<int16_t,128>pcm{};Rng rng{};
 uint64_t calls=0,samples=0,pcm_errors=0,state_errors=0,rng_errors=0;
 Observer(){if(const char*p=std::getenv("CFS_SLAP_RENDER")){
  render=std::strtoul(p,nullptr,0);library=dlopen(std::getenv("CFS_SLAP_LIBRARY"),RTLD_NOW|RTLD_LOCAL);
  if(!library||(reference=(Render)dlsym(library,"pk_cf_slap_render"))==nullptr)std::abort();
 }}
 template<class M>void step(M&m,unsigned pc){
  if(!reference||(pc!=render&&pc!=ret))return;
  unsigned sp=m.getA7();
  if(ret&&pc==ret&&sp==entry_sp+4){
   for(unsigned i=0;i<count;i++)if(int16_t(m.peek32(dst+2*i)>>16)!=pcm[i])pcm_errors++;
   for(unsigned i=0;i<expected.size();i+=4){uint32_t want=(uint32_t(expected[i])<<24)|(uint32_t(expected[i+1])<<16)|(unsigned(expected[i+2])<<8)|expected[i+3];if(m.peek32(raw+i)!=want)state_errors++;}
   if(m.peek32(rng_at)!=rng.low||m.peek32(rng_at+4)!=rng.high)rng_errors++;
   calls++;samples+=count;ret=0;
  }
  if(pc==render){
   if(ret){if(sp==entry_sp&&m.peek32(sp)==ret)return;std::abort();}entry_sp=sp;ret=m.peek32(sp);raw=m.peek32(sp+4);dst=m.peek32(sp+8);count=m.peek32(sp+12);rng_at=m.peek32(sp+20);
   if(count>pcm.size())std::abort();
   for(unsigned i=0;i<expected.size();i+=4){auto v=m.peek32(raw+i);expected[i]=v>>24;expected[i+1]=v>>16;expected[i+2]=v>>8;expected[i+3]=v;}
   unsigned tables=m.peek32(sp+16);
   for(unsigned k=0;k<2;k++){unsigned at=m.peek32(tables+4+4*k);if(at!=table_addresses[k]){
    table_addresses[k]=at;curves[k].resize(4100);for(unsigned i=0;i<4100;i+=4){auto v=m.peek32(at+i);for(unsigned j=0;j<4;j++)curves[k][i+j]=v>>(24-8*j);}
   }}
   Tables t;t.envelope1=curves[0].data();t.envelope2=curves[1].data();rng={m.peek32(rng_at),m.peek32(rng_at+4)};
   if(reference(expected.data(),pcm.data(),count,&t,&rng)!=1)std::abort();
  }
 }
 ~Observer(){if(reference)if(const char*p=std::getenv("CFS_REPORT")){std::ofstream f(p);f<<"{\"Slap_calls\":"<<calls<<",\"Slap_native_samples\":"<<samples<<",\"Slap_PCM_mismatches\":"<<pcm_errors<<",\"Slap_raw_state_mismatches\":"<<state_errors<<",\"Slap_RNG_mismatches\":"<<rng_errors<<",\"in_flight_call\":"<<(ret?1:0)<<"}\n";}}
};inline Observer observer;
}
