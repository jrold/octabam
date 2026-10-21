// Persistent DSP instance: every request enters the actual source-DMA parser.
#include "dsp56kEmu/dsp.h"
#include "dsp56kEmu/memory.h"
#include "dsp56kEmu/peripherals.h"
#include <fstream>
#include <sstream>
#include <vector>
#include <map>
#include <iostream>
#include "dsp56kBase/logging.h"
using namespace dsp56k;
class Allow:public IMemoryValidator{bool memValidateAccess(EMemArea,TWord,bool)const override{return true;}};
int main(int argc,char**argv)try{
 Logging::setLogFunc([](const std::string&s){if(s.find("ERROR")!=std::string::npos)throw std::runtime_error(s);});
 std::map<std::string,std::string>a;for(int i=1;i+1<argc;i+=2)a[argv[i]]=argv[i+1];
 Allow allow;Memory mem(allow,0x80000,0x800000,0x200000);Peripherals56362 px;Peripherals56367 py;DSP dsp(mem,&px,&py);
 std::ifstream code(a.at("-code"),std::ios::binary);std::vector<unsigned char>b{std::istreambuf_iterator<char>(code),{}};
 for(unsigned i=0;i<b.size()/3;i++)mem.set(MemArea_P,i,b[3*i]|(b[3*i+1]<<8)|(b[3*i+2]<<16));
 std::ifstream data(a.at("-data"));std::string line;
 while(getline(data,line)){std::istringstream f(line);std::string sp,s;if(!(f>>sp>>s))continue;unsigned at=std::stoul(s,nullptr,16);while(f>>s)mem.set(sp=="Y"?MemArea_Y:MemArea_X,at++,std::stoul(s,nullptr,16));}
 unsigned entry=std::stoul(a.at("-entry"),nullptr,16);
 mem.set(MemArea_P,0x5000,0x0bf080);mem.set(MemArea_P,0x5001,entry);mem.set(MemArea_P,0x5002,0x0af080);mem.set(MemArea_P,0x5003,0x5002);
 std::ifstream requests(a.at("-requests"));std::ofstream out(a.at("-out"),std::ios::binary);std::string request;unsigned request_number=0;
 while(getline(requests,request)){request_number++;
   std::istringstream packet(request);unsigned v,i=0;std::vector<unsigned>values;
   while(packet>>std::hex>>v){mem.set(MemArea_X,0x80+i,v|(((i*17+3+request_number*13)%256)<<16));values.push_back(v);i++;}
   const bool primitive=a.count("-kind")&&a.at("-kind")=="arithmetic";
   if(primitive){if(values.size()!=7)throw std::runtime_error("arithmetic request length");
    unsigned input=values[0];if(input&0x8000)input|=0xff0000;
    mem.set(MemArea_X,0x3980,input);mem.set(MemArea_X,0x39b0,1);mem.set(MemArea_X,0x39ba,0x3980);mem.set(MemArea_X,0x39bc,values[1]);mem.set(MemArea_X,0x39b2,0x80);mem.set(MemArea_X,0x39b8,0);
    for(unsigned j=0;j<5;j++)mem.set(MemArea_X,0x80+j,values[2+j]|0xa50000);
   }
   mem.set(MemArea_X,0x209,0x80);mem.set(MemArea_X,0x418,0x20);
   for(unsigned i=0;i<8;i++)dsp.regs().m[i].var=0xffffff;
   dsp.regs().sp.var=0;dsp.regs().sc.var=0;dsp.regs().sr.var=0;dsp.setPC(0x5000);uint64_t cycles=0;bool done=false;
   for(unsigned step=0;step<2000000;step++){
     auto pc=dsp.getPC().toWord();
     if(pc==(primitive?0x5002:0x426)){done=true;break;}auto ic=dsp.getInstructionCounter();auto cost=dsp.calcOpcodeCycles(pc);dsp.execInterpreter();cycles+=cost*(dsp.getInstructionCounter()-ic);
   }
   if(!done)throw std::runtime_error("resident source did not return");
   out.write((char*)&cycles,8);
   for(unsigned i=0;i<16;i++){int32_t v=mem.get(MemArea_X,(primitive?0x3980:0)+2*i);if(v&0x800000)v|=0xff000000;out.write((char*)&v,4);}
   for(unsigned i=0;i<24;i++){uint16_t v=mem.get(MemArea_X,0x39f0+i);out.write((char*)&v,2);}
   for(unsigned i=0;i<180;i++){uint16_t v=mem.get(MemArea_X,0x3800+i);out.write((char*)&v,2);}
   for(unsigned i=0;i<6;i++){uint16_t v=mem.get(MemArea_X,0x3970+i);out.write((char*)&v,2);}
   for(unsigned i=0;i<3;i++){uint32_t v=mem.get(MemArea_X,0x3a23+i);out.write((char*)&v,4);}
   if(dsp.regs().sp.var!=0)throw std::runtime_error("source seam leaked return stack");
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
