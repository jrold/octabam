#!/usr/bin/env python3
"""Compare remaining-synthesis candidates with actual PKFM17 C bodies.

This linked-CF development gate checks independent original native PCM,
canonical objects, RNG and rational clocks on every frame. Isolated CF costs
are candidates for complete-image measurement, not hardware admission.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'out/perky/hybrid/cf-placement'
PKFM17 = ROOT / 'out/perky/hybrid/full-map-packet-reserve-v2'
sys.path[:0] = [str(ROOT / 'tools/perky'), str(ROOT / 'modules/perky')]
import generate_cf_synthesis_remaining as candidate
import generate_cf_slap_envelope_cache as slap_candidate


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--slap-envelope', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((BASE / 'BUILD.json').read_text())
    actual = json.loads((PKFM17 / 'BUILD.json').read_text())
    assert actual['runtime_sha256'] == 'e16f1da5b17b55083ab7fa7f165efd4e6ec262ada259291d4927b2412921d6c9'
    flags = actual['compiler_flags']
    sources = {'resonant': ROOT / 'modules/perky/cf_resonant.c',
               'slap': PKFM17 / 'slap-rng-emac.c'}
    commands = []

    def run(command, name):
        command = list(map(str, command))
        commands.append(command)
        with (work / (name + '.log')).open('w') as log:
            subprocess.run(command, cwd=ROOT, stdout=log,
                           stderr=subprocess.STDOUT, check=True)

    original = ROOT / 'tools/harness/perky_cf/placement_cf_runner.cpp'
    text = original.read_text()
    text = '#include "cf_resonant.h"\n#include "cf_slap.h"\n' + text
    text = text.replace('compare(t,native,kind=="solo"||f==0||f+1==frames)',
                        'compare(t,native,true)')
    text = text.replace('        uint64_t begin=m.getCycles(),n=0;uint32_t low=sp;', '''
        for(unsigned k=0;k<6;k++)m68k_set_reg(m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k),0x12340000+k);
        for(unsigned k=0;k<5;k++)m68k_set_reg(m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k),0x47010000+16*k);
        uint64_t begin=m.getCycles(),n=0;uint32_t low=sp;''')
    text = text.replace('        require(m68k_get_reg(m.getCpuState(),M68K_REG_SP)==sp+4,"stack ABI");predictor.save();', '''
        for(unsigned k=0;k<6;k++)require(m68k_get_reg(m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k))==0x12340000+k,"D ABI");
        for(unsigned k=0;k<5;k++)require(m68k_get_reg(m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k))==0x47010000+16*k,"A ABI");
        require(m68k_get_reg(m.getCpuState(),M68K_REG_SP)==sp+4,"stack ABI");predictor.save();''')
    begin = text.index('    for(unsigned voice=0;voice<2;voice++)')
    end = text.index('    csv.close();', begin)
    text = text[:begin] + '''
    for(unsigned algorithm:{4u,8u})for(unsigned mode=0;mode<(algorithm==4?2u:3u);mode++)
      for(unsigned corner:{0u,64u,127u}){
        std::array<unsigned,4>a{9,9,algorithm,5},m{1,2,mode,1};
        run("held",4,a,m,96,corner,false);
        run("dense",4,a,m,96,corner,true);
        run("layout",15,a,m,32,corner,true);
      }
''' + text[end:]
    directed = '''
    uint32_t direct_checks=0,seed=0xa3b47f21;
    auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
    pk_cf_res_tables res_tables{storage[2].data(),storage[3].data(),storage[9].data(),storage[10].data()};
    pk_cf_fold_tables slap_tables{};slap_tables.pitch=storage[0].data();slap_tables.envelope1=storage[2].data();slap_tables.envelope2=storage[3].data();
    auto snare=native.get<decltype(&pk_cf_res_snare_render)>("pk_cf_res_snare_render");
    auto bass=native.get<decltype(&pk_cf_res_bass_render)>("pk_cf_res_bass_render");
    auto slap=native.get<decltype(&pk_cf_slap_render)>("pk_cf_slap_render");
    for(unsigned k=0;k<4;k++)t.m.write32(t.at("remaining_res_tables")+4*k,addresses[(unsigned[]){2,3,9,10}[k]]);
    for(unsigned k=0;k<3;k++)t.m.write32(t.at("remaining_slap_tables")+4*k,addresses[(unsigned[]){0,2,3}[k]]);
    const unsigned lengths[]={0,1,2,15,16,17,18,19,20,21,31,32,33,47,64};
    const uint32_t edges[]={0,1,15,16,17,19,20,21,32,64,0x7fffffff,0x80000000,0xffffffff};
    const unsigned mac_modes[]={0,0x20,0x40,0x60,0xb0,0xf0};
    for(unsigned kind=0;kind<3;kind++)for(unsigned c=0;c<96;c++){
      unsigned size=kind==0?PK_CF_RES_SNARE_STATE_BYTES:kind==1?PK_CF_RES_BASS_STATE_BYTES:PK_CF_SLAP_STATE_BYTES;
      Bytes object(size);for(auto&v:object)v=uint8_t(rnd());
      auto le=[&](unsigned at,uint32_t value,unsigned width){for(unsigned k=0;k<width;k++)object.at(at+k)=uint8_t(value>>(8*k));};
      object[0x74]=c%7;object[0x75]=c%4;
      for(unsigned at:{0x78u,0x7au,0x7bu,0x7cu,0x84u})object[at]=rnd()&1;
      le(0x80,edges[c%13],4);le(0x94,c%5?rnd()&65535:0,2);le(0x96,c%7?rnd()&65535:0,2);
      le(0x60,c%22,2);le(0x62,c%5,2);
      if(kind<2){
        const unsigned snare_maps[]={0x174,0x18c,0x1a4,0x1bc},bass_maps[]={0xf8,0x110,0x128,0x144};
        for(unsigned j=0;j<4;j++){
          unsigned at=kind==0?snare_maps[j]:bass_maps[j];
          le(at,c%4?4090+rnd()%8:rnd(),4);le(at+4,edges[(c+j)%13],4);
          le(at+8,edges[(c+2*j)%13],4);le(at+12,edges[(c+3*j)%13],4);
          le(at+16,edges[(c+4*j)%13],4);
        }
      }else{
        le(0x266a,c%4805,2);
        for(unsigned j=0;j<5;j++)le(0xcc+2*j,rnd()%4805,2);
      }
      pk_cf_res_rng rng{rnd(),rnd()};
      for(unsigned n:lengths){
        int16_t pcm[66];for(auto&v:pcm)v=int16_t(rnd());
        for(unsigned k=0;k<size;k++)t.m.write8(t.at("remaining_state")+k,object[k]);
        for(unsigned k=0;k<66;k++)t.m.write16(t.at("remaining_output")+2*k,uint16_t(pcm[k]));
        t.m.write32(t.at("remaining_rng"),rng.low);t.m.write32(t.at("remaining_rng")+4,rng.high);
        t.m.write32(t.at("remaining_n"),n);t.m.write32(t.at("remaining_kind"),kind);
        t.m.write32(t.at("remaining_mac_mode"),mac_modes[c%6]);
        int result=kind==0?snare(object.data(),pcm,n,&res_tables,&rng):kind==1?bass(object.data(),pcm,n,&res_tables,&rng):slap(object.data(),pcm,n,&slap_tables,reinterpret_cast<pk_cf_fold_rng*>(&rng));
        t.call("remaining_direct");require(t.m.read32(t.at("remaining_status"))==unsigned(result),"direct status");
        require(t.bytes(t.at("remaining_state"),size)==object,"direct raw state kind="+std::to_string(kind)+" case="+std::to_string(c)+" n="+std::to_string(n));
        for(unsigned k=0;k<66;k++)require(t.m.read16(t.at("remaining_output")+2*k)==uint16_t(pcm[k]),"direct PCM/guard");
        require(t.m.read32(t.at("remaining_rng"))==rng.low&&t.m.read32(t.at("remaining_rng")+4)==rng.high,"direct RNG");
        for(unsigned k=0;k<7;k++)require(t.m.read32(t.at("remaining_mac_before")+4*k)==t.m.read32(t.at("remaining_mac_after")+4*k),"direct raw MAC register ABI");
        direct_checks++;
      }
    }
    std::ofstream direct(work+"/DIRECT.json");direct<<"{\\"status\\":\\"PASS_RAW_STATE_PCM_RNG_GUARDS_MAC_ABI\\",\\"cases\\":"<<direct_checks<<"}\\n";
'''
    text = text.replace('    csv.close();', directed + '    csv.close();', 1)
    text = text.replace('\\"algorithm_layouts\\":81,\\"mode_rows\\":6',
                        '\\"algorithm_layouts\\":2,\\"mode_rows\\":5')
    runner = work / 'runner.cpp'
    runner.write_text(text)
    command = list(next(c for c in manifest['commands'] if str(original) in c))
    command[command.index(str(original))] = str(runner)
    command[command.index('-o') + 1] = str(work / 'runner')
    command += ['-I' + str(ROOT / 'modules/perky')]
    run(command, 'runner-build')
    helpers = [ROOT / 'modules/perky/budget_transport.s',
               ROOT / 'modules/perky/cf_synthesis_delay.s']
    for index, path in enumerate(helpers):
        run(['m68k-elf-gcc', '-mcpu=54455', '-c', path, '-o',
             work / f'helper{index}.o'], f'helper{index}-build')
    probe = ROOT / 'tools/harness/perky_cf/synthesis_remaining_probe.c'
    run(['m68k-elf-gcc', *flags, '-c', probe, '-o', work / 'probe.o'], 'direct-probe-build')
    template = next(c for c in manifest['commands'] if '-nostdlib' in c)
    results = {}
    for variant in ('baseline', 'candidate'):
        directory = work / variant
        directory.mkdir()
        for name in ('native.dylib', 'assets'):
            (directory / name).symlink_to(BASE / name,
                                         target_is_directory=name == 'assets')
        inputs = dict(sources)
        if variant == 'candidate':
            inputs['resonant'] = candidate.resonant_transform(directory, sources['resonant'])
            if args.slap_envelope:
                inputs['slap'] = slap_candidate.slap_transform(directory, sources['slap'])
        for name, source in inputs.items():
            run(['m68k-elf-gcc', *flags, '-c', source, '-o',
                 directory / (name + '.o')], variant + '-' + name)
            run(['m68k-elf-gcc', *flags, '-S', source, '-o',
                 directory / (name + '.s')], variant + '-' + name + '-asm')
            if variant == 'baseline':
                frozen_name = 'pkresonant' if name == 'resonant' else 'pkslap'
                assert (directory / (name + '.s')).read_bytes() == (
                    PKFM17 / 'probe/cf-generated' / (frozen_name + '.s')).read_bytes(), (
                        'Recompiled baseline differs from actual PKFM17 assembly', name)
        replacements = {str(BASE / 'cf_resonant.o'): str(directory / 'resonant.o'),
                        str(BASE / 'cf_slap.o'): str(directory / 'slap.o'),
                        str(BASE / 'target.elf'): str(directory / 'target.elf')}
        command = [replacements.get(value, value) for value in template]
        command += [str(work / f'helper{index}.o') for index in range(len(helpers))]
        command += [str(work / 'probe.o')]
        command += ['-Wl,--undefined=' + name for name in (
            'remaining_direct', 'remaining_state', 'remaining_output', 'remaining_res_tables',
            'remaining_slap_tables', 'remaining_rng', 'remaining_n', 'remaining_kind',
            'remaining_status', 'remaining_mac_mode', 'remaining_mac_before', 'remaining_mac_after')]
        run(command, variant + '-link')
        run(['m68k-elf-objcopy', '-O', 'binary', directory / 'target.elf',
             directory / 'target.bin'], variant + '-binary')
        for command, name in [('m68k-elf-nm', 'target.nm'),
                              ('m68k-elf-objdump', 'target.dis')]:
            switches = ['-S'] if name.endswith('.nm') else ['-d']
            (directory / name).write_bytes(subprocess.check_output(
                [command, *switches, str(directory / 'target.elf')]))
        run([work / 'runner', directory, directory / 'assets'], variant + '-execute')
        groups = {}
        for row in csv.DictReader((directory / 'costs.csv').open()):
            key = row['kind'] + '/' + row['algos'] + '/' + row['modes']
            groups.setdefault(key, []).append(int(row['cycles']))
        results[variant] = {
            'execution': json.loads((directory / 'EXECUTION.json').read_text()),
            'direct': json.loads((directory / 'DIRECT.json').read_text()),
            'cycles': {key: {'mean': sum(values) / len(values), 'maximum': max(values)}
                       for key, values in groups.items()},
            'source_sha256': {str(path): sha(path) for path in inputs.values()},
            'elf_sha256': sha(directory / 'target.elf')}
        print(variant, results[variant]['execution'], flush=True)
    changes = {key: results['baseline']['cycles'][key]['mean'] - value['mean']
               for key, value in results['candidate']['cycles'].items()}
    bound = [Path(__file__), Path(candidate.__file__), Path(slap_candidate.__file__), original, probe,
             BASE / 'BUILD.json', BASE / 'native.dylib', PKFM17 / 'BUILD.json',
             *sources.values(), *helpers]
    report = {'status': 'PASS_LINKED_CF_ORIGINAL_PCM_STATE_RNG_CLOCK',
              'scope': 'Standalone synthesis comparison; excludes stock ISR/DSP scheduling and hardware effects',
              'PKFM17_runtime_sha256': actual['runtime_sha256'],
              'CF_hz': 264000000, 'results': results,
              'mean_cycles_saved': changes, 'commands': commands,
              'input_sha256': {str(path): sha(path) for path in bound}}
    (work / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(changes, indent=2))


if __name__ == '__main__':
    main()
