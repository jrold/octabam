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
static uint32_t u32(std::ifstream&f){uint8_t b[4];f.read((char*)b,4);return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);}
int main(int argc,char**argv){if(argc!=3)return 2;std::string ad=argv[2];auto p=rd(ad+"/pitch.bin"),c=rd(ad+"/chromatic.bin"),e1=rd(ad+"/envelope1.bin"),e2=rd(ad+"/envelope2.bin"),m1=rd(ad+"/m1.bin");std::array<std::vector<uint8_t>,4>w={rd(ad+"/w0.bin"),rd(ad+"/w1.bin"),rd(ad+"/w2.bin"),rd(ad+"/w3.bin")};constexpr uint32_t wa[4]={0x080222a0,0x080224a0,0x080226a0,0x080228a0};pk4_assets a{};a.pitch=p.data();a.chromatic=c.data();a.envelope1=e1.data();a.envelope2=e2.data();a.m1_wave=m1.data();a.m1_wave_address=0x080310e0;for(int i=0;i<4;i++){a.waves[i].address=wa[i];a.waves[i].table=w[i].data();}
std::ifstream f(argv[1],std::ios::binary);char magic[4];f.read(magic,4);if(std::string(magic,4)!="PKCT"||u32(f)!=1)return 3;uint32_t cases=0;while(f.peek()!=EOF){uint8_t h[4];f.read((char*)h,4);if(f.gcount()==0)break;uint32_t n=u32(f);std::vector<uint8_t>exp(n);f.read((char*)exp.data(),n);uint8_t raw[4]={64,64,64,64};raw[h[2]]=h[3];pk4_engine e;pk4_init(&e,&a);if(!pk4_prepare_event(&e,0,raw[1],raw[0],raw[2],raw[3],h[1],h[0],255,45,1))return 4;const uint8_t*got=nullptr;size_t gn=0;if(h[0]==0){got=e.tracks[0].fold1;gn=sizeof e.tracks[0].fold1;}else if(h[0]==1){got=e.tracks[0].fold2;gn=sizeof e.tracks[0].fold2;}else{got=e.tracks[0].karplus;gn=sizeof e.tracks[0].karplus;}if(gn!=n||memcmp(got,exp.data(),n)){size_t j=0;while(j<n&&got[j]==exp[j])j++;std::cerr<<"state mismatch case="<<cases<<" engine="<<(int)h[0]<<" mode="<<(int)h[1]<<" ctl="<<(int)h[2]<<" value="<<(int)h[3]<<" at 0x"<<std::hex<<j<<" got="<<(int)got[j]<<" exp="<<(int)exp[j]<<std::dec<<"\n";return 10+h[0];}cases++;}
std::cout<<"PERKY4 C state prep: PASS "<<cases<<" Fold1/Fold2/Karplus OT-control states byte-exact vs Python ARM translation\n";}
