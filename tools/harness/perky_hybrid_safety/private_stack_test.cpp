// Synthetic calibration of switch-window coverage and refusal instrumentation.
// Integrated runs separately execute the real image, tasks, audio and eDMA.
#include "mc68k/cpuState.h"
#include "observer.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <vector>
int main(int argc,char** argv) {
    assert(argc==4);
    const bool fast=std::atoi(argv[2]);
    const unsigned window=std::atoi(argv[3]);
    auto& o=hybrid_safety::observer;
    ot::Machine m({});auto* cpu=m.getCpuState();
    m68k_set_reg(cpu,M68K_REG_SR,0x2000);m68k_set_reg(cpu,M68K_REG_VBR,0x40000000);
    const uint32_t task=0x460bcc2c, initial=task-64;
    m.poke32(ot::g_curTcb,task);m.setA7(initial);m.setPC(0x40002000);
    for(unsigned i=0;i<15;++i)m68k_set_reg(cpu,m68k_register_t(M68K_REG_D0+i),0x11220000+i);
    m.poke32(0x40000104,0x40001000);m.poke32(0x40000120,0x40001100);
    std::ifstream f(argv[1],std::ios::binary);assert(f);
    std::vector<uint8_t> code((std::istreambuf_iterator<char>(f)),{});assert(code.size()==30);
    for(unsigned i=0;i<code.size();++i)m.write8(0x40001000+i,code[i]);
    const uint8_t inner[]={0x4f,0xef,0xff,0xf0,0x4e,0x71,0x4f,0xef,0,0x10,0x4e,0x73};
    for(unsigned i=0;i<sizeof inner;++i)m.write8(0x40001100+i,inner[i]);
    for(unsigned i=0;i<32;++i)m.write16(0x40002000+2*i,0x4e71);
    o.refresh(m);
    auto step=[&]{assert(fast?m.stepFast():m.step());};
    auto until=[&](uint32_t pc){for(unsigned i=0;i<64 && m.pc()!=pc;++i)step();assert(m.pc()==pc);};
    const auto started=m.getCycles();
    m.injectInterrupt(65,5);
    const uint32_t windows[]={0x40001006,0x40001010,0x40001016,0x4000101c,0x4000100c};
    assert(window<6);
    until(windows[window<5?window:1]);
    if(window==5) {
        // Calibrate three independently counted failures while restoring the
        // stimulus before executing target code. The real-run observer is read only.
        const auto violations=o.violations;
        m68k_set_reg(cpu,M68K_REG_SR,0x2400);step();
        assert(o.violations>violations);m68k_set_reg(cpu,M68K_REG_SR,0x2500);
        const auto fences=o.fence_writes;
        m.write32(0x495ffd80,0); // uncached alias of the bottom fence
        assert(o.fence_writes==fences+1);
        const auto ownership=o.violations;
        m.poke32(ot::g_curTcb,0x460d4f80);step();
        assert(o.violations>ownership);m.poke32(ot::g_curTcb,task);
    } else {
        m.injectInterrupt(72,6);
    }
    for(unsigned i=0;i<64 && m.getA7()!=initial;++i)step();
    assert(m.getA7()==initial && o.switched==1 && o.restored==1);
    assert(m.getCycles()-started==o.isr_max_cycles+4); // interrupted task NOP
    assert(o.nested[task].empty() && o.saved_writes==1);
    if(window<5)assert(o.violations==0 && o.fence_writes==0);
    if(window==1)assert(o.peak==276);
    std::printf("PASS private observer fast=%u window=%u peak=%u prefix=%u violations=%llu fences=%llu ISR=%llu elapsed=%llu\n",
        fast,window,o.peak,o.prefix_peak,(unsigned long long)o.violations,(unsigned long long)o.fence_writes,(unsigned long long)o.isr_max_cycles,(unsigned long long)(m.getCycles()-started));
}
