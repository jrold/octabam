#pragma once
#include "machine.h"
#include <array>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <string>

// Host-only observation of architectural data accesses and executed instruction
// bytes. These are working sets and requested bytes, never silicon cache misses
// or SDRAM transactions. Enable only while target instructions execute, so the
// native oracle's reads and fixture writes cannot contaminate the measurement.
struct HybridResources {
    struct Traffic {
        uint64_t reads=0,writes=0,read_bytes=0,write_bytes=0;
        std::set<uint32_t> lines;
    };
    bool enabled=false;
    std::ofstream csv;
    std::array<Traffic,6> traffic;
    std::set<uint32_t> instruction_bytes,instruction_lines;
    std::map<uint32_t,uint32_t> instruction_sizes;
    uint32_t voice_begin,voice_end,asset_begin,asset_end,output_begin,output_end;
    uint64_t ordinal=0;
    HybridResources(ot::Machine &m,const std::string &path,const std::string &sizes,
                    uint32_t vb,uint32_t ve,uint32_t ab,uint32_t ae,uint32_t ob,uint32_t oe)
        :csv(path),voice_begin(vb),voice_end(ve),asset_begin(ab),asset_end(ae),output_begin(ob),output_end(oe) {
        if(!csv)throw std::runtime_error("resource CSV open failed");
        std::ifstream input(sizes);uint32_t address,size;
        while(input>>std::hex>>address>>size)instruction_sizes[address]=size;
        if(instruction_sizes.empty())throw std::runtime_error("instruction sizes absent");
        csv<<"call,pair,entry,cycles,instructions,instruction_bytes,instruction_lines_16";
        for(auto name:{"stack","state","assets","output","other","instruction_stream"})
            csv<<','<<name<<"_reads,"<<name<<"_writes,"<<name<<"_read_bytes,"<<name<<"_write_bytes,"<<name<<"_lines_16";
        csv<<'\n';
        m.addReadWatch(0,0xffffffffu,[&](uint32_t a,uint8_t n,uint32_t,uint32_t){if(enabled)access(a,n,false);});
        m.addWriteWatch(0,0xffffffffu,[&](uint32_t a,uint8_t n,uint32_t,uint32_t){if(enabled)access(a,n,true);});
        // Calibrate all widths, including a line-crossing access, then reset.
        enabled=true;
        m.write8(0x47300000,0);m.write16(0x47300002,0);m.write32(0x4730000e,0);
        (void)m.read8(0x47300000);(void)m.read16(0x47300002);(void)m.read32(0x4730000e);
        enabled=false;
        const auto &c=traffic[4];
        if(c.reads!=3||c.writes!=3||c.read_bytes!=7||c.write_bytes!=7||c.lines.size()!=2)
            throw std::runtime_error("resource watch calibration failed");
        reset();
    }
    void access(uint32_t a,uint8_t n,bool write) {
        unsigned group=a>=0x47000000&&a<=0x47100003?0:
            a>=voice_begin&&a<voice_end?1:a>=asset_begin&&a<asset_end?2:
            a>=output_begin&&a<output_end?3:
            a>=instruction_sizes.begin()->first&&a<instruction_sizes.rbegin()->first+instruction_sizes.rbegin()->second?5:4;
        auto &v=traffic[group];
        if(write){++v.writes;v.write_bytes+=n;}else{++v.reads;v.read_bytes+=n;}
        for(uint32_t i=0;i<n;++i)v.lines.insert((a+i)>>4);
    }
    void reset(){for(auto &t:traffic)t=Traffic{};instruction_bytes.clear();instruction_lines.clear();}
    void begin(){reset();enabled=true;}
    void instruction(uint32_t pc){
        auto it=instruction_sizes.find(pc);
        if(it==instruction_sizes.end())throw std::runtime_error("executed instruction absent from disassembly");
        for(uint32_t i=0;i<it->second;++i){instruction_bytes.insert(pc+i);instruction_lines.insert((pc+i)>>4);}
    }
    void end(const std::string &pair,const std::string &entry,uint64_t cycles,uint64_t instructions){
        enabled=false;
        csv<<ordinal++<<','<<pair<<','<<entry<<','<<cycles<<','<<instructions<<','<<instruction_bytes.size()<<','<<instruction_lines.size();
        for(const auto &t:traffic)csv<<','<<t.reads<<','<<t.writes<<','<<t.read_bytes<<','<<t.write_bytes<<','<<t.lines.size();
        csv<<'\n';
    }
};
inline HybridResources *hybrid_resources=nullptr;
