#!/usr/bin/env python3
"""Original ARM control corners and candidate real pk_render Fold records."""
from pathlib import Path
import platform,random,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'modules/perky'))
import fold_drum_transport as fold
import fold_drum_compact as compact
import simple_drum_transport as simple
OUT=ROOT/'out/perky/fold-production-transport'

def main():
    for mode in range(3):
        for corner,raw in enumerate((0,64,127)):
            record=fold.State.fresh().prepare((raw,)*4,mode,trigger=True)
            v=compact.FoldDrum1.from_arm((ROOT/f'out/perky/engine-fixtures/engine-1-mode-{mode+1}-corner-{corner}/wrapper-window-before.bin').read_bytes()[0xc4:0xc4+0xf4])
            assert [int.from_bytes(record[i:i+2],'big') for i in range(0,8,2)]==[v.words[i] for i in (32,20,36,33)]
            assert record[9]==v.words[14] and [1,2,0][record[8]]==v.words[34]
            assert v.words[31]==43 and v.words[38]==2
    OUT.mkdir(parents=True,exist_ok=True);exe=OUT/'runner'
    flags=['-arch','x86_64','-Wl,-pagezero_size,0x1000'] if platform.system()=='Darwin' else []
    subprocess.run(['cc',*flags,'-DPK_FOLD_CANDIDATE=1','-O2',str(ROOT/'modules/perky/control.c'),str(ROOT/'tools/harness/perky_cf/production_transport.c'),'-o',str(exe)],check=True,capture_output=True)
    states=[None]*8;families=[None]*8;rng=random.Random(0xf01d);rows=[];expected=[]
    for i in range(2048):
        track=i%8;engine=(0,2,10)[(i//8)%3];mode=(i//24)%3;trig=i%4!=0
        raw=tuple(rng.choice([0,127,rng.randrange(128)]) for _ in range(4))
        # The row is row[0..5]=fp[] and row[6..11]=page slots. `pk_render`
        # takes MODE from p[MODE_SLOT] = p[4] = fp[4] (MODE_SLOT=4, the
        # visible main SRC-page MODE parameter), NOT from page slot 0 --
        # so the mode belongs in row[4]. Writing it at row[6] left fp[4]=0
        # and every row was driven with MODE 0: the oracle was told the
        # requested mode while the machine was told 0, so every mode!=0
        # row mismatched on record[8].
        params=list(raw)+[mode,0,0,0,0,0,0,engine]
        if engine==10:
            # No prepare runs for this model, so the record is the row
            # verbatim EXCEPT that pk_render itself sets p[6]=p[MODE_SLOT]
            # before it dispatches; nothing overwrites it on this path.
            passthrough=list(params);passthrough[6]=mode
            want=bytes(passthrough);states[track]=None
        else:
            if families[track]!=engine or states[track] is None:states[track]=(fold.State if engine==0 else simple.State).fresh()
            want=states[track].prepare(raw,mode,trigger=trig)
        families[track]=engine;rows.append(bytes(params+[track,int(trig)]));expected.append(want)
    (OUT/'input').write_bytes(b''.join(rows));subprocess.run([str(exe),str(OUT/'input'),str(OUT/'output')],check=True,capture_output=True)
    data=(OUT/'output').read_bytes();assert len(data)==len(expected)*12
    for i,want in enumerate(expected):assert data[i*12:i*12+12]==want,(i,data[i*12:i*12+12].hex(),want.hex())
    print('Fold candidate transport: PASS (9 original ARM mode/control corners, 2048 actual production writer calls, eight tracks, all modes, switches among Fold/Simple/Noise)')
if __name__=='__main__':main()
