#!/usr/bin/env python3
"""Read-only native CF cycle attribution for the preserved tap-DMA image."""
import argparse,json,os,subprocess
from pathlib import Path
import build_perky_noise_hat_taps_observer as b
import measure_perky_noise_hat_taps as m
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-taps-profile'
def prepare(source,controls=False):
 WORK.mkdir(parents=True,exist_ok=True)
 for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin'):
  p=WORK/name
  if p.is_symlink():p.unlink()
  p.symlink_to(source/name,target_is_directory=(source/name).is_dir())
 header=WORK/'profile-observer.h'
 s=(ROOT/'tools/harness/perky_cf/noise_hat_taps_observer.h').read_text().replace('namespace noise_hat_exact {','namespace '+('nht_control_base' if controls else 'nht_exact_base')+' {').replace('inline Observer observer;','')
 if controls:s+='\n'+(ROOT/'tools/harness/perky_cf/noise_hat_controls_observer.h').read_text().replace('namespace noise_hat_exact {','namespace nht_exact_base {').replace('inline Observer observer;','')
 header.write_text('#include "'+str(b.base.BASE/'observer.h')+'"\n'+s+'\n#include "'+str(ROOT/'tools/harness/perky_cf/noise_hat_cycle_profile.h')+'"\n')
 b.WORK=WORK;b.HEADER=header;b.build()
 if controls:
  lib=WORK/'observer/resident-oracle.dylib'
  subprocess.run(['cc','-O3','-std=c11','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(WORK/'observer/taps-oracle.c'),str(ROOT/'tools/harness/perky_cf/noise_hat_controls_oracle.c'),str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),'-o',str(lib)],check=True)
  receipt=WORK/'observer/OBSERVER_BUILD.json';report=json.loads(receipt.read_text());report['complete_oracle_sha256']=b.base.sha(lib);report['control_oracle_source_sha256']=b.base.sha(ROOT/'tools/harness/perky_cf/noise_hat_controls_oracle.c');receipt.write_text(json.dumps(report,indent=2)+'\n')
 rows=subprocess.check_output(['m68k-elf-nm','-n','-S',str(source/'probe/platform/runtime.elf')],text=True)
 symbols=WORK/'profile-symbols.txt'
 symbols.write_text(''.join(f'{int(v[0],16):x} {int(v[0],16)+int(v[1],16):x} {v[3]}\n' for line in rows.splitlines() if len(v:=line.split())==4 and v[2] in ('t','T')))
 return symbols
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'out/perky/hybrid/noise-hat-taps');p.add_argument('--frames',type=int,default=4096);p.add_argument('--mode',type=int,default=0);p.add_argument('--reuse',action='store_true');p.add_argument('--controls',action='store_true');p.add_argument('--work',type=Path,default=WORK);a=p.parse_args()
 WORK=a.work.resolve();a.source=a.source.resolve()
 if a.controls:
  import measure_perky_noise_hat_fast as m
 symbols=WORK/'profile-symbols.txt' if a.reuse else prepare(a.source,a.controls)
 # The normal runner retains every audio/state/ownership and program gate.
 m.WORK=WORK
 original=m.c.run
 def run(*args,**kw):
  d=WORK/'integrated-results'/(args[1]+'-static')
  kw['extra_env'].update(NHT_PROFILE_SYMBOLS=str(symbols),NHT_PROFILE_REPORT=str(d/'cycles.json'))
  return original(*args,**kw)
 m.c.run=run
 import sys
 sys.argv=[sys.argv[0],'--frames',str(a.frames),'--mode',str(a.mode)]
 m.main()
