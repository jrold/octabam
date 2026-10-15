// Actual firmware/controller test. Arrival bursts are adversarial host stimuli,
// not a claim that a physical clock generated them at this rate.
#include "machine.h"
#include "rtos.h"
#include "mc68k/cpuState.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <vector>

int main(int argc, char** argv) {
    assert(argc == 3);
    for (bool burst : {false, true}) for (unsigned variant = 0; variant < 2; ++variant) {
        std::ifstream input(argv[variant + 1], std::ios::binary);
        assert(input);
        std::vector<uint8_t> image((std::istreambuf_iterator<char>(input)), {});
        ot::Machine m(image);
        assert(m.run(50'000'000) == ot::Machine::Stop::Handoff);
        ot::Rtos r(m, 3990, 132e6, false);
        r.install();
        assert(r.runUntil(1000, [&] { return m.pc() == 0x4005595c; }) == ot::Rtos::Stop::Gate);
        assert(m.peek32(ot::g_curTcb) == 0x460d4f80);
        assert(m.peek32(m.vbr() + 0x60*4) == 0x400a1e0c);
        assert(m.read8(ot::g_intc0 + 0x60) == 3);
        assert(m.read16(0x400a1e64) == 0x46fc);
        assert(m.read16(0x400a1e66) == (variant ? 0x2300 : 0x2200));
        m.watchPc({0x400a1e10});
        auto request = [&] { m.write32(ot::g_intc0 + 0x10, m.read32(ot::g_intc0 + 0x10) | 1); };
        const auto ticks0 = r.ticks();
        const uint32_t phase0 = m.peek32(0x4610757c);
        assert(m.peek32(0x46107568) == 0);
        request();
        assert(r.runUntil(10, [&] { return m.pc() == 0x400a1e68; }) == ot::Rtos::Stop::Gate);
        const auto held = m.getA7();
        assert(((m68k_get_reg(m.getCpuState(), M68K_REG_SR)>>8)&7) == (variant ? 3 : 2));
        request();
        if (burst) {
            // Same number of target instructions between the two new force
            // writes in both variants. The original has cleared the first;
            // the guarded image must keep it pending throughout the body.
            const auto at = m.instructions();
            assert(r.runUntil(10, [&] { return m.instructions() >= at+64; }) == ot::Rtos::Stop::Gate);
            const bool pending = (m.read32(ot::g_intc0+0x10)&1) != 0;
            std::printf("BEFORE_SECOND variant=%u pending=%u ticks=%llu depth_bytes=%u\n",
                variant, pending, (unsigned long long)(r.ticks()-ticks0), held-m.getA7());
            assert(pending == (variant != 0));
            request();
        } else {
            const auto acks0 = r.acks().size();
            r.panelIn({0x21, 0}); // real UART1 RX interrupt, level 6
            assert(r.runUntil(10, [&] { return r.panelPending() == 0; }) == ot::Rtos::Stop::Gate);
            bool uart6 = false;
            for (size_t i=acks0; i<r.acks().size(); ++i)
                if (r.acks()[i].vector == 0x5b && r.acks()[i].level == 6) uart6 = true;
            assert(uart6);
        }
        assert(r.runToMainSpin(100) == ot::Rtos::Stop::Gate);
        const auto delivered = r.ticks()-ticks0;
        const unsigned expected = burst ? 3 : 2;
        const uint32_t phase_advance = m.peek32(0x4610757c) - phase0;
        // The due flags distinguish musical clock/subtick work from IRQ
        // requests. Arbitrary force writes are not a valid clock oracle.
        if (!variant || !burst) assert(delivered == expected);
        if (variant && burst) assert(delivered == 2);
        assert((m.read32(ot::g_intc0+0x10)&1) == 0);
        const auto& entries=m.pcHits();
        assert(entries.size()==delivered);
        if(variant) for(const auto& hit:entries) assert(hit.sp==entries.front().sp);
        else assert(entries[1].sp<entries[0].sp); // reentry negative control
        std::printf("RESULT variant=%u case=%s requests=%u serviced=%llu pending=0 phase_advance=%u same_entry_sp=%u\n",
            variant, burst ? "TWO_DEFERRED_ARRIVALS" : "ONE_DEFERRED_PLUS_UART6", expected,
            (unsigned long long)delivered, phase_advance,variant);
        std::fflush(stdout);
    }
    std::puts("PASS_LOCAL: single deferral and UART6 function; arbitrary burst demonstrates the one-bit latch limit, not a natural clock-loss proof");
    return 0;
}
