#!/usr/bin/env python3
"""Wrap the final offloaded MAIN, then decode both upgrade paths exactly."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/perky'),str(ROOT/'tools/verify')]
import build_machine_canary as base
import measure_perky_full_map as f
from verify_perky_final_wrappers import decode_card
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 w=f.W;build=json.loads((w/'BUILD.json').read_text());version=build['version'];out=w/'upgrade';out.mkdir(exist_ok=True)
 image=w/'probe'/f'mainos_{version}.bin';assert sha(image)==build['main_sha256']
 elek=out/f'elek_{version}.bin';card=out/f'OCTATRACK_{version}.bin';midi=out/f'OCTATRACK_OS1.40C_{version}.syx'
 commands=[[str(base.EFT),'-i',str(base.STOCK_SYX),'-c','3',str(image),'-V',version,'-o',str(midi)],
  [sys.executable,str(base.MAKE_BIN),str(elek),'-o',str(card)],
  [sys.executable,str(ROOT/'tools/verify/verify_perky_final_wrappers.py'),'--mainos',str(image),'--elek',str(elek),'--card',str(card),'--midi',str(midi),'--eft',str(base.EFT),'--version',version,'--work',str(out/'roundtrip')]]
 with (out/'wrap.log').open('w') as log:
  for cmd in commands:subprocess.run(cmd,cwd=ROOT,env={**os.environ,'EFT_EMIT_CONTAINER':str(elek)},stdout=log,stderr=subprocess.STDOUT,check=True)
 assert card.stat().st_size<=base.CARD_OS_BIN_MAX,(card.stat().st_size,base.CARD_OS_BIN_MAX)
 damaged=bytearray(card.read_bytes());damaged[len(damaged)//2]^=1;bad=out/'corrupt.bin';bad.write_bytes(damaged)
 try:
  try:decode_card(bad)
  except SystemExit:pass
  else:raise AssertionError('corrupted real card accepted')
 finally:bad.unlink()
 r=dict(status='PASS_FINAL_MAIN_CARD_MIDI_ROUNDTRIP_SIZE_AND_CORRUPTION',version=version,commands=commands,main_sha256=sha(image),card_size_limit=base.CARD_OS_BIN_MAX,artifacts={k:dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for k,p in (('main',image),('elek',elek),('card',card),('midi',midi))},inputs={str(p):sha(p) for p in (base.STOCK_SYX,base.EFT,base.MAKE_BIN,Path(__file__),ROOT/'tools/verify/verify_perky_final_wrappers.py')},limits=['Packaging integrity; not hardware acceptance.'])
 (w/'WRAPPERS.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'],card.stat().st_size,flush=True)
if __name__=='__main__':main()
