// The builder inlines the native-state witness here without its global instance.
#include "noise_hat_resident_observer.h"
#include <algorithm>
namespace noise_hat_exact {
struct FullObserver:nhr_inner_base::Observer {
    using FullRef=Ref;
    FullRef full_ref=nullptr;
    struct FullFrame{std::array<int32_t,16>pcm{};unsigned filled=0;};
    std::map<unsigned,FullFrame>full_frames;
    unsigned split=0,stage=0,phase=0,have=0,output_addr=0,mail_addr=0;
    int16_t carry=0;uint32_t frame_sp=0,frame_ret=0;
    std::array<int32_t,16>wanted{};bool compare=false;
    uint64_t full_checked=0,full_mismatches=0,clock_mismatches=0;
    std::vector<std::string>examples;
    FullObserver(){
        if(!ref)return;
        full_ref=(FullRef)dlsym(lib,"pk_nhr_full_oracle");if(!full_ref)std::abort();
        output_addr=std::strtoul(std::getenv("NHR_OUTPUT"),nullptr,0);
        mail_addr=std::strtoul(std::getenv("NHR_MAIL"),nullptr,0);
    }
    template<class M>void step(M&m,uint32_t pc){
        if(!ref)return;
        auto sp=m.getA7();
        if(frame_ret&&pc==frame_ret&&sp==frame_sp+4){
            if(compare){for(unsigned i=0;i<16;i++){
                int32_t got=int32_t(m.peek32(output_addr+4*i));
                if(got!=wanted[i]){full_mismatches++;if(examples.size()<8)examples.push_back(std::to_string(i)+":"+std::to_string(got)+"/"+std::to_string(wanted[i]));}}
                full_checked++;}
            frame_ret=0;compare=false;
        }
        nhr_inner_base::Observer::step(m,pc);
        if(pc==submit){split=m.peek32(sp+4);stage=split?0:1;frame_sp=sp;frame_ret=m.peek32(sp);full_frames[next.seq]=FullFrame{};return;}
        if(pc==accept){
            unsigned seq=m.peek32(mail_addr+2)>>16;
            auto found=full_frames.find(seq);
            if(found==full_frames.end()||found->second.filled!=16){clock_mismatches++;return;}
            wanted=found->second.pcm;compare=true;
            while(full_frames.size()>8)full_frames.erase(full_frames.begin());return;
        }
        if(pc!=entry)return;
        unsigned raw=m.peek32(sp+4),n=m.peek32(sp+8),mode=m.peek32(sp+12),tp=m.peek32(sp+16),rp=m.peek32(sp+20),hp=m.peek32(sp+24);
        int init=m.peek32(sp+28),trig=m.peek32(sp+32);
        std::vector<uint8_t>control(mode==2?0x160:0x2dd8);for(unsigned i=0;i<control.size();i++)control[i]=m.peek32(raw+i)>>24;
        nhr_inner_base::Tables tables{curve[0].data(),curve[1].data()};
        nhr_inner_base::RNG rng{m.peek32(rp),m.peek32(rp+4)};
        uint16_t hold[]{uint16_t(m.peek32(hp)>>16),uint16_t(m.peek32(hp+2)>>16)},state[127]{};
        std::vector<int16_t>native(n);
        if(!full_ref(control.data(),n,mode,&tables,&rng,hold,init,trig,native.data(),state))std::abort();
        unsigned outn=stage?16-split:split;stage++;
        if(trig){phase=0;have=0;carry=0;}
        // Rational position oracle: output k reads floor((phase+160*k)/147).
        unsigned end=phase+160*outn,needed=end/147+(end%147>=13)-have;
        if(needed!=n)clock_mismatches++;
        std::vector<int16_t>data;if(have)data.push_back(carry);data.insert(data.end(),native.begin(),native.end());
        unsigned at=0;auto&f=full_frames[next.seq];
        for(unsigned k=0;k<outn;k++){
            if(at>=data.size()||(phase&&at+1>=data.size())){clock_mismatches++;break;}
            int32_t a=data[at],b=phase?data[at+1]:a;
            int64_t product=int64_t(b-a)*32*phase;
            int32_t delta=product<0?-int32_t((-product+146)/147):int32_t(product/147);
            if(f.filled<16)f.pcm[f.filled++]=a*32+delta;else clock_mismatches++;
            unsigned position=phase+160;at+=position/147;phase=position%147;
        }
        have=phase>=13;carry=have&&at<data.size()?data[at]:0;
    }
    ~FullObserver(){if(const char*p=std::getenv("NHR_EXACT_REPORT")){
        std::ofstream f(std::string(p)+".full.json");f<<"{\"checked_frames\":"<<full_checked<<",\"source_PCM_mismatches\":"<<full_mismatches<<",\"clock_mismatches\":"<<clock_mismatches<<",\"examples\":[";
        for(unsigned i=0;i<examples.size();i++)f<<(i?",":"")<<'"'<<examples[i]<<'"';f<<"]}\n";}}
};inline FullObserver observer;
}
