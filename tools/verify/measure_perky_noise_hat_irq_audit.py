#!/usr/bin/env python3
"""Reproduce the old pulse failure with read-only DSP continuation witnesses."""
import argparse,hashlib,json
from pathlib import Path
import measure_perky_cf_placement_integrated as c
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-irq-audit'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dirty',type=int,default=123);p.add_argument('--frames',type=int,default=128)
    p.add_argument('--expect-audio-failure',action='store_true');g=p.add_mutually_exclusive_group();g.add_argument('--clear-amp-phase',action='store_true');g.add_argument('--clear-amp-block',action='store_true');a=p.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    probe=WORK/'probe'
    if not probe.exists():probe.symlink_to(ROOT/'out/perky/hybrid/noise-hat-offload/probe',target_is_directory=True)
    name=f'PULSE-AUDIT-SEED-{a.dirty}'+('-AMP-PHASE-RESET' if a.clear_amp_phase else '-AMP-BLOCK-RESET' if a.clear_amp_block else '');c.SCENARIOS[name]=([9,9,8,5],[1,2,0,2],15)
    audit=WORK/(name+'.json')
    row=c.run(WORK,name,'static',a.frames,image_name='PKNHA1',retain_audio_failure=True,
        extra_port_args=('--dsp-dirty',str(a.dirty)),extra_env={'NHA_IRQ_AUDIT':str(audit),**({'NHA_CLEAR_STOCK_AMP_PHASE':'1'} if a.clear_amp_phase else {}),**({'NHA_CLEAR_STOCK_AMP_BLOCK':'1'} if a.clear_amp_block else {})})
    witness=json.loads(audit.read_text())
    assert witness['calls']==witness['checked']>0 and witness['register_changes']==0,witness
    assert all(int(k) in ((1<<24)|0x81,(1<<24)|0x82,(1<<24)|0x83) for k in witness['write_pages']),witness
    assert len(witness['init_calls'])==16 and all(n==1 for n in witness['init_calls'].values()),witness['init_calls']
    assert bool(row['audio_failures'])==a.expect_audio_failure,row['audio_failures']
    report=dict(status='EXPECTED_STOCK_AUDIO_FAILURE_REPRODUCED' if a.expect_audio_failure else 'ALL_AUDIO_CHAINS_PASS',
        seed=a.dirty,diagnostic_four_AMP_phase_words_cleared=a.clear_amp_phase,diagnostic_128_AMP_words_cleared=a.clear_amp_block,row=row,witness=witness,source_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in
            (Path(__file__),ROOT/'tools/harness/perky_cf/noise_hat_irq_audit.h',ROOT/'tools/verify/build_perky_noise_hat_irq_audit.py')})
    (WORK/(name+'-REPORT.json')).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
