#!/usr/bin/env python3
"""Actual complete stock mixer block versus exact fixed-pair implementation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


MAIN=r'''
int main(int argc,char**argv){
 require(argc==3,"work image");std::string w=argv[1];HybridPredictor::selftest();
 Target original(w,argv[2],false),control(w,argv[2],false),candidate(w,argv[2],true);
 uint32_t seed=0xc28e761b;auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
 const unsigned modes[]={0,0x20,0x40,0x60,0x80,0xa0,0xb0,0xc0};const int offsets[]={-64,-4,0,2,4,16,64,0x8000};
 std::ofstream csv(w+"/costs.csv");csv<<"case,mode,alias,original,candidate,saved\n";int64_t saved=0;unsigned samples=0;
 for(unsigned c=0;c<4096;c++){
  unsigned mode=modes[(c/32)%8];int offset=offsets[(c/8)%8];uint32_t regs[16],emac[8];for(auto&v:regs)v=rnd();for(auto&v:emac)v=rnd();emac[0]=mode|(rnd()&0xf00);emac[1]=rnd()&0xffff;
  if(c%4==0){regs[0]=0;regs[1]=0;}if(c%4==1){regs[0]=0xffffffff;regs[1]=0xffffffff;}if(c%4==2){regs[0]=0x80000000;regs[1]=0x80000000;}
  regs[8]=c%3==0?0x47000100:0x47004000;regs[10]=c%5==0?0x47000100+offset:0x47006000;regs[11]=0x47000100;regs[12]=0x47000100+offset;regs[13]=c%7==0?regs[12]:0x47008000;regs[15]=0x47100000;
  if(c%3==0)regs[7]=0x80000012;uint16_t sr=0x2700|(rnd()&31);std::vector<uint32_t> memory(0x10000/4);for(auto&v:memory)v=rnd();
  if(c%11==0)for(auto&v:memory)v=0;if(c%11==1)for(auto&v:memory)v=0x80000000;if(c%11==2)for(auto&v:memory)v=0x7fffffff;
  std::array<uint32_t,17> expected{};Bytes expected_memory,expected_emac;uint64_t cycles[3];Target*targets[]={&original,&control,&candidate};
  for(unsigned which=0;which<3;which++){
   auto&t=*targets[which];t.predictor.load();for(unsigned i=0;i<memory.size();i++)t.m.write32(0x47000000+4*i,memory[i]);for(unsigned i=0;i<8;i++)t.m.write32(0x47030000+4*i,emac[i]);t.call("seed_emac");
   m68k_set_reg(t.m.getCpuState(),M68K_REG_SR,sr);for(unsigned i=0;i<16;i++)m68k_set_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i),regs[i]);cycles[which]=t.run(0x4000cbfa,0x4000cc62);
   std::array<uint32_t,17> actual{};for(unsigned i=0;i<16;i++)actual[i]=m68k_get_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i));actual[16]=m68k_get_reg(t.m.getCpuState(),M68K_REG_SR);
   auto data=t.bytes(0x47000000,0x10000);t.call("read_emac");auto mac=t.bytes(0x47030100,32);t.predictor.save();
   if(!which){expected=actual;expected_memory=data;expected_emac=mac;}else{
    if(actual!=expected)for(unsigned i=0;i<17;i++)if(actual[i]!=expected[i])std::cerr<<"reg "<<i<<" got "<<std::hex<<actual[i]<<" expected "<<expected[i]<<std::dec<<'\n';
    require(actual==expected,"register/full CCR mismatch case "+std::to_string(c));require(data==expected_memory,"complete aliased source/destination/gain/unused memory mismatch case "+std::to_string(c));require(mac==expected_emac,"full raw EMAC mismatch case "+std::to_string(c));
   }
  }
  require(cycles[0]==cycles[1],"same-image independent predictor cycle mismatch");int64_t delta=int64_t(cycles[0])-int64_t(cycles[2]);csv<<c<<','<<mode<<','<<offset<<','<<cycles[0]<<','<<cycles[2]<<','<<delta<<'\n';if(c>=2048&&mode==0xb0){saved+=delta;samples++;}
 }
 original.alignment.finish(w+"/original-alignment.json");control.alignment.finish(w+"/control-alignment.json");candidate.alignment.finish(w+"/candidate-alignment.json");
 std::ofstream result(w+"/EXECUTION.json");result<<"{\"status\":\"PASS_ACTUAL_COMPLETE_STOCK_MIX_BLOCK_REGS_CCR_EMAC_ALL_MEMORY\",\"cases\":4096,\"same_image_cycle_controls\":true,\"mean_saved_cycles\":"<<double(saved)/samples<<",\"steady_stock_mode_samples\":"<<samples<<"}\n";std::cout<<"PASS4096cases\n";
}
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/stock-source-block-v1');parser.add_argument('--image',type=Path,default=ROOT/'out/perky/hybrid/full-map-packet-reserve-v2/probe/mainos_PKFM17.bin');args=parser.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    genpath=ROOT/'tools/perky/generate_stock_source_mix_block.py';gen=module('stock_source_block_generator',genpath);generated=gen.generate(work)
    prior=module('stock_source_loop_proof',ROOT/'tools/verify/verify_stock_source_mix_unroll.py');emac=module('stock_emac_proof',ROOT/'tools/verify/verify_stock_envelope_fusion.py')
    image=args.image.resolve();blob=image.read_bytes();assert blob[gen.SITE['address']-gen.BASE:gen.SITE['end']-gen.BASE]==gen.expected_span()
    commands=[]
    def run(command):
        command=list(map(str,command));commands.append(command);subprocess.run(command,cwd=ROOT,check=True)
    seed=work/'seed.s';seed.write_text(emac.SEED.replace('pk_stock_envelope_fusion','pk_stock_source_mix_block'))
    run(['m68k-elf-gcc','-mcpu=54455','-c',generated['path'],'-o',work/'kernel.o']);run(['m68k-elf-gcc','-mcpu=54455','-c',seed,'-o',work/'seed.o']);run(['m68k-elf-gcc','-mcpu=54455','-nostdlib','-Ttext=0x45000000',work/'kernel.o',work/'seed.o','-o',work/'kernel.elf']);run(['m68k-elf-objcopy','-O','binary',work/'kernel.elf',work/'kernel.bin'])
    for suffix,tool,flags in [('nm','m68k-elf-nm',['-n']),('dis','m68k-elf-objdump',['-d'])]:(work/f'kernel.{suffix}').write_bytes(subprocess.check_output([tool,*flags,str(work/'kernel.elf')]))
    # Reuse only the isolated target loader/runner; all test cases and complete
    # block entry/continuation are specified here. Refuse template drift.
    runner_text=prior.RUNNER.split('int main(int argc,char**argv)')[0]
    for old,new in [('for(unsigned i=0;i<12;i++)m.write8(0x4000cc02+i','for(unsigned i=0;i<8;i++)m.write8(0x4000cbfa+i'),('unsigned body=patched?symbols.at("pk_stock_source_mix_fallback_body"):0x4000cc02;','unsigned body=0;')]:
        assert runner_text.count(old)==1,old;runner_text=runner_text.replace(old,new)
    runner=work/'runner.cpp';runner.write_text(runner_text+MAIN);build=json.loads((ROOT/'out/perky/hybrid/cf-placement/BUILD.json').read_text());oldsource=str(ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp');command=next(c for c in build['commands'] if oldsource in c);command=[str(runner) if v==oldsource else v for v in command];command[command.index('-o')+1]=str(work/'runner');run(command);run([work/'runner',work,image])
    result=json.loads((work/'EXECUTION.json').read_text());result['mean_saved_us_per_block']=result['mean_saved_cycles']/264
    paths=[Path(__file__),genpath,Path(prior.__file__),Path(emac.__file__),seed,runner,work/'runner',work/'kernel.elf',image,ROOT/'tools/emu/ot_emu/v4e.cpp',ROOT/'tools/harness/perky_cf/hybrid_cf_predictor.hpp']
    result.update(source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},commands=commands,generator=generated,limits=['Actual complete fixed stock mixer block with a separately linked helper. Full-image workload/lifecycle admission remains required.','Cycle savings use the unchanged local model with independent same-image predictor controls; no hardware claim.'])
    (work/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
