#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <vector>
extern "C" {
#include "cf_perky4.h"
}
static std::vector<uint8_t> rd(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error(p);return {std::istreambuf_iterator<char>(f),{}};}
static uint32_t le32(const uint8_t*p){return p[0]|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
int main(int argc,char**argv){if(argc!=3)return 2;std::string ad=argv[2];auto p=rd(ad+"/pitch.bin"),c=rd(ad+"/chromatic.bin"),e1=rd(ad+"/envelope1.bin"),e2=rd(ad+"/envelope2.bin"),m1=rd(ad+"/m1.bin");std::array<std::vector<uint8_t>,4>w={rd(ad+"/w0.bin"),rd(ad+"/w1.bin"),rd(ad+"/w2.bin"),rd(ad+"/w3.bin")};constexpr uint32_t wa[4]={0x080222a0,0x080224a0,0x080226a0,0x080228a0};pk4_assets a{};a.pitch=p.data();a.chromatic=c.data();a.envelope1=e1.data();a.envelope2=e2.data();a.m1_wave=m1.data();a.m1_wave_address=0x080310e0;for(int i=0;i<4;i++){a.waves[i].address=wa[i];a.waves[i].table=w[i].data();}
auto fx=rd(argv[1]);if(fx.size()<8||memcmp(fx.data(),"NTC1",4))return 3;uint32_t count=le32(fx.data()+4);size_t pos=8;for(uint32_t r=0;r<count;r++){unsigned mode=fx[pos],ctl=fx[pos+1],val=fx[pos+2];pos+=4;const uint8_t*exp=fx.data()+pos;pos+=0x120;pos+=8;uint8_t raw[4]={64,64,64,64};raw[ctl]=(uint8_t)val;pk4_engine e;pk4_init(&e,&a);if(!pk4_prepare_event(&e,0,raw[1],raw[0],raw[2],raw[3],mode,PK4_ALGO_NOISE_TONE,255,45,1))return 4;const uint8_t*got=mode==0?e.tracks[0].nt_m1:e.tracks[0].nt_shared;if(memcmp(got,exp,0x120)){size_t j=0;while(j<0x120&&got[j]==exp[j])j++;std::cerr<<"NT state mismatch rec="<<r<<" mode="<<mode<<" ctl="<<ctl<<" val="<<val<<" at 0x"<<std::hex<<j<<" got="<<(int)got[j]<<" exp="<<(int)exp[j]<<std::dec<<"\n";return 10;} }
std::cout<<"PERKY4 C Noise/Tone state prep: PASS "<<count<<" OT-control states byte-exact vs Python ARM translation\n";}
