#!/usr/bin/env python3
"""Re-execute original Fold/other core control and PCM references narrowly.

The historical complete-release runner has static guards for an older CF
implementation. This invokes its independent original-author differentials
directly; it is not a waiver or a pass for that old release runner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/perky')]
import verify_perky_cf_final as old


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/cf-placement/fold-author')
    p.add_argument('--firmware',type=Path,default=Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'))
    p.add_argument('--perkybits',type=Path,default=Path('/Users/jrold/Downloads/perkybits'))
    a=p.parse_args();work=a.work.resolve();work.mkdir(parents=True,exist_ok=True)
    for name,digest in old.PERKYBITS_REFERENCE_SHA256.items():
        assert hashlib.sha256((a.perkybits/'Source'/name).read_bytes()).hexdigest()==digest,name
    generated=old.fixtures.generate(a.firmware.resolve(),work/'fixtures')
    objects=[]
    for name in old.PRODUCTION_C:
        source=ROOT/'modules/perky'/(name+'.c');obj=work/(name+'.o')
        old.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',ROOT/'modules/perky','-c',source,'-o',obj])
        objects.append(obj)
    fdir,assets=generated['fixture_dir'],generated['assets']
    for name,params,native in (
        ('perky4_state_diff',[fdir/'fold_karp_control_fixtures.bin',assets],False),
        ('perky4_control_pcm_diff',[assets,fdir],True),
        ('perky4_render_stress',[assets],True),
        ('perky4_long_tail_diff',[assets],True)):
        exe=old.compile_cpp(name,work,objects,a.perkybits,native=native);old.run([exe,*params])
    result=dict(status='PASS_EXECUTED_ORIGINAL_CORE_DIFFERENTIALS',hardware_validated=False,
        reference_sha256=old.PERKYBITS_REFERENCE_SHA256,
        sources={str(ROOT/'modules/perky'/(n+'.c')):hashlib.sha256((ROOT/'modules/perky'/(n+'.c')).read_bytes()).hexdigest() for n in old.PRODUCTION_C},
        limits=['Source-native correctness, not target runtime timing or the historical full-release qualification.'])
    (work/'AUTHOR.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
