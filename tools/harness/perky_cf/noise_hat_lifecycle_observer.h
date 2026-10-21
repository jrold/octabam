#pragma once
/* Host-only witness: the transport oracle stops at the first live backend
 * departure. CF arithmetic is checked separately from complete pre-call
 * target bytes; that stateless check cannot certify state migration. */
namespace noise_hat_exact {
struct Observer:nhl_control_base::Observer {
 using Native=int(*)(const uint8_t*,unsigned,unsigned,const nht_lifecycle_base::Tables*,const nht_lifecycle_base::RNG*,const uint16_t*,int16_t*);
 Native native=nullptr;
 unsigned enabled=0,render=0,engine=0,assets=0,layout=0;
 unsigned native_ret=0,native_sp=0,native_at=0;
 std::vector<int16_t>native_expected;
 uint64_t cf_calls=0,cf_samples=0,cf_errors=0,toggles=0;
 unsigned last_enabled=1;bool departed=false;
 std::vector<std::string>cf_examples;
 Observer(){if(!ref)return;
  auto env=[](const char*n){return unsigned(std::strtoul(std::getenv(n),nullptr,0));};
  enabled=env("NHL_ENABLED");render=env("NHL_RENDER");engine=env("NHL_ENGINE");assets=env("NHL_ASSETS");layout=env("NHL_LAYOUT");
  native=(Native)dlsym(lib,"nhl_native_reference");if(!native)std::abort();
 }
 template<class M>void step(M&m,unsigned pc){
  if(!ref)return;auto sp=m.getA7();
  if(native_ret&&pc==native_ret&&sp==native_sp+4){
   for(unsigned i=0;i<native_expected.size();i++){
    int16_t got=m.peek32(native_at+2*i)>>16;
    if(got!=native_expected[i]){cf_errors++;if(cf_examples.size()<16)cf_examples.push_back(std::to_string(cf_calls)+":"+std::to_string(i)+":"+std::to_string(got)+"/"+std::to_string(native_expected[i]));}
   }
   native_ret=0;
  }
  if(pc==submit){
   unsigned on=m.peek32(enabled)!=0;
   if(on!=last_enabled){toggles++;last_enabled=on;if(!on&&seq)departed=true;}
   lifecycle_allow=on&&!departed;
  }
  if(pc==render&&m.peek32(sp+4)==engine&&m.peek32(sp+8)==3&&!m.peek32(enabled)){
   using Layout=const unsigned*(*)();auto offsets=((Layout)dlsym(lib,"nhl_offsets"))();
   if(m.peek32(layout)!=offsets[0]||m.peek32(layout+40)!=offsets[3]||m.peek32(layout+44)!=offsets[4])std::abort();
   unsigned tr=engine+3*offsets[0];
   if((m.peek32(tr+offsets[3])>>24)==5){
    unsigned mode=m.peek32(tr+offsets[4])>>24;mode=mode==0?1:mode==1?0:2;
    unsigned raw=tr+offsets[1]+(mode==2?0x2c98:0),n=m.peek32(sp+16);
    std::vector<uint8_t>control(mode==2?0x160:0x2dd8);for(unsigned i=0;i<control.size();i++)control[i]=m.peek32(raw+i)>>24;
    if(curve[0].empty())for(unsigned j=0;j<2;j++){curve[j].resize(2050);unsigned at=m.peek32(assets+8+4*j);for(unsigned i=0;i<2050;i++)curve[j][i]=m.peek32(at+i)>>24;}
    nht_lifecycle_base::Tables tables{curve[0].data(),curve[1].data()};
    nht_lifecycle_base::RNG rng{m.peek32(tr+offsets[2]),m.peek32(tr+offsets[2]+4)};
    unsigned hold_at=engine+m.peek32(layout+48);
    uint16_t hold[]{uint16_t(m.peek32(hold_at)>>16),uint16_t(m.peek32(hold_at+2)>>16)};
    native_expected.resize(n);if(!native(control.data(),n,mode,&tables,&rng,hold,native_expected.data()))std::abort();
    native_sp=sp;native_ret=m.peek32(sp);native_at=m.peek32(sp+12);cf_calls++;cf_samples+=n;
   }
  }
  nhl_control_base::Observer::step(m,pc);
 }
 ~Observer(){if(ref)if(const char*p=std::getenv("NHR_EXACT_REPORT")){std::ofstream f(std::string(p)+".lifecycle.json");f<<"{\"backend_transitions\":"<<toggles<<",\"dynamic_oracle_stopped_at_departure\":"<<(departed?"true":"false")<<",\"CF_native_calls\":"<<cf_calls<<",\"CF_native_samples\":"<<cf_samples<<",\"CF_native_mismatches\":"<<cf_errors<<",\"CF_native_scope\":\"stateless original renderer from full target pre-call state; no migration/clock claim\",\"examples\":[";for(unsigned i=0;i<cf_examples.size();i++)f<<(i?",":"")<<'"'<<cf_examples[i]<<'"';f<<"]}\n";}}
};inline Observer observer;
}
