#!/usr/bin/env python3
"""Execute the exact three-engine ColdFire C source against native control laws."""
import random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'modules/perky')]
import verify_perky_light2_src_page as g
import simple_drum_control as law


def main():
    g.CONTROL=ROOT/'modules/perky/control_three_candidate.c'
    g.WORK=ROOT/'out/perky/three-controls';g.ALGO_COUNT=3;g.ALGO_ENGINE=(0,3,2)
    r=random.Random(3);cases=[]
    for i in range(300):
        cases.append(g.Case(f'controls{i}',track=(0,4)[i%2],part=(i//37)%4,
                            ping=i%2,trig=int(i%3!=0),algo=(i//10)%3 if i%7 else 127,
                            mode=r.randrange(4),knobs=tuple(r.randrange(128) for _ in range(4)),dirty=r.randrange(256),hidden=10))
    data=g.execute(cases)
    assert data,'host execution skipped'
    g.check_descriptor(data['desc']);g.check_admission(data['admit'])
    states={};part=None
    for i,case in enumerate(cases):
        if part!=case.part:states={};part=case.part
        engine=g.ALGO_ENGINE[case.algo] if case.algo<3 else 0
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
        expected=[0x504b0000,0x59310000|case.trig,0,0]+[g.pair(v) for v in values]+[(mode<<16)|int(decay>=4080),engine]
        words=g.record_words(data['rows'],i,case)
        assert words==expected,(i,case.name,'controls/mode/engine/record',words,expected)
        states[case.track]=s
    print(f'[PASS] three-engine ColdFire controls: {len(cases)} executed automation/trigger/family/Part/dirty-LFO/ALGO-clamp cases; full DSP records exact against original control laws')


if __name__=='__main__':main()
