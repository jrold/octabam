// Reuse the actual-image Target and its independently trained predictor.
#define main production_callback_main
#include "hybrid_cf_production_runner.cpp"
#undef main

int main(int argc,char**argv){
    if(argc!=4)return 2;
    HybridPredictor::selftest();
    const std::string work=argv[3];
    Target a(argv[1],work+"/reference.nm"),b(argv[2],work+"/candidate.nm");
    const unsigned offsets[]={0,336,672,1140,1608},sizes[]={336,336,468,468,288};
    uint32_t random=0x12481527;uint64_t cases=0,compared=0;
    auto equal=[&](uint32_t aa,uint32_t bb,uint32_t n){
        if(a.bytes(aa,n)!=b.bytes(bb,n))throw std::runtime_error("empty callback changed poisoned state or source RAM");
        compared+=n;
    };
    for(unsigned mode=0;mode<5;++mode){
        std::vector<uint8_t> pristine[2];unsigned ti=0;
        for(auto*t:{&a,&b}){
            t->call("pk_hybrid_boot_init",{});
            t->m.write32(t->symbols.at("pk_hybrid_profiler_enable").address,0);
            auto v=t->symbols.at("pk_hybrid_voices");
            if(v.size!=3968)throw std::runtime_error("requires witnessed 1984-byte instances");
            pristine[ti++]=t->bytes(v.address,v.size);
        }
        for(unsigned inst=0;inst<2;++inst)for(unsigned sample=0;sample<1024;++sample){
            std::vector<uint8_t> poison(sizes[mode]);
            for(auto&v:poison){random^=random<<13;random^=random>>17;random^=random<<5;v=uint8_t(random);}
            unsigned index=0,track=inst?5:1;
            for(auto*t:{&a,&b}){
                auto v=t->symbols.at("pk_hybrid_voices");
                for(unsigned i=0;i<v.size;++i)t->m.write8(v.address+i,pristine[index][i]);
                ++index;
                t->call("pk_hybrid_cf_prepare_event",{inst,127,44,50,60,mode<2?0:mode-2,mode<2?mode:2,255,45,1});
                for(unsigned i=0;i<poison.size();++i)t->m.write8(v.address+inst*1984+offsets[mode]+i,poison[i]);
                t->m.write32(0x80001c80,0x80010000);
                t->m.write8(0x46104d0c+track,(sample&1)?16:0);
                t->call("pk_render",{track,0,0,0});
            }
            equal(0x80001c40,0x80001c40,0x1900);
            for(auto name:{"pk_hybrid_voices","pk_hybrid_frame_pcm","pk_hybrid_trigger_latch","pk_hybrid_frame_started"}){
                auto x=a.symbols.at(name),y=b.symbols.at(name);
                if(x.size!=y.size)throw std::runtime_error("state extent changed");
                equal(x.address,y.address,x.size);
            }
            if(m68k_get_reg(a.m.getCpuState(),M68K_REG_D0)!=m68k_get_reg(b.m.getCpuState(),M68K_REG_D0))
                throw std::runtime_error("callback status changed");
            ++cases;
        }
    }
    std::ofstream f(work+"/EMPTY_POISON.json");
    f<<"{\"status\":\"PASS_EXACT_EMPTY_CALLBACK_POISONED_RENDERER_STATES\",\"cases\":"<<cases
     <<",\"algorithms\":5,\"instances\":2,\"compared_bytes\":"<<compared<<"}\n";
}
