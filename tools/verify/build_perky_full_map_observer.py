#!/usr/bin/env python3
"""Whole-machine independent original-source witness for the complete map."""
import json,os,subprocess
from pathlib import Path
import build_perky_noise_hat_handoff_observer as h
ROOT=h.ROOT;W=Path(os.environ.get('PERKY_FULL_MAP_WORK',str(ROOT/'out/perky/hybrid/full-map'))).resolve()
def main():
 h.WORK=W;original=h.b.build
 def full():h.b.HEADER=ROOT/'tools/harness/perky_cf/full_map_observer.h';return original()
 h.b.build=full
 try:h.build()
 finally:h.b.build=original
 out=W/'observer';source=ROOT/'tools/harness/perky_cf/full_map_oracle.c';lib=out/'full-map-oracle.dylib'
 subprocess.run(['cc','-O3','-std=c11','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),'-I'+str(ROOT/'tools/harness/perky_cf'),str(source),str(ROOT/'modules/perky/cf_noise_hat_offload.c'),str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),'-o',str(lib)],check=True)
 p=out/'OBSERVER_BUILD.json';r=json.loads(p.read_text());r['full_map_oracle_sha256']=h.b.base.sha(lib);r['source_sha256'].update({str(p.relative_to(ROOT)):h.b.base.sha(p) for p in (Path(__file__).resolve(),source,ROOT/'tools/harness/perky_cf/full_map_observer.h')});r['scope']='Independent original initializer/control/render streams on all four voices, DSP current PCM/state/side/clock and delayed feedback; read-only target observation.';p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
