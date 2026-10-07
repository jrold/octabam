// Capture the original v1.2.1 control/trigger/render paths for every panel family.
// External source/firmware only; output RAM and PCM are local qualification inputs.
#include "EngineCatalog.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <vector>

static void save(const std::filesystem::path& p,const void* data,std::size_t n){std::ofstream f(p,std::ios::binary);f.write(static_cast<const char*>(data),n);if(!f)throw std::runtime_error("write "+p.string());}

static void saveRng(PerkonsM7& cpu,const std::filesystem::path& file,std::string& error){
 std::uint32_t manager=0,address=0,state[2]={};
 if(!cpu.readMemory(0x20000024u,&manager,sizeof(manager),error)||!cpu.readMemory(manager+0x30u,&address,sizeof(address),error))throw std::runtime_error(error);
 if(address && !cpu.readMemory(address+0x10u,state,sizeof(state),error))throw std::runtime_error(error);
 save(file,state,sizeof(state));
}

static void saveNoiseHatHold(PerkonsM7& cpu,const std::filesystem::path& file,std::string& error){
 std::uint8_t state[4]={};
 if(!cpu.readMemory(0x20007594u,state,sizeof(state),error))throw std::runtime_error(error);
 save(file,state,sizeof(state));
}

int main(int argc,char**argv){
 if(argc!=3)return 2;
 FirmwareImage fw;std::string error;
 if(!fw.load(argv[1],error)){std::cerr<<error;return 3;}
 std::filesystem::path out=argv[2];std::filesystem::create_directories(out);
 std::ofstream meta(out/"cases.tsv");meta<<"engine\tmode\tcorner\tname\twrapper_address\tcontrol_values\n";
 constexpr std::uint32_t wrappers[]={0x20000280,0x200006d4,0x20003930,0x20000b58};
 constexpr unsigned noiseHatIndex=9;
 constexpr std::array<std::array<std::uint16_t,4>,3> corners={{{0,0,0,0},{2048,2048,2048,2048},{4095,4095,4095,4095}}};
 for(unsigned i=0;i<kPerkyEngines.size();++i)for(unsigned mode=0;mode<3;++mode)for(unsigned corner=0;corner<3;++corner){
  PerkonsM7 cpu;PerkonsVoices v(cpu);const auto& e=kPerkyEngines[i];
  if(!cpu.load(fw,error)||!v.initialise(fw,error)||!v.setAlgorithm(e.slot,e.panelAlgorithm,error)||!v.setMode(e.slot,e.panelModeToFirmware[mode],error)||!v.setSoundParameters(e.slot,corners[corner],error)||!v.trigger(e.slot,error)){std::cerr<<error;return 4;}
  v.setNativeDspEnabledForTesting(false);
  std::ostringstream tag;tag<<"engine-"<<i+1<<"-mode-"<<mode+1<<"-corner-"<<corner;
  auto dir=out/tag.str();std::filesystem::create_directories(dir);
  std::vector<std::uint8_t> ram(0x6000);
  auto address=wrappers[static_cast<unsigned>(e.slot)];
  if(!cpu.readMemory(address,ram.data(),ram.size(),error)){std::cerr<<error;return 5;}
  save(dir/"wrapper-window-before.bin",ram.data(),ram.size());
  std::int16_t pcm[256];
  if(!v.renderInto(e.slot,pcm,256,error)){std::cerr<<error;return 6;}
  save(dir/"arm-pcm.bin",pcm,sizeof(pcm));
  if(!cpu.readMemory(address,ram.data(),ram.size(),error)){std::cerr<<error;return 7;}
  save(dir/"wrapper-window-after.bin",ram.data(),ram.size());
  // The original ARM block has now initialized any lazy random object.
  // Capture a second block with explicit RNG inputs for DSP parity.
  if(i==noiseHatIndex)saveNoiseHatHold(cpu,dir/"noise-hat-hold-continuation-before.bin",error);
  saveRng(cpu,dir/"rng-continuation-before.bin",error);
  if(!v.renderInto(e.slot,pcm,256,error)){std::cerr<<error;return 8;}
  save(dir/"arm-pcm-continuation.bin",pcm,sizeof(pcm));
  if(!cpu.readMemory(address,ram.data(),ram.size(),error)){std::cerr<<error;return 9;}
  save(dir/"wrapper-window-continuation-after.bin",ram.data(),ram.size());
  if(i==noiseHatIndex)saveNoiseHatHold(cpu,dir/"noise-hat-hold-continuation-after.bin",error);
  saveRng(cpu,dir/"rng-continuation-after.bin",error);
  meta<<i+1<<'\t'<<mode+1<<'\t'<<corner<<'\t'<<e.name<<'\t'<<std::hex<<address<<std::dec<<'\t';for(auto x:corners[corner])meta<<x<<',';meta<<'\n';
 }
 std::cout<<"Original ARM family captures: PASS (12 families x 3 panel modes x 3 control corners; triggered pre/post RAM windows and 256 PCM samples)\n";
}
