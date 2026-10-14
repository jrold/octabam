#ifndef OCTABAM_HYBRID_CF_SHADOW_RUNNER_HPP
#define OCTABAM_HYBRID_CF_SHADOW_RUNNER_HPP
#include "hybrid_cf_shadow.h"
#include "machine.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/* Streaming digest retains a bounded receipt for every byte compared. Exact
 * memcmp-style comparison below, not hash equality, is the correctness gate. */
class HybridSha256 {
    std::array<uint32_t,8> state{{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
        0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}};
    std::array<uint8_t,64> block{};
    uint64_t bytes=0;
    unsigned used=0;
    static uint32_t rotate(uint32_t value,unsigned bits) {
        return (value>>bits)|(value<<(32-bits));
    }
    void transform() {
        static const uint32_t k[64]={
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        uint32_t w[64];
        for(unsigned i=0;i<16;i++)w[i]=(uint32_t(block[4*i])<<24)|(uint32_t(block[4*i+1])<<16)|(uint32_t(block[4*i+2])<<8)|block[4*i+3];
        for(unsigned i=16;i<64;i++) {
            const auto s0=rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3);
            const auto s1=rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10);
            w[i]=w[i-16]+s0+w[i-7]+s1;
        }
        uint32_t a=state[0],b=state[1],c=state[2],d=state[3],e=state[4],f=state[5],g=state[6],h=state[7];
        for(unsigned i=0;i<64;i++) {
            const auto s1=rotate(e,6)^rotate(e,11)^rotate(e,25);
            const auto t1=h+s1+((e&f)^((~e)&g))+k[i]+w[i];
            const auto s0=rotate(a,2)^rotate(a,13)^rotate(a,22);
            const auto t2=s0+((a&b)^(a&c)^(b&c));
            h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        state[0]+=a;state[1]+=b;state[2]+=c;state[3]+=d;
        state[4]+=e;state[5]+=f;state[6]+=g;state[7]+=h;
    }
public:
    void add(const uint8_t *data,size_t count) {
        bytes+=count;
        while(count--) {block[used++]=*data++;if(used==64){transform();used=0;}}
    }
    std::string finish() const {
        auto copy=*this;
        const uint64_t bits=copy.bytes*8;
        const uint8_t mark=0x80,zero=0;
        copy.add(&mark,1);
        while(copy.used!=56)copy.add(&zero,1);
        uint8_t length[8];for(unsigned i=0;i<8;i++)length[i]=uint8_t(bits>>(56-8*i));
        copy.add(length,8);
        std::ostringstream result;result<<std::hex<<std::setfill('0');
        for(auto word:copy.state)result<<std::setw(8)<<word;
        return result.str();
    }
};

class HybridShadow {
    ot::Machine &machine;
    const std::map<std::string,uint32_t> &symbols;
    std::string directory;
    std::array<uint32_t,HYB_LAYOUT_WORDS> layout{};
    std::array<std::vector<uint8_t>,13> asset_storage;
    std::array<uint64_t,3> checks{};
    uint64_t compared_bytes=0;
    HybridSha256 target_digest,native_digest;
    uint32_t symbol(const char *name) const { return symbols.at(name); }
    static void append32(std::vector<uint8_t> &out,uint32_t value) {
        for(unsigned byte=0;byte<4;byte++)out.push_back(uint8_t(value>>(8*byte)));
    }
    void appendMemory(std::vector<uint8_t> &out,uint32_t address,unsigned count) {
        for(unsigned i=0;i<count;i++)out.push_back(machine.read8(address+i));
    }
    std::vector<uint8_t> targetSnapshot() {
        std::vector<uint8_t> out;
        for(unsigned i=0;i<2;i++) {
            const auto base=symbol("voices")+i*layout[HYB_VOICE_SIZE];
            appendMemory(out,base+layout[HYB_WT_OFFSET],2*layout[HYB_WT_BYTES]);
            appendMemory(out,base+layout[HYB_SNARE_OFFSET],layout[HYB_SNARE_BYTES]);
            appendMemory(out,base+layout[HYB_BASS_OFFSET],layout[HYB_BASS_BYTES]);
            appendMemory(out,base+layout[HYB_NT_OFFSET],layout[HYB_NT_BYTES]);
            for(unsigned control=0;control<layout[HYB_CONTROL_COUNT];control++) {
                const auto address=base+layout[HYB_CONTROL_OFFSET]+control*layout[HYB_CONTROL_SIZE];
                for(unsigned k=0;k<4;k++)append32(out,machine.read32(address+layout[HYB_TARGETS_OFFSET]+4*k));
                appendMemory(out,address+layout[HYB_RAW_OFFSET],4);
                out.push_back(machine.read8(address+layout[HYB_MODE_OFFSET]));
                out.push_back(machine.read8(address+layout[HYB_VALID_OFFSET]));
            }
            append32(out,machine.read32(base+layout[HYB_RNG_LOW_OFFSET]));
            append32(out,machine.read32(base+layout[HYB_RNG_HIGH_OFFSET]));
        }
        for(unsigned i=0;i<32;i++) {
            const auto value=machine.read16(symbol("output")+2*i);
            out.push_back(uint8_t(value));out.push_back(uint8_t(value>>8));
        }
        append32(out,machine.read32(symbol("status")));
        return out;
    }
public:
    HybridShadow(ot::Machine &m,const std::map<std::string,uint32_t> &s,
                 const std::string &assets,const std::string &out)
        :machine(m),symbols(s),directory(out) {
        HybridSha256 test;
        const std::string abc="abc";test.add(reinterpret_cast<const uint8_t *>(abc.data()),abc.size());
        if(test.finish()!="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
            throw std::runtime_error("shadow digest self-test");
        const std::string long_vector="abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
        HybridSha256 longer;longer.add(reinterpret_cast<const uint8_t *>(long_vector.data()),long_vector.size());
        if(longer.finish()!="248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1")
            throw std::runtime_error("shadow multi-block digest self-test");
        for(unsigned i=0;i<layout.size();i++)layout[i]=machine.read32(symbol("bench_layout")+4*i);
        if(layout[HYB_LAYOUT_MAGIC]!=0x48594231 || layout[HYB_CONTROL_COUNT]!=3 ||
           layout[HYB_VOICE_SIZE]>8192 || layout[HYB_WT_BYTES]!=0x150 ||
           layout[HYB_SNARE_BYTES]!=0x1d4 || layout[HYB_BASS_BYTES]!=0x1d4 ||
           layout[HYB_NT_BYTES]!=0x120)
            throw std::runtime_error("unexpected compiler-emitted target layout");
        const char *names[]={"pitch","chromatic","envelope1","envelope2","w0","w1","w2","w3","m1","interp_a","interp_b","wt_base","wt_bank"};
        const uint8_t *pointers[13];
        for(unsigned i=0;i<13;i++) {
            std::ifstream input(assets+"/"+names[i]+".bin",std::ios::binary);
            if(!input)throw std::runtime_error("shadow asset absent");
            asset_storage[i]={std::istreambuf_iterator<char>(input),{}};
            pointers[i]=asset_storage[i].data();
        }
        hybrid_shadow_bind(pointers);

    }
    void check(const std::string &phase) {
        const unsigned action=phase=="init"?HYB_INIT:
            phase.rfind("prepare-",0)==0?HYB_PREPARE:
            (phase=="render"||phase=="tail-render"||phase=="clean-render")?HYB_RENDER:3;
        if(action>HYB_RENDER)throw std::runtime_error("unknown shadow phase "+phase);
        uint32_t inputs[14];
        for(unsigned i=0;i<2;i++) {
            inputs[i]=machine.read32(symbol("profile")+4*i);
            inputs[2+i]=machine.read32(symbol("modes")+4*i);
            for(unsigned k=0;k<4;k++)inputs[4+4*i+k]=machine.read32(symbol("knobs")+16*i+4*k);
            inputs[12+i]=machine.read32(symbol("triggers")+4*i);
        }
        hybrid_shadow_step(action,inputs);
        auto target=targetSnapshot();
        std::vector<uint8_t> native(hybrid_shadow_snapshot(nullptr,0));
        if(hybrid_shadow_snapshot(native.data(),native.size())!=native.size()||native.size()!=target.size())
            throw std::runtime_error("shadow canonical size disagreement");
        const auto mismatch=std::mismatch(target.begin(),target.end(),native.begin()).first;
        if(mismatch!=target.end()) {
            const auto index=unsigned(mismatch-target.begin());
            std::ofstream report(directory+"/shadow-mismatch.json");
            report<<"{\"phase\":\""<<phase<<"\",\"snapshot_index\":"<<(checks[0]+checks[1]+checks[2])
                  <<",\"byte_offset\":"<<index<<",\"target_byte\":"<<unsigned(target[index])
                  <<",\"native_byte\":"<<unsigned(native[index])<<"}\n";
            const unsigned begin=index>32?index-32:0,end=std::min(unsigned(target.size()),index+33);
            for(const auto &entry:{std::make_pair("target",&target),std::make_pair("native",&native)}) {
                std::ofstream bytes(directory+"/shadow-mismatch-"+entry.first+".bin",std::ios::binary);
                bytes.write(reinterpret_cast<const char *>(entry.second->data()+begin),end-begin);
            }
            throw std::runtime_error("target/native state or PCM mismatch in "+phase+" byte "+std::to_string(index));
        }
        const uint8_t tag=uint8_t(action);
        target_digest.add(&tag,1);target_digest.add(target.data(),target.size());
        native_digest.add(&tag,1);native_digest.add(native.data(),native.size());
        compared_bytes+=target.size();++checks[action];
    }
    void finish(uint64_t expected_init,uint64_t expected_prepare,uint64_t expected_render) {
        if(checks!=std::array<uint64_t,3>{{expected_init,expected_prepare,expected_render}})
            throw std::runtime_error("incomplete target/native shadow coverage");
        std::ofstream report(directory+"/shadow-result.json");
        report<<"{\"status\":\"PASS_EXACT_TARGET_NATIVE\",\"init_checks\":"<<checks[0]
              <<",\"prepare_checks\":"<<checks[1]<<",\"render_checks\":"<<checks[2]
              <<",\"compared_bytes\":"<<compared_bytes<<",\"byte_mismatches\":0"
              <<",\"target_stream_sha256\":\""<<target_digest.finish()
              <<"\",\"native_stream_sha256\":\""<<native_digest.finish()
              <<"\",\"stream_encoding\":\"action u8 then all five state byte arrays, each control field, RNG, PCM and status; numeric fields LE; ABI padding excluded\"}\n";
    }
};
#endif
