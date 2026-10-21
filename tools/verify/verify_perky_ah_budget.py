#!/usr/bin/env python3
"""Actual CF Acoustic Hats optimization vs frozen native full object/audio.

The ordinary gate covers all modes/corners and event splits. The edge stream
also changes sample endings, holds, mute, filter seeding and arbitrary finite
float histories on both targets before each call. No target repair follows a
call. Cycle deltas are standalone development evidence, not admission.
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
import generate_cf_ah_budget as candidate


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
        command = list(map(str, command));commands.append(command)
        with (w / (log + '.log')).open('w') as out:
            subprocess.run(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, check=True)

    manifest = json.loads((BASE / 'BUILD.json').read_text())
    original_runner = ROOT / 'tools/harness/perky_cf/placement_cf_runner.cpp'
    text = original_runner.read_text()
    text = text.replace('compare(t,native,kind=="solo"||f==0||f+1==frames)', 'compare(t,native,true)')
    marker = '            auto c=t.call("placement_frame");'
    assert text.count(marker) == 1
    text = text.replace(marker, '''
            if(kind=="edge"&&f>0){
                auto ns=native.get<uint8_t*>("placement_ah_state");
                unsigned sa=t.at("placement_ah_state");
                auto set8=[&](unsigned o,uint8_t v){t.m.write8(sa+o,v);ns[o]=v;};
                auto set32=[&](unsigned o,uint32_t v){for(unsigned k=0;k<4;k++)set8(o+k,uint8_t(v>>(8*k)));};
                static uint32_t seed=0x41484632;
                auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
                const uint32_t edge[]={0,1,0xffffffff,0x80000000,0x7fffffff,32767,0xffff8000};
                set32(0xc4,(f%4==0)?0:(f%4==1)?1:(f%4==2)?0xffffffff:10);
                set32(0xfc,(f%5==0)?0:(f%5==1)?1:(f%5==2)?2:100000);
                set32(0xc8,rnd()&0xfff);set32(0xdc,f%4);
                set32(0x100,edge[f%7]);
                set32(0x104,(rnd()&0x807fffff)|((1+f%250)<<23));
                set8(0x108,f%3==0?3:0);set8(0xb8,f%7==0?1:0);
                auto nh=native.get<int32_t*>("placement_ah_hold");*nh=int32_t(edge[(f+3)%7]);
                t.m.write32(t.at("placement_ah_hold"),uint32_t(*nh));
            }
''' + marker, 1)
    begin = text.index('    for(unsigned voice=0;voice<2;voice++)')
    end = text.index('    csv.close();', begin)
    text = text[:begin] + '''
    for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
        std::array<unsigned,4>a{9,9,8,10},m{1,2,0,mode};
        run("solo",8,a,m,128,corner,false);
        run("dense",8,a,m,128,corner,true);
        run("layout",15,a,m,64,corner,true);
        run("edge",8,a,m,128,corner,false);
    }
''' + text[end:]
    text = text.replace('\\"algorithm_layouts\\":81,\\"mode_rows\\":6', '\\"algorithm_layouts\\":1,\\"mode_rows\\":3')
    runner = w / 'runner.cpp';runner.write_text(text)
    command = list(next(c for c in manifest['commands'] if str(original_runner) in c))
    command[command.index(str(original_runner))] = str(runner)
    command[command.index('-o') + 1] = str(w / 'runner')
    run(command, 'runner-build')
    flags = [*gcc.FLAGS, '-ffunction-sections', '-fdata-sections', '-I', ROOT / 'modules/perky', '-I', BASE]
    template = list(next(c for c in manifest['commands'] if '-nostdlib' in c))
    results = {}
    for variant in ('baseline', 'arithmetic', 'cached'):
        d = w / variant;d.mkdir(exist_ok=True)
        for name in ('native.dylib', 'assets'):
            p = d / name
            if not p.exists():p.symlink_to(BASE / name, target_is_directory=name == 'assets')
        source = d / 'acoustic-hats.c'
        candidate.generate(ROOT / 'modules/perky/cf_acoustic_hats.c', source,
                           cached_state=variant == 'cached', native_arithmetic=variant != 'baseline')
        run(['m68k-elf-gcc', *flags, '-c', source, '-o', d / 'acoustic-hats.o'], variant + '-compile')
        command = [str(d / 'acoustic-hats.o') if v == str(BASE / 'cf_acoustic_hats.o') else str(d / 'target.elf') if v == str(BASE / 'target.elf') else v for v in template]
        run(command, variant + '-link')
        run(['m68k-elf-objcopy', '-O', 'binary', d / 'target.elf', d / 'target.bin'], variant + '-binary')
        (d / 'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm', '-S', str(d / 'target.elf')]))
        (d / 'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump', '-d', str(d / 'target.elf')]))
        run([w / 'runner', d, d / 'assets'], variant + '-execute')
        groups = {}
        for row in csv.DictReader((d / 'costs.csv').open()):
            groups.setdefault(row['kind'], []).append(int(row['cycles']))
        results[variant] = dict(execution=json.loads((d / 'EXECUTION.json').read_text()),
            cost_cycles={k:dict(mean=sum(v)/len(v), maximum=max(v)) for k,v in groups.items()},
            source_sha256=sha(source), elf_sha256=sha(d / 'target.elf'))
        print(variant, results[variant], flush=True)
    report = dict(status='PASS_EXACT_TARGET_NATIVE_AND_EDGE_STATE', CPU_hz=264000000,
        scope='Standalone synthesis development; excludes stock ISR and DSP exchange',
        results=results, commands=commands,
        input_sha256={str(p):sha(p) for p in (Path(__file__), Path(candidate.__file__), ROOT / 'modules/perky/cf_acoustic_hats.c', BASE / 'native.dylib', runner)})
    (w / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
