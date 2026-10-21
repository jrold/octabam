// Persistent DSP instance: every request enters the actual source-DMA parser.
#include "dsp56kEmu/dsp.h"
#include "dsp56kEmu/memory.h"
#include "dsp56kEmu/peripherals.h"
#include <fstream>
#include <sstream>
#include <vector>
#include <map>
#include <iostream>
using namespace dsp56k;
class Allow:public IMemoryValidator{bool memValidateAccess(EMemArea,TWord,bool)const override{return true;}};
int main(int argc,char**argv)try{
 std::map<std::string,std::string>a;for(int i=1;i+1<argc;i+=2)a[argv[i]]=argv[i+1];
 Allow allow;Memory mem(allow,0x80000,0x800000,0x200000);Peripherals56362 px;Peripherals56367 py;DSP dsp(mem,&px,&py);
 std::ifstream code(a.at("-code"),std::ios::binary);std::vector<unsigned char>b{std::istreambuf_iterator<char>(code),{}};
 for(unsigned i=0;i<b.size()/3;i++)mem.set(MemArea_P,i,b[3*i]|(b[3*i+1]<<8)|(b[3*i+2]<<16));
 std::ifstream data(a.at("-data"));std::string line;
 while(getline(data,line)){std::istringstream f(line);std::string sp,s;if(!(f>>sp>>s))continue;unsigned at=std::stoul(s,nullptr,16);while(f>>s)mem.set(sp=="Y"?MemArea_Y:MemArea_X,at++,std::stoul(s,nullptr,16));}
 unsigned entry=std::stoul(a.at("-entry"),nullptr,16);
 mem.set(MemArea_P,0x5000,0x0bf080);mem.set(MemArea_P,0x5001,entry);mem.set(MemArea_P,0x5002,0x0af080);mem.set(MemArea_P,0x5003,0x5002);
 std::ifstream requests(a.at("-requests"));std::ofstream out(a.at("-out"),std::ios::binary);unsigned n,mode,seq=0;
 while(requests>>n>>mode){
   unsigned velocity=mode==0?0x3801:mode==1?0x3851:0x3879;
   std::vector<unsigned>packet{0x4e52,++seq,0,0,n|(mode<<5),1,velocity,mem.get(MemArea_X,velocity)};
   for(unsigned i=0;i<packet.size();i++)mem.set(MemArea_X,0x80+80+i,packet[i]|((i*17+3)%256<<16));
   mem.set(MemArea_X,0x209,0x80);mem.set(MemArea_X,0x418,0x20);
   for(unsigned i=0;i<8;i++)dsp.regs().m[i].var=0xffffff;
   dsp.regs().sp.var=0;dsp.regs().sc.var=0;dsp.regs().sr.var=0;dsp.setPC(0x5000);uint64_t cycles=0;bool done=false;
   for(unsigned step=0;step<2000000;step++){
     auto pc=dsp.getPC().toWord();if(pc==0x5002){done=true;break;}auto ic=dsp.getInstructionCounter();auto cost=dsp.calcOpcodeCycles(pc);dsp.execInterpreter();cycles+=cost*(dsp.getInstructionCounter()-ic);
   }
   if(!done)throw std::runtime_error("resident source did not return");
   out.write((char*)&cycles,8);
   for(unsigned i=0;i<20;i++){uint16_t v=mem.get(MemArea_X,0x39f4+i);out.write((char*)&v,2);}
   for(unsigned i=0;i<180;i++){uint16_t v=mem.get(MemArea_X,0x3800+i);out.write((char*)&v,2);}
   for(unsigned i=0;i<6;i++){uint16_t v=mem.get(MemArea_X,0x3970+i);out.write((char*)&v,2);}
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
