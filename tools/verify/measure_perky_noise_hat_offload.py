#!/usr/bin/env python3
"""Execute split Noise Hat through HI08 with WT/WT, Slap and stock tracks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools','tools/build','tools/perky','tools/verify','modules/perky')]
import perky_noise_hat_offload as N
import ab_records as A
import measure_perky_cf_placement_integrated as combined

WORK=ROOT/'out/perky/hybrid/noise-hat-offload'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frames',type=int,default=4096)
    p.add_argument('--mode',type=int,choices=(0,1,2),action='append')
    p.add_argument('--kind',choices=('static','flex'),default='static')
    p.add_argument('--analyze-existing',action='store_true',help='Revalidate an already completed, hash-bound combined row')
    p.add_argument('--reference',action='store_true',help='Same-image CF control with the DSP service bypassed')
    args=p.parse_args()
    observer=WORK/'observer'
    if not observer.exists():observer.symlink_to(ROOT/'out/perky/hybrid/cf-placement-integrated/observer',target_is_directory=True)
    build=json.loads((WORK/'BUILD.json').read_text())
    appended=json.loads((WORK/'probe/p-records.json').read_text())
    peeks=['0:P:0,8192','1:P:0,8192','0:X:3800,616'];expected={}
    for core,tag in enumerate(('A','B')):
        upload=(WORK/f'dsp-{tag}.upload.bin').read_bytes();records,_=A.records(upload,A.BASE,len(upload))
        expected[core]={}
        for space,address,n,offset in records:
            if space!=0:continue
            words=[A.rd(upload,offset+3*i) for i in range(n)]
            if address<0x2000:expected[core].update({address+i:v for i,v in enumerate(words)})
            elif any(address==a and n==len(w) for a,w in appended[tag] if a>=0x30000):
                expected[core].update({address+i:v for i,v in enumerate(words)})
                peeks.append(f'{core}:P:{address:x},{n}')
    rows=[]
    for mode in args.mode or (0,1,2):
        name=f'WTWT-SLAP-HAT-{"CF-CONTROL" if args.reference else "OFFLOAD"}-M{mode+1}'
        combined.SCENARIOS[name]=([9,9,8,5],[1,2,0,mode],15)
        directory=WORK/'integrated-results'/(name+'-'+args.kind)
        symbols=combined.private.symbols(WORK/'probe/platform/runtime.elf')
        address=symbols['pk_nha_enabled'];switch=0 if args.reference else 1
        pokes=[f'{address+i:#x}={v:#x}' for i,v in enumerate(switch.to_bytes(4,'big'))]
        if args.analyze_existing:
            previous=directory/'OFFLOAD_ROW.json'
            row=json.loads((previous if previous.exists() else directory/'ROW.json').read_text())
            assert row['requested_frames']==args.frames
            for path,digest in row['inputs'].items():
                if path.endswith(('.bin','.elf')) and Path(path).exists():
                    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
        else:
            row=combined.run(WORK,name,args.kind,args.frames,image_name='PKNHA1',
                extra_dumps=(('pk_nha_calls',4),('pk_nha_samples',4),('pk_nha_failures',4),('pk_nha_phase',4)),
                extra_port_args=('--dsp-peek',';'.join(peeks),'--dsp-pcwatch',f'0:{build["irq_entry"]+2:x}'),extra_pokes=pokes,
                retain_audio_failure=True,extra_env={'NHA_EXACT_LIBRARY':str(observer/'oracle.dylib'),'NHA_EXACT_ENTRY':hex(symbols['pk_cf_nh_offload']),
                    'NHA_EXACT_REPORT':str(directory/'exact.json')})
        counts={n:int.from_bytes((directory/(n+'.bin')).read_bytes(),'big') for n in ('pk_nha_calls','pk_nha_samples','pk_nha_failures')}
        assert counts['pk_nha_failures']==0,counts
        if args.reference:assert counts['pk_nha_calls']==counts['pk_nha_samples']==0
        else:assert counts['pk_nha_calls']>0 and counts['pk_nha_samples']>0,counts
        assert counts['pk_nha_samples']<=row['native_samples'][3]
        log=(directory/'port.log').read_text()
        hits=int(re.search(r'dsp pcwatch:.*last (\d+) arrival',log)[1]);assert bool(hits)==(not args.reference),'wrong RPC activation'
        exact=json.loads((directory/'exact.json').read_text())
        assert exact['calls']==exact['checked']>0 and exact['mismatches']==exact['pending']==0,exact
        assert exact['native_samples']==row['native_samples'][3],('blind native witness',exact,row['native_samples'])
        loaded={core:{} for core in (0,1)}
        for core,address,words in re.findall(r'core (\d+) P:(?:0x)?([0-9a-f]+): ([0-9a-f ]+)',log):
            loaded[int(core)].update({int(address,16)+i:int(w,16) for i,w in enumerate(words.split())})
        for core in (0,1):
            for address,value in expected[core].items():
                if address in ((0x58c,0x59b) if core==0 else (0x371,0x380)):
                    assert value==0xffff and loaded[core][address] in (0x3fff,0x5fff)
                else:assert loaded[core][address]==value,(core,hex(address),'P write/ownership drift')
        driver_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        row.pop('driver_sha256',None)
        if not args.analyze_existing:row['execution_driver_sha256']=driver_sha
        row.update(offload_counts=counts,IRQ_arrivals_last=hits,exact=exact,reference=args.reference,
            panel_mode=mode+1,firmware_mode=(1,0,2)[mode],
            exact_observer_library_sha256=hashlib.sha256((observer/'oracle.dylib').read_bytes()).hexdigest(),
            analysis_driver_sha256=driver_sha,
            program_ownership='all loaded private/shared P exact except stock bank masks')
        (directory/'OFFLOAD_ROW.json').write_text(json.dumps(row,indent=2)+'\n');rows.append(row)
        summary='INTEGRATED_CF_CONTROL.json' if args.reference else 'INTEGRATED_OFFLOAD.json'
        (WORK/summary).write_text(json.dumps(dict(status='AUDIO_GATE_FAILED' if any(r['status']=='AUDIO_GATE_FAILED' for r in rows) else 'MEASURED_NOT_HARDWARE_QUALIFIED',rows=rows),indent=2)+'\n')
    assert all(r['status']=='FUNCTIONAL_MODEL_ROW' for r in rows),'Combined audio gate failed; timing and exactness evidence retained in OFFLOAD_ROW.json'


if __name__=='__main__':main()
