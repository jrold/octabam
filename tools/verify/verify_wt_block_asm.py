#!/usr/bin/env python3
"""Compare isolated actual ColdFire WT candidates with the PKFM15 renderer."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]
import generate_cf_final as gcc
import generate_wt_block_asm as candidate


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


DIRECT = '''
#include <stddef.h>
#include "cf_perky4.h"
uint8_t wt_direct_state[PK_CF_WT_STATE_BYTES];
int16_t wt_direct_pcm[80];
uint32_t wt_direct_n,wt_direct_status;
pk_cf_wt_tables wt_direct_tables;
const uint32_t wt_direct_offset=offsetof(pk4_track,wt);
void wt_direct_run(void){wt_direct_status=pk_cf_wt_render(wt_direct_state,wt_direct_pcm,wt_direct_n,&wt_direct_tables);}
'''

FREQUENCY_PROOF = '''
volatile uint32_t wt_frequency_proof[4096];
void wt_frequency_prove(void){
    pk_cf_render_math_context c=pk_cf_render_math_begin();
    for(uint32_t i=0;i<4096;i++)wt_frequency_proof[i]=wt_frequency_step(i);
    pk_cf_render_math_end(c);
}
'''

CASES = r'''
    unsigned factor_cases=0;
    if(t.symbols.count("wt_pe_factors"))for(unsigned pe=0;pe<65536;pe++){
      unsigned want=(((pe&8191)+8192)>>(13-(pe>>13)))-1;
      require(t.m.read8(t.at("wt_pe_factors")+(pe>>6))==want,"exhaustive envelope factor map");factor_cases++;
    }
    t.call("wt_frequency_prove");
    for(unsigned i=0;i<4096;i++){
      int32_t shifted=int32_t(i<<20),hi=int32_t((int64_t(shifted)*0x057619f1)>>32);
      require(t.m.read32(t.at("wt_frequency_proof")+4*i)==uint32_t((hi>>10)-(shifted>>31)),"exhaustive frequency step");
    }
    for(unsigned voice=0;voice<2;voice++)for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
      std::array<unsigned,4>a{9,9,8,5},m{0,0,0,0};m[voice]=mode;
      run("solo",1u<<voice,a,m,192,corner,false);run("solo",1u<<voice,a,m,192,corner,true);
    }
    for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
      std::array<unsigned,4>a{9,9,8,5},m{mode,(mode+1)%3,0,1};
      run("dual",3,a,m,256,corner,false);run("dual",3,a,m,256,corner,true);
      run("slap",7,a,m,256,corner,true);
    }
    // Full public-renderer boundary cases, independent native C oracle.
    using Render=int(*)(uint8_t*,int16_t*,uint32_t,const void*);
    Render original=native.get<Render>("pk_cf_wt_render");
    const uint8_t *tables[]={storage[0].data(),storage[2].data(),storage[3].data(),storage[11].data(),storage[12].data()};
    for(unsigned i=0;i<5;i++)t.m.write32(t.at("wt_direct_tables")+4*i,addresses[(unsigned[]){0,2,3,11,12}[i]]);
    auto base=t.bytes(t.at("placement_engine")+t.m.read32(t.at("wt_direct_offset")),336);
    uint32_t seed=0x691dcbb5,direct=0;
    auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
    const uint32_t phases[]={0,1,1048063,1048064,1048575,1048576,1048577,0x7fffffff,0x80000000,0xffffffff};
    for(unsigned c=0;c<1600;c++){
      auto state=base;
      auto w16=[&](unsigned at,uint32_t value){state[at]=uint8_t(value);state[at+1]=uint8_t(value>>8);};
      auto w32=[&](unsigned at,uint32_t value){for(unsigned k=0;k<4;k++)state[at+k]=uint8_t(value>>(8*k));};
      w32(0xf4,phases[c%10]);w16(0x112,rnd());w16(0x114,rnd());state[6]=uint8_t(rnd());state[0xb8]=c%11==0;
      w16(0xec,rnd());state[0x128]=c&1;
      for(unsigned at:{0x74u,0xc4u}){
        state[at]=c%7;state[at+1]=c%4;
        for(unsigned f:{4u,6u,7u,0x10u})state[at+f]=rnd()&1;
        w16(at+0x20,rnd());w16(at+0x22,rnd());w32(at+0xc,c%13==0?0xffffffff:rnd()&0x1fffff);
      }
      uint32_t wave=0x080327cc+4096*(c%48),second=0x080327cc+4096*((c*7)%48);
      w32(0x100,c%3?0x080222a0:wave);w32(0x108,second);
      w32(0x104,c%5==0?0x080222a1:wave);w32(0x10c,c%7==0?0x080327cd:second);
      if(c%17==0)w32(0x100,0x080222a1);
      if(c%19==0)w32(0x108,0x080327cd);
      int16_t pcm[80];for(unsigned k=0;k<80;k++)pcm[k]=int16_t(0x49a1+k);
      unsigned n=c%65;auto want=state;int status=original(want.data(),pcm,n,tables);
      for(unsigned k=0;k<336;k++)t.m.write8(t.at("wt_direct_state")+k,state[k]);
      for(unsigned k=0;k<80;k++)t.m.write16(t.at("wt_direct_pcm")+2*k,uint16_t(0x49a1+k));
      t.m.write32(t.at("wt_direct_n"),n);
      for(unsigned k=0;k<6;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k),0x12340000+k);
      for(unsigned k=0;k<5;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k),0x47010000+16*k);
      t.call("wt_direct_run");
      require(t.m.read32(t.at("wt_direct_status"))==unsigned(status),"direct status case "+std::to_string(c));
      require(t.bytes(t.at("wt_direct_state"),336)==want,"direct full state case "+std::to_string(c));
      for(unsigned k=0;k<80;k++)require(t.m.read16(t.at("wt_direct_pcm")+2*k)==uint16_t(pcm[k]),"direct PCM/guard case "+std::to_string(c)+" sample "+std::to_string(k));
      for(unsigned k=0;k<6;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k))==0x12340000+k,"WT D ABI");
      for(unsigned k=0;k<5;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k))==0x47010000+16*k,"WT A ABI");
      direct++;
    }
    std::ofstream extra(work+"/DIRECT.json");extra<<"{\"cases\":"<<direct<<",\"frequency_cases\":4096,\"factor_cases\":"<<factor_cases<<",\"fast_entries\":"<<t.fast_entries<<",\"status\":\"PASS_FULL_STATE_PCM_ABI\"}\n";
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'out/perky/hybrid/wt-block-asm')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'out/perky/hybrid/full-map-state-v4')
    parser.add_argument('--variants', nargs='+', default=['baseline', 'oscillator', 'factor', 'candidate'])
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    base = ROOT / 'out/perky/hybrid/cf-placement'
    source = args.baseline.resolve() / 'wavetable-native20.c'
    report = json.loads((base / 'BUILD.json').read_text())
    commands = []
    def run(command):
        command = list(map(str, command)); commands.append(command)
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    flags = [*gcc.FLAGS, '-ffunction-sections', '-fdata-sections', '-I', ROOT / 'modules/perky']
    wrapper = work / 'direct.c'; wrapper.write_text(DIRECT)
    run(['m68k-elf-gcc', *flags, '-c', wrapper, '-o', work / 'direct.o'])
    run(['m68k-elf-gcc', '-mcpu=54455', '-c', candidate.ASSEMBLY, '-o', work / 'oscillator.o'])
    runner_source = ROOT / 'tools/harness/perky_cf/placement_cf_runner.cpp'
    text = runner_source.read_text()
    text = text.replace('    Cost call(const std::string&s){', '    uint64_t fast_entries=0;\n    Cost call(const std::string&s){')
    text = text.replace('while(m.pcFast()!=end){require(++n',
                        'unsigned fast_pc=symbols.count("pk_cf_wt_oscillator_block")?at("pk_cf_wt_oscillator_block"):0xffffffff;while(m.pcFast()!=end){if(m.pcFast()==fast_pc)fast_entries++;require(++n')
    text = text.replace('compare(t,native,kind=="solo"||f==0||f+1==frames);', 'compare(t,native,true);')
    labels = r'\"algorithm_layouts\":81,\"mode_rows\":6'
    assert text.count(labels) == 1
    text = text.replace(labels, r'\"algorithm_layouts\":1,\"mode_rows\":3')
    first = text.index('    for(unsigned voice=0;voice<2;voice++)')
    last = text.index('    csv.close();', first)
    text = text[:first] + CASES + text[last:]
    runner = work / 'runner.cpp'; runner.write_text(text)
    command = next(c for c in report['commands'] if str(runner_source) in c)
    command = [str(runner) if c == str(runner_source) else c for c in command]
    command[command.index('-o') + 1] = str(work / 'runner')
    run(command)
    link = next(c for c in report['commands'] if '-nostdlib' in c)
    results = {}
    for variant in args.variants:
        assert variant in ('baseline', 'oscillator', 'factor', 'candidate')
        directory = work / variant; directory.mkdir(exist_ok=True)
        for name in ('assets', 'native.dylib'):
            target = directory / name
            if not target.exists(): target.symlink_to(base / name, target_is_directory=(base / name).is_dir())
        csource = directory / 'wavetable.c'
        csource.write_text(source.read_text() if variant == 'baseline' else candidate.transform_text(
            source.read_text(), oscillator=variant in ('oscillator', 'candidate'), factor=variant in ('factor', 'candidate')))
        csource.write_text(csource.read_text()+FREQUENCY_PROOF)
        run(['m68k-elf-gcc', *flags, '-c', csource, '-o', directory / 'wavetable.o'])
        command = [str(directory / 'wavetable.o') if c == str(base / 'cf_wavetable.o') else c for c in link]
        command[command.index('-o') + 1] = str(directory / 'target.elf')
        command += [str(work / 'direct.o')] + ['-Wl,--undefined=' + n for n in
                    ('wt_direct_state', 'wt_direct_pcm', 'wt_direct_n', 'wt_direct_status', 'wt_direct_tables', 'wt_direct_offset', 'wt_direct_run', 'wt_frequency_proof', 'wt_frequency_prove')]
        if variant in ('oscillator', 'candidate'): command += [str(work / 'oscillator.o')]
        run(command)
        run(['m68k-elf-objcopy', '-O', 'binary', directory / 'target.elf', directory / 'target.bin'])
        (directory / 'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm', '-S', str(directory / 'target.elf')]))
        (directory / 'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump', '-d', str(directory / 'target.elf')]))
        with (directory / 'execute.log').open('w') as log:
            subprocess.run([str(work / 'runner'), str(directory), str(directory / 'assets')], check=True,
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        groups = {}
        for row in csv.DictReader((directory / 'costs.csv').open()):
            key = row['kind'] + '-' + row['mask'] + '-' + row['modes']
            groups.setdefault(key, []).append(int(row['cycles']))
        results[variant] = dict(execution=json.loads((directory / 'EXECUTION.json').read_text()),
                                direct=json.loads((directory / 'DIRECT.json').read_text()),
                                groups={k: dict(mean=sum(v) / len(v), max=max(v), blocks=len(v)) for k, v in groups.items()},
                                elf_sha256=sha(directory / 'target.elf'), source_sha256=sha(csource))
        (work / 'RESULT.json').write_text(json.dumps(dict(status='PARTIAL', results=results), indent=2) + '\n')
        print(variant, 'PASS', results[variant]['direct'], flush=True)
    paths = [Path(__file__), Path(candidate.__file__), candidate.ASSEMBLY, source, wrapper, runner, work / 'runner',
             base / 'native.dylib', *base.glob('*.o'), *sorted((base / 'assets').glob('*.bin'))]
    result = dict(status='PASS_ACTUAL_WT_PCM_FULL_STATE_RNG_CLOCK_AND_ABI', results=results,
                  scenario_count=63, layout='WT/WT with optional Slap; solo/dual/combined masks',
                  control_corners=[0,64,127], all_layout_qualification=False,
                  source_sha256={str(path): sha(path) for path in paths}, commands=commands,
                  limits=['Isolated combined synthesis includes native conversion and packing; stock ISR, DMA and scheduling remain separate.'])
    (work / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
