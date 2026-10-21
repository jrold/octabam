// Read-only register/stack witness around the actual live DSP host interrupt.
#pragma once
#include <cstdlib>
#include <fstream>
#include <vector>
#include <sstream>
#include <map>
#include <array>
namespace nha_irq_audit {
struct Audit {
    bool active=false; uint64_t calls=0,checked=0,changes=0,writes=0;
    uint32_t resume=0;std::vector<uint64_t> before;std::vector<std::string> details,write_details;
    std::map<unsigned,uint64_t> pages;unsigned max_sp=0;
    std::map<unsigned,std::array<uint64_t,6>> audio_rows;
    std::map<unsigned,uint64_t> inits;
    std::map<unsigned,std::vector<unsigned>> amp_states;
    bool enabled=std::getenv("NHA_IRQ_AUDIT")!=nullptr;
    template<class D,class M> void audio(D&d,M&m,unsigned core,unsigned pc){
        if(!enabled)return;
        unsigned stage=pc==(core?0x221:0x426)?1:pc==(core?0x2cc:0x4d7)?2:pc==(core?0x303:0x50e)?3:pc==(core?0x2cd:0x4d8)?4:0;
        if(pc==(core?0x2c2:0x4cd)||pc==(core?0x2f8:0x503))inits[100*core+10*(m.get(dsp56k::MemArea_X,0x418)/32)+unsigned(pc==(core?0x2f8:0x503))]++;
        if(!stage)return;
        unsigned pos=m.get(dsp56k::MemArea_X,0x418)/32;if(pos>3)return;
        if(stage==1){auto&v=amp_states[core*100+pos*10];v.clear();
            unsigned at=m.get(dsp56k::MemArea_X,0x20a),record=m.get(dsp56k::MemArea_X,0x419);
            v.push_back(at);v.push_back(record);
            for(unsigned j=0;j<32;j++)v.push_back(m.get(dsp56k::MemArea_X,at+j));
            for(unsigned j=0;j<32;j++)v.push_back(m.get(dsp56k::MemArea_X,record+j));}
        auto&v=audio_rows[100*core+10*pos+stage];v[0]++;
        for(unsigned i=0;i<32;i++){int32_t s=int32_t(m.get(dsp56k::MemArea_X,i)<<8)>>8;if(std::abs(s)>64)v[1]++;}
        v[2]=m.get(dsp56k::MemArea_X,0x20c);v[3]=m.get(dsp56k::MemArea_X,0x20d);
        v[4]=d.regs().r[2].var;v[5]=d.regs().r[1].var;
    }
    template<class D> static std::vector<uint64_t> regs(D&d){
        auto&r=d.regs();std::vector<uint64_t>v;
        v.push_back(r.a.var);v.push_back(r.b.var);v.push_back(r.x.var);v.push_back(r.y.var);
        v.push_back(d.getSR().var);v.push_back(r.omr.var);v.push_back(r.la.var);v.push_back(r.lc.var);
        v.push_back(r.sp.var);v.push_back(r.sc.var);v.push_back(r.pc.var);
        for(unsigned i=0;i<8;i++){v.push_back(r.r[i].var);v.push_back(r.n[i].var);v.push_back(r.m[i].var);}
        for(unsigned i=0;i<16;i++)v.push_back(r.ss[i].var);
        return v;
    }
    template<class D> void enter(D&d){if(!std::getenv("NHA_IRQ_AUDIT"))return;before=regs(d);resume=d.getPC().toWord();active=true;++calls;}
    template<class D> void after(D&d){
        if(!active||d.getProcessingMode()==dsp56k::DSP::LongInterrupt)return;
        auto now=regs(d);++checked;active=false;
        // Popped stack entries above SP are scratch. Compare all active words.
        for(size_t i=0;i<before.size();i++){
            if(i>=35 && (i==35 || i>35+(before[8]&15)))continue;
            if(now[i]!=before[i]){
            ++changes;if(details.size()<32){std::ostringstream s;s<<"resume="<<std::hex<<resume<<" reg="<<std::dec<<i<<" "<<std::hex<<before[i]<<" -> "<<now[i];details.push_back(s.str());}
            }
        }
    }
    template<class D> void write(D&d,unsigned area,unsigned off,unsigned value){
        if(!active)return;
        max_sp=std::max(max_sp,unsigned(d.regs().sp.var&15));
        if(area==1&&off>=0x3800&&off<0x3a68)return;
        pages[(area<<24)|(off>>8)]++;
        ++writes;if(write_details.size()<8){std::ostringstream s;s<<"write pc="<<std::hex<<d.getPcCurrentInstruction()<<" area="<<area<<" at="<<off<<" value="<<value;write_details.push_back(s.str());}
    }
    ~Audit(){if(const char*p=std::getenv("NHA_IRQ_AUDIT")){std::ofstream f(p);f<<"{\"calls\":"<<calls<<",\"checked\":"<<checked<<",\"register_changes\":"<<changes<<",\"outside_writes\":"<<writes<<",\"max_sp\":"<<max_sp<<",\"details\":[";for(unsigned i=0;i<details.size();i++)f<<(i?",":"")<<'"'<<details[i]<<'"';f<<"],\"write_examples\":[";for(unsigned i=0;i<write_details.size();i++)f<<(i?",":"")<<'"'<<write_details[i]<<'"';f<<"],\"write_pages\":{";bool comma=false;for(auto&v:pages){f<<(comma?",":"")<<'"'<<v.first<<"\":"<<v.second;comma=true;}f<<"},\"audio_stages\":{";comma=false;for(auto&v:audio_rows){f<<(comma?",":"")<<'"'<<v.first<<"\":[";for(unsigned j=0;j<v.second.size();j++)f<<(j?",":"")<<v.second[j];f<<']';comma=true;}f<<"},\"init_calls\":{";comma=false;for(auto&v:inits){f<<(comma?",":"")<<'"'<<v.first<<"\":"<<v.second;comma=true;}f<<"},\"amp_states\":{";comma=false;for(auto&v:amp_states){f<<(comma?",":"")<<'"'<<v.first<<"\":[";for(unsigned j=0;j<v.second.size();j++)f<<(j?",":"")<<v.second[j];f<<']';comma=true;}f<<"}}\n";}}
};inline Audit audit;
}
