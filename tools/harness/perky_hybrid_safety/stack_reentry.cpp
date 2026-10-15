// Actual-image, adversarial interrupt-arrival test. No firmware bytes included.
// Repeated requests are forced by the TEST, not claimed as a playback workload.
#include "machine.h"
#include "rtos.h"
#include "mc68k/cpuState.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <vector>

int main(int argc, char** argv) {
    assert(argc == 2);
    std::ifstream f(argv[1], std::ios::binary);
    assert(f);
    const std::vector<uint8_t> image((std::istreambuf_iterator<char>(f)), {});
    for (bool counterfactual : {false, true}) {
        ot::Machine m(image);
        assert(m.run(50'000'000) == ot::Machine::Stop::Handoff);
        ot::Rtos r(m, 3990.0, 132e6, false);
        r.install();
        // Stop in the real keyrepeat task after its two saved address registers.
        assert(r.runUntil(1000, [&] { return m.pc() == 0x4005595c; }) == ot::Rtos::Stop::Gate);
        const auto& task = ot::g_expectedTasks[8];
        assert(task.tcb == 0x460d4f80 && task.size == 2048);
        bool actual_create = false;
        for (const auto& c : r.created())
            if (c.tcb == task.tcb) {
                assert(c.stack == task.stack && c.size == task.size && c.entry == task.entry);
                actual_create = true;
            }
        assert(actual_create);
        assert(m.peek32(ot::g_curTcb) == task.tcb);
        const uint32_t sp = m.getA7(), top = task.stack + task.size;
        // Stock task entry retains its exit return address above the saves.
        std::fprintf(stderr, "TASK top=0x%08x sp=0x%08x bytes=%u\n", top, sp, top-sp);
        assert(sp == top - 12);
        assert(m.peek32(m.vbr() + 4 * 0x60) == 0x400a1e0c);
        assert((m.read8(ot::g_intc0 + 0x60) & 7) == 3);
        assert(m.read16(0x400a1e66) == 0x2200);
        // Approval boundary: only the disposable TEST machine is changed.
        // The input image and repository runtime are never written.
        if (counterfactual) m.write16(0x400a1e66, 0x2300);
        auto request = [&] { m.write32(ot::g_intc0 + 0x10, m.read32(ot::g_intc0 + 0x10) | 1); };
        for (unsigned depth = 1; depth <= (counterfactual ? 1u : 9u); ++depth) {
            const auto previous = m.getA7();
            request();
            // A changed SP is necessary: the previous invocation is already at
            // this PC, and runUntil tests its predicate before executing code.
            const auto result = r.runUntil(10, [&] { return m.pc() == 0x400a1e68 && m.getA7() < previous; });
            if (result != ot::Rtos::Stop::Gate) std::fprintf(stderr, "STOP pc=%08x sp=%08x sr=%04x force=%08x reason=%s\n",m.pc(),m.getA7(),unsigned(m68k_get_reg(m.getCpuState(),M68K_REG_SR)),m.read32(ot::g_intc0+0x10),r.why().c_str());
            assert(result == ot::Rtos::Stop::Gate);
            // The core executes the task's PEA before acknowledging the first
            // request: 4 extra task bytes, then 8+208 per actual IRQ entry.
            assert(m.getA7() == sp - 4 - 216 * depth);
            assert(m.peek32(ot::g_curTcb) == task.tcb);
            assert(m.getA7() >= task.stack);
            assert(((m68k_get_reg(m.getCpuState(), M68K_REG_SR) >> 8) & 7) == (counterfactual ? 3 : 2));
            // Actual exception record lies above the 208-byte handler frame.
            const uint32_t ex = m.getA7() + 208;
            assert((m.peek32(ex) >> 28) == 4); // aligned ColdFire frame
            assert(((m.read16(ex) >> 2) & 255) == 0x60);
            std::printf("ENTRY variant=%s depth=%u task=0x%08x task_bytes=%u nested_bytes=%u sp=0x%08x free=%u\n",
                counterfactual ? "IPL3_COUNTERFACTUAL" : "UNCHANGED", depth, task.tcb, top-sp+4, sp-m.getA7()-4, m.getA7(), m.getA7()-task.stack);
        }
        if (!counterfactual) {
            // Stop BEFORE a tenth request would write outside the task stack.
            assert(top - (sp - 4 - 216 * 10) == 2176);
            std::puts("PASS_UNCHANGED: nine actual nested entries; tenth prologue would exceed capacity by 128 bytes; tenth NOT issued");
        } else {
            const uint32_t held = m.getA7();
            request();
            // Execute the actual body until its first call. The request must
            // remain pending; no second handler frame may be entered.
            assert(r.runUntil(10, [&] { return m.pc() == 0x400a1608; }) == ot::Rtos::Stop::Gate);
            assert(m.getA7() == held - 8); // one argument + JSR return address
            assert((m.read32(ot::g_intc0 + 0x10) & 1) != 0);
            std::puts("PASS_COUNTERFACTUAL: same-level request stays pending through first sequencer call; audio5/DMA6 remain above IPL3 (not a complete remedy qualification)");
        }
    }
}
