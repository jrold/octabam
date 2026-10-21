// The same independent oracle, observed at async submit and commit boundaries.
#pragma once
#define noise_hat_exact noise_hat_async_base
#define NHA_NO_GLOBAL_OBSERVER
#include "noise_hat_observer.h"
#undef NHA_NO_GLOBAL_OBSERVER
#undef noise_hat_exact
namespace noise_hat_exact {
struct AsyncObserver:noise_hat_async_base::Observer {
    uint32_t completion=0,completion_sp=0,completion_ret=0;
    AsyncObserver(){if(const char*p=std::getenv("NHA_EXACT_COMPLETE"))completion=std::strtoul(p,nullptr,0);}
    void step(ot::Machine&m,uint32_t pc){
        if(!render)return;
        if(pc==completion){completion_sp=m.getA7();completion_ret=m.peek32(completion_sp);return;}
        if(pending&&completion_ret&&pc==completion_ret&&m.getA7()==completion_sp+4){
            // Reuse the ordinary witness's complete comparison at this RTS.
            sp=completion_sp;ret=completion_ret;
            noise_hat_async_base::Observer::step(m,pc);completion_ret=0;return;
        }
        if(pc==entry){
            // The ordinary observer captures exactly the same seven arguments.
            noise_hat_async_base::Observer::step(m,pc);
            // Submit returns before PCM exists. Disable its ordinary RTS match.
            ret=0;
        }
    }
};inline AsyncObserver observer;
}
