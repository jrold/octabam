// Bounded read-only ownership/driver probe of the checkpoint firmware.
// Stimuli are host requests to the real kernel; no firmware patch is installed.
#include "machine.h"
#include "rtos.h"
#include "mc68k/cpuState.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <vector>

static std::vector<uint8_t> load(const char* path) {
    std::ifstream f(path, std::ios::binary); assert(f);
    return {(std::istreambuf_iterator<char>(f)), {}};
}

int main(int argc, char** argv) {
    assert(argc == 4);
    {
        // Calibrate independent extra instructions proposed for an audio-stack
        // switch. No interrupt wrapper, detour, or changed firmware is built.
        auto code=load(argv[3]); assert(code.size()==24);
        ot::Machine c({});
        for(unsigned i=0;i<code.size();++i)c.write8(0x40002000+i,code[i]);
        for(unsigned op=0;op<4;++op) {
            uint64_t cost=0;
            for(unsigned n=0;n<100;++n) {
                m68k_set_reg(c.getCpuState(),M68K_REG_SR,0x2500);
                c.setA7(0x460bcc24);c.poke32(0x41600dc0,0x460bcc24);
                c.setPC(0x40002000+6*op);
                const auto before=c.getCycles();assert(c.stepFast());
                const auto elapsed=c.getCycles()-before;
                if(!n)cost=elapsed;else assert(cost==elapsed);
                if(op==1)assert(c.peek32(0x41600dc0)==0x460bcc24);
                if(op==2)assert(c.getA7()==0x41600da0);
                if(op==3)assert(c.getA7()==0x460bcc24);
            }
            std::printf("INSTRUCTION_COST specimen=%u cycles=%llu repetitions=100\n",op,(unsigned long long)cost);
        }
    }
    ot::Machine m(load(argv[1]));
    m.watchPc({0x40000638}); // after create's actual stack/TCB stores
    assert(m.run(50'000'000) == ot::Machine::Stop::Handoff);
    ot::AtaCard card(load(argv[2])); // memory only, no writeback
    ot::Rtos r(m,3990,132e6,false);
    r.attachCard(card); r.mapCardMemory(); r.install();
    // runUntil evaluates on every instruction; audit each fresh context before
    // make-ready/scheduler can consume it. watchPc is a separate cross-check.
    unsigned initialized=0;
    const auto stop=r.runUntil(1000,[&] {
        if(m.pc()==0x40000638) {
            const auto s=m.getA7();
            const auto tcb=m.peek32(s+4),entry=m.peek32(s+8),prio=m.peek32(s+12);
            const auto base=m.peek32(s+16),size=m.peek32(s+20);
            const auto top=base+(size&~3u),saved=m.peek32(tcb+0x48);
            assert(saved==top-12 && m.peek32(saved)==0x407c2000);
            assert(m.peek32(saved+4)==entry && m.peek32(saved+8)==0x400006e4);
            assert(m.peek32(tcb+8)==0x800068dc+4*prio);
            assert(m.peek32(tcb+0x4c)==0 && m.peek32(tcb+0x50)==0);
            std::printf("INIT task=%s tcb=%08x entry=%08x priority=%u base=%08x size=%u saved=%08x creator=%08x\n",
                ot::taskName(tcb),tcb,entry,prio,base,size,saved,m.peek32(ot::g_curTcb));
            ++initialized;
        }
        return r.created().size()==10 && r.ran().size()==11 && m.pc()==ot::g_mainSpin;
    });
    assert(stop==ot::Rtos::Stop::Gate && initialized==10 && m.pcHits().size()==10);
    assert(r.gate());
    uint64_t bottomWrites=0;
    for(const auto& t:r.created())
        m.addWriteWatch(t.stack,t.stack+31,[&](uint32_t,uint8_t,uint32_t,uint32_t){++bottomWrites;});
    assert(m.read16(0x400a1e66)==0x2300);
    assert(r.requestCardMount());
    assert(r.runUntil(10000,[&]{return m.peek32(ot::g_cardReady)!=0;})==ot::Rtos::Stop::Gate);
    assert(r.runToMainSpin()==ot::Rtos::Stop::Gate);
    const auto table=m.peek32(0x460d16cc);
    assert(table==0x46c85c76 && m.peek32(table)==0x400157b4);
    std::printf("DRIVER table=%08x read=%08x read2=%08x write=%08x reads=%llu\n",
        table,m.peek32(table),m.peek32(table+4),m.peek32(table+8),(unsigned long long)card.sectorsRead());
    // Queue a single-sector USB-worker READ on the mounted memory-only card.
    const uint32_t msg=0x46c00020;
    m.poke32(msg,1);m.poke32(msg+4,0);m.poke32(msg+8,1);
    m.watchPc({0x4001eef2,0x400157b4,0x4001568c,0x40015098,0x40014b94});
    uint32_t d0=0;
    // Hold dispatch only while posting, so the probe can stop in the worker
    // rather than letting callAsMain consume the complete worker invocation.
    const auto sr=m68k_get_reg(m.getCpuState(),M68K_REG_SR);
    m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);
    assert(r.postMessage(0x460bb3a0,msg,d0));
    m68k_set_reg(m.getCpuState(),M68K_REG_SR,sr);
    assert(r.runUntil(100,[&]{return m.pc()==0x4001509c;})==ot::Rtos::Stop::Gate);
    assert(m.peek32(ot::g_curTcb)==0x460bcc2c && m.getA7()==0x460bcc2c-144);
    const auto taskSP=m.getA7();
    const auto ticks=r.ticks();
    const auto acks=r.acks().size();
    m.write32(ot::g_intc0+0x10,m.read32(ot::g_intc0+0x10)|1);
    assert(r.runUntil(10,[&]{return m.pc()==0x400a1e68;})==ot::Rtos::Stop::Gate);
    assert(m.getA7()==taskSP-216);
    const auto held=m.getA7();
    r.panelIn({0x21,0});
    unsigned low=m.getA7();
    assert(r.runUntil(100,[&]{
        low=std::min(low,m.getA7());
        return r.ticks()>ticks && m.pc()==0x400150a2 && m.getA7()==taskSP;
    })==ot::Rtos::Stop::Gate);
    bool uart=false;
    for(size_t i=acks;i<r.acks().size();++i) if(r.acks()[i].vector==0x5b && r.acks()[i].level==6)uart=true;
    assert(uart && r.panelPending()==0 && (m.read32(ot::g_intc0+0x10)&1)==0);
    std::printf("INTERRUPTED_STORAGE task_bytes=144 seq_entry_bytes=%u observed_combined=%u restored_sp=%08x UART6=1\n",
        taskSP-held,0x460bcc2c-low,m.getA7());
    assert(r.runToMainSpin()==ot::Rtos::Stop::Gate);
    bool indirect=false;
    for(const auto& hit:m.pcHits()) {
        if(hit.pc==0x40000638)continue; // watch history is cumulative
        std::printf("DRIVER_HIT pc=%08x sp=%08x depth=%u a0=%08x\n",hit.pc,hit.sp,0x460bcc2c-hit.sp,hit.a0);
        if(hit.pc==0x4001eef2) {assert(hit.a0==0x400157b4);indirect=true;}
    }
    assert(indirect);
    assert(bottomWrites==0);
    std::puts("BOTTOM_WATCH tasks=10 bytes_each=32 writes_after_initialization=0");
    std::puts("PASS: actual task initialization and PIO storage-worker driver dispatch; not an all-path stack qualification");
    return 0;
}
