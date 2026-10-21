#include "machine.h"
#include "hybrid_cf_alignment.hpp"
#include "hybrid_cf_predictor.hpp"
#include "mc68k/Musashi/m68k.h"
#include "mc68k/cpuState.h"
#include <algorithm>
#include <array>
#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>
using Bytes=std::vector<uint8_t>;
static Bytes read(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("read "+p);return {std::istreambuf_iterator<char>(f),{}};}
static void require(bool b,const std::string&s){if(!b)throw std::runtime_error(s);}
struct Symbol{uint32_t address,size;};
struct Cost{uint64_t cycles,instructions;uint32_t stack;};
struct Target{
    ot::Machine m;HybridAlignment alignment;HybridPredictor predictor;
    std::map<std::string,Symbol> symbols;
    Target(const std::string&w):m(read(w+"/target.bin")),alignment(m){
        std::ifstream nm(w+"/target.nm");std::string line;
        while(getline(nm,line)){std::istringstream f(line);uint32_t a,n;char t;std::string s;if(f>>std::hex>>a>>n>>t>>s)symbols[s]={a,n};}
        m.mapRegion(0x44000000,0x400000);m.mapRegion(0x47000000,0x400000);
    }
    uint32_t at(const std::string&s){return symbols.at(s).address;}
    Cost call(const std::string&s){
        predictor.load();HybridAlignmentScope scope;
        constexpr uint32_t sp=0x47100000,end=0x47200000;
        m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);m68k_set_reg(m.getCpuState(),M68K_REG_SP,sp);
        m68k_set_reg(m.getCpuState(),M68K_REG_PC,at(s));m.write32(sp,end);
        uint64_t begin=m.getCycles(),n=0;uint32_t low=sp;
        while(m.pcFast()!=end){require(++n<10000000&&m.stepFast(),"target stopped: "+m.why());low=std::min(low,m68k_get_reg(m.getCpuState(),M68K_REG_SP));}
        require(m68k_get_reg(m.getCpuState(),M68K_REG_SP)==sp+4,"stack ABI");predictor.save();
        return {m.getCycles()-begin,n,sp-low};
    }
    Bytes bytes(uint32_t a,uint32_t n){Bytes v;for(uint32_t i=0;i<n;i++)v.push_back(m.read8(a+i));return v;}
    void scalar(Bytes&v,uint32_t x){for(unsigned i=0;i<4;i++)v.push_back(uint8_t(x>>(8*i)));}
    void raw(Bytes&v,uint32_t a,uint32_t n){auto p=bytes(a,n);v.insert(v.end(),p.begin(),p.end());}
    void control(Bytes&v,uint32_t a,const std::vector<uint32_t>&l){for(unsigned i=0;i<4;i++)scalar(v,m.read32(a+4*i));raw(v,a+l[4],4);v.push_back(m.read8(a+l[5]));v.push_back(m.read8(a+l[6]));}
    Bytes snapshot(){
        std::vector<uint32_t> l;for(unsigned i=0;i<14;i++)l.push_back(m.read32(at("placement_layout")+4*i));
        Bytes out;
        for(unsigned tr=0;tr<4;tr++){
            uint32_t t=at("placement_engine")+tr*l[0];raw(out,t,l[1]);
            for(unsigned i=0;i<13;i++)control(out,t+l[2]+i*l[3],l);
            scalar(out,m.read32(t+l[7]));scalar(out,m.read32(t+l[8]));scalar(out,m.read16(t+l[9]));
            scalar(out,m.read8(t+l[10]));scalar(out,m.read8(t+l[11]));
            for(unsigned i=0;i<3;i++)scalar(out,m.read32(at("placement_clocks")+tr*l[13]+4*i));
        }
        for(unsigned i=0;i<2;i++)scalar(out,m.read16(at("placement_engine")+l[12]+2*i));
        raw(out,at("placement_ah_state"),268);control(out,at("placement_ah_control"),l);scalar(out,m.read32(at("placement_ah_hold")));
        return out;
    }
};
struct Native{
    void *library;void(*init)();void(*frame)();void(*bind)(const uint8_t*const*);unsigned(*snapshot)(uint8_t*);
    uint32_t *inputs,*mask,*status,*trace_enabled,*native_count;int32_t *output,*trace;uint32_t *packets;
    template<class T>T get(const char*n){auto p=dlsym(library,n);require(p!=nullptr,n);return reinterpret_cast<T>(p);}
    explicit Native(const std::string&w){library=dlopen((w+"/native.dylib").c_str(),RTLD_NOW|RTLD_LOCAL);if(!library)throw std::runtime_error(dlerror());
        init=get<void(*)()>("placement_init");frame=get<void(*)()>("placement_frame");bind=get<void(*)(const uint8_t*const*)>("placement_bind");snapshot=get<unsigned(*)(uint8_t*)>("placement_snapshot");
        inputs=get<uint32_t*>("placement_inputs");mask=get<uint32_t*>("placement_mask");status=get<uint32_t*>("placement_status");output=get<int32_t*>("placement_output");packets=get<uint32_t*>("placement_packets");
        trace=get<int32_t*>("placement_trace");trace_enabled=get<uint32_t*>("placement_trace_enabled");native_count=get<uint32_t*>("placement_native_samples");}
    Bytes bytes(){Bytes b(200000);auto n=snapshot(b.data());require(n<b.size(),"snapshot size");b.resize(n);return b;}
};
static uint64_t frames_checked=0,snapshots_checked=0,native_samples=0;
static void compare(Target&t,Native&n,bool state){
    require(t.m.read32(t.at("placement_status"))==1&&*n.status==1,"render status");
    for(unsigned tr=0;tr<4;tr++)if(*n.mask&(1u<<tr)){
        require(t.m.read32(t.at("placement_native_samples")+4*tr)==n.native_count[tr],"native sample count mismatch");
        for(unsigned i=0;i<16;i++)require(int32_t(t.m.read32(t.at("placement_output")+4*(16*tr+i)))==n.output[16*tr+i],"native/CF PCM");
        for(unsigned i=0;i<40;i++)require(t.m.read32(t.at("placement_packets")+4*(40*tr+i))==n.packets[40*tr+i],"native/CF source packet");
        // Independent mathematical clock check from the exact native data.
        unsigned start=0;
        for(unsigned half=0;half<2;half++){
            int32_t q[24];for(unsigned i=0;i<24;i++)q[i]=n.trace[(tr*2+half)*24+i];
            const unsigned count=q[3];if(!count)continue;
            unsigned phase=q[0],index=0;native_samples+=q[2];
            for(unsigned i=0;i<count;i++){
                int64_t a=q[4+index],b=phase?q[5+index]:a,product=(b-a)*32*phase;
                int64_t quotient=product/147;if(product<0&&product%147)--quotient;
                require(n.output[tr*16+start+i]==32*a+quotient,"independent rational clock");
                unsigned p=phase+160;index+=p/147;phase=p%147;
            }
            require(index+unsigned(phase>=13)==unsigned(q[1]+q[2]),"native count/FIFO conservation");start+=count;
        }
        require(start==16,"clock segment coverage");
    }
    if(state){require(t.snapshot()==n.bytes(),"complete canonical state/RNG/clock mismatch");++snapshots_checked;}
    ++frames_checked;
}

int main(int argc,char**argv){
    require(argc==3,"work assets");const std::string work=argv[1],assets=argv[2];
    HybridPredictor::selftest();Target t(work);hybrid_alignment=&t.alignment;Native native(work);
    std::vector<Bytes> storage;std::vector<const uint8_t*> ptrs;std::vector<uint32_t> addresses;
    uint32_t addr=0x44000000;
    for(auto name:{"pitch","chromatic","envelope1","envelope2","w0","w1","w2","w3","m1","interp_a","interp_b","wt_base","wt_bank","closed","open","ride"}){
        storage.push_back(read(assets+"/"+name+".bin"));addresses.push_back(addr);
        for(unsigned i=0;i<storage.back().size();i++)t.m.write8(addr+i,storage.back()[i]);addr=(addr+storage.back().size()+3)&~3u;
    }
    for(const auto &v:storage)ptrs.push_back(v.data());native.bind(ptrs.data());
    auto asset=[&](unsigned offset,unsigned index){t.m.write32(t.at("placement_assets")+offset,addresses[index]);};
    for(unsigned i=0;i<4;i++)asset(4*i,i);
    for(unsigned i=0;i<4;i++){t.m.write32(t.at("placement_assets")+16+8*i,0x080222a0+512*i);asset(20+8*i,4+i);}
    asset(48,8);t.m.write32(t.at("placement_assets")+52,0x080310e0);asset(56,9);asset(60,10);asset(64,11);asset(68,12);
    t.m.write32(t.at("placement_ah_tables"),addresses[2]);t.m.write32(t.at("placement_ah_tables")+4,addresses[3]);
    for(unsigned i=0;i<3;i++){uint32_t a=t.at("placement_ah_tables")+8+12*i;t.m.write32(a,(uint32_t[]){0x080cbef0,0x080a1bf0,0x080627cc}[i]);t.m.write32(a+4,addresses[13+i]);t.m.write32(a+8,storage[13+i].size());}
    // Native tracing is host work. Target traces are disabled so none of
    // their observation stores are charged as synthesis work.
    t.m.write32(t.at("placement_trace_enabled"),0);*native.trace_enabled=1;
    std::ofstream csv(work+"/costs.csv");csv<<"kind,case,mask,frame,cycles,instructions,stack_bytes,algos,modes\n";
    unsigned case_number=0;
    auto run=[&](const std::string&kind,unsigned mask,const std::array<unsigned,4>&algos,const std::array<unsigned,4>&modes,unsigned frames,unsigned corner,bool dense){
        t.predictor=HybridPredictor{};t.call("placement_init");native.init();*native.mask=mask;t.m.write32(t.at("placement_mask"),mask);
        for(unsigned f=0;f<frames;f++){
            for(unsigned tr=0;tr<4;tr++){
                unsigned split=f==0?0:dense?f%16:0,trig=f==0||(dense&&f%4==0);
                uint32_t in[]={algos[tr],modes[tr],dense?96u+f%32u:corner,dense?(f*7+31*tr)&127u:corner,
                    dense?(f*13+17*tr)&127u:corner,dense?(f*19+11*tr)&127u:corner,255,45,split,trig};
                for(unsigned j=0;j<10;j++){t.m.write32(t.at("placement_inputs")+4*(tr*10+j),in[j]);native.inputs[tr*10+j]=in[j];}
            }
            auto c=t.call("placement_frame");native.frame();compare(t,native,kind=="solo"||f==0||f+1==frames);
            csv<<kind<<','<<case_number<<','<<mask<<','<<f<<','<<c.cycles<<','<<c.instructions<<','<<c.stack<<',';
            for(auto a:algos)csv<<a<<':';csv<<',';for(auto m:modes)csv<<m<<':';csv<<'\n';
        }
        ++case_number;
    };
    for(unsigned voice=0;voice<2;voice++)for(auto engine:voice?std::vector<unsigned>{1,7}:std::vector<unsigned>{0,6})
        for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
            std::array<unsigned,4>a{0,1,4,5},m{};a[voice]=engine;m[voice]=mode;run("solo",1u<<voice,a,m,64,corner,false);run("solo",1u<<voice,a,m,32,corner,true);
        }
    const unsigned families[4][3]={{0,9,6},{1,9,7},{4,8,2},{5,3,10}};
    const std::array<unsigned,4> mode_rows[]={{0,0,0,0},{1,1,1,1},{2,2,2,2},{0,1,2,0},{1,2,0,1},{2,0,1,2}};
    for(unsigned combo=0;combo<81;combo++){
        unsigned n=combo;std::array<unsigned,4>a;
        for(unsigned tr=0;tr<4;tr++){a[tr]=families[tr][n%3];n/=3;}
        for(auto m:mode_rows){
            // Existing placement: one oscillator on B at most. Both WTs
            // necessarily stay CF. A has no resident V3/V4 implementation.
            unsigned mask=15;if(a[0]!=9)mask&=~1u;else if(a[1]!=9)mask&=~2u;
            std::vector<unsigned> masks{mask};
            if(a[0]!=9&&a[1]!=9)masks.push_back(15u&~2u);
            for(auto b:masks){
                run("layout",b,a,m,32,64,true);
                // Conditional CF remainder measurements, not credit for
                // any unimplemented DSP-A family, memory or timing fit.
                run("A_V3",b&~4u,a,m,32,64,true);
                run("A_V4",b&~8u,a,m,32,64,true);
                run("cf_remainder",b&3u,a,m,32,64,true);
            }
        }
        if(combo%9==0)std::cout<<"layouts "<<combo<<"/81 checked\n"<<std::flush;
    }
    csv.close();t.alignment.finish(work+"/alignment.json");
    std::ofstream report(work+"/EXECUTION.json");report<<"{\"frames\":"<<frames_checked<<",\"state_snapshots\":"<<snapshots_checked<<",\"native_samples\":"<<native_samples<<",\"algorithm_layouts\":81,\"mode_rows\":6,\"correctness\":\"passed\"}\n";
    std::cout<<"PASS frames="<<frames_checked<<" state snapshots="<<snapshots_checked<<" rational clock native="<<native_samples<<'\n';
}
