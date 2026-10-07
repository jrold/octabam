#!/usr/bin/env python3
"""Execute experimental Fold Drum record seam; no ColdFire or hardware claim."""
from pathlib import Path
import struct,sys
import verify_perky_controlled_voice_exec as c
import verify_perky_synth_seam_exec as old
ROOT=c.ROOT
sys.path[:0]=[str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
import build_fold_candidate as candidate
import fold_drum_compact as fold
OUT=ROOT/'out/perky/fold-seam'
SLOT=0;RECORD=[]

def main():
    global SLOT,RECORD
    target=ROOT/'out/perky/fold-multi';source,fresh=candidate.build(target)
    c.OUT=OUT;OUT.mkdir(parents=True,exist_ok=True);c.build_host();c.CYCLE_METER=True
    wrapper=old.WRAPPER;start=wrapper.index('        move #>$000100,r1');end=wrapper.index('        move r4,x:>$209',start)
    wrapper=wrapper[:start]+wrapper[end:]
    wrapper=wrapper.replace('        move b1,x:(r4+$3)','        or #>$030000,b\n        move b1,x:(r4+$3)')
    binary,entry=c.assemble(c.source_builder.force_long_local_jsr(wrapper)+'\n'+source.replace('@CONT@','$000400'))
    labels={p[0]:int(p[1],16) for p in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}
    tables=c.words(target/'tables.words');initial=c.words(target/'state_init.words')
    def data(path,state,table):
        path.write_text('X 3800 '+' '.join(f'{v:06x}' for v in state)+'\nX 3900 '+' '.join(['000000']*117)+'\nX 500 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{v|0x030000:06x}' for v in RECORD)+'\n'+f'X 418 {SLOT:06x}\nX 20b 004080\nP 400 0bf080 {labels["pkse_finish"]:06x} 00000c\nY 7a5 '+' '.join(f'{v:06x}' for v in table)+'\nX 3964 00ffff '+' '.join(['000000']*16)+'\n')
        return state[232:236]
    c.write_data=data
    assets=ROOT/'out/perky/simple-drum-assets'
    pitch=(assets/'pitch.bin').read_bytes();e1=(assets/'envelope1.bin').read_bytes();e2=(assets/'envelope2.bin').read_bytes()
    waves={i:(assets/f'wave_{i:08x}.bin').read_bytes() for i in [0x080222a0,0x080226a0,0x080228a0]}
    total=0;meters=[]
    for SLOT in (0,0x20,0x40,0x60):
        for mode in range(3):
            for prepared in [(0,428,0,0),(4092,6,4092,4092),(2046,29,2046,2046)]:
                RECORD=[v for word in prepared for v in (word>>8,word&255)]+[mode,0,0,0]
                for event in (-1,*range(16)):
                    audio,states,_=c.run(binary,entry,'fold',initial,tables,[(tuple([0]*12),event)])
                    v=fold.FoldDrum1(list(fresh));v.words[32]=prepared[0];v.words[20]=prepared[1];v.words[36]=prepared[2];v.words[33]=prepared[3];v.words[31]=43;v.words[34]=[1,2,0][mode]
                    rng=[initial[232]|initial[233]<<16,initial[234]|initial[235]<<16]
                    pcm=[]
                    if event>=0:
                        if event:pcm+=v.render(event,waves,pitch,e1,e2,rng)
                        v.words[10]=v.words[17]=v.words[21]=v.words[28]=1
                        for i in [15,16,18,26,27,29,35]:v.words[i]=0
                        pcm+=v.render(16-event,waves,pitch,e1,e2,rng)
                    else:pcm=v.render(16,waves,pitch,e1,e2,rng)
                    assert audio[0]==[x<<8 for x in pcm],(SLOT,mode,prepared,event,'PCM')
                    assert [x&65535 for x in states[0][:40]]==v.words,(SLOT,mode,prepared,event,'state',[(i,a,b) for i,(a,b) in enumerate(zip(states[0],v.words)) if a!=b])
                    want_rng=[rng[0]&65535,rng[0]>>16,rng[1]&65535,rng[1]>>16]
                    assert states[0][58:62]==want_rng,(SLOT,mode,prepared,event,'RNG')
                    assert states[0][62:64]==[0x4100,0x1234]
                    meters.append(int((OUT/'fold.meter').read_text().strip()));total+=1
    SLOT=0
    for mode in range(3):
        for decay in (6,428):
            prepared=(4092,decay,4092,4092)
            RECORD=[v for word in prepared for v in (word>>8,word&255)]+[mode,0,0,0]
            events=[(i//48)%16 if i%48==0 else -1 for i in range(512)]
            audio,states,_=c.run(binary,entry,'fold-persistent',initial,tables,[(tuple([0]*12),event) for event in events])
            v=fold.FoldDrum1(list(fresh));v.words[32]=prepared[0];v.words[20]=decay;v.words[36]=4092;v.words[33]=4092;v.words[31]=43;v.words[34]=[1,2,0][mode]
            rng=[initial[232]|initial[233]<<16,initial[234]|initial[235]<<16]
            for i,event in enumerate(events):
                pcm=[]
                if event>=0:
                    if event:pcm+=v.render(event,waves,pitch,e1,e2,rng)
                    v.words[10]=v.words[17]=v.words[21]=v.words[28]=1
                    for off in [15,16,18,26,27,29,35]:v.words[off]=0
                    pcm+=v.render(16-event,waves,pitch,e1,e2,rng)
                else:pcm=v.render(16,waves,pitch,e1,e2,rng)
                assert audio[i]==[x<<8 for x in pcm],(mode,decay,i,'persistent PCM')
                assert [x&65535 for x in states[i][:40]]==v.words,(mode,decay,i,'persistent state')
                assert states[i][58:62]==[rng[0]&65535,rng[0]>>16,rng[1]&65535,rng[1]>>16],(mode,decay,i,'persistent RNG')
            meters+=list(map(int,(OUT/'fold-persistent.meter').read_text().split()));total+=len(events)
    assert max(meters)<=23040,('source deadline',max(meters))
    print(f'Fold candidate seam: PASS ({total} tagged record PCM/state/RNG cases; all slots/modes/trigger offsets; worst {max(meters)} modeled cycles)')
if __name__=='__main__':main()
