#!/usr/bin/env python3
"""Execute real production pk_render in an isolated native memory fixture.

The x86-64 runner uses Rosetta on Apple Silicon because a 4-GB PAGEZERO in the
Python/arm64 process prevents mapping the Octatrack address fixture. All memory
is private and anonymous. Full ColdFire port execution is a separate gate.
"""
from pathlib import Path
import platform,random,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'modules/perky'))
import simple_drum_transport as model
OUT=ROOT/'out/perky/simple-production-transport'

def main():
    OUT.mkdir(parents=True,exist_ok=True);exe=OUT/'runner-x86'
    target_flags=['-arch','x86_64','-Wl,-pagezero_size,0x1000'] if platform.system()=='Darwin' else []
    subprocess.run(['cc',*target_flags,'-O2',str(ROOT/'modules/perky/control.c'),str(ROOT/'tools/harness/perky_cf/production_transport.c'),'-o',str(exe)],check=True,capture_output=True)
    states=[model.State.fresh() for _ in range(8)];rng=random.Random(0x503003);rows=[];expected=[]
    for i in range(1024):
        t=i%8;raw=tuple(rng.choice([0,127,rng.randrange(128)]) for _ in range(4)) if i%16<8 else (64,64,64,64);mode=(i//8)%3;trig=i%4!=0
        params=list(raw)+[0,0,mode,0,0,0,0,2]
        if i%33==0:
            params[11]=10;want=bytes(params);states[t]=model.State.fresh()
        else:want=states[t].prepare(raw,mode,trigger=trig)
        rows.append(bytes(params+[t,int(trig)]));expected.append(want)
    (OUT/'input').write_bytes(b''.join(rows))
    subprocess.run([str(exe),str(OUT/'input'),str(OUT/'output')],check=True,capture_output=True)
    data=(OUT/'output').read_bytes();assert len(data)==len(rows)*12
    for i,want in enumerate(expected):
        got=data[i*12:(i+1)*12];assert got==want,(i,got.hex(),want.hex())
    print(f'Production pk_render transport: PASS ({len(rows)} real writer calls; eight tracks, all modes, prepared values and unchanged Noise/Tone)')
if __name__=='__main__':main()
