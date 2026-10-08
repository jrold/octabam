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
auto fx=rd(argv[1]);if(fx.size()<8||memcmp(fx.data(),"P4SQ",4))return 3;uint32_t count=le32(fx.data()+4);size_t pos=8;pk4_engine e;pk4_init(&e,&a);std::array<uint32_t,4> events{};for(uint32_t r=0;r<count;r++){if(pos+12>fx.size())return 4;unsigned tr=fx[pos],algo=fx[pos+1],mode=fx[pos+2],trig=fx[pos+3];uint8_t src[4]={fx[pos+4],fx[pos+5],fx[pos+6],fx[pos+7]};uint32_t n=le32(fx.data()+pos+8);pos+=12;if(pos+n>fx.size())return 5;const uint8_t*exp=fx.data()+pos;pos+=n;std::array<pk4_track,3> other{};unsigned oi=0;for(unsigned t=0;t<4;t++)if(t!=tr)other[oi++]=e.tracks[t];if(!pk4_prepare_event(&e,tr,src[0],src[1],src[2],src[3],mode,algo,255,45,trig))return 6;oi=0;for(unsigned t=0;t<4;t++)if(t!=tr){if(memcmp(&other[oi++],&e.tracks[t],sizeof(pk4_track))){std::cerr<<"cross-track mutation event "<<r<<" source track "<<tr<<" touched track "<<t<<"\n";return 7;}}
const uint8_t*got=nullptr;size_t gn=0;if(algo==0){got=e.tracks[tr].fold1;gn=sizeof e.tracks[tr].fold1;}else if(algo==1){got=e.tracks[tr].fold2;gn=sizeof e.tracks[tr].fold2;}else if(algo==2){got=e.tracks[tr].karplus;gn=sizeof e.tracks[tr].karplus;}else{got=mode==0?e.tracks[tr].nt_m1:e.tracks[tr].nt_shared;gn=PK_CF_NT_STATE_BYTES;}if(gn!=n||memcmp(got,exp,n)){size_t j=0;while(j<n&&got[j]==exp[j])j++;std::cerr<<"sequence state mismatch event="<<r<<" track="<<tr<<" algo="<<algo<<" mode="<<mode<<" at 0x"<<std::hex<<j<<" got="<<(int)got[j]<<" exp="<<(int)exp[j]<<std::dec<<"\n";return 10;}events[tr]++;}
if(pos!=fx.size()) return 11;
std::cout << "PERKY4 p-lock sequence: PASS " << count
          << " events; four independent tracks; Algo+Mode+Decay+Tune+Param1+Param2 "
             "changed per trig; zero cross-track state mutation\n";
for(int i=0;i<4;i++) std::cout << "  track " << i << ": " << events[i] << " events\n";
return 0;
}
