// Supplemental host observations for the bounded guard qualification.
#pragma once
#include "observer.h"
#include <cstdio>
namespace guard_audit {
struct Audit {
    FILE* file = nullptr;
    uint32_t render = 0;
    bool active = false;
    uint64_t posts = 0, pops = 0;
    uint32_t initial = 0;
    struct Wait {uint32_t pc, sp;};
    std::map<uint32_t,Wait> waits;
    Audit() {
        if(auto* p=std::getenv("HYBRID_GUARD_AUDIT")) file=std::fopen(p,"w");
        if(auto* p=std::getenv("HYBRID_RENDER_PC")) render=std::strtoul(p,nullptr,0);
    }
    void step(ot::Machine& m, uint32_t pc) {
        const uint32_t sp=m.getA7(), task=m.peek32(ot::g_curTcb);
        if(pc==0x40000d00 && m.peek32(sp+4)==0x460d17ae)
            waits[task]={m.peek32(sp),sp};
        if(!file) return;
        if(!active && m.read8(0x46c00010)==1) {
            active=true;initial=m.peek32(0x460d17b2);
            std::fprintf(file,"BEGIN %llu %u\n",(unsigned long long)m.getCycles(),initial);
        }
        if(!active) return;
        const auto tick=(unsigned long long)m.getCycles();
        auto message=[&](char kind,uint32_t msg) {
            std::fprintf(file,"QUEUE %c %llu %08x",kind,tick,msg);
            for(unsigned i=0;i<8;++i)std::fprintf(file," %02x",m.read8(msg+i));
            std::fputc('\n',file);
        };
        if(pc==0x40000c3c && m.peek32(sp+4)==0x460d17ae) {
            ++posts;message('P',m.peek32(sp+8));
        }
        auto wait=waits.find(task);
        if(wait!=waits.end() && pc==wait->second.pc && sp==wait->second.sp+4) {
            ++pops;message('G',m68k_get_reg(m.getCpuState(),M68K_REG_D0));waits.erase(wait);
        }
        if(pc==render && m.peek32(sp+16)==16) {
            auto track=m.peek32(sp+4),fp=m.peek32(0x800062a8);
            if(track<8) {
                std::fprintf(file,"SOURCE %llu %llu %u %u %u",tick,(unsigned long long)hybrid_safety::observer.frames,track,m.peek32(sp+12),unsigned(m.read8(0x46104d0c+track)));
                for(unsigned i=0;i<6;++i)std::fprintf(file," %u",m.read16(fp+2*i)>>8);
                std::fputc('\n',file);
                if(track==7) std::fprintf(file,"CFCOUNT %llu %u %u\n",(unsigned long long)hybrid_safety::observer.frames,m.peek32(0x40c89a7c),m.peek32(0x40c89a80));
            }
        }
    }
    ~Audit() {
        if(file) {std::fprintf(file,"END %llu %llu\n",(unsigned long long)posts,(unsigned long long)pops);std::fclose(file);}
    }
};
inline Audit audit;
}
