// Real stock eDMA mask-lowering path, adversarial UART6/state6 arrivals.
// Seeds a bounded live-SP position; integrated tests separately execute audio.
#include "machine.h"
#include "rtos.h"
#include "mc68k/cpuState.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <vector>
int main(int argc,char** argv) {
    assert(argc==2);std::ifstream f(argv[1],std::ios::binary);assert(f);
    std::vector<uint8_t> image((std::istreambuf_iterator<char>(f)),{});
    for(bool dma_child:{false,true}) {
        ot::Machine m(image);assert(m.run(50'000'000)==ot::Machine::Stop::Handoff);
        ot::Rtos r(m,3990,132e6,false);r.install();assert(r.runToMainSpin()==ot::Rtos::Stop::Gate);
        const uint32_t seed=0x41600da0-1308,task=m.peek32(ot::g_curTcb);
        m.setA7(seed);m.setPC(ot::g_mainSpin);m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2500);
        m.poke32(0x46104d3e,5);m.injectInterrupt(72,6);
        assert(r.runUntil(10,[&]{return m.pc()==0x400031a4;})==ot::Rtos::Stop::Gate);
        assert(m.getA7()==seed-176 && m.peek32(0x46104d3e)==6);
        assert(((m68k_get_reg(m.getCpuState(),M68K_REG_SR)>>8)&7)==5);
        uint32_t low=m.getA7();bool child=false;
        if(dma_child)m.injectInterrupt(73,6);else r.panelIn({0x21,0});
        assert(r.runUntil(100,[&]{
            low=std::min(low,m.getA7());
            if(m.pc()==(dma_child?0x40004844u:0x400109c4u))child=true;
            return child && m.pc()==ot::g_mainSpin && m.getA7()==seed;
        })==ot::Rtos::Stop::Gate);
        assert(m.peek32(ot::g_curTcb)==task && seed-low<=212);
        assert(dma_child ? m.peek32(0x46104d3e)==7u : (m.peek32(0x46104d3e)==6u || m.peek32(0x46104d3e)==7u));
        std::printf("PASS real eDMA5 -> %s: depth=%u <=212; state=%u; exact A7/owner restored\n",
            dma_child?"eDMA6":"UART6",seed-low,m.peek32(0x46104d3e));
    }
}
