// Host-only observer, staged into an isolated copy of the emulator sources.
// Reads RAM/registers; never writes target state or advances modeled time.
#pragma once
#include "machine.h"
#include "rtos.h"
#include "mc68k/Musashi/m68k.h"
#include <cstdlib>
#include <fstream>
#include <map>
#include <set>
#include <vector>
#include <tuple>
namespace hybrid_safety {
struct Stack {
    uint32_t lo, hi, minimum, pc = 0, irq_min = 0xffffffffu;
    uint64_t instructions = 0, below = 0;
};
struct Irq { uint32_t sp, vector, minimum; uint64_t cycles; uint32_t entry_cycles; };
struct Dma { uint32_t lo, hi; bool active = false; };
struct Observer {
    std::map<uint32_t, Stack> stacks;
    std::map<uint32_t, std::vector<Irq>> nested;
    std::map<uint32_t, std::pair<uint32_t,uint32_t>> handlers;
    std::map<uint32_t, uint64_t> entries, chains;
    std::map<uint32_t, Dma> dma;
    uint64_t instructions = 0, source_writes = 0, overlaps = 0, starts = 0;
    uint32_t depth = 0, frame_depth = 0, frame_need = 0, irq_floor = 7;
    uint64_t frames = 0, returns = 0;
    uint64_t render_calls[8]={}, render_samples[8]={};
    uint32_t queue_max=0, ring_max=0;
    uint32_t render_pc=0;
    uint64_t guard_writes=0, source_dma_starts=0, dma_restarts=0, isr_max_cycles=0, isr_duration_misses=0;
    std::map<std::tuple<uint32_t,uint32_t,uint32_t,uint32_t,int16_t>,uint64_t> source_shapes;
    std::ofstream events;
    Observer() {
        if(const char* p=std::getenv("HYBRID_RENDER_PC")) render_pc=std::strtoul(p,nullptr,0);
        for(const auto& t : ot::g_expectedTasks)
            stacks.emplace(t.tcb, Stack{t.stack, t.stack+t.size, t.stack+t.size});
        // Main's creator stack/size is checked independently from boot disassembly.
        stacks.emplace(ot::g_mainTcb, Stack{0x46c7aed8,0x46c7bed8,0x46c7bed8});
        if(const char* p = std::getenv("HYBRID_SAFETY_EVENTS")) events.open(p);
    }
    void refresh(ot::Machine& m) {
        handlers.clear();
        for(unsigned v=2; v<256; ++v) {
            const auto p=m.peek32(0x40000000+4*v);
            if(p && p!=0x40000d74) {
                handlers[p]={v,0};
                // Musashi can execute the first handler instruction inside the
                // interrupted step. Cover a leading lea -N(sp),sp explicitly.
                if(m.read16(p)==0x46fc) handlers[p+4]={v,0}; // move.w #imm,sr
                if(m.read16(p)==0x4fef) {
                    int16_t d=static_cast<int16_t>(m.read16(p+2));
                    if(d<0) handlers[p+4]={v,static_cast<uint32_t>(-d)};
                }
            }
        }
    }
    void step(ot::Machine& m, uint32_t pc) {
        ++instructions;
        queue_max=std::max(queue_max,m.peek32(0x460d17b2));
        ring_max=std::max(ring_max,m.peek32(0x460ffda0));
        if(render_pc && pc==render_pc) {
            auto s=m.getA7(), track=m.peek32(s+4), start=m.peek32(s+12), end=m.peek32(s+16);
            if(track<8 && end>=start && end<=16) {++render_calls[track];render_samples[track]+=end-start;}
        }
        if(pc==ot::g_sched || pc==ot::g_mainSpin) refresh(m);
        const auto sp=m.getA7(), tcb=m.peek32(ot::g_curTcb);
        const auto sr=m68k_get_reg(m.getCpuState(), M68K_REG_SR);
        auto& chain=nested[tcb];
        const auto found=handlers.find(pc);
        if(found!=handlers.end() && found->second.first!=32 && found->second.first!=171) {
            const auto entry_sp=sp+found->second.second;
            const auto f=m.peek32(entry_sp), v=(f>>18)&255;
            if((f>>28)>=4 && (f>>28)<=7 && v==found->second.first && (chain.empty() || chain.back().sp!=entry_sp)) {
                chain.push_back({entry_sp,v,sp,m.getCycles(),found->second.second ? 1u:0u}); ++entries[v];
                if(v==65) ++frames;
                depth=std::max(depth,static_cast<uint32_t>(chain.size()));
                uint32_t key=0; for(auto& i:chain) key=(key<<8)|i.vector;
                ++chains[key];
            }
        }
        for(auto& i:chain) {
            i.minimum=std::min(i.minimum,sp);
            if(i.vector==65) {
                frame_need=std::max(frame_need,i.sp+8-sp);
                frame_depth=std::max(frame_depth,static_cast<uint32_t>(chain.size()));
                irq_floor=std::min(irq_floor,(sr>>8)&7);
            }
        }
        auto it=stacks.find(tcb);
        if(it!=stacks.end() && !(pc>=0x40000550 && pc<=0x400005a8)) {
            auto& s=it->second;
            ++s.instructions;
            if(sp<s.minimum) {s.minimum=sp;s.pc=pc;}
            if(sp<s.lo || sp>s.hi) {++s.below; if(events.is_open() && s.below<5) events<<"STACK_OUTSIDE "<<tcb<<' '<<pc<<' '<<sp<<'\n';}
            if(!chain.empty()) s.irq_min=std::min(s.irq_min,sp);
        }
        if(m.read16(pc)==0x4e73 && !chain.empty() && sp==chain.back().sp) {
            if(chain.back().vector==65) {
                ++returns;
                auto cost=m.getCycles()-chain.back().cycles+chain.back().entry_cycles+10;
                isr_max_cycles=std::max(isr_max_cycles,cost);
                if(cost*44100ull>16ull*264000000) ++isr_duration_misses;
            }
            chain.pop_back();
        }
        // Actual state transitions, observed on every instruction, not poked.
        if(events.is_open()) {
            static uint32_t old[5]={~0u,~0u,~0u,~0u,~0u};
            const uint32_t now[]={m.peek32(ot::g_partPtr),m.read8(0x100b14cf),
                m.peek32(0x800065b8),m.read8(0x100b14cc),m.read8(0x80000002)};
            for(unsigned i=0;i<5;++i) if(now[i]!=old[i]) {
                events<<instructions<<' '<<pc<<' '<<i<<' '<<now[i]<<'\n';old[i]=now[i];
            }
        }
    }
    void write(uint32_t a, uint8_t size, uint32_t pc) {
        ++source_writes;
        for(const auto& d:dma) if(d.second.active && a<d.second.hi && a+size>d.second.lo) {
            ++overlaps;
            if(events.is_open()) events<<"DMA_OVERLAP "<<pc<<' '<<a<<' '<<d.first<<'\n';
        }
    }
    void guard(uint32_t tcb) {
        if(stacks[tcb].instructions) ++guard_writes;
    }
    void start(uint32_t ch,uint32_t src,uint32_t bytes,uint32_t loops,int16_t soff) {
        ++starts;
        if(dma[ch].active) ++dma_restarts;
        if(src>=0x80001c90 && src<0x80003190) {
            ++source_dma_starts; ++source_shapes[{ch,src,bytes,loops,soff}];
        }
        // The observed source-to-host TCDs use contiguous positive strides.
        // Non-source transfers are still counted; negative-stride coverage is absent.
        const uint32_t n=soff>0 ? bytes*loops : 0;
        dma[ch]={src,src+n,n!=0};
    }
    void done(uint32_t ch) {dma[ch].active=false;}
    ~Observer() {
        const char* p=std::getenv("HYBRID_SAFETY_REPORT"); if(!p) return;
        std::ofstream f(p);
        f<<"{\"instructions\":"<<instructions<<",\"frames\":"<<frames
         <<",\"frame_returns\":"<<returns<<",\"max_nesting\":"<<depth
         <<",\"max_frame_nesting\":"<<frame_depth<<",\"max_frame_stack_bytes\":"<<frame_need
         <<",\"minimum_frame_IPL\":"<<irq_floor<<",\"source_writes\":"<<source_writes
         <<",\"DMA_starts\":"<<starts<<",\"DMA_read_write_overlaps\":"<<overlaps<<",\"stacks\":[";
        bool comma=false;
        for(const auto& pair:stacks) {
            auto& s=pair.second; if(comma) f<<',';comma=true;
            f<<"{\"task\":\""<<ot::taskName(pair.first)<<"\",\"base\":"<<s.lo
             <<",\"capacity\":"<<s.hi-s.lo<<",\"observed_bytes\":"<<s.hi-s.minimum
             <<",\"minimum_sp\":"<<s.minimum<<",\"pc_at_minimum\":"<<s.pc
             <<",\"instructions\":"<<s.instructions<<",\"outside_extent\":"<<s.below<<'}';
        }
        f<<"],\"guard_writes_after_dispatch\":"<<guard_writes
         <<",\"source_DMA_starts\":"<<source_dma_starts<<",\"DMA_active_restarts\":"<<dma_restarts
         <<",\"full_ISR_max_cycles\":"<<isr_max_cycles<<",\"ISR_duration_misses\":"<<isr_duration_misses;
        f<<",\"source_DMA_shapes\":[";comma=false;
        for(const auto& p:source_shapes) {
            if(comma) f<<',';comma=true;
            const auto& k=p.first;
            f<<'['<<std::get<0>(k)<<','<<std::get<1>(k)<<','<<std::get<2>(k)<<','<<std::get<3>(k)<<','<<std::get<4>(k)<<','<<p.second<<']';
        }
        f<<"],\"render_calls\":[";
        for(unsigned i=0;i<8;++i) {if(i)f<<',';f<<render_calls[i];}
        f<<"],\"render_samples\":[";
        for(unsigned i=0;i<8;++i) {if(i)f<<',';f<<render_samples[i];}
        f<<"],\"sys_queue_max\":"<<queue_max<<",\"panel_ring_max\":"<<ring_max;
        f<<",\"interrupt_chains\":[";comma=false;
        for(auto& pair:chains) {if(comma)f<<',';comma=true;f<<"["<<pair.first<<','<<pair.second<<"]";}
        f<<"]}\n";
    }
};
inline Observer observer;
}
