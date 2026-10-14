#!/usr/bin/env python3
"""Qualify all four placed engines with the unchanged native clock/trim/return.

Renderer oracles remain independent of DSP output. Raw Complex native/ARM
parity is separately proven by verify_perky_four_renderer.py.
"""
import itertools, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
import verify_perky_three_audio as a
import source_clock as clock
import fold_drum_compact as f1
import fold_drum2_compact as f2
import simple_drum_live as simple
import simple_drum_compact as compact
import build_four_payload as production
import complex_drum_compact as complex_ref
import complex_drum_production as complex_state
import random, json
c=a.c


class Complex:
    def __init__(self,words):self.words=complex_state.from_original(words)
    def render(self,n,waves,pitch,e1,e2,rng):
        v=complex_ref.CompactComplexDrum(complex_state.to_original(self.words))
        pcm=complex_ref.render_block(v,n,waves,pitch,e1,e2)
        self.words=complex_state.from_original(v.words)
        return pcm
    def apply(self,record):
        values=[(record[2*i]<<8)|record[2*i+1] for i in range(4)]
        self.words[32],self.words[20],self.words[31],self.words[33]=values
        self.words[14]=record[8]>>7
        frequency=record[9]<<3
        self.words[36]=int(frequency*0x57619f1//(1<<22))
        self.words[37]=0
        wave=(0x080222a0,0x080224a0,0x080228a0)[record[8]&3]
        self.words[8]=wave&65535;self.words[9]=wave>>16
    def hit(self):
        self.words[10]=self.words[17]=self.words[21]=self.words[28]=1
        for offset in (15,16,18,26,27,29):self.words[offset]=0


def main():
    c.OUT=ROOT/f'out/perky/four-clock-audio-{a.TAG}';c.OUT.mkdir(parents=True,exist_ok=True)
    c.HOST.parent.mkdir(parents=True,exist_ok=True);c.build_host();c.CYCLE_METER=True;c.assemble=a.at_production_addresses
    source,fresh=production.build(c.OUT/'payload',native_clock=True)
    tables=c.words(c.OUT/'payload/tables.words');initial=c.words(c.OUT/'payload/state_init.words')
    wrapper=a.seam.WRAPPER
    begin=wrapper.index('        move #>$000100,r1');end=wrapper.index('        move r4,x:>$209',begin)
    wrapper=wrapper[:begin]+wrapper[end:]
    wrapper=wrapper.replace('        move r4,x:>$209','        move #>$4080,a\n        move a1,x:>$20b\n        move r4,x:>$209',1)
    wrapper=wrapper.replace('        move b1,x:(r4+$3)','        or #>$030000,b\n        move b1,x:(r4+$3)')
    binary,entry=c.assemble(wrapper+source.replace('@CONT@','$000400'))
    symbols={p[0]:int(p[1],16) for p in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}
    record=[]
    def data(path,state,table):
        path.write_text('X 3800 '+' '.join(f'{v:06x}' for v in state)+'\nX 3900 '+' '.join(['000000']*118)+'\n'
                        +'X 500 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{v|0x030000:06x}' for v in record)+'\n'
                        +'X 418 000000\nX 20b 004080\nP 400 0bf080 '+f'{symbols["pkse_finish"]:06x}'+' 00000c\nY 7a5 '+' '.join(f'{v:06x}' for v in table)+'\n'
                        +'X 3964 00ffff '+' '.join(['000000']*16)+'\nX 39b0 '+' '.join(['000000']*17)+'\n')
        return state[232:236]
    c.write_data=data
    pitch=(a.ASSETS/'pitch.bin').read_bytes();e1=(a.ASSETS/'envelope1.bin').read_bytes();e2=(a.ASSETS/'envelope2.bin').read_bytes()
    waves={i:(a.ASSETS/f'wave_{i:08x}.bin').read_bytes() for i in (0x080222a0,0x080224a0,0x080226a0,0x080228a0)}
    fresh2=a.arm(ROOT/'out/perky/engine-fixtures/engine-4-mode-1-corner-0','wrapper-window-pre-trigger.bin')
    raw=(ROOT/'out/perky/engine-fixtures/engine-6-mode-1-corner-0/wrapper-window-pre-trigger.bin').read_bytes()[0x1f8:0x338]
    fresh_complex=complex_ref.CompactComplexDrum.from_arm(raw).words
    totals=0;worst={}
    for engine in (0,3,2,5):
        meters=[]
        controls=((0,428,0,0),(2046,29,2046,2046),(4092,6,4092,4092)) if engine!=2 else ((0,65535,65535,0),(2048,428,1040,1024),(4095,1,1,2047))
        for mode,gate in itertools.product(range(3),(0,1)):
            for prepared in controls:
                if engine==5:prepared=(prepared[0],prepared[1],99+(prepared[2]//4),prepared[3])
                record=[v for word in prepared for v in (word>>8,word&255)]+[mode|(0x80 if engine==5 and gate else 0),(254,31,3)[0 if prepared[0]==0 else 1 if prepared[0]==2046 else 2] if engine==5 else gate,0,engine]
                events=[(i//16)%16 if i%16==0 else -1 for i in range(256)]
                audio,states,_=c.run(binary,entry,'persistent',initial,tables,[(tuple([0]*12),e) for e in events])
                v=f1.FoldDrum1(list(fresh)) if engine==0 else f2.FoldDrum2(list(fresh2)) if engine==3 else Complex(list(fresh_complex)) if engine==5 else simple.LiveSimpleDrum.fresh()
                rng=[initial[232]|initial[233]<<16,initial[234]|initial[235]<<16]
                fifo=clock.Clock()
                def render(n):
                    needed=fifo.needed(n)
                    native=v.render(needed,waves,pitch,e1,e2,rng) if engine!=2 else compact.render_block(v.voice,needed,waves,pitch,e1,e2)
                    return fifo.render(native,n)
                for i,event in enumerate(events):
                    # After the initial update, unchanged native controls are
                    # left alone between trigs. In particular do not reset
                    # Fold2 oscillator A's increment in the oracle merely
                    # because shipping source happens to run that update.
                    if engine==2 and (i==0 or event>=0):v.apply_prepared_record(bytes(record))
                    elif engine==5 and (i==0 or event>=0):v.apply(record)
                    elif engine!=2 and (i==0 or event>=0):
                        v.words[32]=prepared[0];v.words[20]=prepared[1];v.words[33]=prepared[3];v.words[31]=43;v.words[14]=gate
                        if engine==0:v.words[36]=prepared[2];v.words[34]=(1,2,0)[mode]
                        else:
                            v.words[44]=prepared[2];v.words[42]=(1,2,0)[mode]
                            v.words[4]=struct.unpack_from('<H',pitch,2*prepared[0])[0];v.words[5]=0
                    pcm=[]
                    if event>=0:
                        if event:pcm+=render(event)
                        fifo.reset()
                        if engine==2:v.trigger()
                        elif engine==5:v.hit()
                        elif engine==3:
                            a.trigger(v.words)
                            # PerkonsVoices::trigger owns the mandatory
                            # original update AFTER the primary swap.
                            v.words[4]=struct.unpack_from('<H',pitch,2*prepared[0])[0];v.words[5]=0
                        else:
                            v.words[10]=v.words[17]=v.words[21]=v.words[28]=1
                            for offset in (15,16,18,26,27,29,35):v.words[offset]=0
                        pcm+=render(16-event)
                    else:pcm=render(16)
                    assert all(abs(x-y)<=1 for x,y in zip(audio[i],pcm)),(a.TAG,engine,mode,prepared,i,'shipping rate/PCM',audio[i],pcm)
                    expected=v.words if engine!=2 else v.voice.words
                    assert [x&65535 for x in states[i][:len(expected)]]==expected,(a.TAG,engine,mode,prepared,i,'native renderer state',[(j,x,y) for j,(x,y) in enumerate(zip(states[i],expected)) if (x&65535)!=y])
                    if engine!=2:assert states[i][58:62]==[rng[0]&65535,rng[0]>>16,rng[1]&65535,rng[1]>>16],(engine,i,'native RNG')
                    assert states[i][62:64]==[0x4100,0x1234],(engine,i,'stock continuation')
                meters+=list(map(int,(c.OUT/'persistent.meter').read_text().split()));totals+=len(events)
        worst[engine]=max(meters)
        assert worst[engine]<=23040,(a.TAG,engine,'unchanged source deadline',worst[engine],23040)
        print(f'[PASS] core {a.TAG} engine {engine}: 4608 blocks, all modes/gates/trigger offsets, native state/RNG exact, rational resampled PCM <=1 LSB, worst {worst[engine]} modeled cycles')
    print(f'[PASS] core {a.TAG}: {totals} shipping renderer/clock/trim/continuation blocks; worst cycles {worst}')
    # Dirty instance/scratch/FIFO/clock RAM must converge to the exact clean
    # initialized voice. Assets are upload-owned immutable inputs, not dirty
    # instance state. Pitch cache starts invalid as the packaged upload does.
    clean_data=data; dirty=random.Random(0x44495254); dirt_cases=0
    for engine,mode in itertools.product((0,3,2,5),range(3)):
        values=(2814,29,180,2046) if engine==5 else (2048,428,1040,1024) if engine==2 else (2046,29,2046,2046)
        record=[v for word in values for v in (word>>8,word&255)]+[mode,31 if engine==5 else 0,0,engine]
        script=[(tuple([0]*12),0)]+[(tuple([0]*12),-1)]*7
        c.write_data=clean_data
        clean_audio,clean_states,_=c.run(binary,entry,'dirty-clean',initial,tables,script)
        corrupt=list(initial);corrupt[:58]=[dirty.randrange(65536) for _ in range(58)]
        corrupt[236:242]=[0x5555]*6
        def dirty_data(path,state,table):
            clean_data(path,state,table)
            with path.open('a') as out:
                for addr,count in ((0x3900,100),(0x3980,40),(0x39b0,17)):
                    out.write(f'X {addr:x} '+' '.join(f'{dirty.randrange(0x1000000):06x}' for _ in range(count))+'\n')
            return state[232:236]
        c.write_data=dirty_data
        dirty_audio,dirty_states,_=c.run(binary,entry,'dirty-poisoned',corrupt,tables,script)
        assert dirty_audio==clean_audio and dirty_states==clean_states,(a.TAG,engine,mode,'dirty memory init')
        dirt_cases+=1
    c.write_data=clean_data
    print(f'[PASS] core {a.TAG}: {dirt_cases} dirty state/scratch/FIFO/clock initializations, PCM and complete visible state equal to clean')
    # Directly reject position 1..3 even if a diagnostic caller bypasses
    # ColdFire admission. These overlays hold immutable fourth-wave samples.
    blocked=0
    for wave_offset,wave_count in ((0,64),(64,64),(128,44)):
        # Production r6 names the caller's requested overlay. Observe the
        # primary voice and immutable assets through fixed addresses instead;
        # don't advance r6 in a debug dump and contaminate later calls.
        observer=wrapper.replace('        move #>$000500,r4',
            '        clr a\n        move a1,x:>$38ed\n        move #>$000500,r4',1)
        observer=observer.replace('pkse_finish:\n',
            'pkse_finish:\n        move #>$3800,r1\n',1)
        observer=observer.replace('move x:(r6)+,a','move x:(r1)+,a',1)
        observer=observer.replace('        move #>$1234,a\n        move a1,x:(r2)+\n        rts',
            f'        move #>$1234,a\n        move a1,x:(r2)+\n'
            f'        move #>${0x383a+wave_offset:x},r1\n'
            '        move #>$200,r2\n'
            f'        do #>{wave_count},p4blocked_capture\n'
            '        move x:(r1)+,a\n        move a1,y:(r2)+\n'
            'p4blocked_capture:\n        nop\n        rts',1)
        blocked_binary,blocked_entry=c.assemble(observer+source.replace('@CONT@','$000400'))
        # The continuation stub must call this observer's relocated finish,
        # not the earlier wrapper's address. clean_data resolves symbols here.
        symbols={p[0]:int(p[1],16) for p in map(str.split,blocked_binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}
        for position,engine,mode in itertools.product(range(1,4),(0,3,2,5),range(3)):
            record=[v for word in (2814,29,180,2046) for v in (word>>8,word&255)]+[mode,31 if engine==5 else 0,0,engine]
            def blocked_data(path,state,table):
                clean_data(path,state,table)
                with path.open('a') as out:out.write(f'X 418 {position*32:06x}\n')
                return state[232:236]
            c.write_data=blocked_data
            pcm,rows,_=c.run(blocked_binary,blocked_entry,'blocked',initial,tables,[(tuple([0]*12),i) for i in range(16)])
            assert all(not any(row) for row in pcm),(a.TAG,position,engine,mode,'unsupported position audio')
            assert all(row[:58]==initial[:58] and row[58:62]==initial[232:236] for row in rows),(a.TAG,position,'unsupported position changed state/RNG')
            # Host rows are X:0x200/64 followed by Y:0x200/64.
            dumps=[[int(v,16) for v in row.split()] for row in (c.OUT/'blocked.state').read_text().splitlines()]
            expected=initial[58+wave_offset:58+wave_offset+wave_count]
            assert all(row[64:64+wave_count]==expected for row in dumps),(a.TAG,position,wave_offset,'unsupported position overwrote fourth-wave asset')
            if wave_offset==0:blocked+=16
    c.write_data=clean_data
    print(f'[PASS] core {a.TAG}: {blocked} tagged unsupported-position trigs rejected before voice initialization; every algorithm/mode/offset; primary state/RNG and all 172 X wave words unchanged')
    # Unlike the fixed-tuple corpus above, these records contain different
    # controls/engines before and after an interior p-lock. Warm the old voice
    # first so a wrongly applied new tuple cannot hide in an inactive prefix.
    switched=wrapper.replace('        move #>$000500,r4','''        move x:>$100,a
        tst a
        beq p3test_oldrecord
        move #>$600,r4
        bra p3test_recordready
p3test_oldrecord:
        move #>$500,r4
p3test_recordready:''',1)
    binary,entry=c.assemble(switched+source.replace('@CONT@','$000400'))
    symbols={p[0]:int(p[1],16) for p in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(p)==2}
    def tuple_for(engine,mode,new):
        prepared=((4095,1,1,2047) if new else (2048,428,1040,1024)) if engine==2 else ((0,428,4092,4092) if new else (2046,29,2046,2046))
        if engine==5:prepared=(768,428,99,4092) if new else (2814,29,180,2046)
        return [v for word in prepared for v in (word>>8,word&255)]+[mode,(254 if new else 31) if engine==5 else 0,0,engine]
    def make_voice(engine):
        return f1.FoldDrum1(list(fresh)) if engine==0 else f2.FoldDrum2(list(fresh2)) if engine==3 else Complex(list(fresh_complex)) if engine==5 else simple.LiveSimpleDrum.fresh()
    def apply(v,record):
        if record[11]==2:v.apply_prepared_record(bytes(record));return
        if record[11]==5:v.apply(record);return
        values=[(record[2*i]<<8)|record[2*i+1] for i in range(4)]
        v.words[32],v.words[20],v.words[33],v.words[31],v.words[14]=values[0],values[1],values[3],43,record[9]
        if record[11]==0:v.words[36]=values[2];v.words[34]=(1,2,0)[record[8]]
        else:
            v.words[44]=values[2];v.words[42]=(1,2,0)[record[8]]
            v.words[4]=struct.unpack_from('<H',pitch,2*values[0])[0];v.words[5]=0
    def hit(v,record):
        if record[11]==2:v.trigger()
        elif record[11]==5:v.hit()
        elif record[11]==3:
            a.trigger(v.words);v.words[4]=struct.unpack_from('<H',pitch,2*v.words[32])[0];v.words[5]=0
        else:
            v.words[10]=v.words[17]=v.words[21]=v.words[28]=1
            for offset in (15,16,18,26,27,29,35):v.words[offset]=0
    base_data=data;switch_count=0;switch_worst=0
    for old_engine,new_engine,mode,event in itertools.product((0,3,2,5),(0,3,2,5),range(3),range(16)):
        old=tuple_for(old_engine,mode,False);new=tuple_for(new_engine,(mode+1)%3,True)
        record=old
        def split_data(path,state,table):
            base_data(path,state,table)
            prefix=list(old);prefix[10]=0xa5
            with path.open('a') as out:
                out.write('X 600 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{v|0x030000:06x}' for v in new+prefix)+'\n')
            return state[232:236]
        c.write_data=split_data
        audio,states,_=c.run(binary,entry,'split',initial,tables,[(tuple([0]*12),0),(tuple([1]+[0]*11),event)])
        rng=[initial[232]|initial[233]<<16,initial[234]|initial[235]<<16]
        fifo=clock.Clock();v=make_voice(old_engine);apply(v,old);hit(v,old)
        def segment(n,engine):
            needed=fifo.needed(n)
            pcm=v.render(needed,waves,pitch,e1,e2,rng) if engine!=2 else compact.render_block(v.voice,needed,waves,pitch,e1,e2)
            return fifo.render(pcm,n)
        first=segment(16,old_engine)
        apply(v,old);second=segment(event,old_engine)
        if old_engine!=new_engine:v=make_voice(new_engine)
        apply(v,new);hit(v,new);fifo.reset();second+=segment(16-event,new_engine)
        for got,wanted in zip(audio,(first,second)):
            assert all(abs(x-y)<=1 for x,y in zip(got,wanted)),(old_engine,new_engine,mode,event,'atomic pre/post p-lock PCM',got,wanted)
        expected=v.words if new_engine!=2 else v.voice.words
        assert [x&65535 for x in states[1][:len(expected)]]==expected,(old_engine,new_engine,mode,event,'p-lock state')
        assert states[1][58:62]==[rng[0]&65535,rng[0]>>16,rng[1]&65535,rng[1]>>16],(old_engine,new_engine,event,'p-lock RNG')
        meters=list(map(int,(c.OUT/'split.meter').read_text().split()));switch_worst=max(switch_worst,max(meters));switch_count+=1
    assert switch_worst<=23040,(a.TAG,'p-lock/source deadline',switch_worst,23040)
    (c.OUT/'report.json').write_text(json.dumps({'core':a.TAG,'blocks':totals,'worst_cycles':worst,'rejected_position_blocks':blocked,'dirty_cases':dirt_cases,'transitions':switch_count,'worst_transition_cycles':switch_worst},indent=2)+'\n')
    print(f'[PASS] core {a.TAG}: {switch_count} active-voice interior p-lock cases, every engine transition/mode/offset; exact native state/RNG, PCM <=1 LSB; worst {switch_worst} modeled cycles')


if __name__=='__main__':main()
