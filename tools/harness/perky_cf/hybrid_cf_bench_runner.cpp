#include "machine.h"
#include "hybrid_cf_shadow_runner.hpp"
#include "hybrid_cf_alignment.hpp"
#include "mc68k/Musashi/m68k.h"
#include "mc68k/cpuState.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <map>
#include <vector>
#include <algorithm>
#include <stdexcept>
static std::vector<uint8_t> read(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("read "+p);return {std::istreambuf_iterator<char>(f),{}};}
static void load(ot::Machine&m,const std::vector<uint8_t>&b,uint32_t a){for(unsigned i=0;i<b.size();i++)m.write8(a+i,b[i]);}
struct Cost {uint64_t cycles,instructions;uint32_t stack;};
const uint32_t SP=0x47100000, END=0x47200000;
static Cost call(ot::Machine&m,uint32_t pc){HybridAlignmentScope alignment_scope;m68k_set_reg(m.getCpuState(),M68K_REG_SR,0x2700);m68k_set_reg(m.getCpuState(),M68K_REG_SP,SP);m68k_set_reg(m.getCpuState(),M68K_REG_PC,pc);m.write32(SP,END);uint64_t before=m.getCycles(),n=0;uint32_t lo=SP;while(m.pcFast()!=END){if(++n>10000000||!m.stepFast())throw std::runtime_error("target call stopped: "+m.why()+" PC="+std::to_string(m.pcFast()));lo=std::min(lo,m68k_get_reg(m.getCpuState(),M68K_REG_SP));}if(m.getCycles()<before)throw std::runtime_error("cycles underflow");if(m68k_get_reg(m.getCpuState(),M68K_REG_SP)!=SP+4)throw std::runtime_error("stack ABI");return {m.getCycles()-before,n,SP-lo};}

// Standalone lower-level benchmark. No OS image or DSP is loaded.
int main(int argc,char**argv) {
    if(argc!=3) return 2;
    std::string out=argv[1],ad=argv[2];
    std::map<std::string,uint32_t> s,sizes;
    std::ifstream nm(out+"/target.nm");std::string line;
    while(getline(nm,line)) {
        std::istringstream f(line);uint32_t a,z;char t;std::string n;
        if(f>>std::hex>>a>>z>>t>>n){s[n]=a;sizes[n]=z;}
    }
    for(auto n:{"bench_init","bench_prepare","bench_render","assets","voices","status","output","profile","modes","knobs","triggers","ready_cookie"})
        if(!s[n])throw std::runtime_error(n);
    ot::Machine m(read(out+"/target.bin"));HybridAlignment alignment(m);hybrid_alignment=&alignment;
    uint32_t a=0x44000000;
    std::map<std::string,uint32_t> assets;
    for(auto n:{"pitch","chromatic","envelope1","envelope2","w0","w1","w2","w3","m1","interp_a","interp_b","wt_base","wt_bank"}) {
        auto b=read(ad+"/"+n+".bin");assets[n]=a;load(m,b,a);a=(a+b.size()+3)&~3u;
    }
    auto putasset=[&](unsigned off,std::string n){m.write32(s["assets"]+off,assets[n]);};
    putasset(0,"pitch");putasset(4,"chromatic");putasset(8,"envelope1");putasset(12,"envelope2");
    for(unsigned i=0;i<4;i++) {m.write32(s["assets"]+16+8*i,0x080222a0+512*i);putasset(20+8*i,"w"+std::to_string(i));}
    putasset(48,"m1");m.write32(s["assets"]+52,0x080310e0);putasset(56,"interp_a");putasset(60,"interp_b");putasset(64,"wt_base");putasset(68,"wt_bank");
    HybridShadow shadow(m,s,ad,out);
    // BSS is deliberately dirty. The prospective small adapter must clear its
    // owned state explicitly and produce exactly the same bytes as clean RAM.
    if(m.read32(s["ready_cookie"])!=0x504b434f)throw std::runtime_error("cookie not loaded COLD");
    for(unsigned j=0;j<sizes["voices"];j++)m.write8(s["voices"]+j,0);
    call(m,s["bench_init"]);
    std::vector<uint8_t> initialized(sizes["voices"]);
    for(unsigned j=0;j<initialized.size();j++)initialized[j]=m.read8(s["voices"]+j);
    for(unsigned j=0;j<sizes["voices"];j++)m.write8(s["voices"]+j,(j*37+0xa5)&255);
    m.write32(s["ready_cookie"],0x504b434f);call(m,s["bench_init"]);
    for(unsigned j=0;j<initialized.size();j++)if(initialized[j]!=m.read8(s["voices"]+j))throw std::runtime_error("dirty BSS init drift");
    if(m.read32(s["ready_cookie"])!=0x504b5244)throw std::runtime_error("cookie not READY after init");
    std::ofstream csv(out+"/costs.csv");
    csv<<"left,right,corner,phase,frame,cycles,instructions,stack_bytes,status\n";
    struct Profile{const char*name;unsigned p,mode;};
    const Profile ps[]={{"V1M1",0,0},{"V1M2",0,1},{"V1M3",0,2},{"V2M1",1,0},{"V2M2",1,1},{"V2M3",1,2},{"snare",2,0},{"bass",3,1},{"third",4,2}};
    unsigned bad=0;
    auto configure=[&](Profile l,Profile r,unsigned corner){
        m.write32(s["profile"],l.p);m.write32(s["profile"]+4,r.p);
        m.write32(s["modes"],l.mode);m.write32(s["modes"]+4,r.mode);
        for(unsigned i=0;i<2;i++){m.write32(s["triggers"]+i*4,1);for(unsigned k=0;k<4;k++)m.write32(s["knobs"]+i*16+k*4,corner);}
    };
    for(unsigned li=0;li<9;li++)for(unsigned ri=0;ri<9;ri++)for(unsigned corner:{0u,64u,127u}) {
        auto l=ps[li],r=ps[ri];
        auto emit=[&](const char*phase,unsigned frame,Cost c){shadow.check(phase);csv<<l.name<<','<<r.name<<','<<corner<<','<<phase<<','<<frame<<','<<c.cycles<<','<<c.instructions<<','<<c.stack<<','<<m.read32(s["status"])<<'\n';if(!m.read32(s["status"]))bad++;};
        configure(l,r,corner);emit("init",0,call(m,s["bench_init"]));emit("prepare-fresh",0,call(m,s["bench_prepare"]));
        for(unsigned f=0;f<64;f++) {
            if(f==16||f==24||f==32) {
                for(unsigned i=0;i<2;i++) {
                    m.write32(s["triggers"]+i*4,f==32);
                    for(unsigned k=0;k<4;k++)m.write32(s["knobs"]+i*16+k*4,(corner+f+17*i+7*k)&127);
                }
                emit(f==32?"prepare-dirty-trigger":"prepare-dirty-no-trigger",f,call(m,s["bench_prepare"]));
            }
            if(f==40) {
                for(unsigned i=0;i<2;i++){m.write32(s["triggers"]+i*4,0);m.write32(s["modes"]+i*4,(m.read32(s["modes"]+i*4)+1)%3);}
                emit("prepare-mode-change",f,call(m,s["bench_prepare"]));
            }
            if(f==48) {
                auto nl=ps[(li+4)%9],nr=ps[(ri+7)%9];
                m.write32(s["profile"],nl.p);m.write32(s["profile"]+4,nr.p);m.write32(s["modes"],nl.mode);m.write32(s["modes"]+4,nr.mode);
                for(unsigned i=0;i<2;i++)m.write32(s["triggers"]+i*4,1);
                emit("prepare-family-change",f,call(m,s["bench_prepare"]));
            }
            if(f==56) {
                m.write32(s["profile"],l.p);m.write32(s["profile"]+4,r.p);m.write32(s["modes"],l.mode);m.write32(s["modes"]+4,r.mode);
                for(unsigned i=0;i<2;i++)m.write32(s["triggers"]+i*4,0);
                emit("prepare-return-without-trigger",f,call(m,s["bench_prepare"]));
            }
            emit("render",f,call(m,s["bench_render"]));
        }
        for(unsigned i=0;i<2;i++)m.write32(s["triggers"]+i*4,0);
        emit("prepare-clean",64,call(m,s["bench_prepare"]));
        emit("clean-render",64,call(m,s["bench_render"]));
    }
    // Continuation through 8192 samples, including the natural envelope tail.
    for(auto l:ps) {
        configure(l,l,64);call(m,s["bench_init"]);shadow.check("init");call(m,s["bench_prepare"]);shadow.check("prepare-fresh");
        for(unsigned f=0;f<512;f++) {auto c=call(m,s["bench_render"]);shadow.check("tail-render");csv<<l.name<<','<<l.name<<",64,tail-render,"<<f<<','<<c.cycles<<','<<c.instructions<<','<<c.stack<<','<<m.read32(s["status"])<<'\n';if(!m.read32(s["status"]))bad++;}
    }
    shadow.finish(252,1953,20403);
    std::ofstream init(out+"/readiness.json");
    init<<"{\"dirty_bss_equal_clean\":true,\"cold_cookie_loaded\":true,\"ready_after_init\":true,\"instance_bytes\":"<<sizes["voices"]/2<<",\"two_instance_bytes\":"<<sizes["voices"]<<",\"mapped_assets_bytes_with_alignment\":"<<a-0x44000000<<",\"render_failures\":"<<bad<<"}\n";
    std::cout<<"two-instance target matrix cases=243 render_frames=15552 tail_frames=4608 failures="<<bad<<"\n";
    alignment.finish(out+"/bench-alignment.json");return bad?1:0;
}
