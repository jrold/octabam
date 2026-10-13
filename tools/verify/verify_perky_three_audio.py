#!/usr/bin/env python3
"""Execute the actual three-engine composition, including Fold2's live seam.

Original ARM pre/post snapshots independently constrain the trigger/update.
The per-sample oracle is separately compared to the PerkyBits native renderer
by verify_perky_fold2_dsp_exec.py. Output/state continuity is checked here.
"""
import os, struct, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import build_three_payload as production
import verify_perky_controlled_voice_exec as c
import verify_perky_synth_seam_exec as seam
import fold_drum2_compact as fold2
import simple_drum_ref as ref
import verify_perky_fold_seam_exec as fold1_gate
import perky_emit_shards as emit
import build_bus as assembler

OUT=ROOT/'out/perky/three-audio'
ASSETS=ROOT/'out/perky/simple-drum-assets'
TAG=os.environ.get('PERKY_CORE','A')
ORIGINAL_ASSEMBLE=c.assemble


def at_production_addresses(source):
    if '; PERKY3_CORE_OWNED' not in source:return ORIGINAL_ASSEMBLE(source)
    c.ORG=0x1000 if TAG=='A' else 0xdc0
    cut=source.index('; ===== BEGIN')
    asm=c.OUT/'three-source.asm';asm.write_text('; PERKY3_CORE_OWNED\n'+source[cut:])
    pieces,whole,dest,final,syms=emit.emit(asm,TAG)
    wrapper,labels=assembler.assemble_syms(emit.rewrite(source[:cut],syms,final),0x5000,'three_wrapper',strict_layout=True)
    spans=[(0x5000,wrapper)]
    for name,a,b,text,_ in pieces:
        words,_=assembler.assemble_syms(emit.rewrite(text,syms,final),dest[name],name,strict_layout=True)
        assert len(words)==b-a,(TAG,name,'extent')
        spans.append((dest[name],words))
    flat=[0]*(max(a+len(w) for a,w in spans)-c.ORG)
    for addr,words in spans:flat[addr-c.ORG:addr-c.ORG+len(words)]=words
    binary=c.OUT/'three-production.bin'
    binary.write_bytes(b''.join(w.to_bytes(3,'little') for w in flat))
    labels.update({label:final(addr) for label,addr in syms.items()})
    binary.with_suffix('.sym').write_text('\n'.join(f'{label} {addr:06x}' for label,addr in labels.items())+'\n')
    return binary,labels['pk_controlled_voice_exec']


def arm(case,name):
    return fold2.FoldDrum2.from_arm((case/name).read_bytes()[0xc4:0xc4+0x134]).words


def trigger(state):
    # The native ARM trigger switches oscillator pointer identities before
    # zeroing the new primary phase and restoring the saved crossfade level.
    state[10]=state[17]=state[21]=state[28]=1
    state[26]=state[27]=state[43]=0
    state[50]^=1
    base=2 if state[50]==0 else 34
    state[base]=state[base+1]=0
    state[49]=state[48]


def main():
    c.OUT=OUT;OUT.mkdir(parents=True,exist_ok=True)
    assert TAG in ('A','B')
    c.assemble=at_production_addresses
    c.HOST.parent.mkdir(parents=True,exist_ok=True);c.build_host();c.CYCLE_METER=True
    source,_=production.build(OUT/'payload')
    tables=c.words(OUT/'payload/tables.words')
    pitch=(ASSETS/'pitch.bin').read_bytes()
    e1=(ASSETS/'envelope1.bin').read_bytes();e2=(ASSETS/'envelope2.bin').read_bytes()
    waves={i:(ASSETS/f'wave_{i:08x}.bin').read_bytes() for i in (0x080222a0,0x080224a0,0x080226a0,0x080228a0)}
    # This wrapper executes the SAME update/trigger helpers called by the
    # shipping source entry. No emitter-inferred operation is accepted.
    wrapper='''pk_controlled_voice_exec:
        move #>$200,r6
        move #>$3900,r5
        move #>$ffffff,m1
        move #>$ffffff,m2
        move #>$ffffff,m3
        move #>$ffffff,m4
        move #>$ffffff,m5
        move #>$ffffff,m6
        jsrl pk_simple_base
        move x:>$3975,a
        move a1,x:(r6+$4)
        clr a
        move a1,x:(r6+$5)
        jsrl pk_three_fold2_trigger
        rts
'''
    binary,entry=c.assemble(wrapper+source.replace('@CONT@','$000400'))
    def data(path,state,table):
        path.write_text('X 200 '+' '.join(f'{v:06x}' for v in state)+'\nX 3900 '+' '.join(['000000']*117)+'\nX 3964 00ffff '+' '.join(['000000']*16)+'\nY 7a5 '+' '.join(f'{v:06x}' for v in table)+'\n')
        return []
    c.write_data=data
    count=0
    for mode in range(1,4):
        for corner in range(5):
            case=ROOT/f'out/perky/engine-fixtures/engine-4-mode-{mode}-corner-{corner}'
            for pre,post in [('wrapper-window-pre-trigger.bin','wrapper-window-before.bin'),('wrapper-window-retrigger-pre.bin','wrapper-window-retrigger-before.bin')]:
                before=arm(case,pre);wanted=arm(case,post)
                # Continuous control ownership is checked by its existing
                # executable control seam gate. Use original ARM prepared
                # values here to isolate trigger and oscillator update.
                for i in (14,20,31,32,33,42,44):before[i]=wanted[i]
                expected=list(before)
                expected[4]=struct.unpack_from('<H',pitch,2*expected[32])[0]
                expected[5]=0
                trigger(expected)
                assert expected==wanted,(mode,corner,pre,'independent original ARM law',[(i,a,b) for i,(a,b) in enumerate(zip(expected,wanted)) if a!=b])
                _,states,_=c.run(binary,entry,'trigger',before+[0]*13,tables,[(tuple([0]*12),-1)])
                assert states[0][:51]==wanted,(mode,corner,pre,'executed trigger/update',[(i,a,b) for i,(a,b) in enumerate(zip(states[0],wanted)) if a!=b])
                count+=1
    print(f'[PASS] three-engine Fold2 production trigger/update: {count} original ARM first/active cases, exact 51-word state')
    # Full tagged-source entry: controls -> event split -> render -> trim ->
    # stock continuation. The independently native-qualified model receives
    # the same pre-state, prepared words, modes and repeated event offsets.
    wrapper=seam.WRAPPER
    begin=wrapper.index('        move #>$000100,r1')
    end=wrapper.index('        move r4,x:>$209',begin)
    wrapper=wrapper[:begin]+wrapper[end:]
    # The debug voice dump at X:0x200.. overwrites stock's X:0x20b. Supply
    # the stock dispatcher's fresh ring cursor on EVERY continuation block.
    wrapper=wrapper.replace('        move r4,x:>$209','        move #>$4080,a\n        move a1,x:>$20b\n        move r4,x:>$209',1)
    wrapper=wrapper.replace('        move b1,x:(r4+$3)','        or #>$030000,b\n        move b1,x:(r4+$3)')
    binary,entry=c.assemble(wrapper+source.replace('@CONT@','$000400'))
    symbols={p[0]:int(p[1],16) for p in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}
    record=[]
    def full_data(path,state,table):
        path.write_text('X 3800 '+' '.join(f'{v:06x}' for v in state)+'\nX 3900 '+' '.join(['000000']*118)+'\nX 500 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{v|0x030000:06x}' for v in record)+'\nX 418 000000\nX 20b 004080\nP 400 0bf080 '+f'{symbols["pkse_finish"]:06x}'+' 00000c\nY 7a5 '+' '.join(f'{v:06x}' for v in table)+'\nX 3964 00ffff '+' '.join(['000000']*16)+'\n')
        return state[232:236]
    c.write_data=full_data
    initial=c.words(OUT/'payload/state_init.words')
    fresh2=arm(ROOT/'out/perky/engine-fixtures/engine-4-mode-1-corner-0','wrapper-window-pre-trigger.bin')
    total=0;meters=[]
    for mode in range(3):
        for prepared in ((0,428,0,0),(2046,29,2046,2046),(4092,6,4092,4092)):
            record=[v for word in prepared for v in (word>>8,word&255)]+[mode,0,0,3]
            events=[(i//16)%16 if i%16==0 else -1 for i in range(256)]
            audio,states,_=c.run(binary,entry,'fold2-persistent',initial,tables,[(tuple([0]*12),event) for event in events])
            voice=fold2.FoldDrum2(list(fresh2))
            rng=[initial[232]|initial[233]<<16,initial[234]|initial[235]<<16]
            for i,event in enumerate(events):
                voice.words[32],voice.words[20],voice.words[44],voice.words[33]=prepared
                voice.words[31]=43;voice.words[42]=(1,2,0)[mode];voice.words[14]=0
                voice.words[4]=struct.unpack_from('<H',pitch,2*prepared[0])[0];voice.words[5]=0
                pcm=[]
                if event>=0:
                    if event:pcm+=voice.render(event,waves,pitch,e1,e2,rng)
                    trigger(voice.words)
                    voice.words[4]=struct.unpack_from('<H',pitch,2*prepared[0])[0];voice.words[5]=0
                    pcm+=voice.render(16-event,waves,pitch,e1,e2,rng)
                else:pcm=voice.render(16,waves,pitch,e1,e2,rng)
                assert audio[i]==[x<<5 for x in pcm],(mode,prepared,i,'Fold2 shipping PCM')
                assert [x&65535 for x in states[i][:51]]==voice.words,(mode,prepared,i,'Fold2 shipping state',[(j,a,b) for j,(a,b) in enumerate(zip(states[i],voice.words)) if (a&65535)!=b])
                assert states[i][58:62]==[rng[0]&65535,rng[0]>>16,rng[1]&65535,rng[1]>>16],(mode,prepared,i,'Fold2 shipping RNG')
                assert states[i][62:64]==[0x4100,0x1234],(mode,i,'stock continuation')
            meters+=list(map(int,(OUT/'fold2-persistent.meter').read_text().split()));total+=len(events)
    assert max(meters)<=23040,('Fold2 modeled source deadline',max(meters))
    print(f'[PASS] Fold2 shipping controls/event/PCM/state/RNG/trim/continuation: {total} blocks; worst {max(meters)} modeled cycles')
    # Existing Fold1 corpus now executes this composition instead of the
    # historical four-engine candidate. Its PCM/state/RNG assertions stay.
    fold1_gate.candidate.build=production.build
    fold1_gate.OUT=ROOT/'out/perky/three-fold1'
    fold1_gate.main()
    print('[PASS] three-engine Fold1 production seam: original exact PCM/state/RNG and continuation corpus')


if __name__=='__main__':main()
