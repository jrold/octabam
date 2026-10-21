#!/usr/bin/env python3
"""Repeat the unchanged fast-probe workload driver in a separate result folder."""
from pathlib import Path
import measure_perky_noise_hat_fast as measure

def main():
 source=measure.WORK
 work=source.parent/'noise-hat-lifecycle/rerun';work.mkdir(parents=True,exist_ok=True)
 for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin','observer'):
  path=work/name
  if not path.exists():path.symlink_to(source/name,target_is_directory=(source/name).is_dir())
  assert path.resolve()==(source/name).resolve(),('unexpected artifact binding',path)
 measure.WORK=work
 measure.main()

if __name__=='__main__':main()
