#!/usr/bin/env python3
"""Exercise stock scene morph and actual panel-fader delivery with four synths."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/verify'))
import verify_perky_hybrid_private_stack as private
import verify_perky_hybrid_workload as workload
import stems_panel as panel
import emu_card
import blockdump
import recloop


def run(work):
    out=work/'scene-panel';out.mkdir(parents=True,exist_ok=True)
    project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
    tone=out/'tone.wav';workload.make_tone(tone)
    card=workload.stage_integrated_fixture(project,out/'fixture','snare','bass',tone_path=tone)
    tree=out/'tree';tree.mkdir()
    for name,data in emu_card.extract_image(card.read_bytes()).items():
        path=tree/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    a=(24,56,32,48);b=(104,112,96,120)
    for bank in tree.rglob('bank01.*'):
        if bank.suffix not in ('.work','.strd'):continue
        data=bytearray(bank.read_bytes())
        for part in range(workload.otp.NPARTS_ALL):
            base=workload.otp.PART_BASE+part*workload.otp.PART_STRIDE+9
            data[base+0x10:base+0x12]=bytes((0,1))
            for track in (0,1,4,5):
                data[base+0x11a+24*track+3:base+0x11a+24*track+6]=bytes(3)
                for scene,values in enumerate((a,b)):
                    at=base+0x662+(scene*8+track)*32
                    data[at:at+32]=bytes([255])*32
                    for index,value in zip((0,1,3,4),values):data[at+index]=value
        for pattern in range(4):
            for track in (0,1,4,5):
                at=workload.otp.trac_off(pattern,track)+0x59
                data[at:at+64*32]=bytes([255])*(64*32)
        data[-2:]=(sum(data[0x10:-2])&65535).to_bytes(2,'big');bank.write_bytes(data)
    card.write_bytes(emu_card.build_image(tree));shutil.rmtree(tree)
    image=work/'probe/mainos_PKHYB2P.bin';elf=work/'probe/platform/runtime.elf'
    syms=private.symbols(elf);sizes=subprocess.check_output(['m68k-elf-nm','-S',str(elf)],text=True)
    size=next(int(line.split()[1],16) for line in sizes.splitlines() if line.split()[-1]=='pk_hybrid_voices')//2
    assert size==1974,'review the production voice/control layout before changing offsets'
    # Last pk4_control occupies 22 bytes, followed by two RNG longs and four
    # active/pad bytes. Offset is guarded against the actual target size.
    raw_offset=size-12-22+16
    original_card=out/'card-input.img';shutil.copyfile(card,original_card)
    inputs={str(p):private.sha(p) for p in (image,elf,original_card,Path(__file__),work/'observer/ot_emu_safety')}
    import os
    os.environ.update(private.environment(work,'scene-panel'))
    panel.PORT_BIN=work/'observer/ot_emu_safety';rows=[]
    with panel.MenuPort(image,card,'OCTABAM','RIG',True,log_path=out/'port.log',
        extra=('--load-ms','90000','--dsp-dirty','123','--pit-clock-hz','132000000',
               '--cf-cycles-clock','1.0','--block-dump',str(out/'blocks.bin'))) as p:
        p.settle();p.poke(0x46c00010,b'\x01')
        # ab_fixture deliberately mutes both scenes. Enable them through
        # real stock keys before asking their lock values to reach synthesis.
        for key,flag in [('scene_a',0x80000006),('scene_b',0x80000007)]:
            if p.peek(flag,1)[0]:p.chord('func',key,settle=60)
            assert p.peek(flag,1)==b'\x00',('scene remained muted',key)
        p.press('play',hold=30,settle=400)
        for pos in (0,32,64,96,127,96,64,32,0):
            p.rt.uart64.rx.extend([0x40,2*(127-pos)+1]);p.run(60)
            xf=p.long(0x460d16c8);assert xf==127-pos,('undelivered panel fader',pos,xf)
            raw=[list(p.peek(syms['pk_hybrid_voices']+instance*size+raw_offset,4)) for instance in (0,1)]
            native=[list(p.peek(syms['simple_controls']+track*40+32,4)) for track in (0,4)]
            if pos in (0,127):
                expected=list(a if pos==0 else b)
                assert raw==[expected,expected],('CF scene endpoint delivery',pos,raw,expected)
                assert native==[expected,expected],('DSP scene endpoint delivery',pos,native,expected)
            rows.append({'position':pos,'stock_fader':xf,'CF_raw_controls':raw,'DSP_raw_controls':native,'frames':p.rt.frames})
            (out/'EVENTS.json').write_text(json.dumps(rows,indent=2)+'\n')
        p.press('stop',hold=20,settle=60)
        # Stop releasing new test frames only after STOP, then finish the
        # current exception. A timed interactive run can end inside an ISR.
        p.rt.frame=False;p.run(2)
    for _ in range(100):
        try:stack=private.read(work/'scene-panel-stack.json');break
        except (OSError,json.JSONDecodeError):time.sleep(.1)
    else:raise AssertionError('observer did not close')
    assert stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
    context=private.read(work/'scene-panel-private.json')
    assert stack['frames']==stack['frame_returns']==context['switched']==context['restored']
    assert context['in_flight_at_capture_end']==context['ownership_register_frame_or_mask_violations']==context['fence_writes']==0
    classes=blockdump.classes(blockdump.read(out/'blocks.bin'))
    active={t:sum(abs(v)>64 for v in recloop.readback_audio(classes,t)) for t in range(1,9)}
    assert all(n>64 for n in active.values()),active
    result={'status':'PASS_ACTUAL_SCENE_FADER_DELIVERY','events':rows,'active_all_eight_track_samples':active,
        'full_ISR_max_cycles':stack['full_ISR_max_cycles'],'modeled_deadline_misses':0,'panel_ring_max':stack['panel_ring_max'],
        'inputs':inputs,'mutable_card_output':{'path':str(card),'sha256':private.sha(card)},
        'limits':['Scene fixture deliberately disables LFOs and step locks to isolate scene endpoint delivery. The separate sustained matrix exercises LFOs and p-locks.','Hardware UI latency remains unqualified.']}
    assert inputs=={path:private.sha(path) for path in inputs},'immutable input drift'
    (work/'SCENE_PANEL.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True)
    run(ap.parse_args().work.resolve())
