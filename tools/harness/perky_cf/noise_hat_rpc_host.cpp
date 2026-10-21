// Real HDI08 request/response and interrupt preservation gate for the opt-in
// Noise Hat service. Host-side word delivery is untimed; the integrated CF
// workload separately measures the physical register protocol and waits.
#include "dsp56kEmu/dsp.h"
#include "dsp56kEmu/memory.h"
#include "dsp56kEmu/peripherals.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <map>
#include <vector>
#include <cstdlib>
using namespace dsp56k;
class Allow : public IMemoryValidator {public:bool memValidateAccess(EMemArea,TWord,bool)const override{return true;}};
static void require(bool b,const char*s){if(!b)throw std::runtime_error(s);}
int main(int argc,char**argv)try{
    std::map<std::string,std::string>a;for(int i=1;i+1<argc;i+=2)a[argv[i]]=argv[i+1];
    Allow allow;Memory mem(allow,0x80000,0x800000,0x200000);Peripherals56362 px;Peripherals56367 py;DSP dsp(mem,&px,&py);
    std::ifstream code(a.at("-code"),std::ios::binary);std::vector<unsigned char>b{std::istreambuf_iterator<char>(code),{}};
    require(!b.empty()&&b.size()%3==0,"bad code");
    for(size_t i=0;i<b.size()/3;i++)mem.set(MemArea_P,i,b[3*i]|(b[3*i+1]<<8)|(b[3*i+2]<<16));
    std::ifstream data(a.at("-data"));std::string line;
    while(getline(data,line)){std::istringstream f(line);std::string sp,s;if(!(f>>sp>>s))continue;unsigned ad=std::stoul(s,nullptr,16);
        while(f>>s)mem.set(sp=="X"?MemArea_X:sp=="Y"?MemArea_Y:MemArea_P,ad++,std::stoul(s,nullptr,16));}
    constexpr TWord state=0x3800,side=0x3970,countAt=0x39b0,modeAt=0x39b1,idle=0x5000;
    unsigned mode=mem.get(MemArea_X,modeAt),n=mem.get(MemArea_X,countAt);
    unsigned first=mode==1?81:0,count=mode==0?81:mode==1?28:59;
    const bool hadPending=(n%2)!=0;const TWord pendingWord=0x8070;
    std::vector<TWord>request{mode,n,TWord(hadPending),hadPending?pendingWord:0},response;
    for(unsigned i=0;i<count;i++)request.push_back(mem.get(MemArea_X,state+first+i));
    for(unsigned i=0;i<6;i++)request.push_back(mem.get(MemArea_X,side+i));
    // Poison the service's receive destination: only the real port can fill it.
    for(unsigned i=0;i<count;i++)mem.set(MemArea_X,state+first+i,0xdead);
    mem.set(MemArea_P,0x2c,0x0bf080);mem.set(MemArea_P,0x2d,std::stoul(a.at("-entry"),nullptr,16));
    mem.set(MemArea_P,idle,0x0af080);mem.set(MemArea_P,idle+1,idle);dsp.setPC(idle);
    auto&r=dsp.regs();r.a.var=0x12fedcba98765400ll;r.b.var=int64_t(0xfe123456abcdef00ull);r.x.var=0xfedcba654321;r.y.var=0x13579b2468ac;
    r.sr.var=0x40;r.la.var=0x1234;r.lc.var=0x34;
    for(unsigned i=0;i<8;i++){r.r[i].var=0x700+i;r.n[i].var=0x20+i;r.m[i].var=i%2?0xffffff:0x7f;}
    auto witness=[&](){std::vector<int64_t>v{r.a.var,r.b.var,r.x.var,r.y.var,r.sr.var,r.omr.var,r.la.var,r.lc.var,r.sp.var};
        for(unsigned i=0;i<8;i++){v.push_back(r.r[i].var);v.push_back(r.n[i].var);v.push_back(r.m[i].var);}return v;};
    auto before=witness();auto&h=px.getHDI08();h.setTransmitDataAlwaysEmpty(false);h.writePortControlRegister(64);h.writeControlRegister(0);h.writeStatusRegister(2);
    dsp.setHostStepped(true);dsp.injectInterrupt(0x2c);size_t sent=0;bool entered=false,finished=false;uint64_t cycles=0;
    const bool serviceClock=!std::getenv("PK_NHA_IRQ_CLOCK")||std::string(std::getenv("PK_NHA_IRQ_CLOCK"))!="0";
    for(unsigned step=0;step<2000000;step++){
        if(serviceClock&&dsp.getProcessingMode()==DSP::LongInterrupt)dsp.getExecPeripheralsFunc()(&dsp);
        if(sent<request.size()&&!h.hasRXData()){auto v=request[sent++];h.writeRX(&v,1);}
        while(h.hasTX()&&response.size()<count+6+n+2)response.push_back(h.readTX());
        auto pc=dsp.getPC().toWord();if(!response.empty()||pc!=idle)entered=true;
        if(entered&&pc==idle){finished=true;break;}
        const auto instructions=dsp.getInstructionCounter();auto cost=dsp.calcOpcodeCycles(pc);dsp.execInterpreter();
        cycles+=cost*(dsp.getInstructionCounter()-instructions);if(r.sr.var&0x8000)dsp.doLoopEnd();
    }
    if(!finished)std::cerr<<"wire stalled pc="<<std::hex<<dsp.getPC().toWord()<<" sent="<<std::dec<<sent<<" response="<<response.size()<<"\n";
    require(finished&&sent==request.size(),"wire/IRQ did not return");
    auto after=witness();if(before!=after)for(size_t i=0;i<before.size();i++)if(before[i]!=after[i])std::cerr<<"register "<<i<<" "<<std::hex<<before[i]<<" -> "<<after[i]<<"\n";
    if(before!=after)std::cerr<<"saved A0="<<std::hex<<mem.get(MemArea_X,0x39c2)<<" B0="<<mem.get(MemArea_X,0x39c5)<<"\n";
    require(before==after,"interrupted DSP register state changed");
    require(response.size()==count+6+n+2,"response length");
    require(response.front()==(0x4e4800|(mode<<5)|n)&&response.back()==0x4e4844,"response framing");
    require(h.hasTX()==hadPending,"pending stock word ownership");
    if(hadPending)require(h.readTX()==pendingWord,"pending stock word changed");
    for(unsigned i=0;i<count;i++)require(mem.get(MemArea_X,state+first+i)==response[1+i],"wire state mismatch");
    std::ofstream out(a.at("-out"),std::ios::binary);
    for(unsigned i=0;i<n;i++){int32_t sample=int32_t(response[1+count+6+i]<<8)>>8;out.write((char*)&sample,4);out.write((char*)&sample,4);}
    std::ofstream dump(a.at("-state"));unsigned base=std::stoul(a.at("-statebase"),nullptr,16),words=std::stoul(a.at("-state-words"));
    for(auto area:{MemArea_X,MemArea_Y})for(unsigned i=0;i<words;i++)dump<<std::hex<<mem.get(area,base+i)<<' ';dump<<'\n';
    std::ofstream(a.at("-meter"))<<cycles<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
