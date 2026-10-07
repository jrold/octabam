"""Forty-word Fold Drum 1 renderer state; common Simple Drum primitives reused.

The extra six words hold mode, transient counter, fold amount, and noise
sample/hold state. Firmware tables and snapshots remain external inputs.
"""
from dataclasses import dataclass
import simple_drum_compact as common

WORDS=40
MODE,COUNTER,FOLD,NOISE_COUNT,NOISE_RATE,NOISE_SAMPLE=range(34,40)
@dataclass
class FoldDrum1:
    words: list[int]

    @classmethod
    def from_arm(cls,raw):
        if len(raw)!=0xf4:raise ValueError('Fold Drum 1 state must be 0xf4 bytes')
        w=common.CompactSimpleDrum.from_arm(raw+bytes(0x120-len(raw))).words
        w[33]=common._u16(raw,0xee)
        w += [raw[5],common._u16(raw,0xec),common._u16(raw,0xf0),common._u16(raw,0x60),common._u16(raw,0x62),common._u16(raw,0x70)]
        return cls(w)

    def apply_to_arm(self,template):
        raw=bytearray(common.CompactSimpleDrum(self.words[:34]).apply_to_arm(template+bytes(0x120-len(template)))[:0xf4])
        raw[5]=self.words[MODE]
        for off,value in [(0xee,self.words[33]),(0xec,self.words[COUNTER]),(0xf0,self.words[FOLD]),(0x60,self.words[NOISE_COUNT]),(0x62,self.words[NOISE_RATE]),(0x70,self.words[NOISE_SAMPLE])]:common._put16(raw,off,value)
        return bytes(raw)

    def render(self,n,waves,pitch,envelope1,envelope2,rng):
        v=common.CompactSimpleDrum(self.words[:34]);out=[]
        base=common.cached_base_frequency(v,pitch)
        for _ in range(n):
            amp=common._render_envelope(v,10,envelope1,envelope2)
            env=common._render_envelope(v,21,envelope1,envelope2)
            factor=(((env&0x1fff)+0x2000)>>(13-(env>>13)))-1
            freq=base+((v.words[33]*factor)>>9)
            common._set_oscillator_frequency(v,freq)
            osc=common._render_oscillator(v,waves)
            driven=common._asr32(common._mullo32(osc,common._s16(self.words[FOLD])+256),8)
            phase=(common._u32bits(driven)+0x8000)&0x1ffff
            folded=phase-0x8000 if phase<0x10000 else 0x18000-phase
            counter=self.words[COUNTER]
            if counter<=0x210:
                if self.words[MODE]==0:folded+=0x3fff
                elif self.words[MODE]==2:
                    if self.words[NOISE_COUNT]:self.words[NOISE_COUNT]-=1
                    else:
                        self.words[NOISE_COUNT]=self.words[NOISE_RATE]
                        low,high=rng
                        product=low*0x4c957f2d
                        newlow=((product&0xffffffff)+1)&0xffffffff
                        carry=int(newlow<(product&0xffffffff))
                        high=(low*0x5851f42d+high*0x4c957f2d+(product>>32)+carry)&0xffffffff
                        rng[:]=[newlow,high];self.words[NOISE_SAMPLE]=high&0xffff
                    noise=common._s16(self.words[NOISE_SAMPLE])
                    if counter<=0x110:
                        if counter<=0x8f:folded+=(noise*11)>>4
                        else:folded+=(((noise*(0x110-counter))>>8)*44)>>6
                self.words[COUNTER]=(counter+1)&0xffff
            mixed=common._asr32(common._u32bits(folded+osc),1)
            shaped=common._asr32(common._mullo32(amp,mixed),16)
            sample=common._asr32(common._mullo32(shaped,v.words[0]&255),8)
            out.append(0 if v.words[1] else max(-32768,min(32767,sample)))
        self.words[:34]=v.words
        return out
