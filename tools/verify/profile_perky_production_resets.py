#!/usr/bin/env python3
"""Read-only full lifecycle attribution with the independent production witness."""
import argparse,json,subprocess,sys
from pathlib import Path
import build_perky_noise_hat_production_observer as b
import qualify_perky_noise_hat_production as p
ROOT=p.ROOT

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--source',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
 parser.add_argument('--build-only',action='store_true');parser.add_argument('--backend',choices=('cf','dsp'))
 a=parser.parse_args();source=a.source.resolve();work=a.work.resolve();assert source!=work
 work.mkdir(parents=True,exist_ok=True)
 for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin','BUILD.json'):
  dest=work/name
  if not dest.exists():dest.symlink_to(source/name,target_is_directory=(source/name).is_dir())
 if a.build_only:
  b.WORK=work;b.main(profile=True);return
 assert a.backend and (work/'observer/OBSERVER_BUILD.json').exists()
 lines=subprocess.check_output(['m68k-elf-nm','-n','-S',str(source/'probe/platform/runtime.elf')],text=True)
 symbols=work/f'{a.backend}-symbols.txt';symbols.write_text(''.join(f'{int(v[0],16):x} {int(v[0],16)+int(v[1],16):x} {v[3]}\n' for line in lines.splitlines() if len(v:=line.split())==4 and v[2] in ('t','T')))
 p.SOURCE=work;env=p.q.environment
 def profile_env(directory,syms):
  e=env(directory,syms);e.update(NHT_PROFILE_REPORT=str(directory/'cycles.json'),NHT_PROFILE_SYMBOLS=str(symbols));return e
 p.q.environment=profile_env
 sys.argv=[sys.argv[0],'--backend',a.backend];p.main()
 directory=work/('production-'+a.backend);result=json.loads((directory/'PRODUCTION_RESULT.json').read_text());cycles=json.loads((directory/'panel/cycles.json').read_text())
 assert cycles['sum_cycles']==result['safety']['full_ISR_sum_cycles']
 assert cycles['top'][0]['cycles']==result['full_ISR']['max_cycles']
 assert len(cycles['reset_frames'])==5 and all(r['reset_mask']==15 for r in cycles['reset_frames'])
 assert all(sum(r['buckets'].values())==r['cycles'] for r in [*cycles['top'],*cycles['reset_frames']])
 report=dict(status='PASS_READ_ONLY_PRODUCTION_RESET_PROFILE' if not any(result['errors'].values()) else 'FAILED_PROFILE_QUALIFICATION',source_image_sha256=p.sha(next(x for x in (source/'probe').glob('mainos_PK*.bin') if p.sha(x)==json.loads((source/'BUILD.json').read_text())['main_sha256'])),source_elf_sha256=p.sha(source/'probe/platform/runtime.elf'),result=result,profile=cycles,observer=json.loads((work/'observer/OBSERVER_BUILD.json').read_text()),source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):p.sha(Path(__file__).resolve())},limits=['Read-only instruction trace; bucket attribution for all reset frames and the worst 64 total frames. Aggregate cycle sum covers every returned ISR. No target calls, writes, timer reads or callback changes.'])
 (directory/'RESET_PROFILE.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status=report['status'],ISR=result['full_ISR'],resets=cycles['reset_frames']),indent=2))
if __name__=='__main__':main()
