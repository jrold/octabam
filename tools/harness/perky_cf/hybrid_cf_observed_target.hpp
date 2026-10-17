#pragma once
// Reuse the production executor. Machine's host PC profile records executed
// addresses without adding target instructions or reading target peripherals.
#define main perky_production_callback_main
#include "hybrid_cf_production_runner.cpp"
#undef main
#include <set>

struct ObservedCost : Cost {
    std::set<uint32_t> code_bytes;
    std::array<std::set<uint32_t>,7> data_lines;
};
struct ObservedTarget : Target {
    std::map<uint32_t,uint32_t> instruction_sizes;
    std::array<std::set<uint32_t>,7> data_lines;
    ObservedTarget(const std::string& dir,const std::string& nm):Target(dir,nm) {
        std::ifstream f(nm.substr(0,nm.size()-3)+".sizes");uint32_t address,size;
        while(f>>std::hex>>address>>size)instruction_sizes[address]=size;
        if(instruction_sizes.empty())throw std::runtime_error("missing instruction-size witness");
        m.setProfile(1);
        auto request=[this](uint32_t a,uint8_t n,uint32_t,uint32_t) {
            if(!observing)return;
            auto& lines=data_lines[category(a)];
            for(unsigned i=0;i<n;++i)lines.insert((a+i)>>4);
        };
        m.addReadWatch(0,0xffffffffu,request);m.addWriteWatch(0,0xffffffffu,request);
    }
    ObservedCost call(const std::string& name,const std::vector<uint32_t>& args) {
        m.clearProfile();for(auto& lines:data_lines)lines.clear();
        ObservedCost result;static_cast<Cost&>(result)=Target::call(name,args);
        for(const auto& item:m.profile()) {
            auto decoded=instruction_sizes.find(item.first);
            if(decoded==instruction_sizes.end())throw std::runtime_error("executed PC missing from disassembly");
            for(unsigned i=0;i<decoded->second;++i)result.code_bytes.insert(item.first+i);
        }
        result.data_lines=data_lines;return result;
    }
};
