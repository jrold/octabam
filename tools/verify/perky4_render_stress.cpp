#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
#include <fstream>
#include "NativeV121FoldDrums.h"
#include "NativeV121Karplus.h"
#include "NativeV121NoiseTone.h"
#include "NativeV121NoiseToneShared.h"
extern "C" {
#include "cf_perky4.h"
}
static std::vector<uint8_t> rd(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error(p);return {std::istreambuf_iterator<char>(f),{}};}
static int32_t s24(uint32_t v){v&=0xffffffu;return (v&0x800000u)?(int32_t)(v|0xff000000u):(int32_t)v;}
int main(int argc,char**argv){if(argc!=2)return 2;std::string ad=argv[1];auto pv=rd(ad+"/pitch.bin"),cv=rd(ad+"/chromatic.bin"),e1v=rd(ad+"/envelope1.bin"),e2v=rd(ad+"/envelope2.bin"),m1v=rd(ad+"/m1.bin");std::array<std::vector<uint8_t>,4>wv={rd(ad+"/w0.bin"),rd(ad+"/w1.bin"),rd(ad+"/w2.bin"),rd(ad+"/w3.bin")};constexpr std::array<uint32_t,4>wa={0x080222a0u,0x080224a0u,0x080226a0u,0x080228a0u};
pk4_assets a{};a.pitch=pv.data();a.chromatic=cv.data();a.envelope1=e1v.data();a.envelope2=e2v.data();a.m1_wave=m1v.data();a.m1_wave_address=0x080310e0u;for(int i=0;i<4;i++){a.waves[i].address=wa[i];a.waves[i].table=wv[i].data();}
using F=NativeV121FoldDrums;F::PitchTable fp{};F::EnvelopeTable fe1{},fe2{};std::array<F::WaveTable,4>fw{};memcpy(fp.data(),pv.data(),fp.size());memcpy(fe1.data(),e1v.data(),fe1.size());memcpy(fe2.data(),e2v.data(),fe2.size());F::Tables ft{&fp,&fe1,&fe2,{}};for(int i=0;i<4;i++){memcpy(fw[i].data(),wv[i].data(),fw[i].size());ft.waves[i]={wa[i],&fw[i]};}
using K=NativeV121Karplus;K::EnvelopeTable ke1{},ke2{};memcpy(ke1.data(),e1v.data(),ke1.size());memcpy(ke2.data(),e2v.data(),ke2.size());K::Tables kt{&ke1,&ke2};
NativeV121NoiseToneShared::EnvelopeTable ne1{},ne2{};std::array<NativeV121NoiseToneShared::WaveTable,4>nw{};memcpy(ne1.data(),e1v.data(),ne1.size());memcpy(ne2.data(),e2v.data(),ne2.size());NativeV121NoiseToneShared::Tables nt{&ne1,&ne2,{}};for(int i=0;i<4;i++){memcpy(nw[i].data(),wv[i].data(),nw[i].size());nt.waves[i]={wa[i],&nw[i]};}
NativeV121NoiseToneWaveform2::WaveTable m1{};memcpy(m1.data(),m1v.data(),m1.size());
pk4_engine e;pk4_init(&e,&a);std::array<uint64_t,4>sampleByAlgo{};std::array<uint64_t,3>ntMode{};constexpr unsigned N=16;constexpr unsigned EVENTS=16384;
for(unsigned ev=0;ev<EVENTS;ev++){unsigned tr=ev&3u,step=ev>>2,algo=(step+tr*3u)&3u,mode=(step*2u+tr)%3u;uint8_t dec=(uint8_t)((step*17u+tr*11u)&127u),tun=(uint8_t)((step*29u+tr*7u)&127u),p1=(uint8_t)((step*43u+tr*5u)&127u),p2=(uint8_t)((step*61u+tr*3u)&127u);std::array<pk4_track,3> other{};unsigned oi=0;for(unsigned t=0;t<4;t++)if(t!=tr)other[oi++]=e.tracks[t];if(!pk4_prepare_event(&e,tr,dec,tun,p1,p2,(uint8_t)mode,(uint8_t)algo,255,45,1)){std::cerr<<"prepare fail\n";return 3;}auto&r=e.tracks[tr];std::array<int16_t,N>ref{},got{};uint32_t rlo=r.rng_low,rhi=r.rng_high;
if(algo==0){F::Fold1State s{};memcpy(s.data(),r.fold1,s.size());F::RngState rr{rlo,rhi};if(!F::renderFold1(s,ref.data(),N,ft,rr))return 10;if(!pk4_render(&e,tr,got.data(),N))return 11;if(ref!=got||memcmp(s.data(),r.fold1,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){std::cerr<<"Fold1 render mismatch ev "<<ev<<"\n";return 12;}}
else if(algo==1){F::Fold2State s{};memcpy(s.data(),r.fold2,s.size());F::RngState rr{rlo,rhi};uint32_t obj=0x20000000u+tr*0x10000u;if(!F::renderFold2(s,obj,ref.data(),N,ft,rr))return 13;if(!pk4_render(&e,tr,got.data(),N))return 14;if(ref!=got||memcmp(s.data(),r.fold2,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){std::cerr<<"Fold2 render mismatch ev "<<ev<<"\n";return 15;}}
else if(algo==2){K::State s{};memcpy(s.data(),r.karplus,s.size());K::RngState rr{rlo,rhi};if(!K::renderBlock(s,ref.data(),N,kt,rr))return 16;if(!pk4_render(&e,tr,got.data(),N))return 17;if(ref!=got||memcmp(s.data(),r.karplus,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){std::cerr<<"Karplus render mismatch ev "<<ev<<"\n";return 18;}}
else if(mode==0){NativeV121NoiseToneWaveform2::State s{};memcpy(s.data(),r.nt_m1,s.size());if(!NativeV121NoiseToneWaveform2::renderBlock(s,ref.data(),N,m1,0x080310e0u,m1,0x080310e0u))return 19;if(!pk4_render(&e,tr,got.data(),N))return 20;if(ref!=got||memcmp(s.data(),r.nt_m1,s.size())||rlo!=r.rng_low||rhi!=r.rng_high){std::cerr<<"NT M1 mismatch ev "<<ev<<"\n";return 21;}ntMode[0]+=N;}
else {NativeV121NoiseToneShared::State s{};memcpy(s.data(),r.nt_shared,s.size());NativeV121NoiseToneShared::RngState rr{rlo,rhi};if(!NativeV121NoiseToneShared::renderBlock(s,ref.data(),N,nt,rr))return 22;if(!pk4_render(&e,tr,got.data(),N))return 23;if(ref!=got||memcmp(s.data(),r.nt_shared,s.size())||rr.low!=r.rng_low||rr.high!=r.rng_high){std::cerr<<"NT shared mismatch ev "<<ev<<" mode "<<mode<<"\n";return 24;}ntMode[mode]+=N;}
for(unsigned t=0,oi2=0;t<4;t++)if(t!=tr){if(memcmp(&other[oi2++],&e.tracks[t],sizeof(pk4_track))){std::cerr<<"cross-track mutation render ev "<<ev<<"\n";return 25;}}
uint32_t rec[36]{};if(pk4_encode_stock_segment(rec,got.data(),N)!=36)return 26;if((rec[0]>>8)!=N||(rec[1]>>8)!=0||(rec[2]>>8)!=0x40000u||(rec[3]>>8)!=0)return 27;for(unsigned i=0;i<N;i++){int32_t l=s24(rec[4+2*i]>>8),rr=s24(rec[5+2*i]>>8);if(l!=(int32_t)got[i]*256||rr!=l){std::cerr<<"record PCM mismatch ev "<<ev<<" sample "<<i<<"\n";return 28;}}
sampleByAlgo[algo]+=N;}
std::cout<<"PERKY4 four-track render stress: PASS "<<EVENTS<<" trigs / "<<EVENTS*N<<" samples; dynamic Algo+Mode; all six SRC values changed; zero cross-track mutation\n";std::cout<<"  Fold1 "<<sampleByAlgo[0]<<" samples exact\n  Fold2 "<<sampleByAlgo[1]<<" samples exact\n  Karplus "<<sampleByAlgo[2]<<" samples exact\n  Noise/Tone "<<sampleByAlgo[3]<<" samples exact (M1 "<<ntMode[0]<<", M2 "<<ntMode[1]<<", M3 "<<ntMode[2]<<")\n";std::cout<<"  stock source record: "<<EVENTS<<" blocks round-tripped exactly at unity rate, mono duplicated to L/R\n";}
