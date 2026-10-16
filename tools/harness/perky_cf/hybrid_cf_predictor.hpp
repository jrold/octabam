#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <stdexcept>

// The retained throughput model stores these outside m68ki_cpu_core. A host
// process comparing two target images must give each its own predictor history.
extern "C" {
extern uint8_t m68k_bht_state[128],m68k_btb_valid[8],m68k_btb_state[8];
extern uint32_t m68k_btb_tag[8];
extern uint64_t m68k_bcc_count,m68k_btb_hits,m68k_bht_hits,m68k_mispredicts;
}
struct HybridPredictor {
    std::array<uint8_t,128> bht{};
    std::array<uint8_t,8> valid{},state{};
    std::array<uint32_t,8> tag{};
    std::array<uint64_t,4> counts{};
    void load()const {
        std::copy(bht.begin(),bht.end(),m68k_bht_state);
        std::copy(valid.begin(),valid.end(),m68k_btb_valid);
        std::copy(state.begin(),state.end(),m68k_btb_state);
        std::copy(tag.begin(),tag.end(),m68k_btb_tag);
        m68k_bcc_count=counts[0];m68k_btb_hits=counts[1];
        m68k_bht_hits=counts[2];m68k_mispredicts=counts[3];
    }
    void save() {
        std::copy_n(m68k_bht_state,bht.size(),bht.begin());
        std::copy_n(m68k_btb_valid,valid.size(),valid.begin());
        std::copy_n(m68k_btb_state,state.size(),state.begin());
        std::copy_n(m68k_btb_tag,tag.size(),tag.begin());
        counts={m68k_bcc_count,m68k_btb_hits,m68k_bht_hits,m68k_mispredicts};
    }
    static void selftest() {
        HybridPredictor a,b;
        a.load();m68k_bht_state[7]=3;m68k_btb_tag[2]=0x40c;
        m68k_btb_valid[2]=1;m68k_btb_state[2]=2;m68k_bcc_count=5;a.save();
        b.load();
        if(m68k_bht_state[7] || m68k_btb_valid[2] || m68k_bcc_count)
            throw std::runtime_error("predictor cold isolation failed");
        m68k_bht_state[7]=1;m68k_bcc_count=9;b.save();a.load();
        if(m68k_bht_state[7]!=3 || m68k_btb_tag[2]!=0x40c ||
           m68k_btb_valid[2]!=1 || m68k_btb_state[2]!=2 || m68k_bcc_count!=5)
            throw std::runtime_error("predictor trained isolation failed");
        b.load();
        if(m68k_bht_state[7]!=1 || m68k_btb_valid[2] || m68k_bcc_count!=9)
            throw std::runtime_error("predictor reverse isolation failed");
    }
};
