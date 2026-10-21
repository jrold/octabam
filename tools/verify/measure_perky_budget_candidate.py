#!/usr/bin/env python3
"""Measure a new candidate with the frozen calibration instrument and oracle."""
import argparse,json,os,shutil
from pathlib import Path
import calibrate_perky_hybrid_budget as c
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--frames',type=int,default=16384);p.add_argument('--v4',type=int,choices=(5,3,10),default=5);p.add_argument('--mode',type=int,choices=(0,1,2),default=1);a=p.parse_args()
 source=a.build.resolve();w=a.work.resolve();w.mkdir(parents=True,exist_ok=True)
 b=json.loads((source/'BUILD.json').read_text());version=b['version'];image=source/'probe'/f'mainos_{version}.bin'
 c.CURRENT=source;c.PINNED[version]=c.sha(image)
 observer=w/'observer'
 if not observer.exists():observer.symlink_to(c.DEFAULT_WORK/'observer',target_is_directory=True)
 oracle=source/'observer';oracle.mkdir(exist_ok=True)
 ref=c.ROOT/'out/perky/hybrid/full-map-release/observer/full-map-oracle.dylib'
 if not (oracle/ref.name).exists():(oracle/ref.name).symlink_to(ref)
 row=dict(version=version,role='candidate',algos=[9,9,8,a.v4],modes=[1,2,0,a.mode],FX='all14')
 name=f'{version}-WTWT-Slap-{a.v4}-M{a.mode}-all14';c.cases=lambda:{name:row}
 c.run(w,name,a.frames)
if __name__=='__main__':main()
