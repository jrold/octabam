#!/usr/bin/env python3
"""Exact compact-state gate for engine 008 Slap, all three panel modes."""
from pathlib import Path
import argparse,struct,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')]
import slap_compact as slap
from extract_noise_tone_tables import parse_container,find_m7
FIX=ROOT/'out/perky/engine-fixtures'; ENV1=0x08022EA0;ENV2=0x080236A2

def tables(image):
 s=find_m7(parse_container(image.read_bytes())[1]);return s.read(ENV1,4096),s.read(ENV2,4096)
def state(case,name):return (case/name).read_bytes()[0xC4:0xC4+0x2670]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('firmware',type=Path);a=ap.parse_args();e1,e2=tables(a.firmware);checked=0
 for mode in range(1,4):
  for corner in range(3):
   case=FIX/f'engine-8-mode-{mode}-corner-{corner}'
   voice=slap.Slap.from_arm(state(case,'wrapper-window-after.bin'))
   rng=list(struct.unpack('<II',(case/'rng-continuation-before.bin').read_bytes()))
   got=voice.render(256,e1,e2,rng);want=list(struct.unpack('<256h',(case/'arm-pcm-continuation.bin').read_bytes()))
   assert got==want,('slap',mode,corner,'PCM',next((i for i,(x,y) in enumerate(zip(got,want)) if x!=y),None))
   expected=slap.Slap.from_arm(state(case,'wrapper-window-continuation-after.bin'))
   assert voice.words==expected.words,('slap',mode,corner,'state')
   assert voice.ring==expected.ring,('slap',mode,corner,'ring')
   assert struct.pack('<II',*rng)==(case/'rng-continuation-after.bin').read_bytes(),('slap',mode,corner,'RNG')
   checked+=1
 print(f'Slap compact: PASS ({checked} continuation blocks; exact PCM/state/ring/RNG)')
if __name__=='__main__':main()
