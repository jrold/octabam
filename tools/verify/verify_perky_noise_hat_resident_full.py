#!/usr/bin/env python3
"""Check delayed source PCM against complete original synthesis + rational clock."""
import json,os
from pathlib import Path
import measure_perky_noise_hat_resident as measured
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-resident-full'
def main():
    measured.WORK=WORK
    syms=measured.c.private.symbols(WORK/'probe/platform/runtime.elf')
    os.environ['NHR_OUTPUT']=hex(syms['placement_output']+3*16*4)
    os.environ['NHR_MAIL']=hex(syms['pk_nhr_mail'])
    measured.main()
    rows=[]
    for p in sorted((WORK/'integrated-results').glob('*/exact.json.full.json')):
        r=json.loads(p.read_text());rows.append(dict(row=p.parent.name,**r))
    report=dict(status='PASS_COMPLETE_DELAYED_SOURCE_PCM' if rows and all(r['checked_frames']>0 and r['source_PCM_mismatches']==r['clock_mismatches']==0 for r in rows) else 'FAIL_COMPLETE_DELAYED_SOURCE_PCM',
        rows=rows,scope='Same firmware image. Original complete CF render including ring, plus independent rational native clock, compared to delayed target source PCM before AMP/FX.')
    (WORK/'FULL_GATE.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['status'].startswith('PASS'),report
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
