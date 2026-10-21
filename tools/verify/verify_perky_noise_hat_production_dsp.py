#!/usr/bin/env python3
"""Actual production program: persistent author audio, import and reset gates."""
import json,struct,subprocess,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/verify','tools/perky','tools/build','tools')]
import perky_noise_hat_production as program
import verify_perky_noise_hat_taps as gate
import verify_perky_noise_hat_handoff_import as imports
W=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 gate.N=program;gate.WORK=W;gate.main()
 imports.W=W;imports.main()
 out=W/'reset-gate';out.mkdir(exist_ok=True)
 # Execute the exact final upload, including its original-initializer table.
 data=(W/'import-gate/initial.data').read_text()
 initial=[]
 for line in data.splitlines():
  f=line.split()
  if f[:2]==['X','3800']:initial=[int(x,16)&65535 for x in f[2:182]]
 assert len(initial)==180
 poison='X 3800 '+' '.join(['a5a5']*180)+'\nX 3970 '+' '.join(['a5a5']*6)+'\nX 3a23 '+' '.join(['7f']*3)+'\n'
 (out/'initial.data').write_text(data+poison)
 packets=[]
 # Zero-length segments still MUST perform reset, including inactive limbs.
 for i in range(96):
  mode=i%3
  if i%2==0:packets.append([0x4e54,i+1,mode<<5,0,0,((mode+1)%3<<5)|(1<<9)|(1<<7),0,0])
  else:packets.append([0x4e54,i+1,(mode<<5)|(1<<9)|(1<<7),0,0,((mode+1)%3)<<5,0,0])
 (out/'requests').write_text(''.join(' '.join(f'{v:x}' for v in p)+'\n' for p in packets))
 host=W/'persistent-gate/taps_host';entry=json.loads((W/'program/resident-symbols.json').read_text())['source_entry']
 cmd=[str(host),'-code',str(W/'import-gate/code.bin'),'-entry',f'{entry:x}','-data',str(out/'initial.data'),'-requests',str(out/'requests'),'-out',str(out/'response.bin')]
 subprocess.run(cmd,check=True)
 response=(out/'response.bin').read_bytes();assert len(response)==96*504
 for i in range(96):
  row=response[i*504:(i+1)*504]
  assert list(struct.unpack_from('<180H',row,120))==initial,(i,'resident reset')
  assert list(struct.unpack_from('<6H',row,480))==[0,0,1,0,0,0],(i,'side reset')
  clock=struct.unpack_from('<3I',row,492);assert clock[:2]==(0,0),(i,'clock reset',clock)
  assert struct.unpack_from('<3H',row,72)==(0x4e52,i+1,0)
 result=dict(status='PASS_PERSISTENT_AUTHOR_IMPORT_AND_RESIDENT_EPOCH_RESET',reset_cases=96,
  reset_clock_carry_rule='have=0; carry not observed until next native conversion',
  persistent=json.loads((W/'PERSISTENT_GATE.json').read_text()),imports=json.loads((W/'IMPORT_GATE.json').read_text()),
  inputs={str(p):sha(p) for p in (W/'dsp-A.upload.bin',W/'program/resident-symbols.json')},
  source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/perky/perky_noise_hat_production.py')},commands=[cmd],hardware_validated=False)
 (W/'PRODUCTION_DSP_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
