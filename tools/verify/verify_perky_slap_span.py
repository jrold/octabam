#!/usr/bin/env python3
"""PKFM20-linked Slap span gate using retained independent full-ring oracle."""
import argparse
import inspect
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky')]
import generate_cf_slap_span as candidate
import verify_perky_slap_fixed as retained


MAC = '''
uint32_t slap_probe_mac_before[7],slap_probe_mac_after[7],slap_probe_mac_mode;
static void slap_probe_capture(uint32_t*out){
 uint32_t status;
 __asm__ volatile("move.l %%macsr,%0\\n\\tmove.l #0,%%macsr":"=d"(status)::"cc","memory");out[0]=status;
 __asm__ volatile("move.l %%acc0,%0":"=d"(out[1]));
 __asm__ volatile("move.l %%acc1,%0":"=d"(out[2]));
 __asm__ volatile("move.l %%acc2,%0":"=d"(out[3]));
 __asm__ volatile("move.l %%acc3,%0":"=d"(out[4]));
 __asm__ volatile("move.l %%accext01,%0":"=d"(out[5]));
 __asm__ volatile("move.l %%accext23,%0":"=d"(out[6]));
 __asm__ volatile("move.l %0,%%macsr"::"d"(status):"cc","memory");
}
'''
MAC_INIT = '''
 __asm__ volatile("move.l #0,%%macsr\\n\\tmove.l #0x12345678,%%acc0\\n\\t"
 "move.l #0xfedcba98,%%acc1\\n\\tmove.l #0x89abcdef,%%acc2\\n\\t"
 "move.l #0x76543210,%%acc3\\n\\tmove.l #0xdeadbeef,%%accext01\\n\\t"
 "move.l #0xabcdef01,%%accext23\\n\\tmove.l %0,%%macsr"::"d"(slap_probe_mac_mode):"cc","memory");
 slap_probe_capture(slap_probe_mac_before);
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    assert not work.exists(), 'Use a fresh output directory'
    work.mkdir(parents=True)
    build = ROOT / 'out/perky/hybrid/full-map-remaining-cf-mix-v1'
    metadata = json.loads((build / 'BUILD.json').read_text())
    source = build / 'slap-rng-emac.c'
    baseline_asm = work / 'frozen-slap.s'
    subprocess.run(['m68k-elf-gcc', *metadata['compiler_flags'], '-S', str(source),
                    '-o', str(baseline_asm)], check=True, cwd=ROOT)
    assert baseline_asm.read_bytes() == (build / 'probe/cf-generated/pkslap.s').read_bytes()
    adapted = inspect.getsource(retained.main)
    adapted = adapted.replace('tools/harness/perky_cf/slap_fixed_delay.s',
                              'tools/harness/perky_cf/slap_span_delay.s')
    adapted = adapted.replace('pk_cf_slap_delay_fixed_dispatch', 'pk_cf_slap_delay_span')
    adapted = adapted.replace('pk_cf_slap_delay_fixed', 'pk_cf_slap_delay_span_fast')
    adapted = adapted.replace("'fixed'", "'span'").replace('fixed_entries', 'span_entries')
    old = "flags = [*gcc.FLAGS, '-ffunction-sections', '-fdata-sections', '-I', ROOT / 'modules/perky']"
    assert adapted.count(old) == 1
    adapted = adapted.replace(old, 'flags = _flags', 1)
    adapted = adapted.replace('metadata<2', 'metadata<4')
    old = '        int32_t mix=int16_t(rnd()),data[24],want[24];'
    assert adapted.count(old) == 1
    adapted = adapted.replace(old, '''        if(metadata==2)for(unsigned k=0;k<5;k++){delay[k]=rnd()%4805;gain[k]=uint16_t(rnd());}
        if(metadata==3)for(unsigned k=0;k<5;k++){delay[k]=(cursor+k)%3;gain[k]=uint16_t(rnd());}
''' + old, 1)
    adapted = adapted.replace('int16_t(rnd());\n        t.m.write16(sa,cursor)',
                              'int32_t(rnd());\n        t.m.write16(sa,cursor)', 1)
    adapted = adapted.replace('        t.call("slap_probe_run");', '''        t.m.write32(t.at("slap_probe_mac_mode"),(unsigned[]){0,0x20,0x40,0x60,0xb0,0xf0}[cursor%6]);
        t.call("slap_probe_run");
        for(unsigned k=0;k<7;k++)require(t.m.read32(t.at("slap_probe_mac_before")+4*k)==t.m.read32(t.at("slap_probe_mac_after")+4*k),"Slap raw MAC ABI");''', 1)
    adapted = adapted.replace('void slap_probe_run(void){', MAC.replace('\\', '\\\\') +
                              '\nvoid slap_probe_run(void){' + MAC_INIT.replace('\\', '\\\\'))
    old = '(&slap_probe_state,slap_probe_ring,slap_probe_data,slap_probe_n);}'
    assert adapted.count(old) == 1
    adapted = adapted.replace(old, '(&slap_probe_state,slap_probe_ring,slap_probe_data,slap_probe_n);slap_probe_capture(slap_probe_mac_after);}', 1)
    adapted = adapted.replace("'slap_probe_run')", "'slap_probe_run','slap_probe_mac_mode','slap_probe_mac_before','slap_probe_mac_after')", 1)
    namespace = dict(vars(retained), candidate=candidate, __file__=__file__, _flags=metadata['compiler_flags'])
    (work / 'ADAPTED.py').write_text(adapted)
    exec(compile(adapted, __file__, 'exec'), namespace)
    sys.argv = [sys.argv[0], '--work', str(work), '--baseline', str(source)]
    namespace['main']()
    path = work / 'RESULT.json'
    report = json.loads(path.read_text())
    report['PKFM20_MAIN_sha256'] = metadata['main_sha256']
    report['PKFM20_ELF_sha256'] = metadata['runtime_sha256']
    report['input_sha256'].update({str(p): retained.sha(p) for p in (
        Path(__file__), Path(retained.__file__), build / 'BUILD.json', baseline_asm,
        work / 'ADAPTED.py', work / 'runner', *(ROOT / 'out/perky/hybrid/cf-placement').glob('*.o'))})
    report['mean_cycles_saved'] = {key: report['results']['baseline']['cost_cycles'][key]['mean'] - value['mean']
        for key, value in report['results']['span']['cost_cycles'].items()}
    path.write_text(json.dumps(report, indent=2) + '\n')
    print('Mean cycles saved:', report['mean_cycles_saved'])


if __name__ == '__main__':
    main()
