#!/usr/bin/env python3
"""Actual CF packet helpers: aliased memory, ABI, raw MAC and paired costs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky')]
import generate_cf_publish_unrolled as generator


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


MAIN = r'''
int main(int argc,char**argv){
 require(argc==3,"work image");std::string w=argv[1];HybridPredictor::selftest();
 Target original(w,argv[2],false),control(w,argv[2],false),candidate(w,argv[2],false);
 uint32_t seed=0x719df246;auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
 const unsigned modes[]={0,0x20,0x40,0x60,0x80,0xa0,0xb0,0xc0};
 const int alias[]={-128,-16,-4,0,4,16,64,128,512};
 std::ofstream csv(w+"/costs.csv");csv<<"kind,case,count,alias,original,candidate,saved\n";
 int64_t savings[2]={};unsigned samples[2]={},cases=0;
 for(unsigned kind=0;kind<2;kind++)for(unsigned c=0;c<4096;c++){
  unsigned n=kind?c%257:c%17;int offset=alias[(c/17)%9];
  uint32_t regs[16],emac[8];for(auto&v:regs)v=rnd();for(auto&v:emac)v=rnd();
  emac[0]=modes[c%8]|(rnd()&0xf00);emac[1]=rnd()&0xffff;
  regs[15]=0x47100000;unsigned dst=0x47000800+(c%2)*2,src=dst+offset;
  std::vector<uint32_t> memory(0x2000/4);for(auto&v:memory)v=rnd();
  if(c%11==0)for(auto&v:memory)v=0;if(c%11==1)for(auto&v:memory)v=0x80000000;if(c%11==2)for(auto&v:memory)v=0x7fffffff;
  Bytes expected_data,expected_mac;uint32_t expected_return=0;uint64_t cycles[3];
  Target*targets[]={&original,&control,&candidate};
  for(unsigned which=0;which<3;which++){
   auto&t=*targets[which];t.predictor.load();for(unsigned i=0;i<memory.size();i++)t.m.write32(0x47000000+4*i,memory[i]);
   for(unsigned i=0;i<8;i++)t.m.write32(0x47030000+4*i,emac[i]);t.call("seed_emac");
   m68k_set_reg(t.m.getCpuState(),M68K_REG_SR,0x2500|(rnd()&31));
   for(unsigned i=0;i<16;i++)m68k_set_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i),regs[i]);
   t.m.write32(regs[15],0x47200000);t.m.write32(regs[15]+4,dst);
   t.m.write32(regs[15]+8,kind?n:src);t.m.write32(regs[15]+12,n);
   const char*name=kind?(which==2?"pk_prod_clear":"reference_clear"):(which==2?"pk_prod_pack":"reference_pack");
   cycles[which]=t.run(t.symbols.at(name),0x47200000);
   for(unsigned i=2;i<8;i++)require(m68k_get_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i))==regs[i],"D ABI");
   for(unsigned i=10;i<15;i++)require(m68k_get_reg(t.m.getCpuState(),m68k_register_t(M68K_REG_D0+i))==regs[i],"A ABI");
   require(m68k_get_reg(t.m.getCpuState(),M68K_REG_SP)==regs[15]+4,"stack ABI");
   require((m68k_get_reg(t.m.getCpuState(),M68K_REG_SR)&0xffe0)==0x2500,"SR mask changed");
   auto data=t.bytes(0x47000000,0x2000);auto result=m68k_get_reg(t.m.getCpuState(),M68K_REG_D0);
   t.call("read_emac");auto mac=t.bytes(0x47030100,32);t.predictor.save();
   if(!which){expected_data=data;expected_mac=mac;expected_return=result;}
   else{require(data==expected_data,"complete aliased memory/guards case"+std::to_string(c));require(mac==expected_mac,"raw MAC/mask mismatch");if(kind)require(result==expected_return&&result==dst+4*n,"clear return");}
  }
  require(cycles[0]==cycles[1],"same-image cycle mismatch");int64_t delta=int64_t(cycles[0])-int64_t(cycles[2]);
  csv<<kind<<','<<c<<','<<n<<','<<offset<<','<<cycles[0]<<','<<cycles[2]<<','<<delta<<'\n';cases++;
  if(c>=2048&&(!kind||(n>=4&&n<=36&&!(n&1)))){savings[kind]+=delta;samples[kind]++;}
 }
 original.alignment.finish(w+"/original-alignment.json");control.alignment.finish(w+"/control-alignment.json");candidate.alignment.finish(w+"/candidate-alignment.json");
 std::ofstream result(w+"/EXECUTION.json");result<<"{\"status\":\"PASS_EXACT_PACKET_PUBLISH_CLEAR_MEMORY_MAC_ABI\",\"cases\":"<<cases<<",\"same_image_cycle_controls\":true,\"mean_saved_pack_cycles\":"<<double(savings[0])/samples[0]<<",\"mean_saved_clear_cycles\":"<<double(savings[1])/samples[1]<<"}\n";
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, default=ROOT / 'out/perky/hybrid/stock-cf-optimization/publish-unrolled')
    parser.add_argument('--image', type=Path, default=ROOT / 'out/perky/hybrid/full-map-remaining-cf-mix-v1/probe/mainos_PKFM20.bin')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = generator.generate(work)
    template = module('packet_mac_template', ROOT / 'tools/verify/verify_stock_envelope_fusion.py')
    original = ROOT / 'modules/perky/production_publish.s'
    reference = work / 'reference.s'
    reference.write_text(original.read_text().replace('pk_prod_pack', 'reference_pack').replace('pk_prod_clear', 'reference_clear'))
    seed = work / 'seed.s'
    seed.write_text(template.SEED.split('.globl entry_patch')[0])
    commands = []

    def run(command):
        command = list(map(str, command))
        commands.append(command)
        subprocess.run(command, cwd=ROOT, check=True)

    for path, name in ((source, 'candidate'), (reference, 'reference'), (seed, 'seed')):
        run(['m68k-elf-gcc', '-mcpu=54455', '-c', path, '-o', work / (name + '.o')])
    run(['m68k-elf-gcc', '-mcpu=54455', '-nostdlib', '-Ttext=0x45000000',
         *[work / (name + '.o') for name in ('candidate', 'reference', 'seed')], '-o', work / 'kernel.elf'])
    run(['m68k-elf-objcopy', '-O', 'binary', work / 'kernel.elf', work / 'kernel.bin'])
    for suffix, tool, flags in (('nm', 'm68k-elf-nm', ['-n']), ('dis', 'm68k-elf-objdump', ['-d'])):
        (work / ('kernel.' + suffix)).write_bytes(subprocess.check_output([tool, *flags, str(work / 'kernel.elf')]))
    prefix = template.RUNNER.split('int main(int argc,char**argv)')[0]
    old = '  if(patch)for(unsigned i=0;i<12;i++)m.write8(0x400984d2+i,m.read8(symbols.at("entry_patch")+i));\n'
    assert prefix.count(old) == 1
    runner = work / 'runner.cpp'
    runner.write_text(prefix.replace(old, '') + MAIN)
    manifest = json.loads((ROOT / 'out/perky/hybrid/cf-placement/BUILD.json').read_text())
    old_source = str(ROOT / 'tools/harness/perky_cf/placement_cf_runner.cpp')
    command = next(c for c in manifest['commands'] if old_source in c)
    command = [str(runner) if value == old_source else value for value in command]
    command[command.index('-o') + 1] = str(work / 'runner')
    run(command)
    run([work / 'runner', work, args.image.resolve()])
    result = json.loads((work / 'EXECUTION.json').read_text())
    paths = [Path(__file__).resolve(), Path(generator.__file__), Path(template.__file__), original,
             source, reference, seed, runner, work / 'runner', work / 'kernel.elf', work / 'kernel.bin', work / 'kernel.nm', args.image.resolve(),
             ROOT / 'tools/emu/ot_emu/v4e.cpp', ROOT / 'tools/harness/perky_cf/hybrid_cf_predictor.hpp']
    result.update(source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  commands=commands, scope='Exact standalone packet memory/order and C ABI; final actual-image admission separately required.')
    (work / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], result['cases'], result['mean_saved_pack_cycles'], result['mean_saved_clear_cycles'])


if __name__ == '__main__':
    main()
