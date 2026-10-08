#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <vector>

#include "NativeV121FoldDrums.h"
#include "NativeV121Karplus.h"
#include "NativeV121NoiseTone.h"
#include "NativeV121NoiseToneShared.h"
extern "C" {
#include "cf_perky4.h"
}

static std::vector<uint8_t> rd(const std::string &p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) throw std::runtime_error(p);
    return {std::istreambuf_iterator<char>(f), {}};
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const std::string ad = argv[1];
    auto pv=rd(ad+"/pitch.bin"), cv=rd(ad+"/chromatic.bin"),
         e1v=rd(ad+"/envelope1.bin"), e2v=rd(ad+"/envelope2.bin"),
         m1v=rd(ad+"/m1.bin");
    std::array<std::vector<uint8_t>,4> wv = {
        rd(ad+"/w0.bin"), rd(ad+"/w1.bin"), rd(ad+"/w2.bin"), rd(ad+"/w3.bin")
    };
    constexpr std::array<uint32_t,4> wa = {
        0x080222a0u,0x080224a0u,0x080226a0u,0x080228a0u
    };

    pk4_assets a{};
    a.pitch=pv.data(); a.chromatic=cv.data(); a.envelope1=e1v.data(); a.envelope2=e2v.data();
    a.m1_wave=m1v.data(); a.m1_wave_address=0x080310e0u;
    for (int i=0;i<4;i++) { a.waves[i].address=wa[i]; a.waves[i].table=wv[i].data(); }

    using F=NativeV121FoldDrums;
    F::PitchTable fp{}; F::EnvelopeTable fe1{},fe2{}; std::array<F::WaveTable,4> fw{};
    memcpy(fp.data(),pv.data(),fp.size()); memcpy(fe1.data(),e1v.data(),fe1.size()); memcpy(fe2.data(),e2v.data(),fe2.size());
    F::Tables ft{&fp,&fe1,&fe2,{}};
    for(int i=0;i<4;i++){memcpy(fw[i].data(),wv[i].data(),fw[i].size());ft.waves[i]={wa[i],&fw[i]};}

    using K=NativeV121Karplus;
    K::EnvelopeTable ke1{},ke2{}; memcpy(ke1.data(),e1v.data(),ke1.size()); memcpy(ke2.data(),e2v.data(),ke2.size());
    K::Tables kt{&ke1,&ke2};

    NativeV121NoiseToneShared::EnvelopeTable ne1{},ne2{};
    std::array<NativeV121NoiseToneShared::WaveTable,4> nw{};
    memcpy(ne1.data(),e1v.data(),ne1.size()); memcpy(ne2.data(),e2v.data(),ne2.size());
    NativeV121NoiseToneShared::Tables nt{&ne1,&ne2,{}};
    for(int i=0;i<4;i++){memcpy(nw[i].data(),wv[i].data(),nw[i].size());nt.waves[i]={wa[i],&nw[i]};}
    NativeV121NoiseToneWaveform2::WaveTable m1{}; memcpy(m1.data(),m1v.data(),m1.size());

    constexpr unsigned N=16;
    constexpr unsigned SAMPLES=8192;
    constexpr unsigned BLOCKS=SAMPLES/N;
    const std::array<std::array<uint8_t,4>,3> profiles = {{{127,17,91,33},{96,64,7,120},{63,111,127,72}}};
    uint64_t exact=0, cases=0;
    std::array<std::array<uint64_t,4>,4> matrix{};
    std::array<uint64_t,3> nt_modes{};

    for (unsigned tr=0; tr<4; ++tr) {
        for (unsigned algo=0; algo<4; ++algo) {
            for (unsigned mode=0; mode<3; ++mode) {
                for (unsigned pi=0; pi<profiles.size(); ++pi) {
                    pk4_engine e{}; pk4_init(&e,&a);
                    const auto &q=profiles[pi];
                    if (!pk4_prepare_event(&e,tr,q[0],q[1],q[2],q[3],(uint8_t)mode,(uint8_t)algo,255,45,1)) {
                        std::cerr<<"prepare failed tr="<<tr<<" algo="<<algo<<" mode="<<mode<<" p="<<pi<<"\n"; return 3;
                    }
                    auto &r=e.tracks[tr];
                    std::array<int16_t,N> ref{},got{};

                    if (algo==0) {
                        F::Fold1State s{}; memcpy(s.data(),r.fold1,s.size()); F::RngState rr{r.rng_low,r.rng_high};
                        for(unsigned b=0;b<BLOCKS;b++){
                            if(!F::renderFold1(s,ref.data(),N,ft,rr)||!pk4_render(&e,tr,got.data(),N)) return 10;
                            if(ref!=got||memcmp(s.data(),r.fold1,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){
                                std::cerr<<"Fold1 tail mismatch tr="<<tr<<" mode="<<mode<<" profile="<<pi<<" block="<<b<<"\n";return 11;}
                        }
                    } else if (algo==1) {
                        F::Fold2State s{}; memcpy(s.data(),r.fold2,s.size()); F::RngState rr{r.rng_low,r.rng_high};
                        uint32_t obj=0x20000000u+tr*0x10000u;
                        for(unsigned b=0;b<BLOCKS;b++){
                            if(!F::renderFold2(s,obj,ref.data(),N,ft,rr)||!pk4_render(&e,tr,got.data(),N)) return 12;
                            if(ref!=got||memcmp(s.data(),r.fold2,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){
                                std::cerr<<"Fold2 tail mismatch tr="<<tr<<" mode="<<mode<<" profile="<<pi<<" block="<<b<<"\n";return 13;}
                        }
                    } else if (algo==2) {
                        K::State s{}; memcpy(s.data(),r.karplus,s.size()); K::RngState rr{r.rng_low,r.rng_high};
                        for(unsigned b=0;b<BLOCKS;b++){
                            if(!K::renderBlock(s,ref.data(),N,kt,rr)||!pk4_render(&e,tr,got.data(),N)) return 14;
                            if(ref!=got||memcmp(s.data(),r.karplus,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){
                                std::cerr<<"Karplus tail mismatch tr="<<tr<<" mode="<<mode<<" profile="<<pi<<" block="<<b<<"\n";return 15;}
                        }
                    } else if (mode==0) {
                        NativeV121NoiseToneWaveform2::State s{}; memcpy(s.data(),r.nt_m1,s.size());
                        const uint32_t lo=r.rng_low,hi=r.rng_high;
                        for(unsigned b=0;b<BLOCKS;b++){
                            if(!NativeV121NoiseToneWaveform2::renderBlock(s,ref.data(),N,m1,0x080310e0u,m1,0x080310e0u)||!pk4_render(&e,tr,got.data(),N)) return 16;
                            if(ref!=got||memcmp(s.data(),r.nt_m1,s.size())||r.rng_low!=lo||r.rng_high!=hi){
                                std::cerr<<"NT M1 tail mismatch tr="<<tr<<" profile="<<pi<<" block="<<b<<"\n";return 17;}
                        }
                    } else {
                        NativeV121NoiseToneShared::State s{}; memcpy(s.data(),r.nt_shared,s.size());
                        NativeV121NoiseToneShared::RngState rr{r.rng_low,r.rng_high};
                        for(unsigned b=0;b<BLOCKS;b++){
                            if(!NativeV121NoiseToneShared::renderBlock(s,ref.data(),N,nt,rr)||!pk4_render(&e,tr,got.data(),N)) return 18;
                            if(ref!=got||memcmp(s.data(),r.nt_shared,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){
                                std::cerr<<"NT shared tail mismatch tr="<<tr<<" mode="<<mode<<" profile="<<pi<<" block="<<b<<"\n";return 19;}
                        }
                    }
                    exact += SAMPLES;
                    matrix[tr][algo] += SAMPLES;
                    if(algo==3) nt_modes[mode]+=SAMPLES;
                    ++cases;
                }
            }
        }
    }
    std::cout<<"PERKY4 long-tail continuity: PASS "<<cases<<" cases / "<<exact<<" exact samples / "<<BLOCKS<<" 16-sample blocks per case\n";
    for(unsigned tr=0;tr<4;tr++)
        std::cout<<"  voice "<<tr<<": Fold1="<<matrix[tr][0]<<" Fold2="<<matrix[tr][1]<<" Karplus="<<matrix[tr][2]<<" NoiseTone="<<matrix[tr][3]<<" exact samples\n";
    std::cout<<"  Noise/Tone modes: M1="<<nt_modes[0]<<" M2="<<nt_modes[1]<<" M3="<<nt_modes[2]<<" exact samples\n";
    return 0;
}
