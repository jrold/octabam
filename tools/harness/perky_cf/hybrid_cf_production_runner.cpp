#include "machine.h"
#include "hybrid_cf_alignment.hpp"
#include "hybrid_cf_predictor.hpp"
#include "mc68k/Musashi/m68k.h"
#include "mc68k/cpuState.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

static std::vector<uint8_t> read(const std::string &p){
    std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("read "+p);
    return {std::istreambuf_iterator<char>(f),{}};
}
struct Symbol{uint32_t address,size;char type;std::string name;};
struct Cost{uint64_t cycles,instructions;uint32_t stack;std::map<std::string,uint64_t> symbols;
    std::array<uint64_t,7> reads{},writes{},cross_reads{},cross_writes{};
    std::array<uint64_t,4> branches{};};
struct Target{
    ot::Machine m;
    HybridAlignment alignment;
    HybridPredictor predictor;
    std::map<std::string,Symbol> symbols;
    std::vector<Symbol> text;
    bool observing=false;
    std::array<uint64_t,7> reads{},writes{},cross_reads{},cross_writes{};
    uint32_t state_base=0,state_end=0,pcm_base=0,pcm_bank=0,code_base=0,code_end=0,module_end=0;
    std::vector<std::pair<uint32_t,uint32_t>> asset_ranges;
    unsigned category(uint32_t a)const{
        // Most watched requests fetch instruction words. The immutable
        // incbin tables also live in ELF .text, so exclude those ranges first.
        if(a>=code_base&&a<code_end){
            for(const auto&r:asset_ranges)if(a>=r.first&&a<r.second)return 5;
            return 4;
        }
        if(a>=0x47000000&&a<=0x47100003)return 0;
        if(a>=state_base&&a<state_end)return 1;
        if((a>=pcm_base&&a<pcm_base+4096)||(a>=pcm_bank&&a<pcm_bank+196608))return 2;
        if(a>=0x80001c40&&a<0x80003540)return 3;
        if(a>=0x40c005e0&&a<module_end)return 5;
        return 6;
    }
    explicit Target(const std::string &dir,const std::string &nm):m(read(dir+"/mainos_PKHYB2P.bin")),alignment(m){
        std::ifstream f(nm);std::string line;
        while(std::getline(f,line)){
            std::istringstream stream(line);std::vector<std::string> fields;std::string field;
            while(stream>>field)fields.push_back(field);
            if(fields.size()!=3&&fields.size()!=4)continue;
            if(fields[0]=="U")continue;
            Symbol v{};v.address=uint32_t(std::stoul(fields[0],nullptr,16));
            v.size=fields.size()==4?uint32_t(std::stoul(fields[1],nullptr,16)):0;
            v.type=fields[fields.size()-2].at(0);v.name=fields.back();symbols[v.name]=v;
            if(v.size&&(v.type=='t'||v.type=='T'))text.push_back(v);
        }
        std::sort(text.begin(),text.end(),[](const auto&a,const auto&b){return a.address<b.address;});
        auto state=symbols.at("pk_hybrid_voices");state_base=state.address;state_end=state.address+state.size;
        pcm_base=symbols.at("pk_pcm_wt_base").address;pcm_bank=symbols.at("pk_pcm_wt_bank").address;
        code_base=text.front().address;code_end=text.back().address+text.back().size;
        module_end=symbols.at("_end").address;
        for(const auto&item:symbols){
            const auto&n=item.first;
            if(n.rfind("pk_asset_",0)==0&&symbols.count(n+"_end"))
                asset_ranges.push_back({item.second.address,symbols.at(n+"_end").address});
        }
        // The driver verifies the ELF .text VMA before permitting this load.
        auto raw=read(dir+"/platform/runtime.raw");
        for(unsigned i=0;i<raw.size();++i)m.write8(0x40c005e0+i,raw[i]);
        m.addReadWatch(0,0xffffffffu,[&](uint32_t a,uint8_t n,uint32_t,uint32_t){if(observing){auto c=category(a);reads[c]+=n;if((a>>4)!=((a+n-1)>>4))++cross_reads[c];}});
        m.addWriteWatch(0,0xffffffffu,[&](uint32_t a,uint8_t n,uint32_t,uint32_t){if(observing){auto c=category(a);writes[c]+=n;if((a>>4)!=((a+n-1)>>4))++cross_writes[c];}});
        observing=true;
        m.write8(0x47300000,0);m.write16(0x47300002,0);m.write32(0x4730000e,0);
        (void)m.read8(0x47300000);(void)m.read16(0x47300002);(void)m.read32(0x4730000e);
        observing=false;
        if(reads[6]!=7||writes[6]!=7||cross_reads[6]!=1||cross_writes[6]!=1)
            throw std::runtime_error("production traffic calibration failed");
        m.setOverrideFn(0xfc07c00c,[&](){return uint32_t(m.getCycles()/2);});
        auto c=call("pk_hybrid_boot_init",{});(void)c;
        if(m68k_get_reg(m.getCpuState(),M68K_REG_D0)!=1)throw std::runtime_error("production boot init failed");
        m.write32(0x46c82456,0x46000000);m.write8(0x100b14cf,0);
        for(unsigned t:{1u,5u}){uint32_t p=0x46000000+0x8ed80;
            m.write8(p+0x22+t,1);m.write8(p+60+30*t,'P');m.write8(p+61+30*t,'K');m.write8(p+62+30*t,1);}
        m.write32(0x800062a8,0x80008000);
    }
    Cost call(const std::string &name,const std::vector<uint32_t>&args){
        predictor.load();const auto branch_before=predictor.counts;
        const uint32_t sp=0x47100000,end=0x47200000;
        m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);
        m68k_set_reg(m.getCpuState(),M68K_REG_SP,sp);
        m68k_set_reg(m.getCpuState(),M68K_REG_PC,symbols.at(name).address);
        m.write32(sp,end);for(unsigned i=0;i<args.size();++i)m.write32(sp+4+4*i,args[i]);
        uint64_t start=m.getCycles(),instructions=0;uint32_t low=sp;Cost cost{};
        reads.fill(0);writes.fill(0);cross_reads.fill(0);cross_writes.fill(0);observing=true;alignment.enabled=true;
        while(m.pcFast()!=end){
            auto pc=m.pcFast();auto before=m.getCycles();
            auto it=std::upper_bound(text.begin(),text.end(),pc,[](uint32_t a,const Symbol&b){return a<b.address;});
            std::string symbol="unmapped";if(it!=text.begin()){--it;if(pc<it->address+it->size)symbol=it->name;}
            if(++instructions>10000000||!m.stepFast())throw std::runtime_error("production target stopped: "+m.why());
            cost.symbols[symbol]+=m.getCycles()-before;
            low=std::min(low,m68k_get_reg(m.getCpuState(),M68K_REG_SP));
        }
        observing=false;alignment.enabled=false;
        if(m68k_get_reg(m.getCpuState(),M68K_REG_SP)!=sp+4)throw std::runtime_error("production stack ABI");
        cost.cycles=m.getCycles()-start;cost.instructions=instructions;cost.stack=sp-low;
        predictor.save();for(unsigned i=0;i<4;++i)cost.branches[i]=predictor.counts[i]-branch_before[i];
        cost.reads=reads;cost.writes=writes;cost.cross_reads=cross_reads;cost.cross_writes=cross_writes;return cost;
    }
    std::vector<uint8_t> bytes(uint32_t a,uint32_t n){std::vector<uint8_t> v;for(unsigned i=0;i<n;++i)v.push_back(m.read8(a+i));return v;}
};

int main(int argc,char **argv){
    HybridPredictor::selftest();
    if(argc!=4&&argc!=5)return 2;
    const bool control4=argc==5&&std::string(argv[4])=="control4";
    const bool rng4=argc==5&&std::string(argv[4])=="rng4";
    const bool aligned=argc==5&&(std::string(argv[4])=="align16"||rng4||control4);
    if(argc==5&&!aligned)throw std::runtime_error("unknown layout experiment");
    const std::string left=argv[1],right=argv[2],work=argv[3];
    Target a(left,work+"/reference.nm"),b(right,work+"/candidate.nm");
    uint32_t reference_stride=0,candidate_stride=0,logical_end=0;
    if(aligned){
        auto layout=[&](const std::string &label){std::ifstream f(work+"/"+label+"-layout.txt");
            std::vector<uint32_t> words;uint32_t n;while(f>>n)words.push_back(n);
            if(words.size()!=(control4?29u:25u))throw std::runtime_error("incomplete compiler layout witness");return words;};
        auto x=layout("reference"),y=layout("candidate");
        auto expected=x;
        if(control4){expected[1]=1980;expected[12]=72;for(unsigned i=13;i<25;i+=2)expected[i]+=4;
            expected[25]=24;expected[26]=22;expected[27]=0;expected[28]=4;}
        else if(rng4){expected[1]=1976;for(unsigned i=13;i<25;i+=2)expected[i]+=2;}
        const bool fields_ok=control4 ? (x[0]==1984&&x[1]==1976&&x[2]==16&&x[25]==22&&x[26]==22&&x[27]==0&&x[28]==2&&y==expected) : rng4 ? (x[0]==1984&&x[1]==1974&&x[2]==16&&y==expected) :
            (x[0]==1974&&y[0]==1984&&x[1]==1974&&y[1]==1974&&x[2]==2&&y[2]==16&&std::equal(x.begin()+3,x.end(),y.begin()+3));
        if(!fields_ok||
           a.symbols.at("pk_hybrid_voices").size!=2*x[0]||b.symbols.at("pk_hybrid_voices").size!=2*y[0]||
           (b.symbols.at("pk_hybrid_voices").address&15))
            throw std::runtime_error("alignment changed logical state layout");
        reference_stride=x[0];candidate_stride=y[0];logical_end=x[1];
    }
    std::ofstream costs(work+"/callback-costs.csv"),exclusive(work+"/callback-symbols.csv");
    costs<<"profiler,left,right,frame,instance,phase,baseline_cycles,candidate_cycles,baseline_instructions,candidate_instructions,baseline_stack,candidate_stack";
    for(auto image:{"baseline","candidate"})for(auto group:{"stack","state","PCM","source_RAM","instruction_stream","module_other","external_control_and_reservation"})
        costs<<','<<image<<'_'<<group<<"_read_bytes,"<<image<<'_'<<group<<"_write_bytes,"
             <<image<<'_'<<group<<"_cross16_reads,"<<image<<'_'<<group<<"_cross16_writes";
    for(auto image:{"baseline","candidate"})for(auto kind:{"bcc_branches","btb_hits","bht_hits","bcc_mispredicts"})costs<<','<<image<<'_'<<kind;
    costs<<'\n';
    exclusive<<"profiler,left,right,phase,image,symbol,cycles\n";
    const std::string names[]={"V1","V2","snare","bass","third"};
    std::map<std::string,uint64_t> totals;
    uint64_t callbacks=0,compared=0;
    auto compare=[&](uint32_t aa,uint32_t bb,uint32_t n){if(a.bytes(aa,n)!=b.bytes(bb,n))throw std::runtime_error("production callback byte mismatch");compared+=n;};
    for(unsigned prof:{0u,1u})for(unsigned l=0;l<5;++l)for(unsigned r=0;r<5;++r){
        for(auto *t:{&a,&b}){t->call("pk_hybrid_boot_init",{});t->m.write32(t->symbols.at("pk_hybrid_profiler_enable").address,prof);}
        for(unsigned f=0;f<128;++f){
            for(auto*t:{&a,&b})t->call("pk_hybrid_frame_begin",{});
            for(unsigned inst=0;inst<2;++inst){
                unsigned p=inst?r:l,track=inst?5:1,split=f%17;
                // Deterministic dense locks, periodic triggers, all split
                // offsets, and a return through every family/mode at f=64.
                if(f>=64)p=(p+(f/16))%5;
                unsigned algo=p<2?p:2,mode=p<2?((f/32)%3):p-2;
                for(auto*t:{&a,&b}){
                    uint8_t values[]={uint8_t((31+f*7)&127),uint8_t(96+f%32),uint8_t(algo),uint8_t((f*13)&127),uint8_t((f*19)&127),uint8_t(mode)};
                    for(unsigned k=0;k<6;++k)t->m.write16(0x80008000+2*k,uint16_t(values[k])<<8);
                    t->m.write8(0x46104d0c+track,f%3==0?16:0);
                }
                for(unsigned half=0;half<2;++half){
                    const std::vector<uint32_t> args={track,half,half?split:0,half?16:split};
                    for(auto*t:{&a,&b})t->m.write32(0x80001c80,0x80010000);
                    auto ac=a.call("pk_render",args),bc=b.call("pk_render",args);
                    if(m68k_get_reg(a.m.getCpuState(),M68K_REG_D0)!=m68k_get_reg(b.m.getCpuState(),M68K_REG_D0))throw std::runtime_error("callback return changed");
                    compare(0x80001c40,0x80001c40,0x1900);compare(0x80001c80,0x80001c80,4);
                    for(auto name:{"pk_hybrid_voices","pk_hybrid_frame_pcm","pk_hybrid_trigger_latch","pk_hybrid_frame_started"}){
                        auto x=a.symbols.at(name),y=b.symbols.at(name);
                        if(aligned&&std::string(name)=="pk_hybrid_voices"){
                            for(unsigned voice=0;voice<2;++voice){
                                auto aa=x.address+voice*reference_stride,bb=y.address+voice*candidate_stride;
                                std::vector<uint8_t> padding;
                                if(control4){
                                    compare(aa,bb,1896);
                                    for(unsigned j=0;j<3;++j)compare(aa+1896+22*j,bb+1896+24*j,22);
                                    compare(aa+1964,bb+1968,12);
                                    padding=a.bytes(aa+1962,2);
                                    auto add=[&](Target&t,uint32_t at,uint32_t n){
                                        auto part=t.bytes(at,n);padding.insert(padding.end(),part.begin(),part.end());};
                                    add(a,aa+1976,8);
                                    for(unsigned j=0;j<3;++j)add(b,bb+1896+24*j+22,2);
                                    add(b,bb+1980,4);
                                }else if(rng4){
                                    compare(aa,bb,1962);compare(aa+1962,bb+1964,12);
                                    padding=a.bytes(aa+1974,10);
                                    auto gap=b.bytes(bb+1962,2),tail=b.bytes(bb+1976,8);
                                    padding.insert(padding.end(),gap.begin(),gap.end());padding.insert(padding.end(),tail.begin(),tail.end());
                                }else{
                                    compare(aa,bb,logical_end);padding=b.bytes(bb+logical_end,candidate_stride-logical_end);
                                }
                                if(std::any_of(padding.begin(),padding.end(),[](uint8_t n){return n!=0;}))
                                    throw std::runtime_error("new voice padding changed");
                            }
                        }else{if(x.size!=y.size)throw std::runtime_error("synthesis state layout changed");compare(x.address,y.address,x.size);}
                    }
                    const std::string phase=half?"final":"prefix";
                    costs<<prof<<','<<names[l]<<','<<names[r]<<','<<f<<','<<inst<<','<<phase<<','<<ac.cycles<<','<<bc.cycles<<','<<ac.instructions<<','<<bc.instructions<<','<<ac.stack<<','<<bc.stack;
                    for(auto c:{&ac,&bc})for(unsigned i=0;i<7;++i)
                        costs<<','<<c->reads[i]<<','<<c->writes[i]<<','<<c->cross_reads[i]<<','<<c->cross_writes[i];
                    for(auto c:{&ac,&bc})for(auto n:c->branches)costs<<','<<n;
                    costs<<'\n';
                    for(auto item:{std::make_pair("baseline",&ac),std::make_pair("candidate",&bc)})
                        for(const auto&v:item.second->symbols){std::string key=std::to_string(prof)+","+names[l]+","+names[r]+","+phase+","+item.first+","+v.first;totals[key]+=v.second;}
                    ++callbacks;
                    for(auto*t:{&a,&b})t->m.write8(0x46104d0c+track,0);
                }
            }
            for(auto*t:{&a,&b})t->call("pk_hybrid_frame_end",{});
        }
    }
    for(const auto&v:totals)exclusive<<v.first<<','<<v.second<<'\n';
    a.alignment.finish(work+"/reference-alignment.json");b.alignment.finish(work+"/candidate-alignment.json");
    std::ofstream report(work+"/CALLBACK_EXACT.json");
    report<<"{\"status\":\"PASS_EXACT_PRODUCTION_CALLBACKS\",\"callbacks\":"<<callbacks<<",\"compared_bytes\":"<<compared<<",\"pairs\":25,\"profiler_modes\":2,\"split_offsets\":17}\n";
    std::cout<<"exact production callbacks="<<callbacks<<" compared bytes="<<compared<<'\n';
    return 0;
}
