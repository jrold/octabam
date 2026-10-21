#!/usr/bin/env python3
"""Run the full live-switch campaign with read-only CF cycle attribution."""
import argparse,json,subprocess
from pathlib import Path
import build_perky_noise_hat_handoff_observer as b
import qualify_perky_noise_hat_handoff as q
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);p.add_argument('--source',type=Path,default=q.SOURCE);p.add_argument('--case',choices=('backend','cf-calibration'),default='backend');a=p.parse_args()
 w=a.work.resolve();source=a.source.resolve();assert w!=source;w.mkdir(parents=True,exist_ok=True)
 for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin'):
  dest=w/name
  if dest.is_symlink():dest.unlink()
  assert not dest.exists();dest.symlink_to(source/name,target_is_directory=(source/name).is_dir())
 b.WORK=w;b.build(profile=True)
 rows=subprocess.check_output(['m68k-elf-nm','-n','-S',str(source/'probe/platform/runtime.elf')],text=True)
 symbols=w/'profile-symbols.txt';symbols.write_text(''.join(f'{int(v[0],16):x} {int(v[0],16)+int(v[1],16):x} {v[3]}\n' for line in rows.splitlines() if len(v:=line.split())==4 and v[2] in ('t','T')))
 q.WORK=w;q.SOURCE=source
 original=q.environment
 def env(d,s):
  e=original(d,s);e.update(NHT_PROFILE_REPORT=str(d/'cycles.json'),NHT_PROFILE_SYMBOLS=str(symbols));return e
 q.environment=env
 result=q.run(a.case)
 report=dict(source_image_sha256=next(h for p,h in result['inputs'].items() if '/mainos_' in p),source_elf_sha256=next(h for p,h in result['inputs'].items() if p.endswith('/runtime.elf')),driver_sha256=q.c.sha(Path(__file__)),symbols_sha256=q.c.sha(symbols),observer=json.loads((w/'observer/OBSERVER_BUILD.json').read_text()),result=result,profile=json.loads((w/a.case/'cycles.json').read_text()))
 (w/'PROFILE.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status=result['status'],top=report['profile']['top'][:5]),indent=2))
if __name__=='__main__':main()
