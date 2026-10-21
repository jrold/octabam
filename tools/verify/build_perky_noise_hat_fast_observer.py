#!/usr/bin/env python3
"""Exact current-source/ring witness plus pre/post full control-shadow proof."""
from pathlib import Path
import json,subprocess
import build_perky_noise_hat_taps_observer as b
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-fast'
def build():
 WORK.mkdir(parents=True,exist_ok=True)
 source=ROOT/'tools/harness/perky_cf/noise_hat_taps_observer.h'
 extension=ROOT/'tools/harness/perky_cf/noise_hat_controls_observer.h'
 combined=WORK/'controls-observer.h'
 combined.write_text(source.read_text().replace('namespace noise_hat_exact {','namespace nht_control_base {').replace('inline Observer observer;','')+'\n#include "'+str(extension)+'"\n')
 b.WORK=WORK;b.HEADER=combined;b.build()
 out=WORK/'observer';oracle=ROOT/'tools/harness/perky_cf/noise_hat_controls_oracle.c'
 subprocess.run(['cc','-O3','-std=c11','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(out/'taps-oracle.c'),str(oracle),str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),'-o',str(out/'resident-oracle.dylib')],check=True)
 receipt=json.loads((out/'OBSERVER_BUILD.json').read_text());receipt.update(complete_oracle_sha256=b.base.sha(out/'resident-oracle.dylib'),control_extension_sha256=b.base.sha(extension),control_oracle_source_sha256=b.base.sha(oracle),original_controls_source_sha256=b.base.sha(ROOT/'modules/perky/cf_perky4.c'))
 (out/'OBSERVER_BUILD.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':build()
