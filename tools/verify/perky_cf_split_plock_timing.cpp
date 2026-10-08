#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
extern "C" {
#include "cf_perky4.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: perky_cf_split_plock_timing <asset-dir>\n";
        return 2;
    }
    const std::string d = argv[1];
    auto pitch=read_file(d+"/pitch.bin"), chrom=read_file(d+"/chromatic.bin");
    auto e1=read_file(d+"/envelope1.bin"), e2=read_file(d+"/envelope2.bin");
    auto m1=read_file(d+"/m1.bin");
    std::array<std::vector<std::uint8_t>,4> w={read_file(d+"/w0.bin"),read_file(d+"/w1.bin"),read_file(d+"/w2.bin"),read_file(d+"/w3.bin")};
    constexpr std::array<std::uint32_t,4> wa={0x080222a0u,0x080224a0u,0x080226a0u,0x080228a0u};
    pk4_assets a{};
    a.pitch=pitch.data(); a.chromatic=chrom.data(); a.envelope1=e1.data(); a.envelope2=e2.data();
    a.m1_wave=m1.data(); a.m1_wave_address=0x080310e0u;
    for(unsigned i=0;i<4;i++){a.waves[i].address=wa[i];a.waves[i].table=w[i].data();}

    constexpr std::array<unsigned,4> splits={0,1,7,15};
    std::uint64_t transitions=0, samples=0;
    for(unsigned track=0;track<PK4_TRACK_COUNT;++track) {
      for(unsigned old_algo=0;old_algo<PK4_ALGO_COUNT;++old_algo) {
        for(unsigned new_algo=0;new_algo<PK4_ALGO_COUNT;++new_algo) {
          for(unsigned old_mode=0;old_mode<3;++old_mode) {
            for(unsigned new_mode=0;new_mode<3;++new_mode) {
              for(unsigned split:splits) {
                pk4_engine got{}, ref{}; pk4_init(&got,&a); pk4_init(&ref,&a);
                const std::uint8_t old_src[6]={
                    (std::uint8_t)((17+track*11+old_algo*7)&127),
                    (std::uint8_t)((53+old_mode*19+track)&127),
                    (std::uint8_t)((91+old_algo*13)&127),
                    (std::uint8_t)((31+old_mode*23)&127),
                    (std::uint8_t)old_mode,(std::uint8_t)old_algo};
                const std::uint8_t new_src[6]={
                    (std::uint8_t)((109+track*5+new_algo*3)&127),
                    (std::uint8_t)((7+new_mode*37+track*9)&127),
                    (std::uint8_t)((65+new_algo*29)&127),
                    (std::uint8_t)((121+new_mode*11)&127),
                    (std::uint8_t)new_mode,(std::uint8_t)new_algo};
                std::array<std::int16_t,16> warm_g{},warm_r{};
                if(!pk4_process_segment(&got,track,old_src,1,1,255,45,warm_g.data(),16)) return 10;
                if(!pk4_process_segment(&ref,track,old_src,1,1,255,45,warm_r.data(),16)) return 11;
                if(warm_g!=warm_r||std::memcmp(&got,&ref,sizeof(got))) return 12;

                std::array<std::int16_t,16> pre_g{},pre_r{},post_g{},post_r{};
                if(!pk4_process_segment(&got,track,new_src,0,1,1,96,pre_g.data(),split)) return 20;
                if(!pk4_render(&ref,track,pre_r.data(),split)) return 21;
                if(pre_g!=pre_r||std::memcmp(&got,&ref,sizeof(got))) {
                    std::cerr<<"pre-event mutation track="<<track<<" old="<<old_algo<<" new="<<new_algo<<" split="<<split<<"\n";
                    return 22;
                }

                const unsigned remain=16-split;
                if(!pk4_process_segment(&got,track,new_src,1,1,96,57,post_g.data(),remain)) return 30;
                if(!pk4_prepare_event(&ref,track,new_src[0],new_src[1],new_src[2],new_src[3],new_src[4],new_src[5],96,57,1)) return 31;
                if(!pk4_render(&ref,track,post_r.data(),remain)) return 32;
                if(post_g!=post_r||std::memcmp(&got,&ref,sizeof(got))) {
                    std::cerr<<"post-event mismatch track="<<track<<" old="<<old_algo<<" new="<<new_algo<<" split="<<split<<"\n";
                    return 33;
                }
                if(got.tracks[track].active_algo!=new_algo||got.tracks[track].active_mode!=new_mode) return 34;
                ++transitions; samples+=16;
              }
            }
          }
        }
      }
    }
    std::cout << "PERKY split-frame p-lock timing: PASS " << transitions
              << " transitions / " << samples << " samples; pre-event keeps old Algo/state; "
                 "post-event applies Algo+Mode+Decay+Tune+Param1+Param2 at the split\n";
    return 0;
}
