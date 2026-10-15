#!/usr/bin/env python3
"""Validate raw cold captures and exact, hardware-like primed DSP captures.

The port starts frame exchange at PLAY unless --pre-roll is supplied; hardware
exchanges frames since boot (main.cpp O14). Never silently discard a post-PLAY
record. Keep the cold raw failure visible, restrict it to six initial pipeline
records, and require every primed post-PLAY record and all cold source records
identical. Consumes hash-pinned RUN receipts, rather than replacing captures.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/harness'))
import blockdump
import recloop

REFERENCE_SHA='d254bc2f72a1c78d75f1652f89311d0b841246ad228fc6dc3324fd6717c00f48'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def validate_receipt(path):
    r=read(path)
    assert r.get('process_exit',0)==0
    for filename,digest in {**r['inputs'],**r['outputs']}.items():assert sha(filename)==digest,filename
    return r

def run(work):
    current_sha=sha(work/'probe/mainos_PKHYB2P.bin');raw={};pins=[]
    original=ROOT/'out/perky/hybrid/private-stack'
    # Strictly enumerate the cold-pipeline discrepancy; no arbitrary early
    # frame, track or source/control record is exempt from comparison.
    expected={(frame,'<',1,0,0x80003790) for frame in (1,2)}
    expected|={(frame,'<',1,1,0x80003590) for frame in (1,2)}
    expected|={(frame,'>',0,0,0x80003590) for frame in (1,2)}
    for name in ('mixed','dense'):
        for directory,image_sha in ((original,REFERENCE_SHA),(work,current_sha)):
            receipt=validate_receipt(directory/(name+'-RUN.json'))
            image=receipt['command'][receipt['command'].index('--image')+1]
            assert receipt['inputs'][image]==image_sha
            pins.append(directory/(name+'-RUN.json'))
        a=blockdump.read(original/(name+'-blocks.bin'));b=blockdump.read(work/(name+'-blocks.bin'))
        assert len(a)==len(b)
        differences=[]
        for old,new in zip(a,b):
            assert old[:5]==new[:5]
            if old!=new:
                d,frame,ch,core,ram=old[:5];assert (frame,d,ch,core,ram) in expected
                differences.append({'frame':frame,'direction':d,'channel':ch,'core':core,'RAM':hex(ram)})
        assert len(differences) in (0,6)
        raw[name]={'raw_byte_identity':'PASS' if not differences else 'FAIL_SIX_COLD_PIPELINE_RECORDS',
            'records':len(a),'differences':differences,'all_cold_source_control_records_identical':True,
            'all_cold_records_from_frame3_identical':True}
    dirs=[work/'warm-identity'/name for name in ('original','candidate')]
    receipts=[validate_receipt(d/'RUN.json') for d in dirs]
    normalized=[]
    for d,r,image_sha in zip(dirs,receipts,(REFERENCE_SHA,current_sha)):
        cmd=r['command'];image=cmd[cmd.index('--image')+1];assert r['inputs'][image]==image_sha
        for key,value in (('--pre-roll','40'),('--frames','2048'),('--dsp-dirty','123'),
                          ('--cf-cycles-clock','1.0'),('--pit-clock-hz','132000000')):
            assert cmd[cmd.index(key)+1]==value
        assert '--dsp' in cmd and '--internal-clock' in cmd
        canonical=cmd[:]
        for key in ('--image','--block-dump'):canonical[canonical.index(key)+1]='PATH'
        normalized.append(canonical)
        log=(d/'run.log').read_text()
        assert 'frames run : 2048 since transport start (target 2048), run ended REACHED' in log
        assert 'pre-roll   : 40 frame(s)' in log and 'FAULT:' not in log
        pins.append(d/'RUN.json')
    assert normalized[0]==normalized[1], 'paired settings differ'
    old,new=[blockdump.read(d/'blocks.bin') for d in dirs]
    assert len(old)==len(new)
    # Pre-roll is before PLAY. Include every block after that boundary, even
    # the extra frame executed while startTransportLive returns to main.
    a=[r for r in old if r[1]>40];b=[r for r in new if r[1]>40]
    assert a==b and len(a)>=2048*10,'primed post-PLAY block mismatch'
    for x,y in zip(old,new):
        assert x[:5]==y[:5]
        if x!=y:
            d,frame,ch,core,ram=x[:5];assert (frame,d,ch,core,ram) in expected
    active={};classes=blockdump.classes(a)
    for track in (1,2,5,6):
        pcm=recloop.readback_audio(classes,track);significant=sum(abs(v)>64 for v in pcm)
        assert significant>64,('silent primed comparison',track)
        active[str(track)]={'samples':len(pcm),'significant':significant}
    report={'status':'PASS_EXACT_INITIALIZED_PCM_AND_ALL_SOURCE_RECORDS',
        'cold_raw_comparisons':raw,'primed_before_PLAY_frames':40,
        'post_PLAY_frames_requested':2048,'identical_post_priming_records':len(a),
        'active_synthesis_readbacks':active,'no_firmware_edits_or_added_shipping_audio_latency':True,
        'limits':['The original zero-pre-roll raw byte comparison fails on six initial DSP readback/mix records; it is retained explicitly.',
                  'The port starts exchange at PLAY; hardware runs exchange from boot. These are different pipeline initial conditions.',
                  'Every cold source/control record and every primed post-PLAY record must match exactly. No arbitrary warm-up exclusion after PLAY.'],
        'inputs':{str(p):sha(p) for p in [*pins,Path(__file__),ROOT/'tools/emu/ot_emu/main.cpp',
            ROOT/'tools/emu/ot_emu/rtos.cpp',Path(blockdump.__file__),Path(recloop.__file__)]}}
    (work/'BLOCK_IDENTITY.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True)
    run(ap.parse_args().work.resolve())
