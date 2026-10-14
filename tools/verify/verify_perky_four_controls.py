#!/usr/bin/env python3
"""Execute the exact four-engine ColdFire C source against native control laws."""
import random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'modules/perky')]
import verify_perky_light2_src_page as g
import simple_drum_control as law


def main():
    g.CONTROL=ROOT/'modules/perky/control_four_candidate.c'
    g.WORK=ROOT/'out/perky/four-controls';g.ALGO_COUNT=4;g.ALGO_ENGINE=(0,3,2,5)
    r=random.Random(3);cases=[]
    for i in range(1024):
        cases.append(g.Case(f'controls{i}',track=(0,4)[i%2],part=(i//37)%4,
                            ping=i%2,trig=int(i%3!=0),algo=(i//10)%4 if i%7 else 127,
                            mode=r.randrange(4),knobs=tuple(r.randrange(128) for _ in range(4)),dirty=r.randrange(256),hidden=10))
    for track in (0,4):
        for base in range(4):
            for held in range(4):
                for algo in (base,held,base):
                    cases.append(g.Case(f'lock{len(cases)}',track=track,part=0,ping=0,trig=1,algo=algo,mode=0,knobs=(64,64,64,64),dirty=125,hidden=10))
    data=g.execute(cases)
    assert data,'host execution skipped'
    g.check_descriptor(data['desc']);g.check_admission(data['admit'])
    states={};part=None
    for i,case in enumerate(cases):
        if part!=case.part:states={};part=case.part
        engine=g.ALGO_ENGINE[case.algo] if case.algo<4 else 0
        s=states.get(case.track)
        if s is None or s['engine']!=engine:s={'engine':engine,'prepared':[0]*4,'targets':[0]*4,'last':None,'mode':None}
        mode=min(case.mode,2)
        def update():s['prepared']=[law.smooth_control(x,y) for x,y in zip(s['prepared'],s['targets'])]
        if s['last']!=case.knobs or s['mode']!=mode:
            update();update();s['targets']=[law.panel_to_target(v) for v in case.knobs]
            for _ in range(16):update()
            s['last']=case.knobs;s['mode']=mode
        if case.trig:update()
        tune,decay,p1,p2=s['prepared']
        values=[tune,law.amplitude_decay_rate(decay),law.pitch_envelope_decay_rate(p1),p2>>1] if engine==2 else [tune,law._envelope_decay_rate(law._time_parameter(decay),50,7280),p1,p2]
        if engine==5:values=[tune,law._envelope_decay_rate(law._time_parameter(decay),50,7280),(0xfffff//((43244160-9552*p1)>>12))&65535,p2]
        wire_mode=mode
        gate=int(decay>=4080)
        if engine==5:
            q=0x400b+12*(4095-p1)
            frequency=((q&8191)+8192)>>(13-((q>>13)&7))
            wire_mode|=gate<<7
            gate=frequency-1
        expected=[0x504b0000,0x59310000|case.trig,0,0]+[g.pair(v) for v in values]+[(wire_mode<<16)|gate,engine]
        words=g.record_words(data['rows'],i,case)
        assert words==expected,(i,case.name,'controls/mode/engine/record',words,expected)
        states[case.track]=s
    print(f'[PASS] four-engine ColdFire controls: {len(cases)} executed automation/trigger/family/Part/dirty-LFO/ALGO-clamp cases; full DSP records exact against original control laws')


if __name__=='__main__':main()
