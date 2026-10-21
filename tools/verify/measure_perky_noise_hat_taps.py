#!/usr/bin/env python3
"""Paired native-clock full-workload rows for current-block tap-DMA Noise Hat."""
import argparse,json,re,hashlib
from pathlib import Path
import measure_perky_cf_placement_integrated as c
import ab_records as A
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-taps'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--frames',type=int,default=4096)
    p.add_argument('--mode',type=int,choices=(0,1,2),action='append');p.add_argument('--reference',action='store_true');a=p.parse_args()
    syms=c.private.symbols(WORK/'probe/platform/runtime.elf');dsp=json.loads((WORK/'program/resident-symbols.json').read_text())
    peeks=['0:P:0,8192','1:P:0,8192'];expected={}
    appended=json.loads((WORK/'probe/p-records.json').read_text())
    for core,tag in enumerate(('A','B')):
        data=(WORK/f'dsp-{tag}.upload.bin').read_bytes();records,_=A.records(data,A.BASE,len(data));expected[core]={}
        for space,at,n,off in records:
            if space:continue
            if at<0x2000 or any(at==x and n==len(words) for x,words in appended[tag] if x>=0x30000):
                expected[core].update({at+i:A.rd(data,off+3*i) for i in range(n)})
                if at>=0x30000:peeks.append(f'{core}:P:{at:x},{n}')
    results=[]
    for mode in a.mode or (0,1,2):
        name=f'WTWT-SLAP-HAT-TAPS-{"CF" if a.reference else "DSP"}-M{mode+1}'
        c.SCENARIOS[name]=([9,9,8,5],[1,2,0,mode],15)
        directory=WORK/'integrated-results'/(name+'-static')
        extra={}
        if not a.reference:extra=dict(NHR_EXACT_LIBRARY=str(WORK/'observer/resident-oracle.dylib'),
            NHR_EXPECT=hex(syms['pk_nhr_expect']),NHR_ACCEPT=hex(syms['pk_nhr_accept']),NHR_FRAME=hex(syms['pk_nhr_frame']),
            NHR_DSP_COMMIT=hex(dsp['commit']),NHR_EXACT_REPORT=str(directory/'exact.json'),NHR_MAIL=hex(syms['pk_nhr_mail']))
        names=('pk_nhr_sequence','pk_nhr_dma_reads','pk_nhr_dma_done','pk_nhr_failures','pk_nhr_consumed','pk_nhr_packet_words','pk_nhr_initializations','pk_nhr_lag_min','pk_nhr_lag_max','pk_nht_pending_max','pk_nht_tap_words')
        enabled=int(not a.reference);pokes=[f'{syms["pk_nhr_enabled"]+i:#x}={v:#x}' for i,v in enumerate(enabled.to_bytes(4,'big'))]
        row=c.run(WORK,name,'static',a.frames,image_name='PKNHD1',retain_audio_failure=True,extra_dumps=[(n,4) for n in names]+[('pk_nhr_mail',48)],extra_pokes=pokes,extra_env=extra,extra_port_args=('--dsp-peek',';'.join(peeks)))
        counts={n:int.from_bytes((directory/(n+'.bin')).read_bytes(),'big') for n in names}
        exact=json.loads((directory/'exact.json').read_text()) if not a.reference else None
        loaded={0:{},1:{}}
        for core,at,words in re.findall(r'core (\d+) P:(?:0x)?([0-9a-f]+): ([0-9a-f ]+)',(directory/'port.log').read_text()):
            loaded[int(core)].update({int(at,16)+i:int(v,16) for i,v in enumerate(words.split())})
        for core in (0,1):
            for at,v in expected[core].items():
                if at in ((0x58c,0x59b) if core==0 else (0x371,0x380)):assert v==0xffff and loaded[core][at] in (0x3fff,0x5fff)
                else:assert loaded[core][at]==v,(core,hex(at),'program drift')
        if exact:
            hat=row['source_and_post_FX']['T6']
            hat['control_record_significant']=hat['source_significant']
            hat.update(source_kind='DSP controls/taps; PCM witnessed before AMP',source_significant=exact['source_significant'],source_peak=exact['source_peak'])
        row.update(program_ownership='all loaded private/shared P exact except stock bank masks',driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),transport_counts=counts,exact=exact,panel_mode=mode+1,firmware_mode=(1,0,2)[mode],reference=a.reference,
                   added_latency_OT_samples=0,feedback_latency_frames=counts['pk_nhr_lag_max']+1 if not a.reference else 0,dynamic_state_round_trip_words=0,return_payload_words_per_frame=24,additional_DMA_words_per_frame=0)
        (directory/'TAPS_ROW.json').write_text(json.dumps(row,indent=2)+'\n');results.append(row)
        (WORK/('CONTROL.json' if a.reference else 'INTEGRATED.json')).write_text(json.dumps(dict(rows=results),indent=2)+'\n')
        print(json.dumps(dict(name=name,status=row['status'],counts=counts,exact=exact,isr=row.get('full_ISR'))),flush=True)
        if row['status']!='FUNCTIONAL_MODEL_ROW':raise RuntimeError('all-track audio gate failed; row retained')
        if counts['pk_nhr_failures']:raise RuntimeError('resident transport/packet failure; row retained')
        if exact and (any(exact[k] for k in ('source_PCM_mismatches','state_mismatches','feedback_mismatches','clock_mismatches','ring_mismatches')) or not exact['source_frames'] or exact['source_significant']<=64):raise RuntimeError('resident exactness failure; row retained')
if __name__=='__main__':main()
