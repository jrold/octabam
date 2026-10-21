#!/usr/bin/env python3
"""Actual ColdFire NT candidate vs frozen independent native PCM/state/RNG.

Runs ordinary and dense controls, all modes/corners and each split0..15, then
directly tests the complete filter codec with arbitrary overflow histories.
Standalone cycle deltas are development evidence, not full-ISR admission.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'out/perky/hybrid/cf-placement'
sys.path[:0] = [str(ROOT / 'tools/perky'), str(ROOT / 'modules/perky')]
import generate_cf_final as gcc
import generate_cf_nt_budget as candidate


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    a = ap.parse_args()
    w = a.work.resolve()
    w.mkdir(parents=True, exist_ok=True)
    commands = []

    def run(command, log):
        command = list(map(str, command))
        commands.append(command)
        with (w / (log + '.log')).open('w') as out:
            subprocess.run(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, check=True)

    manifest = json.loads((BASE / 'BUILD.json').read_text())
    original_runner = ROOT / 'tools/harness/perky_cf/placement_cf_runner.cpp'
    text = original_runner.read_text()
    # A frame's full canonical raw objects, every control, global RNG and all
    # three clock limbs are compared with the frozen pre-optimization dylib.
    text = text.replace('compare(t,native,kind=="solo"||f==0||f+1==frames)', 'compare(t,native,true)')
    begin = text.index('    for(unsigned voice=0;voice<2;voice++)')
    end = text.index('    csv.close();', begin)
    text = text[:begin] + '''
    for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
        std::array<unsigned,4>a{9,9,8,3},m{1,2,0,mode};
        run("solo",8,a,m,128,corner,false);
        run("dense",8,a,m,128,corner,true);
        run("layout",15,a,m,64,corner,true);
    }
    // Independent original filter recurrence with wrapping at each original
    // ARM operation. Probe publication checks every byte of the raw object.
    uint32_t seed=0x4e544632;
    auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
    auto clip=[](int32_t v){return std::max(-32767,std::min(32767,v));};
    auto low=[](int32_t a,int32_t b){return int32_t(uint32_t(a)*uint32_t(b));};
    unsigned probe=t.at("nt_probe_state"),data=t.at("nt_probe_noise"),rg=t.at("nt_probe_rng");
    for(unsigned c=0;c<4096;c++){
        const unsigned n=c%21;Bytes state(0x100),expected;for(auto &b:state)b=uint8_t(rnd());
        auto get16=[&](unsigned o){return unsigned(state[o])|(unsigned(state[o+1])<<8);};
        auto get32=[&](unsigned o){return uint32_t(get16(o))|(uint32_t(get16(o+2))<<16);};
        auto put16=[&](unsigned o,uint32_t v){state[o]=uint8_t(v);state[o+1]=uint8_t(v>>8);};
        auto put32=[&](unsigned o,uint32_t v){put16(o,v);put16(o+2,v>>16);};
        put16(0x60,c%7);put16(0x62,c%5);
        uint32_t lo=rnd(),hi=rnd(),wantlo=lo,wanthi=hi;
        for(unsigned k=0;k<state.size();k++)t.m.write8(probe+k,state[k]);
        t.m.write32(rg,lo);t.m.write32(rg+4,hi);t.m.write32(t.at("nt_probe_n"),n);
        for(unsigned k=0;k<24;k++)t.m.write16(data+2*k,0xa55a);
        uint32_t count=get16(0x60),reload=get16(0x62),held=get16(0x70);
        int32_t coeff=get16(0xaa),drive=get16(0xa8),first=int32_t(get32(0xac)),second=int32_t(get32(0xb0)),velocity=int32_t(get32(0xb4));
        std::vector<int16_t>want;
        for(unsigned k=0;k<n;k++){
            if(count)--count;else{
                count=reload;uint64_t full=uint64_t(wantlo)*0x4c957f2d;
                uint32_t nl=uint32_t(full)+1,carry=nl<uint32_t(full);
                wanthi=wantlo*0x5851f42d+wanthi*0x4c957f2d+uint32_t(full>>32)+carry;
                wantlo=nl;held=uint16_t(wanthi&0x7fffffffu);
            }
            int32_t nv=int16_t(held);want.push_back(int16_t(nv));
            for(unsigned stage=0;stage<2;stage++){
                int32_t p=low(velocity,coeff);if(p<0)p=int32_t(uint32_t(p)+65535);
                first=clip(int32_t(uint32_t(first)+uint32_t(p>>16)));
                second=clip(int32_t(uint32_t(nv)-uint32_t(first)-uint32_t(low(velocity,drive)>>10)));
                p=low(second,coeff);if(p<0)p=int32_t(uint32_t(p)+65535);
                velocity=clip(int32_t(uint32_t(velocity)+uint32_t(p>>16)));
            }
        }
        put16(0x60,count);put16(0x70,held);put32(0xac,uint32_t(first));put32(0xb0,uint32_t(second));put32(0xb4,uint32_t(velocity));
        t.call("nt_probe_run");require(t.bytes(probe,state.size())==state,"NT arbitrary filter raw state");
        require(t.m.read32(rg)==wantlo&&t.m.read32(rg+4)==wanthi,"NT arbitrary RNG");
        for(unsigned k=0;k<24;k++)require(t.m.read16(data+2*k)==(k<n?uint16_t(want[k]):0xa55a),"NT arbitrary noise/guard");
    }
''' + text[end:]
    # The loop bounds above are the actual focused proof, not the old broad
    # runner's declared matrix sizes.
    text = text.replace('\\"algorithm_layouts\\":81,\\"mode_rows\\":6', '\\"algorithm_layouts\\":1,\\"mode_rows\\":3')
    runner = w / 'runner.cpp'
    runner.write_text(text)
    command = list(next(c for c in manifest['commands'] if str(original_runner) in c))
    command[command.index(str(original_runner))] = str(runner)
    command[command.index('-o') + 1] = str(w / 'runner')
    run(command, 'runner-build')
    run(['m68k-elf-gcc', '-mcpu=54455', '-c', ROOT / 'modules/perky/budget_transport.s', '-o', w / 'filter.o'], 'filter-build')
    flags = [*gcc.FLAGS, '-ffunction-sections', '-fdata-sections', '-I', ROOT / 'modules/perky']
    template = list(next(c for c in manifest['commands'] if '-nostdlib' in c))
    results = {}
    for variant in ('baseline', 'native20', 'filter20'):
        d = w / variant
        d.mkdir(exist_ok=True)
        for name in ('native.dylib', 'assets'):
            p = d / name
            if not p.exists():
                p.symlink_to(BASE / name, target_is_directory=name == 'assets')
        source = d / 'noise-tone.c'
        candidate.generate(ROOT / 'modules/perky/cf_noise_tone.c', source,
                           assembly_filter=variant == 'filter20', native20=variant != 'baseline')
        with source.open('a') as out:
            out.write('''
uint8_t nt_probe_state[0x100];int16_t nt_probe_noise[24];pk_cf_nt_rng nt_probe_rng;uint32_t nt_probe_n;
void nt_probe_run(void){volatile pk_cf_render_math_context c=pk_cf_render_math_begin();nt_noise_filter_block(nt_probe_state,nt_probe_noise,nt_probe_n,&nt_probe_rng);pk_cf_render_math_end(c);}
''')
        run(['m68k-elf-gcc', *flags, '-c', source, '-o', d / 'noise-tone.o'], variant + '-compile')
        command = [str(d / 'noise-tone.o') if v == str(BASE / 'cf_noise_tone.o') else str(d / 'target.elf') if v == str(BASE / 'target.elf') else v for v in template]
        command += [str(w / 'filter.o'), *['-Wl,--undefined=' + name for name in ('nt_probe_state', 'nt_probe_noise', 'nt_probe_rng', 'nt_probe_n', 'nt_probe_run')]]
        run(command, variant + '-link')
        run(['m68k-elf-objcopy', '-O', 'binary', d / 'target.elf', d / 'target.bin'], variant + '-binary')
        (d / 'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm', '-S', str(d / 'target.elf')]))
        (d / 'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump', '-d', str(d / 'target.elf')]))
        run([w / 'runner', d, d / 'assets'], variant + '-execute')
        groups = {}
        for row in csv.DictReader((d / 'costs.csv').open()):
            groups.setdefault(row['kind'], []).append(int(row['cycles']))
        results[variant] = dict(execution=json.loads((d / 'EXECUTION.json').read_text()),
            filter_raw_state_rng_cases=4096, native_counts=list(range(21)),
            cost_cycles={k:dict(mean=sum(v)/len(v), maximum=max(v)) for k,v in groups.items()},
            source_sha256=sha(source), elf_sha256=sha(d / 'target.elf'))
        print(variant, results[variant], flush=True)
    report = dict(status='PASS_EXACT_TARGET_NATIVE_AND_FILTER_CODEC', CPU_hz=264000000,
        scope='Standalone synthesis development; excludes stock ISR and DSP exchange',
        results=results, commands=commands,
        input_sha256={str(p):sha(p) for p in (Path(__file__), Path(candidate.__file__), ROOT / 'modules/perky/cf_noise_tone.c', ROOT / 'modules/perky/budget_transport.s', BASE / 'native.dylib', runner)})
    (w / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
