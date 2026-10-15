#include "machine.h"
#include "hybrid_cf_shadow.h"
#include "hybrid_cf_alignment.hpp"
#include "mc68k/Musashi/m68k.h"
#include "mc68k/cpuState.h"
#include <array>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

static std::vector<uint8_t> read(const std::string &p) {
    std::ifstream f(p,std::ios::binary);
    if(!f)throw std::runtime_error("read "+p);
    return {std::istreambuf_iterator<char>(f),{}};
}
struct Target {
    ot::Machine machine;
    HybridAlignment alignment;
    std::map<std::string,uint32_t> symbols,assets;
    std::array<uint32_t,HYB_LAYOUT_WORDS> layout{};
    uint64_t last_cycles=0;
    Target(const std::string &directory,const std::string &ad)
        :machine(read(directory+"/target.bin")),alignment(machine) {
        std::ifstream nm(directory+"/target.nm");std::string line;
        while(std::getline(nm,line)) {
            std::istringstream f(line);uint32_t a,z;char type;std::string name;
            if(f>>std::hex>>a>>z>>type>>name)symbols[name]=a;
        }
        uint32_t address=0x44000000;
        for(auto name:{"pitch","chromatic","envelope1","envelope2","w0","w1","w2","w3","m1","interp_a","interp_b","wt_base","wt_bank"}) {
            auto bytes=read(ad+"/"+name+".bin");assets[name]=address;
            for(auto value:bytes)machine.write8(address++,value);
            address=(address+3)&~3u;
        }
        auto put=[&](uint32_t o,const char *name){machine.write32(symbols.at("assets")+o,assets.at(name));};
        put(0,"pitch");put(4,"chromatic");put(8,"envelope1");put(12,"envelope2");
        for(unsigned i=0;i<4;i++) {
            machine.write32(symbols.at("assets")+16+8*i,0x080222a0+512*i);
            machine.write32(symbols.at("assets")+20+8*i,assets.at("w"+std::to_string(i)));
        }
        put(48,"m1");machine.write32(symbols.at("assets")+52,0x080310e0);
        put(56,"interp_a");put(60,"interp_b");put(64,"wt_base");put(68,"wt_bank");
        for(unsigned i=0;i<layout.size();i++)layout[i]=machine.read32(symbols.at("bench_layout")+4*i);
        if(layout[HYB_RNG_HIGH_OFFSET]!=layout[HYB_RNG_LOW_OFFSET]+4)throw std::runtime_error("RNG layout");
        for(auto table: {std::vector<std::string>{"pitch","envelope1","envelope2","wt_base","wt_bank"},
                         std::vector<std::string>{"envelope1","envelope2","interp_a","interp_b"}}) {
            uint32_t base=table.size()==5?0x45010000:0x45010040;
            for(unsigned i=0;i<table.size();i++)machine.write32(base+4*i,assets.at(table[i]));
        }
        machine.write32(0x45010080,assets.at("envelope1"));machine.write32(0x45010084,assets.at("envelope2"));
        for(unsigned i=0;i<4;i++) {
            machine.write32(0x45010088+8*i,0x080222a0+512*i);
            machine.write32(0x4501008c+8*i,assets.at("w"+std::to_string(i)));
        }
    }
    uint32_t call(const std::string &name,std::initializer_list<uint32_t> args={}) {
        constexpr uint32_t sp=0x47100000,end=0x47200000;
        auto *cpu=machine.getCpuState();hybrid_alignment=&alignment;HybridAlignmentScope scope;
        m68k_set_reg(cpu,M68K_REG_SR,0x2700);m68k_set_reg(cpu,M68K_REG_SP,sp);
        m68k_set_reg(cpu,M68K_REG_PC,symbols.at(name));machine.write32(sp,end);
        unsigned offset=4;for(auto a:args){machine.write32(sp+offset,a);offset+=4;}
        uint64_t steps=0,before=machine.getCycles();
        uint64_t limit=name=="bench_control_math_probe"?300000000:name=="bench_math_probe"?100000000:10000000;
        while(machine.pcFast()!=end)if(++steps>limit||!machine.stepFast())throw std::runtime_error("call "+name+" "+machine.why());
        if(m68k_get_reg(cpu,M68K_REG_SP)!=sp+4)throw std::runtime_error("SP mismatch");
        last_cycles=machine.getCycles()-before;
        return m68k_get_reg(cpu,M68K_REG_D0);
    }
    uint32_t voice(unsigned instance)const{return symbols.at("voices")+instance*layout[HYB_VOICE_SIZE];}
    std::vector<uint8_t> state() {
        std::vector<uint8_t> result;
        for(unsigned i=0;i<2*layout[HYB_VOICE_SIZE];i++)result.push_back(machine.read8(symbols.at("voices")+i));
        return result;
    }
    void restore(const std::vector<uint8_t>&state) {
        for(unsigned i=0;i<state.size();i++)machine.write8(symbols.at("voices")+i,state[i]);
    }
    void le32(uint32_t a,uint32_t value){for(unsigned i=0;i<4;i++)machine.write8(a+i,uint8_t(value>>(8*i)));}
    void prepare(unsigned profile,unsigned mode,unsigned frame) {
        for(unsigned i=0;i<2;i++) {
            machine.write32(symbols.at("profile")+4*i,profile);
            machine.write32(symbols.at("modes")+4*i,mode);
            machine.write32(symbols.at("triggers")+4*i,frame%7==0);
            for(unsigned k=0;k<4;k++)machine.write32(symbols.at("knobs")+16*i+4*k,(frame*19+i*23+k*31)&127);
        }
        call("bench_prepare");
    }
    std::pair<uint32_t,std::vector<uint8_t>> render(unsigned instance,unsigned profile,unsigned mode,unsigned count) {
        uint32_t base=voice(instance),output=0x45000000;
        for(unsigned i=0;i<2*count+32;i++)machine.write8(output+i,0xa5);
        uint32_t rc;
        if(profile<2)rc=call("pk_cf_wt_render",{base+layout[HYB_WT_OFFSET]+profile*layout[HYB_WT_BYTES],output,count,0x45010000});
        else if(mode<2)rc=call(mode==0?"pk_cf_res_snare_render":"pk_cf_res_bass_render",
            {base+layout[mode==0?HYB_SNARE_OFFSET:HYB_BASS_OFFSET],output,count,0x45010040,base+layout[HYB_RNG_LOW_OFFSET]});
        else rc=call("pk_cf_nt_shared_render",{base+layout[HYB_NT_OFFSET],output,count,0x45010080,base+layout[HYB_RNG_LOW_OFFSET]});
        std::vector<uint8_t> pcm;
        for(unsigned i=0;i<2*count+32;i++)pcm.push_back(machine.read8(output+i));
        for(unsigned i=2*count;i<pcm.size();i++)if(pcm[i]!=0xa5)throw std::runtime_error("output guard");
        return {rc,pcm};
    }
};
int main(int argc,char **argv) {
    if(argc!=4)return 2;
    Target reference(argv[1],std::string(argv[1])+"/assets"),candidate(argv[2],std::string(argv[1])+"/assets");
    if(reference.layout!=candidate.layout)throw std::runtime_error("layout changed");
    uint64_t calls=0,failed_wave_calls=0;
    bool math_checked=candidate.symbols.count("bench_math_probe");
    if(math_checked) {
        if(candidate.call("bench_math_probe")!=1 ||
           candidate.machine.read32(candidate.symbols.at("render_math_failures"))!=0 ||
           candidate.machine.read32(candidate.symbols.at("render_math_checks"))!=221184)
            throw std::runtime_error("exact high-product or raw EMAC preservation failed");
    }
    bool control_checked=candidate.symbols.count("bench_control_math_probe");
    if(control_checked) {
        if(candidate.call("bench_control_math_probe")!=1 ||
           candidate.machine.read32(candidate.symbols.at("control_math_failures"))!=0 ||
           candidate.machine.read32(candidate.symbols.at("control_math_checks"))!=438516)
            throw std::runtime_error("exact envelope-rate or note conversion failed");
    }
    std::ofstream costs(std::string(argv[3])+"/render-edge-costs.csv");
    costs<<"profile,mode,instance,count,case,reference_cycles,candidate_cycles,status\n";
    auto compare=[&](unsigned instance,unsigned profile,unsigned mode,unsigned count) {
        auto a=reference.render(instance,profile,mode,count),b=candidate.render(instance,profile,mode,count);
        if(a!=b||reference.state()!=candidate.state())throw std::runtime_error("renderer differential profile="+std::to_string(profile)+" mode="+std::to_string(mode)+" n="+std::to_string(count)+" case="+std::to_string(calls));
        costs<<profile<<','<<mode<<','<<instance<<','<<count<<','<<calls<<','<<reference.last_cycles<<','<<candidate.last_cycles<<','<<a.first<<'\n';
        ++calls;if(!a.first)++failed_wave_calls;
    };
    for(unsigned profile=0;profile<3;profile++)for(unsigned mode=0;mode<3;mode++) {
        reference.call("bench_init");candidate.call("bench_init");
        std::vector<unsigned> counts;for(unsigned n=0;n<=33;n++)counts.push_back(n);
        for(unsigned n:{47u,64u,127u,128u,255u,256u,257u})counts.push_back(n);
        for(unsigned frame=0;frame<counts.size();frame++) {
            reference.prepare(profile,mode,frame);candidate.prepare(profile,mode,frame);
            if(reference.state()!=candidate.state())throw std::runtime_error("control differential");
            for(unsigned instance=0;instance<2;instance++)compare(instance,profile,mode,counts[frame]);
        }
        if(profile==2&&mode<2) {
            auto state=reference.state();
            std::vector<unsigned> fields=mode==0?
                std::vector<unsigned>{0x104,0x108,0x110,0x114,0x128,0x12c,0x134,0x138,0x14c,0x150,0x158,0x15c}:
                std::vector<unsigned>{0x164,0x168,0x170,0x174};
            for(auto field:fields)for(unsigned value:{0x80000000u,0x7fffffffu,0xffff8000u,0x8000u,0xdeadbeefu})for(unsigned count:{0u,1u,8u,16u,17u}) {
                reference.restore(state);candidate.restore(state);
                for(auto target:{&reference,&candidate})target->le32(target->voice(0)+target->layout[mode==0?HYB_SNARE_OFFSET:HYB_BASS_OFFSET]+field,value);
                compare(0,profile,mode,count);
            }
        }
        if(profile==2) {
            auto state=reference.state();
            for(unsigned stage:{0u,1u,3u,4u,255u})for(unsigned curve:{0u,1u,2u,3u})for(unsigned value:{0u,0xffffeu,0x100000u,0x80000000u,0xffffffffu})for(unsigned count:{0u,1u,8u,16u,17u}) {
                reference.restore(state);candidate.restore(state);
                for(auto target:{&reference,&candidate}) {
                    auto base=target->voice(0)+target->layout[mode==0?HYB_SNARE_OFFSET:mode==1?HYB_BASS_OFFSET:HYB_NT_OFFSET];
                    target->machine.write8(base+0x74,stage);target->machine.write8(base+0x75,curve);target->le32(base+0x80,value);
                }
                compare(0,profile,mode,count);
            }
        }
        if(profile==2&&mode<2) {
            auto state=reference.state();
            for(auto rates:std::vector<std::pair<unsigned,unsigned>>{{0,0},{1,1},{65535,65535},{0,65535},{65535,0}})
            for(unsigned flags=0;flags<16;flags++)for(unsigned value:{0u,1u,0xffffeu,0xfffffu,0x80000000u,0xffffffffu})
            for(unsigned stage:{0u,1u,3u,4u,255u})for(unsigned count:{1u,8u,16u,17u}) {
                reference.restore(state);candidate.restore(state);
                for(auto target:{&reference,&candidate}) {
                    auto base=target->voice(0)+target->layout[mode==0?HYB_SNARE_OFFSET:HYB_BASS_OFFSET];
                    target->machine.write8(base+0x74,stage);target->le32(base+0x80,value);
                    unsigned offsets[4]={0x78,0x7a,0x7b,0x84};
                    for(unsigned k=0;k<4;k++)target->machine.write8(base+offsets[k],flags&(1u<<k)?255:0);
                    for(auto entry:std::vector<std::pair<unsigned,unsigned>>{{0x94,rates.first},{0x96,rates.second}}) {
                        target->machine.write8(base+entry.first,uint8_t(entry.second));
                        target->machine.write8(base+entry.first+1,uint8_t(entry.second>>8));
                    }
                }
                compare(0,profile,mode,count);
            }
        }
        if(profile<2) {
            auto state=reference.state();
            for(unsigned field:{0x100u,0x104u,0x108u,0x10cu})for(unsigned count:{0u,1u,15u,16u,17u,65u})for(unsigned phase:{0u,0xfffffu,0xffffffffu}) {
                reference.restore(state);candidate.restore(state);
                for(auto target:{&reference,&candidate}) {
                    auto base=target->voice(0)+target->layout[HYB_WT_OFFSET]+profile*target->layout[HYB_WT_BYTES];
                    target->le32(base+field,0xdeadc0de);target->le32(base+0xf4,phase);
                }
                compare(0,profile,mode,count);
            }
        }
    }
    uint64_t control_transition_cases=0;
    for(unsigned mode:{0u,1u}) {
        reference.call("bench_init");candidate.call("bench_init");
        reference.prepare(2,mode,0);candidate.prepare(2,mode,0);
        auto pristine=reference.state();
        for(unsigned threshold:{0u,1u,64u,2048u,4032u,4080u,4094u,4095u,65535u})
        for(unsigned initial:{0u,1u,std::min(threshold,4095u),std::min(threshold+1u,4095u),4094u,4095u})
        for(unsigned raw_decay:{0u,1u,63u,126u,127u})for(unsigned trigger:{0u,1u}) {
            reference.restore(pristine);candidate.restore(pristine);
            for(auto target:{&reference,&candidate})for(unsigned instance=0;instance<2;instance++) {
                uint32_t base=target->voice(instance)+target->layout[mode==0?HYB_SNARE_OFFSET:HYB_BASS_OFFSET];
                target->machine.write8(base+8,uint8_t(threshold));target->machine.write8(base+9,uint8_t(threshold>>8));
                for(unsigned k=0;k<4;k++)target->le32(base+0x1c+4*k,initial);
                unsigned raw[4]={64,raw_decay,127,0};
                for(unsigned k=0;k<4;k++)target->machine.write32(target->symbols.at("knobs")+16*instance+4*k,raw[k]);
                target->machine.write32(target->symbols.at("triggers")+4*instance,trigger);
            }
            reference.call("bench_prepare");candidate.call("bench_prepare");
            if(reference.state()!=candidate.state())throw std::runtime_error("sustain crossing control differential "+std::to_string(control_transition_cases));
            for(unsigned instance=0;instance<2;instance++) {
                auto a=reference.render(instance,2,mode,16),b=candidate.render(instance,2,mode,16);
                if(a!=b||reference.state()!=candidate.state())throw std::runtime_error("sustain crossing PCM/state/RNG differential");
            }
            ++control_transition_cases;
        }
    }
    reference.alignment.finish(std::string(argv[3])+"/reference-edge-alignment.json");
    candidate.alignment.finish(std::string(argv[3])+"/candidate-edge-alignment.json");
    std::ofstream report(std::string(argv[3])+"/RENDER_EDGES.json");
    report<<"{\"status\":\"PASS_EXACT_TARGET_REFERENCE\",\"render_calls\":"<<calls<<",\"matched_failure_calls\":"<<failed_wave_calls<<",\"block_lengths\":41,\"max_block_samples\":257,\"all_state_PCM_RNG_and_guards_equal\":true,\"EMAC_product_checks\":"<<(math_checked?221184:0)<<",\"EMAC_raw_register_mode_cases\":"<<(math_checked?6:0)<<",\"control_transition_cases\":"<<control_transition_cases<<",\"control_math_checks\":"<<(control_checked?438516:0)<<"}\n";
    std::cout<<"PASS exact renderer edges: "<<calls<<" calls, "<<failed_wave_calls<<" matching refusal paths\n";
}
