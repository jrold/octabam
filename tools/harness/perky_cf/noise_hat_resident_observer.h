#pragma once
#include <cstdlib>
#include <dlfcn.h>
#include <fstream>
#include <deque>
#include <vector>
#include <cstdint>
#include <map>
#include <array>
#include "dsp56kEmu/memory.h"
namespace noise_hat_exact {
struct RNG{uint32_t low,high;};struct Tables{const uint8_t*a,*b;};
struct Expected{unsigned seq=0;std::vector<int16_t>pcm;uint16_t state[180]={};uint16_t side[6]={};unsigned modes=0;};
struct Observer{
    using Ref=int(*)(const uint8_t*,unsigned,unsigned,const Tables*,const RNG*,const uint16_t*,int,int,int16_t*,uint16_t*);
    void*lib=nullptr;Ref ref=nullptr;uint32_t entry=0,accept=0,submit=0,commit=0;
    uint64_t calls=0,samples=0,checked=0,pcm_mismatches=0,state_mismatches=0,state_frames=0;
    std::deque<int16_t>expected;std::deque<Expected>frames;Expected next;
    std::vector<uint8_t>curve[2];
    std::map<unsigned,std::array<unsigned,6>>source_seen;
    Observer(){const char*p=std::getenv("NHR_EXACT_LIBRARY");if(!p)return;lib=dlopen(p,RTLD_NOW);if(!lib)std::abort();ref=(Ref)dlsym(lib,"pk_nhr_oracle");if(!ref)std::abort();
        entry=std::strtoul(std::getenv("NHR_EXPECT"),nullptr,0);accept=std::strtoul(std::getenv("NHR_ACCEPT"),nullptr,0);
        submit=std::strtoul(std::getenv("NHR_FRAME"),nullptr,0);commit=std::strtoul(std::getenv("NHR_DSP_COMMIT"),nullptr,0);}
    template<class M>void step(M&m,uint32_t pc){
        if(!ref)return;auto sp=m.getA7();
        if(pc==submit){if(next.seq){frames.push_back(next);}next.seq++;return;}
        if(pc==accept){unsigned at=m.peek32(sp+4),n=m.peek32(sp+8);for(unsigned i=0;i<n;i++){
            int16_t got=int16_t(m.peek32(at+2*i)>>16);if(expected.empty()||got!=expected.front())pcm_mismatches++;
            if(!expected.empty())expected.pop_front();}checked++;return;}
        if(pc!=entry)return;
        unsigned raw=m.peek32(sp+4),n=m.peek32(sp+8),mode=m.peek32(sp+12),tp=m.peek32(sp+16),rp=m.peek32(sp+20),hp=m.peek32(sp+24);
        int init=m.peek32(sp+28),trig=m.peek32(sp+32);
        std::vector<uint8_t>control(mode==2?0x160:0x2dd8);for(unsigned i=0;i<control.size();i++)control[i]=m.peek32(raw+i)>>24;
        if(curve[0].empty())for(unsigned j=0;j<2;j++){curve[j].resize(2050);unsigned a=m.peek32(tp+4*j);for(unsigned i=0;i<2050;i++)curve[j][i]=m.peek32(a+i)>>24;}
        Tables tables{curve[0].data(),curve[1].data()};RNG rng{m.peek32(rp),m.peek32(rp+4)};uint16_t hold[]{uint16_t(m.peek32(hp)>>16),uint16_t(m.peek32(hp+2)>>16)};
        std::vector<int16_t>out(n);uint16_t state[127]={};
        if(!ref(control.data(),n,mode,&tables,&rng,hold,init,trig,out.data(),state))std::abort();
        for(auto v:out){expected.push_back(v);next.pcm.push_back(v);}samples+=n;calls++;
        unsigned first=mode==1?81:0,count=mode==0?81:mode==1?28:59,base=mode==2?121:0;
        for(unsigned i=first;i<first+count;i++)next.state[base+i]=state[i];
        if(mode==1)for(unsigned i=0;i<6;i++)next.side[i]=state[121+i];next.modes|=1u<<mode;
    }
    template<class M>void dsp(M&m,unsigned pc){
        if(!ref)return;
        if(pc==0x39c){unsigned pos=m.get(dsp56k::MemArea_X,0x418),at=m.get(dsp56k::MemArea_X,0x209);
            auto&v=source_seen[pos];v[0]++;v[1]=at;v[2]=m.get(dsp56k::MemArea_X,at+80);v[3]=m.get(dsp56k::MemArea_X,at+81);v[4]=m.get(dsp56k::MemArea_X,at);v[5]=m.get(dsp56k::MemArea_X,0x39f0);}
        if(pc!=commit)return;
        if(m.get(dsp56k::MemArea_X,0x418)!=0x20)return;
        unsigned record=m.get(dsp56k::MemArea_X,0x209);
        if((m.get(dsp56k::MemArea_X,record+80)&65535)!=0x4e52)return;
        // CF can submit the next frame before the current source is serviced.
        const Expected*e=nullptr;unsigned seq=m.get(dsp56k::MemArea_X,0x39f1);
        for(auto&f:frames)if((f.seq&65535)==seq)e=&f;
        if((next.seq&65535)==seq)e=&next;
        if(!e){state_mismatches++;return;}
        for(unsigned mode=0;mode<3;mode++)if(e->modes&(1u<<mode)){
            unsigned first=mode==1?81:0,count=mode==0?81:mode==1?28:59,base=mode==2?121:0;
            for(unsigned i=first;i<first+count;i++)if((m.get(dsp56k::MemArea_X,0x3800+base+i)&65535)!=e->state[base+i])state_mismatches++;
        }
        if(e->modes&2)for(unsigned i=0;i<6;i++)if((m.get(dsp56k::MemArea_X,0x3970+i)&65535)!=e->side[i])state_mismatches++;
        state_frames++;
        while(frames.size()>4)frames.pop_front();
    }
    ~Observer(){if(const char*p=std::getenv("NHR_EXACT_REPORT")){std::ofstream f(p);f<<"{\"requests\":"<<calls<<",\"native_samples\":"<<samples<<",\"checked_frames\":"<<checked<<",\"pcm_mismatches\":"<<pcm_mismatches<<",\"state_frames\":"<<state_frames<<",\"state_mismatches\":"<<state_mismatches<<",\"pending_native\":"<<expected.size()<<",\"source_seen\":{";bool comma=false;for(auto&v:source_seen){f<<(comma?",":"")<<'"'<<v.first<<"\":[";for(unsigned i=0;i<6;i++)f<<(i?",":"")<<v.second[i];f<<']';comma=true;}f<<"}}\n";}}
};inline Observer observer;
}
