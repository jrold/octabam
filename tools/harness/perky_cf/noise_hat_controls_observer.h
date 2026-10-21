#pragma once
namespace noise_hat_exact {
struct Observer:nht_control_base::Observer {
 using Control=void(*)(uint8_t*,uint32_t*,uint8_t*,const uint8_t*,unsigned,unsigned,unsigned,int,const uint8_t*,const uint8_t*);
 Control control=nullptr;unsigned prepare=0,ret=0,call_sp=0,raw_at=0,ctl_at=0;
 std::vector<uint8_t>shadow,pitch,chromatic;uint32_t targets[4]{};uint8_t tail[6]{};
 uint64_t control_calls=0,control_errors=0;std::vector<std::string>control_examples;
 Observer(){if(!ref)return;control=(Control)dlsym(lib,"nhf_reference");if(!control)std::abort();prepare=std::strtoul(std::getenv("NHF_PREPARE"),nullptr,0);}
 template<class M>void step(M&m,unsigned pc){
  if(control){auto sp=m.getA7();
   if(ret&&pc==ret&&sp==call_sp+4){
    for(unsigned i=0;i<shadow.size();i++)if(uint8_t(m.peek32(raw_at+i)>>24)!=shadow[i]){control_errors++;if(control_examples.size()<8)control_examples.push_back(std::to_string(control_calls)+":"+std::to_string(i));}
    for(unsigned i=0;i<4;i++)if(m.peek32(ctl_at+4*i)!=targets[i])control_errors++;
    for(unsigned i=0;i<6;i++)if(uint8_t(m.peek32(ctl_at+16+i)>>24)!=tail[i])control_errors++;
    control_calls++;ret=0;
   }
   if(pc==prepare){
    ctl_at=m.peek32(sp+4);raw_at=m.peek32(sp+8);auto knobs=m.peek32(sp+12),a=m.peek32(sp+32);
    shadow.resize(0x2dd8);for(unsigned i=0;i<shadow.size();i++)shadow[i]=m.peek32(raw_at+i)>>24;
    for(unsigned i=0;i<4;i++)targets[i]=m.peek32(ctl_at+4*i);for(unsigned i=0;i<6;i++)tail[i]=m.peek32(ctl_at+16+i)>>24;
    if(pitch.empty()){pitch.resize(8192);chromatic.resize(24);auto p=m.peek32(a),c=m.peek32(a+4);for(unsigned i=0;i<pitch.size();i++)pitch[i]=m.peek32(p+i)>>24;for(unsigned i=0;i<chromatic.size();i++)chromatic[i]=m.peek32(c+i)>>24;}
    uint8_t raw[4];for(unsigned i=0;i<4;i++)raw[i]=m.peek32(knobs+i)>>24;
    control(shadow.data(),targets,tail,raw,m.peek32(sp+16),m.peek32(sp+20),m.peek32(sp+24),m.peek32(sp+28),pitch.data(),chromatic.data());
    ret=m.peek32(sp);call_sp=sp;
   }
  }
  nht_control_base::Observer::step(m,pc);
 }
 ~Observer(){if(ref)if(const char*p=std::getenv("NHR_EXACT_REPORT")){std::ofstream f(std::string(p)+".controls.json");f<<"{\"calls\":"<<control_calls<<",\"mismatches\":"<<control_errors<<",\"examples\":[";for(unsigned i=0;i<control_examples.size();i++)f<<(i?",":"")<<'"'<<control_examples[i]<<'"';f<<"]}\n";}}
};inline Observer observer;
}
