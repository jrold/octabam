// Host-only extension to observer.h. Does not write target state or charge time.
// The builder replaces the old global instance with this derived observer.
#pragma once
#include <array>
#include "mc68k/cpuState.h"
namespace private_stack {
struct Observer : hybrid_safety::Observer {
    uint32_t entry=0, on_private=0, restore=0, rte=0, lo=0, top=0, saved=0;
    uint32_t owner=0, original=0, format=0, return_pc=0, peak=0, prefix_peak=0, minimum_ipl=7;
    uint64_t switched=0, restored=0, violations=0, fence_writes=0, saved_writes=0;
    bool active=false, restoring=false, watches=false, saved_before_private=false;
    std::array<uint32_t,15> registers{};
    hybrid_safety::Stack private_stack{0,0,0};
    Observer() {
        auto env=[](const char* n) {auto* p=std::getenv(n);return p ? uint32_t(std::strtoul(p,nullptr,0)):0u;};
        entry=env("HYBRID_IRQ_ENTRY");on_private=env("HYBRID_IRQ_PRIVATE");
        restore=env("HYBRID_IRQ_RESTORE");rte=env("HYBRID_IRQ_RTE");
        lo=env("HYBRID_IRQ_LOW");top=env("HYBRID_IRQ_TOP");saved=env("HYBRID_IRQ_SAVED");
        private_stack={lo,top,top};
    }
    void step(ot::Machine& m, uint32_t pc) {
        if(!entry) {hybrid_safety::Observer::step(m,pc);return;}
        if(!watches) {
            watches=true;
            m.addWriteWatch(lo-32,lo-1,[this](uint32_t,uint8_t,uint32_t,uint32_t){++fence_writes;});
            m.addWriteWatch(top,top+31,[this](uint32_t,uint8_t,uint32_t,uint32_t){++fence_writes;});
            m.addWriteWatch(saved,saved+3,[this](uint32_t a,uint8_t n,uint32_t,uint32_t at){
                ++saved_writes;saved_before_private=true;
                if(a!=saved || n!=4 || at!=entry)++violations;
            });
        }
        auto* cpu=m.getCpuState();
        const bool execute=!(cpu->nmi_pending || cpu->int_level>cpu->int_mask);
        const auto sp=m.getA7(),tcb=m.peek32(ot::g_curTcb);
        const auto sr=m68k_get_reg(m.getCpuState(),M68K_REG_SR);
        // The first MOVEL can execute inside the interrupted step. At +6,
        // A7 and all GPRs still have their exception-entry values.
        if(pc==entry || pc==entry+6) {
            const auto f=m.peek32(sp);
            if(((f>>18)&255)==65 && (f>>28)>=4 && (f>>28)<=7 && (!active || sp!=original)) {
                if(active)++violations;
                active=true;restoring=false;owner=tcb;original=sp;
                format=f;return_pc=m.peek32(sp+4);
                for(unsigned i=0;i<15;++i)
                    registers[i]=m68k_get_reg(m.getCpuState(),m68k_register_t(M68K_REG_D0+i));
            }
            handlers[entry+6]={65,0};
        }
        if(pc==on_private && execute) {
            ++switched;
            saved_before_private=false;
            if(!active || sp!=top || m.peek32(saved)!=original)++violations;
        }
        const bool in_private=lo<=sp && sp<=top;
        if(active) {
            if(tcb!=owner)++violations;
            if(in_private) {
                peak=std::max(peak,top-sp);
                minimum_ipl=std::min(minimum_ipl,(sr>>8)&7);
                if(((sr>>8)&7)<5)++violations;
            } else if(!restoring && pc!=entry && pc!=entry+6) {
                // Prefix IRQs may still use the interrupted stack before LEA.
                // They are valid only near the original exception record.
                if(sp>original || original-sp>2048)++violations;
            }
            if(!in_private && sp<=original+8)prefix_peak=std::max(prefix_peak,original+8-sp);
        }
        const auto previous_need=frame_need;
        const auto previous_entries=entries[65];
        auto task=stacks.find(tcb);
        hybrid_safety::Stack old{};
        const bool substitute=in_private && task!=stacks.end();
        if(substitute) {old=task->second;task->second=private_stack;}
        // Pending higher IRQs can preempt a RTE before it executes. Do not
        // count an attempted RTE as a completed audio return.
        hybrid_safety::Observer::step(m,pc,execute);
        if(substitute) {private_stack=task->second;task->second=old;}
        if(entries[65]>previous_entries && pc==entry+6 && !nested[tcb].empty())
            nested[tcb].back().entry_cycles=1; // actual extra MOVEL cost, not omitted
        // Unlike the old single-A7 observer, depths in the two arenas must
        // never be subtracted from each other.
        frame_need=std::max(previous_need,peak+8);
        if(pc==restore)restoring=true;
        if(pc==rte && execute) {
            ++restored;
            if(!active || sp!=original || m.peek32(saved)!=original || m.peek32(sp)!=format || m.peek32(sp+4)!=return_pc)
                ++violations;
            for(unsigned i=0;i<15;++i)
                if(registers[i]!=m68k_get_reg(m.getCpuState(),m68k_register_t(M68K_REG_D0+i)))++violations;
            active=false;restoring=false;
        }
    }
    ~Observer() {
        auto* p=std::getenv("HYBRID_PRIVATE_REPORT");if(!p)return;
        std::ofstream f(p);
        f<<"{\"switched\":"<<switched<<",\"restored\":"<<restored
         <<",\"private_capacity_bytes\":"<<top-lo<<",\"private_observed_peak_bytes\":"<<peak
         <<",\"prefix_observed_peak_bytes\":"<<prefix_peak<<",\"minimum_private_IPL\":"<<minimum_ipl
         <<",\"ownership_register_frame_or_mask_violations\":"<<violations
         <<",\"fence_writes\":"<<fence_writes<<",\"saved_A7_writes\":"<<saved_writes
         <<",\"terminal_saved_store_before_private\":"<<saved_before_private
         <<",\"in_flight_at_capture_end\":"<<(active || saved_before_private)<<"}\n";
    }
};
}
