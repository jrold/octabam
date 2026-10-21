#!/usr/bin/env python3
"""Actual CF fixed-tap Slap vs frozen native and independent whole-ring oracle."""
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
import generate_cf_slap_fixed as candidate


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--baseline', type=Path, default=ROOT / 'out/perky/hybrid/full-map-state-v4/slap-filter-block.c')
    a = ap.parse_args();w = a.work.resolve();w.mkdir(parents=True, exist_ok=True)
    commands = []

    def run(command, log):
        command = list(map(str, command));commands.append(command)
        with (w / (log + '.log')).open('w') as out:
            subprocess.run(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, check=True)

    manifest = json.loads((BASE / 'BUILD.json').read_text())
    original_runner = ROOT / 'tools/harness/perky_cf/placement_cf_runner.cpp'
    text = original_runner.read_text()
    text = text.replace('compare(t,native,kind=="solo"||f==0||f+1==frames)', 'compare(t,native,true)')
    text = text.replace('    Cost call(const std::string&s){', '    uint64_t fixed_entries=0,generic_entries=0;\n    Cost call(const std::string&s){')
    text = text.replace('while(m.pcFast()!=end){require(++n', 'while(m.pcFast()!=end){if(m.pcFast()==at("pk_cf_slap_delay_fixed"))fixed_entries++;if(m.pcFast()==at("pk_cf_slap_delay_block"))generic_entries++;require(++n')
    begin = text.index('    for(unsigned voice=0;voice<2;voice++)');end = text.index('    csv.close();', begin)
    text = text[:begin] + '''
    for(unsigned mode=0;mode<3;mode++)for(unsigned corner:{0u,64u,127u}){
        std::array<unsigned,4>a{9,9,8,5},m{1,2,mode,1};
        run("solo",4,a,m,128,corner,false);
        run("dense",4,a,m,128,corner,true);
        run("layout",15,a,m,64,corner,true);
    }
    uint32_t seed=0x534c4150;
    auto rnd=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
    auto clip=[](int32_t v){return std::max(-32767,std::min(32767,v));};
    auto low=[](int32_t a,int32_t b){return int32_t(uint32_t(a)*uint32_t(b));};
    auto add=[](int32_t a,int32_t b){return int32_t(uint32_t(a)+uint32_t(b));};
    unsigned sa=t.at("slap_probe_state"),ra=t.at("slap_probe_ring"),da=t.at("slap_probe_data");
    int16_t ring[4806];for(unsigned k=0;k<4806;k++){ring[k]=int16_t(rnd());t.m.write8(ra+2*k,uint8_t(ring[k]));t.m.write8(ra+2*k+1,uint8_t(uint16_t(ring[k])>>8));}
    uint32_t cases=0;
    for(unsigned cursor=0;cursor<4805;cursor++)for(unsigned metadata=0;metadata<2;metadata++)for(unsigned n:{0u,1u,17u,20u}){
        uint16_t delay[5]={573,1201,1538,3139,4804},gain[5]={1,1,3,5,7};
        if(metadata){if(cursor%10<5)delay[cursor%5]^=1;else gain[cursor%5]^=0x8040;}
        int32_t mix=int16_t(rnd()),data[24],want[24];
        const int32_t edges[]={-32768,-32767,-1,0,1,32767};
        for(unsigned k=0;k<24;k++)data[k]=want[k]=(cursor%3==0)?edges[(cursor+k)%6]:int16_t(rnd());
        t.m.write16(sa,cursor);t.m.write16(sa+2,uint16_t(mix));
        for(unsigned k=0;k<5;k++){t.m.write16(sa+4+2*k,delay[k]);t.m.write16(sa+14+2*k,gain[k]);}
        for(unsigned k=0;k<24;k++)t.m.write32(da+4*k,uint32_t(data[k]));
        unsigned ix=cursor;
        for(unsigned k=0;k<n;k++){
            int32_t stage=data[k];
            for(unsigned tap=0;tap<5;tap++){
                unsigned ri=ix>=delay[tap]?ix-delay[tap]:4805+ix-delay[tap];
                stage=clip(add(low(stage,int32_t(gain[tap])-16),low(gain[tap],ring[ri]))>>4);
            }
            ix=(ix+1)%4805;ring[ix]=int16_t(stage);
            want[k]=add(low(data[k],4095-mix),low(mix,low(stage,5)>>1))>>12;
        }
        t.m.write32(t.at("slap_probe_n"),n);
        for(unsigned k=0;k<6;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k),0x12340000+k);
        for(unsigned k=0;k<5;k++)m68k_set_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k),0x47010000+16*k);
        t.call("slap_probe_run");
        require(t.m.read16(sa)==ix&&t.m.read16(sa+2)==uint16_t(mix),"Slap cursor/mix");
        for(unsigned k=0;k<5;k++)require(t.m.read16(sa+4+2*k)==delay[k]&&t.m.read16(sa+14+2*k)==gain[k],"Slap metadata");
        for(unsigned k=0;k<24;k++)require(t.m.read32(da+4*k)==uint32_t(want[k]),"Slap delay PCM/guard");
        for(unsigned k=0;k<4806;k++)require(t.m.read8(ra+2*k)==uint8_t(ring[k])&&t.m.read8(ra+2*k+1)==uint8_t(uint16_t(ring[k])>>8),"Slap complete ring/guard");
        for(unsigned k=0;k<6;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_D2+k))==0x12340000+k,"Slap D ABI");
        for(unsigned k=0;k<5;k++)require(m68k_get_reg(t.m.getCpuState(),(m68k_register_t)(M68K_REG_A2+k))==0x47010000+16*k,"Slap A ABI");
        cases++;
    }
    std::ofstream proof(work+"/DELAY.json");proof<<"{\\"fixed_entries\\":"<<t.fixed_entries<<",\\"generic_entries\\":"<<t.generic_entries<<",\\"cases\\":"<<cases<<",\\"status\\":\\"PASS_TARGET_RING_PCM_STATE_ABI\\"}\\n";
''' + text[end:]
    text = text.replace('\\"algorithm_layouts\\":81,\\"mode_rows\\":6', '\\"algorithm_layouts\\":1,\\"mode_rows\\":3')
    runner = w / 'runner.cpp';runner.write_text(text)
    command = list(next(c for c in manifest['commands'] if str(original_runner) in c))
    command[command.index(str(original_runner))] = str(runner);command[command.index('-o') + 1] = str(w / 'runner')
    run(command, 'runner-build')
    helpers = ('modules/perky/budget_transport.s', 'modules/perky/cf_synthesis_delay.s', 'tools/harness/perky_cf/slap_fixed_delay.s')
    for i,path in enumerate(helpers):run(['m68k-elf-gcc', '-mcpu=54455', '-c', ROOT / path, '-o', w / f'helper{i}.o'], f'helper{i}-build')
    flags = [*gcc.FLAGS, '-ffunction-sections', '-fdata-sections', '-I', ROOT / 'modules/perky']
    template = list(next(c for c in manifest['commands'] if '-nostdlib' in c));results = {}
    for variant in ('baseline', 'fixed'):
        d = w / variant;d.mkdir(exist_ok=True)
        for name in ('native.dylib', 'assets'):
            p = d / name
            if not p.exists():p.symlink_to(BASE / name, target_is_directory=name == 'assets')
        source = candidate.transform(d,a.baseline) if variant == 'fixed' else d / 'slap-baseline.c'
        if variant == 'baseline':source.write_text(a.baseline.read_text())
        call = 'pk_cf_slap_delay_fixed_dispatch' if variant == 'fixed' else 'pk_cf_slap_delay_block'
        with source.open('a') as out:out.write('''
slap_delay_state slap_probe_state;uint8_t slap_probe_ring[4806*2];int32_t slap_probe_data[24];uint32_t slap_probe_n;
void slap_probe_run(void){'''+call+'''(&slap_probe_state,slap_probe_ring,slap_probe_data,slap_probe_n);}
''')
        run(['m68k-elf-gcc', *flags, '-c', source, '-o', d / 'slap.o'], variant + '-compile')
        command = [str(d / 'slap.o') if v == str(BASE / 'cf_slap.o') else str(d / 'target.elf') if v == str(BASE / 'target.elf') else v for v in template]
        command += [str(w / f'helper{i}.o') for i in range(3)]
        command += ['-Wl,--undefined=' + name for name in ('pk_cf_slap_delay_fixed', 'pk_cf_slap_delay_block', 'slap_probe_state', 'slap_probe_ring', 'slap_probe_data', 'slap_probe_n', 'slap_probe_run')]
        run(command, variant + '-link');run(['m68k-elf-objcopy', '-O', 'binary', d / 'target.elf', d / 'target.bin'], variant + '-binary')
        (d / 'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm', '-S', str(d / 'target.elf')]))
        (d / 'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump', '-d', str(d / 'target.elf')]))
        run([w / 'runner', d, d / 'assets'], variant + '-execute')
        groups = {}
        for row in csv.DictReader((d / 'costs.csv').open()):groups.setdefault(row['kind'], []).append(int(row['cycles']))
        delay = json.loads((d / 'DELAY.json').read_text())
        if variant == 'fixed':assert delay['fixed_entries']>0 and delay['generic_entries']>0
        results[variant] = dict(execution=json.loads((d / 'EXECUTION.json').read_text()),delay=delay,
            cost_cycles={k:dict(mean=sum(v)/len(v), maximum=max(v)) for k,v in groups.items()},
            source_sha256=sha(source), elf_sha256=sha(d / 'target.elf'))
        print(variant, results[variant], flush=True)
    report = dict(status='PASS_EXACT_TARGET_NATIVE_AND_FULL_RING_ABI', CPU_hz=264000000,
        scope='Standalone synthesis development; excludes stock ISR and DSP exchange',results=results,commands=commands,
        input_sha256={str(p):sha(p) for p in (Path(__file__),Path(candidate.__file__),a.baseline,BASE/'native.dylib',runner,*[ROOT/p for p in helpers])})
    (w/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
