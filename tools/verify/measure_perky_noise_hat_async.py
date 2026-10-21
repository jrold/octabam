#!/usr/bin/env python3
"""Measure same-frame cooperative offload, retaining all failed gates."""
import argparse,json,hashlib,re
from pathlib import Path
import measure_perky_cf_placement_integrated as c
import ab_records as A
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-async'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--frames',type=int,default=4096)
    p.add_argument('--mode',type=int,choices=(0,1,2),action='append');p.add_argument('--reference',action='store_true')
    a=p.parse_args();s=c.private.symbols(WORK/'probe/platform/runtime.elf');rows=[]
    appended=json.loads((WORK/'probe/p-records.json').read_text());peeks=['0:P:0,8192','1:P:0,8192'];expected={}
    for core,tag in enumerate(('A','B')):
        data=(WORK/f'dsp-{tag}.upload.bin').read_bytes();records,_=A.records(data,A.BASE,len(data));expected[core]={}
        for space,at,n,off in records:
            if space:continue
            if at<0x2000 or any(at==x and n==len(words) for x,words in appended[tag] if x>=0x30000):
                expected[core].update({at+i:A.rd(data,off+3*i) for i in range(n)})
                if at>=0x30000:peeks.append(f'{core}:P:{at:x},{n}')
    for mode in a.mode or (0,1,2):
        name=f'WTWT-SLAP-HAT-ASYNC-{"CF" if a.reference else "DSP"}-M{mode+1}';c.SCENARIOS[name]=([9,9,8,5],[1,2,0,mode],15)
        directory=WORK/'integrated-results'/(name+'-static')
        switch=int(not a.reference);pokes=[f'{s["pk_nha_enabled"]+i:#x}={v:#x}' for i,v in enumerate(switch.to_bytes(4,'big'))]
        names=('pk_nha_calls','pk_nha_samples','pk_nha_failures','pk_nhaa_polls','pk_nhaa_poll_words','pk_nhaa_cleanup_waits','pk_nhaa_frame_done')
        row=c.run(WORK,name,'static',a.frames,image_name='PKNHB1',retain_audio_failure=True,extra_dumps=[(n,4) for n in names],extra_pokes=pokes,
            extra_port_args=('--dsp-peek',';'.join(peeks)),
            extra_env={'NHA_EXACT_LIBRARY':str(WORK/'observer/oracle.dylib'),'NHA_EXACT_ENTRY':hex(s['pk_nhaa_begin']),
                       'NHA_EXACT_COMPLETE':hex(s['pk_nhaa_complete']),'NHA_EXACT_REPORT':str(directory/'exact.json')})
        counts={n:int.from_bytes((directory/(n+'.bin')).read_bytes(),'big') for n in names};exact=json.loads((directory/'exact.json').read_text())
        assert counts['pk_nha_failures']==0 and counts['pk_nhaa_frame_done']==1,counts
        assert bool(counts['pk_nha_calls'])==bool(switch),counts
        assert exact['calls']==exact['checked']>0 and exact['mismatches']==exact['pending']==0,exact
        assert exact['native_samples']==row['native_samples'][3],exact
        loaded={0:{},1:{}}
        for core,at,words in re.findall(r'core (\d+) P:(?:0x)?([0-9a-f]+): ([0-9a-f ]+)',(directory/'port.log').read_text()):
            loaded[int(core)].update({int(at,16)+i:int(v,16) for i,v in enumerate(words.split())})
        for core in (0,1):
            for at,v in expected[core].items():
                if at in ((0x58c,0x59b) if core==0 else (0x371,0x380)):assert v==0xffff and loaded[core][at] in (0x3fff,0x5fff)
                else:assert loaded[core][at]==v,(core,hex(at),'program drift')
        row.update(transport_counts=counts,exact=exact,panel_mode=mode+1,firmware_mode=(1,0,2)[mode],reference=a.reference,
                   driver_sha256=sha(Path(__file__)),program_ownership='all loaded private/shared P exact except stock bank masks',
                   nonblocking_fast_path=counts['pk_nhaa_cleanup_waits']==0)
        (directory/'ASYNC_ROW.json').write_text(json.dumps(row,indent=2)+'\n');rows.append(row)
        (WORK/('CONTROL.json' if a.reference else 'INTEGRATED.json')).write_text(json.dumps(dict(rows=rows),indent=2)+'\n')
    assert all(r['status']=='FUNCTIONAL_MODEL_ROW' for r in rows),'stock audio gate failed; evidence retained'
    assert all(r['nonblocking_fast_path'] for r in rows),'cleanup waits required; candidate not admitted as nonblocking'
if __name__=='__main__':main()
