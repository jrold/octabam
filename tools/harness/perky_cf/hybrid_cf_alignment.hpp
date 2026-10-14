#pragma once
#include "machine.h"
#include <fstream>
#include <stdexcept>

// Watch actual effective addresses. An odd displacement can be legal when
// GCC has hoisted an odd base (for example voices+679 plus 935 is even).
// This observes data accesses only and adds no emulated instructions/cycles.
struct HybridAlignment {
    bool enabled = false;
    uint64_t reads = 0, writes = 0, odd_reads = 0, odd_writes = 0;
    uint32_t first_address = 0, first_pc = 0;
    explicit HybridAlignment(ot::Machine &machine) {
        machine.addReadWatch(0, 0xffffffffu,
            [&](uint32_t a, uint8_t n, uint32_t, uint32_t pc) {
                if (enabled && n > 1) {
                    ++reads;
                    if (a & 1) { ++odd_reads; if (!first_address) { first_address=a; first_pc=pc; } }
                }
            });
        machine.addWriteWatch(0, 0xffffffffu,
            [&](uint32_t a, uint8_t n, uint32_t, uint32_t pc) {
                if (enabled && n > 1) {
                    ++writes;
                    if (a & 1) { ++odd_writes; if (!first_address) { first_address=a; first_pc=pc; } }
                }
            });
        enabled = true;
        // Deliberate positive and negative controls in unused SDRAM, before
        // execution. Both word and long paths must expose odd accesses.
        for (uint32_t a : {0x47300000u, 0x47300001u}) {
            machine.write16(a, 0x1234);
            machine.write32(a, 0x56789abc);
            (void)machine.read16(a);
            (void)machine.read32(a);
        }
        if (reads != 4 || writes != 4 || odd_reads != 2 || odd_writes != 2)
            throw std::runtime_error("effective-address watch calibration failed");
        reads = writes = odd_reads = odd_writes = 0;
        first_address = first_pc = 0;
        enabled = false;
    }
    void finish(const std::string &path) {
        std::ofstream report(path);
        report << "{\"calibrated_even_and_odd_word_and_long\":true,\"wide_reads\":" << reads
               << ",\"wide_writes\":" << writes << ",\"odd_reads\":" << odd_reads
               << ",\"odd_writes\":" << odd_writes << ",\"first_address\":" << first_address
               << ",\"first_pc\":" << first_pc << "}\n";
        report.close();
        if (!reads || !writes || odd_reads || odd_writes)
            throw std::runtime_error("target effective-address alignment failed; see " + path);
    }
};
inline HybridAlignment *hybrid_alignment = nullptr;
struct HybridAlignmentScope {
    HybridAlignmentScope() { if (hybrid_alignment) hybrid_alignment->enabled = true; }
    ~HybridAlignmentScope() { if (hybrid_alignment) hybrid_alignment->enabled = false; }
};
