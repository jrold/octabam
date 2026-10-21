#!/usr/bin/env python3
"""Run the existing persistent author/ARM/clock gate on the handoff program."""
import verify_perky_noise_hat_taps as gate
import perky_noise_hat_handoff as program
if __name__=='__main__':
 gate.N=program
 gate.WORK=gate.ROOT/'out/perky/hybrid/noise-hat-handoff'
 gate.main()
 import json,hashlib
 w=gate.WORK;r=json.loads((w/'PERSISTENT_GATE.json').read_text())
 r['candidate_source_sha256']={str(p.relative_to(gate.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (gate.ROOT/'tools/perky/perky_noise_hat_handoff.py',gate.ROOT/'tools/verify/verify_perky_noise_hat_handoff_dsp.py')}
 r['program_sha256']=hashlib.sha256((w/'persistent-gate/program.bin').read_bytes()).hexdigest()
 (w/'PERSISTENT_GATE.json').write_text(json.dumps(r,indent=2)+'\n')
