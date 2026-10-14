#!/usr/bin/env python3
"""Recover deleted original-ARM control probes from local history and execute them.

No checkout changes or downloads. The historical probes, wrapper core, firmware
and local dependencies are recorded; generated firmware observations stay out/.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REV = '210d3672b309ec8d41747526073637516d9bd32f'
PROBES = {
    'NoiseToneControlProbe': ('noise-tone-control', 'f110e65ed60b74deace985488027fbec51bb1a922660234d563519e3baf53bfe', ['--pairwise']),
    'NoiseToneOtControlProbe': ('noise-tone-ot-control', 'c700c78eec501e93d3d499bb973d9e75769629b6ec2f5cb0fe8dfb3908146d3c', []),
}

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path, required=True)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--unicorn-build', type=Path)
    args = ap.parse_args()
    pb, work = args.source.resolve(), args.work.resolve()
    assert work.is_relative_to(ROOT/'out')
    work.mkdir(parents=True, exist_ok=True)
    (work/'capture-manifest.json').write_text(json.dumps({'status':'RUNNING'})+'\n')
    from verify_perky_cf_resonant_dsp import FIRMWARE_SHA256
    assert sha(args.firmware) == FIRMWARE_SHA256
    u = args.unicorn_build or pb/'build-smoke-latency/_deps/unicorn-build'
    cache = ROOT/'out/perky/engine-fixtures/cacheinfo.o'
    libs = [cache, *[u/n for n in ('libunicorn.a','libarm-softmmu.a','libunicorn-common.a')]]
    core = [pb/'Source'/n for n in ('FirmwareImage.cpp','PerkonsM7.cpp','PerkonsVoices.cpp')]
    # These are the historical ARM wrappers, not a new control reconstruction.
    for p in core + [pb/'Source/PerkonsVoices.h']:
        historical = subprocess.check_output(['git','show',f'{REV}:{p.relative_to(pb)}'], cwd=pb)
        assert p.read_bytes() == historical, f'original wrapper drift: {p}'
    sources = core + sorted((pb/'Source').glob('NativeV121*.cpp'))
    manifest = {'status':'RUNNING', 'historical_probe_commit': REV, 'firmware_sha256': sha(args.firmware),
                'sources': {str(p):sha(p) for p in sources},
                'dependencies': {str(p):sha(p) for p in libs}, 'commands': []}
    dependencies=[*sources,*sorted((pb/'Source').glob('*.h')),*libs,Path(__file__).resolve(),
                  ROOT/'tools/re/noise_tone_control_analyze.py',ROOT/'tools/re/noise_tone_ot_control_analyze.py',
                  ROOT/'tools/verify/verify_perky_noise_tone_control_evidence.py',Path(shutil.which('c++')).resolve(),Path(sys.executable).resolve()]
    manifest['input_hashes']={str(p):sha(p) for p in dependencies}
    def run(argv):
        argv = list(map(str, argv))
        print('+ ' + ' '.join(argv), flush=True)
        r = subprocess.run(argv, cwd=ROOT)
        manifest['commands'].append({'argv':argv,'exit_status':r.returncode})
        (work/'capture-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        r.check_returncode()
    for name, (stem, expected, flags) in PROBES.items():
        p = work/f'{name}.cpp'
        p.write_bytes(subprocess.check_output(['git','show',f'{REV}:smoke/{name}.cpp'],cwd=pb))
        assert sha(p) == expected, f'historical probe identity: {name}'
        manifest['sources'][str(p)] = expected
        exe = work/name
        run(['c++','-std=c++20','-O2',f'-I{pb/"Source"}',f'-I{u.parent/"unicorn-src/include"}',
             p,*sources,*libs,'-lpthread','-lm','-o',exe])
        run([exe,args.firmware.resolve(),work/f'{stem}.jsonl',*flags])
        analyzer = 'noise_tone_control_analyze.py' if flags else 'noise_tone_ot_control_analyze.py'
        run([sys.executable,ROOT/'tools/re'/analyzer,work/f'{stem}.jsonl','--json',work/f'{stem}-analysis.json'])
    run([sys.executable,ROOT/'tools/verify/verify_perky_noise_tone_control_evidence.py',
         '--detail',work/'noise-tone-control-analysis.json','--grid',work/'noise-tone-ot-control-analysis.json'])
    manifest['outputs'] = {p.name:sha(p) for p in work.glob('*.json*') if p.name != 'capture-manifest.json'}
    assert all(sha(p)==h for p,h in manifest['input_hashes'].items()), 'source or dependency changed during capture'
    manifest['status'] = 'PASS'
    (work/'capture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Noise/Tone original control evidence: PASS (recovered and executed locally)')

if __name__ == '__main__':
    main()
