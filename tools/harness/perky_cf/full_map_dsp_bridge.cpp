// Untimed direct qualification bridge. Whole-machine timing runs separately.
#include "dsp56kEmu/dsp.h"
#include "dsp56kEmu/memory.h"
#include "dsp56kEmu/peripherals.h"
#include "dsp56kBase/logging.h"
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
using namespace dsp56k;
class FMAllow:public IMemoryValidator{bool memValidateAccess(EMemArea,TWord,bool)const override{return true;}};
struct FMBridge{
 FMAllow allow;Memory mem;Peripherals56362 px;Peripherals56367 py;DSP dsp;
 FMBridge(const char*code,const char*data,unsigned entry):mem(allow,0x80000,0x800000,0x200000),dsp(mem,&px,&py){
  Logging::setLogFunc([](const std::string&s){if(s.find("ERROR")!=std::string::npos)throw std::runtime_error(s);});
  std::ifstream f(code,std::ios::binary);std::vector<unsigned char>b{std::istreambuf_iterator<char>(f),{}};
  for(unsigned i=0;i<b.size()/3;i++)mem.set(MemArea_P,i,b[3*i]|(b[3*i+1]<<8)|(b[3*i+2]<<16));
  std::ifstream d(data);std::string line;
  while(getline(d,line)){std::istringstream r(line);std::string s,v;if(!(r>>s>>v))continue;unsigned at=std::stoul(v,nullptr,16);while(r>>v)mem.set(s=="Y"?MemArea_Y:MemArea_X,at++,std::stoul(v,nullptr,16));}
  mem.set(MemArea_P,0x5000,0x0bf080);mem.set(MemArea_P,0x5001,entry);mem.set(MemArea_P,0x5002,0x0af080);mem.set(MemArea_P,0x5003,0x5002);
 }
 void step(const uint16_t*packet,unsigned length,int32_t*pcm,uint16_t*state,uint16_t*side,uint32_t*clock,uint16_t*mail){
  for(unsigned i=0;i<length;i++)mem.set(MemArea_X,0x80+i,packet[i]|(((i*17+3)%256)<<16));
  mem.set(MemArea_X,0x209,0x80);mem.set(MemArea_X,0x418,0x20);
  for(unsigned i=0;i<8;i++)dsp.regs().m[i].var=0xffffff;
  dsp.regs().sp.var=0;dsp.regs().sc.var=0;dsp.regs().sr.var=0;dsp.setPC(0x5000);bool done=false;
  for(unsigned i=0;i<2000000;i++){if(dsp.getPC().toWord()==0x426){done=true;break;}dsp.execInterpreter();}
  if(!done||dsp.regs().sp.var!=0)throw std::runtime_error("mixed source parser did not return");
  for(unsigned i=0;i<16;i++){unsigned v=mem.get(MemArea_X,2*i);pcm[i]=v&0x800000?v|0xff000000:v;}
  for(unsigned i=0;i<180;i++)state[i]=mem.get(MemArea_X,0x3800+i);
  for(unsigned i=0;i<6;i++)side[i]=mem.get(MemArea_X,0x3970+i);
  for(unsigned i=0;i<3;i++)clock[i]=mem.get(MemArea_X,0x3a23+i);
  for(unsigned i=0;i<24;i++)mail[i]=mem.get(MemArea_X,0x39f0+i);
 }
};
static std::string fm_error;
extern "C" void*fm_dsp_open(const char*c,const char*d,unsigned entry){try{return new FMBridge(c,d,entry);}catch(const std::exception&e){fm_error=e.what();return nullptr;}}
extern "C" int fm_dsp_step(void*p,const uint16_t*packet,unsigned n,int32_t*pcm,uint16_t*state,uint16_t*side,uint32_t*clock,uint16_t*mail){try{static_cast<FMBridge*>(p)->step(packet,n,pcm,state,side,clock,mail);return 1;}catch(const std::exception&e){fm_error=e.what();return 0;}}
extern "C" const char*fm_dsp_error(){return fm_error.c_str();}
extern "C" void fm_dsp_close(void*p){delete static_cast<FMBridge*>(p);}
