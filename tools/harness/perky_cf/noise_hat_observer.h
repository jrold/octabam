// Host-side exactness witness. The target executes one renderer only; the
// original complete CF renderer runs in a native shadow outside target time.
#pragma once
#include "machine.h"
#include <dlfcn.h>
#include <cstdlib>
#include <fstream>
#include <vector>
#include <cstdint>
namespace noise_hat_exact {
struct Tables {const uint8_t *a,*b;};
struct Rng {uint32_t low,high;};
struct Observer {
    using Render=int(*)(uint8_t*,int16_t*,uint32_t,unsigned,const Tables*,Rng*,uint16_t*);
    Render render=nullptr;uint32_t entry=0,sp=0,ret=0,raw=0,output=0,rng=0,hold=0,n=0,mode=0;
    uint64_t calls=0,checked=0,samples=0,mismatches=0;bool pending=false;
    std::vector<uint8_t>state,curve1,curve2;std::vector<int16_t>pcm;Rng expected_rng{};uint16_t expected_hold[2]{};
    Observer(){
        const char *p=std::getenv("NHA_EXACT_LIBRARY"),*q=std::getenv("NHA_EXACT_ENTRY");
        if(!p||!q)return;entry=std::strtoul(q,nullptr,0);
        void *library=dlopen(p,RTLD_NOW);if(!library)std::abort();
        render=reinterpret_cast<Render>(dlsym(library,"pk_cf_nh_render"));if(!render)std::abort();
    }
    static std::vector<uint8_t> bytes(ot::Machine&m,uint32_t a,unsigned size){std::vector<uint8_t>v(size);for(unsigned i=0;i<size;i++)v[i]=m.read8(a+i);return v;}
    void step(ot::Machine&m,uint32_t pc){
        if(!render)return;
        if(pending&&pc==ret&&m.getA7()==sp+4){
            if(bytes(m,raw,state.size())!=state)++mismatches;
            if(m.peek32(rng)!=expected_rng.low||m.peek32(rng+4)!=expected_rng.high)++mismatches;
            if(m.read16(hold)!=expected_hold[0]||m.read16(hold+2)!=expected_hold[1])++mismatches;
            for(unsigned i=0;i<n;i++)if(static_cast<int16_t>(m.read16(output+2*i))!=pcm[i])++mismatches;
            ++checked;samples+=n;pending=false;
        }
        if(pc!=entry)return;
        if(pending){++mismatches;return;}
        sp=m.getA7();ret=m.peek32(sp);raw=m.peek32(sp+4);output=m.peek32(sp+8);n=m.peek32(sp+12);mode=m.peek32(sp+16);
        uint32_t tables=m.peek32(sp+20);rng=m.peek32(sp+24);hold=m.peek32(sp+28);
        if(n>20||mode>2){++mismatches;return;}
        state=bytes(m,raw,mode==2?0x160:0x2dd8);curve1=bytes(m,m.peek32(tables),4096);curve2=bytes(m,m.peek32(tables+4),4096);
        pcm.assign(n,0);expected_rng={m.peek32(rng),m.peek32(rng+4)};expected_hold[0]=m.read16(hold);expected_hold[1]=m.read16(hold+2);
        Tables t{curve1.data(),curve2.data()};
        if(!render(state.data(),pcm.data(),n,mode,&t,&expected_rng,expected_hold))++mismatches;
        ++calls;pending=true;
    }
    ~Observer(){if(const char*p=std::getenv("NHA_EXACT_REPORT"))std::ofstream(p)<<"{\"calls\":"<<calls<<",\"checked\":"<<checked<<",\"native_samples\":"<<samples<<",\"mismatches\":"<<mismatches<<",\"pending\":"<<(pending?1:0)<<"}\n";}
};
#ifndef NHA_NO_GLOBAL_OBSERVER
inline Observer observer;
#endif
}
