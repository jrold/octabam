// Synthetic target IRQs calibrate the observer's entry, nesting and RTE coverage.
#include "mc68k/cpuState.h"
#include "observer.h"
#include <cassert>
#include <cstdio>
using namespace hybrid_safety;
int main() {
    for(bool fast : {false,true}) for(bool sr_prefix : {false,true}) {
        ot::Machine m({});
        auto cpu=m.getCpuState();
        const uint32_t top=0x460bcc2c, task=0x460bcc2c;
        m68k_set_reg(cpu,M68K_REG_SR,0x2000);
        m68k_set_reg(cpu,M68K_REG_VBR,0x40000000);
        m.setA7(top-64);m.setPC(0x40002000);
        m.poke32(ot::g_curTcb,task);
        m.poke32(0x40000104,0x40001000); // vector 65
        m.poke32(0x40000120,0x40001100); // vector 72
        // lea -252(sp),sp; nop; lea 252(sp),sp; rte
        const uint8_t outer[]={0x4f,0xef,0xff,0x04,0x4e,0x71,0x4f,0xef,0,0xfc,0x4e,0x73};
        const uint8_t inner[]={0x4f,0xef,0xff,0xf0,0x4e,0x71,0x4f,0xef,0,0x10,0x4e,0x73};
        if(sr_prefix) m.poke32(0x40001000,0x46fc2500);
        for(unsigned i=0;i<sizeof outer;++i)m.write8(0x40001000+(sr_prefix?4:0)+i,outer[i]);
        for(unsigned i=0;i<sizeof inner;++i)m.write8(0x40001100+i,inner[i]);
        for(unsigned i=0;i<16;++i)m.write16(0x40002000+2*i,0x4e71);
        observer.nested.clear();observer.refresh(m);
        auto step=[&] {assert(fast ? m.stepFast():m.step());};
        auto before=observer.frames, returns=observer.returns;
        m.injectInterrupt(65,5);
        for(unsigned i=0;i<8 && m.pc()!=(sr_prefix?0x40001008u:0x40001004u);++i)step();
        assert(m.pc()==(sr_prefix?0x40001008u:0x40001004u));
        // Observe the outer's state before taking its higher-priority IRQ.
        step();m.injectInterrupt(72,6);
        for(unsigned i=0;i<24 && (m.pc()<0x40002000 || m.pc()>0x40002020);++i)step();
        assert(m.getA7()==top-64);
        assert(observer.frames==before+1 && observer.returns==returns+1);
        assert(observer.depth==2 && observer.frame_need==284);
        assert(observer.nested[task].empty());
        // Positive/negative DMA overlap controls, and an explicit stack overrun.
        const auto overlaps=observer.overlaps;
        observer.start(1,0x80001c90,160,1,4);
        m.write32(0x80001c90,0);
        assert(observer.overlaps==overlaps+1);
        observer.done(1);m.write32(0x80001c90,0);
        assert(observer.overlaps==overlaps+1);
        const auto guard=observer.guard_writes;
        m.write32(observer.stacks[task].lo,0);
        assert(observer.guard_writes==guard+1);
        const auto outside=observer.stacks[task].below;
        m.setA7(observer.stacks[task].lo-4);m.setPC(0x40002000);step();
        assert(observer.stacks[task].below==outside+1);
        std::printf("PASS %s prefix=%d: real IRQ entry, 5->6 nesting, 284-byte frame depth, RTE balance, DMA overlap/refusal, stack overflow detection\n",fast?"stepFast":"step",sr_prefix);
    }
}
