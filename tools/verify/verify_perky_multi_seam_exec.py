#!/usr/bin/env python3
"""Execute the shipping mixed source seam, exact states/PCM and deadline.

Simple Drum reference is the independently native-qualified Python renderer;
Noise/Tone compares the untouched PERKY2 seam at exposed shape-1 controls.
"""
from pathlib import Path
import itertools, os, struct, sys
import verify_perky_controlled_voice_exec as c
import verify_perky_synth_seam_exec as old
ROOT=c.ROOT
sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')]
import simple_drum_live as live, simple_drum_ref as ref, simple_drum_control as control, simple_drum_compact as compact
import build_multi_payload as payload
OUT=ROOT/'out/perky/multi-seam'
SLOT=0;RECORD=[]

def main():
    global SLOT,RECORD
    assets=Path(os.environ.get('PERKY_SIMPLE_ASSETS',ROOT/'out/perky/simple-drum-assets'))
    target=ROOT/'out/perky/multi'
    payload.build(assets,target)
    c.build_host()
    # Capture the actual PERKY2 seam under precisely the same controls/events.
    noise_knobs=[c.knob_row(),c.knob_row(tune=0,decay=0,env=0,mix=0,mode=1),c.knob_row(tune=127,decay=127,env=127,mix=127,mode=2)]
    base_source,initial,full_tables=c.build_source_and_assets()
    c.WRAPPER=old.WRAPPER
    baseline=c.source_builder.force_long_local_jsr(c.WRAPPER)+'\n'+base_source[base_source.index('; ====='):]
    baseline=baseline.replace('jmp     $000426','jmp     $000400')
    binary,entry=c.assemble(baseline)
    finish={p[0]:int(p[1],16) for p in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}['pkse_finish']
    def data(path,state,table):
        path.write_text('X 3800 '+' '.join(f'{v:06x}' for v in state)+'\nX 3900 '+' '.join(['000000']*117)+'\nX 500 03504b 030000 035931 030000\nX 513 00000a\nX 418 000000\nX 20b 004080\n'+f'P 400 0bf080 {finish:06x} 00000c\nY 7a5 '+' '.join(f'{v:06x}' for v in table)+'\n')
        return state[232:236]
    c.write_data=data
    expected={}
    for k in noise_knobs:
        for event in (-1,*range(16)):
            a,s,_=c.run(binary,entry,'reference',initial,full_tables,[(k,event)])
            expected[k,event]=(a,s)
    # Mixed seam consumes authentic 8-bit record bytes without 7-bit host masking.
    wrapper=old.WRAPPER
    start=wrapper.index('        move #>$000100,r1');end=wrapper.index('        move r4,x:>$209',start)
    wrapper=wrapper[:start]+wrapper[end:]
    wrapper=wrapper.replace('        move b1,x:(r4+$3)', '        or #>$030000,b\n        move b1,x:(r4+$3)')
    c.OUT=OUT;c.OUT.mkdir(parents=True,exist_ok=True);c.CYCLE_METER=True
    source=c.source_builder.force_long_local_jsr(wrapper)+'\n'+(target/'multi.asm').read_text().replace('@CONT@','$000400')
    binary,entry=c.assemble(source)
    finish={p[0]:int(p[1],16) for p in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}['pkse_finish']
    tables=c.words(target/'tables.words');initial=c.words(target/'state_init.words')
    def mixed_data(path,state,table):
        data(path,state,table)
        with path.open('a') as f:
            f.write('X 508 '+' '.join(f'{v|0x030000:06x}' for v in RECORD)+'\n'+f'X 418 {SLOT:06x}\nX 3964 00ffff '+' '.join(['000000']*16)+'\n')
        return state[232:236]
    c.write_data=mixed_data
    meters=[];total=0
    for SLOT in (0,0x20,0x40,0x60):
        for k in noise_knobs:
            RECORD=list(k);RECORD[11]=10
            for event in (-1,*range(16)):
                a,s,_=c.run(binary,entry,'noise',initial,tables,[(k,event)])
                wanta,wants=expected[k,event]
                assert a==wanta,(SLOT,event,'Noise/Tone PCM regression')
                assert s[0][:64]==wants[0][:64],(SLOT,event,'Noise/Tone state regression')
                total+=1
    pitch=(assets/'pitch.bin').read_bytes();e1=(assets/'envelope1.bin').read_bytes();e2=(assets/'envelope2.bin').read_bytes()
    ids=[0x080222a0,0x080226a0,0x080228a0];waves={i:(assets/f'wave_{i:08x}.bin').read_bytes() for i in ids}
    for SLOT in (0,0x20,0x40,0x60):
        for mode in range(3):
            for prepared in [(0,65535,65535,0),(4095,1,1,2047),(2048,428,1040,1024)]:
                RECORD=[v for word in prepared for v in (word>>8,word&255)]+[mode,0,0,2]
                for event in (-1,*range(16)):
                    a,s,_=c.run(binary,entry,'simple',initial,tables,[(tuple([0]*12),event)])
                    v=live.LiveSimpleDrum.fresh();v.apply_prepared_record(bytes(RECORD))
                    pcm=[]
                    if event>=0:
                        if event:pcm+=compact.render_block(v.voice,event,waves,pitch,e1,e2)
                        v.trigger()
                        pcm+=compact.render_block(v.voice,16-event,waves,pitch,e1,e2)
                    else:pcm=compact.render_block(v.voice,16,waves,pitch,e1,e2)
                    assert a==[[x<<8 for x in pcm]],(SLOT,mode,prepared,event,'Simple Drum PCM',a,pcm)
                    assert [x&65535 for x in s[0][:34]]==v.voice.words,(SLOT,mode,event,'Simple Drum state')
                    assert s[0][62:64]==[0x4100,0x1234], 'ring/stock continuation'
                    meters.append(int((OUT/'simple.meter').read_text().strip()));total+=1
    SLOT=0
    noise_max=0
    for i,controls in enumerate(itertools.product((0,127),(0,127),(0,127),(0,127),range(3))):
        tune,decay,env,mix,mode=controls
        RECORD=list(c.knob_row(tune=tune,decay=decay,env=env,mix=mix,mode=mode));RECORD[11]=10
        blocks=[(tuple([0]*12),(b//16)%16 if b%16==0 else -1) for b in range(256)]
        c.run(binary,entry,'noise-corner',initial,tables,blocks)
        values=list(map(int,(OUT/'noise-corner.meter').read_text().split()))
        noise_max=max(noise_max,max(values));meters+=values;total+=len(blocks)
    assert noise_max<=23040,('Noise/Tone deadline',noise_max)
    # Persistent state/cache across long release tails and every retrigger offset.
    SLOT=0
    for mode in range(3):
        prepared=(4095,1,1040,2047)
        RECORD=[v for word in prepared for v in (word>>8,word&255)]+[mode,0,0,2]
        events=[(i//16)%16 if i%16==0 else -1 for i in range(256)]
        a,s,_=c.run(binary,entry,'simple-long',initial,tables,[(tuple([0]*12),e) for e in events])
        v=live.LiveSimpleDrum.fresh();v.apply_prepared_record(bytes(RECORD))
        for i,event in enumerate(events):
            pcm=[]
            if event>=0:
                if event:pcm+=compact.render_block(v.voice,event,waves,pitch,e1,e2)
                v.trigger()
                pcm+=compact.render_block(v.voice,16-event,waves,pitch,e1,e2)
            else:pcm=compact.render_block(v.voice,16,waves,pitch,e1,e2)
            assert a[i]==[x<<8 for x in pcm],(mode,i,'persistent PCM')
            assert [x&65535 for x in s[i][:34]]==v.voice.words,(mode,i,'persistent state')
        meters+=list(map(int,(OUT/'simple-long.meter').read_text().split()));total+=len(events)
    RECORD=[0]*11+[99]
    a,s,_=c.run(binary,entry,'unsupported-engine',initial,tables,[(tuple([0]*12),0)])
    assert not any(a[0]) and s[0][62:64]==[0x4100,0x1234], 'unsupported engine must resume stock on exact zero source'
    # Switch engines on one persistent track; each overlay must reset exactly once.
    switch_wrapper=wrapper.replace('        move #>$000500,r4', """        move #>$000500,r4
        move x:>$10b,a
        cmp #>$a,a
        bne pkms_record_ready
        move #>$000600,r4
pkms_record_ready:""")
    switch_source=c.source_builder.force_long_local_jsr(switch_wrapper)+'\n'+(target/'multi.asm').read_text().replace('@CONT@','$000400')
    binary,entry=c.assemble(switch_source)
    finish={p[0]:int(p[1],16) for p in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}['pkse_finish']
    mixed_write=c.write_data
    noise_record=list(noise_knobs[0]);noise_record[11]=10
    def switch_data(path,state,table):
        result=mixed_write(path,state,table)
        with path.open('a') as f:f.write('X 600 00504b 000000 005931 000000 000000 000000 000000 000000 '+' '.join(f'{v:06x}' for v in noise_record)+'\n')
        return result
    c.write_data=switch_data
    RECORD=[v for word in (2048,428,1040,1024) for v in (word>>8,word&255)]+[0,0,0,2]
    blocks=[(tuple([0]*11+[engine]),event) for engine,event in [(2,0),(2,-1),(10,0),(10,-1),(2,7),(2,-1)]]
    a,s,_=c.run(binary,entry,'engine-switch',initial,tables,blocks)
    v=live.LiveSimpleDrum.fresh();v.apply_prepared_record(bytes(RECORD));v.trigger()
    assert a[0]==[x<<8 for x in compact.render_block(v.voice,16,waves,pitch,e1,e2)]
    assert a[1]==[x<<8 for x in compact.render_block(v.voice,16,waves,pitch,e1,e2)]
    assert a[2]==expected[noise_knobs[0],0][0][0], 'switch to Noise/Tone overlay'
    v=live.LiveSimpleDrum.fresh();v.apply_prepared_record(bytes(RECORD))
    pcm=compact.render_block(v.voice,7,waves,pitch,e1,e2);v.trigger();pcm+=compact.render_block(v.voice,9,waves,pitch,e1,e2)
    assert a[4]==[x<<8 for x in pcm], 'switch back to Simple Drum overlay'
    assert a[5]==[x<<8 for x in compact.render_block(v.voice,16,waves,pitch,e1,e2)]
    assert [x&65535 for x in s[5][:34]]==v.voice.words
    total+=len(blocks)
    assert max(meters)<=23040,('deadline',max(meters))
    print(f'Mixed source seam: PASS ({total} exact PCM/state cases, all slots/modes/trigger offsets, PERKY2 regression; worst mixed path {max(meters)} modeled cycles <=23040)')
if __name__=='__main__':main()
