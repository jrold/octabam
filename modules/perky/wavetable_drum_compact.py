"""41-word Wavetable V1/V2 state, with exact native wrap and interpolation.

This host model is an oracle candidate, not an Octatrack DSP renderer.
"""
from dataclasses import dataclass
import simple_drum_compact as common

WORDS=41
SECONDARY,SECONDARY_NEXT,MIX,MIX_NEXT,HALF=34,36,38,39,40
@dataclass
class WavetableDrum:
    words:list[int]

    @classmethod
    def from_arm(cls,raw):
        if len(raw)!=0x150:raise ValueError('Wavetable state must be 0x150 bytes')
        words=common.CompactSimpleDrum.from_arm(raw[:0x120]).words
        for dst,src in [(2,0xf4),(4,0xf8),(6,0x100),(8,0x104)]:common.CompactSimpleDrum._set_list_u32(words,dst,common._u32(raw,src))
        words += [common._u16(raw,off) for off in [0x108,0x10a,0x10c,0x10e,0x112,0x114]]+[raw[0x128]]
        return cls(words)

    def apply_to_arm(self,template):
        raw=bytearray(template)
        raw[:0x120]=common.CompactSimpleDrum(self.words[:34]).apply_to_arm(template[:0x120])
        raw[0x30:0x40]=template[0x30:0x40] # inactive Simple oscillator is untouched
        for src,dst in [(2,0xf4),(4,0xf8),(6,0x100),(8,0x104),(34,0x108),(36,0x10c)]:common._put32(raw,dst,self.words[src]|self.words[src+1]<<16)
        for src,dst in [(38,0x112),(39,0x114)]:common._put16(raw,dst,self.words[src])
        raw[0x128]=self.words[HALF]
        return bytes(raw)

    def render(self,n,waves,pitch,envelope1,envelope2):
        v=common.CompactSimpleDrum(self.words[:34]);base=common.cached_base_frequency(v,pitch);out=[]
        def pointer(at):return self.words[at]|self.words[at+1]<<16
        for _ in range(n):
            amp=common._render_envelope(v,10,envelope1,envelope2)
            env=common._render_envelope(v,21,envelope1,envelope2)
            factor=(((env&0x1fff)+0x2000)>>(13-(env>>13)))-1
            frequency=base+((v.words[33]*factor)>>9)
            if self.words[HALF]==1:frequency>>=1
            common._set_oscillator_frequency(v,frequency)
            phase=(v.u32(2)+v.u32(4))&0xffffffff
            if common._s32(phase)>0x100000:
                phase=(phase-0x100000)&0xffffffff;self.words[MIX]=self.words[MIX_NEXT]
                if v.u32(6)!=v.u32(8):
                    v.set_u32(6,v.u32(8));self.words[34:36]=self.words[36:38]
            v.set_u32(2,phase);index=(phase>>9)&0x7ff;following=(index+1)&0x7ff;fraction=phase&0x1ff
            current=v.u32(6);secondary=pointer(34);next_current=current;next_secondary=secondary
            if index>following and v.u32(8)!=current:next_current=v.u32(8);next_secondary=pointer(36)
            def interpolate(a,b):
                first=common._table_s16(waves[a],index);second=common._table_s16(waves[b],following)
                return common._s16(first+common._asr32(common._mullo32(second-first,fraction),9))
            first=interpolate(current,next_current);second=interpolate(secondary,next_secondary)
            mixed=(first*(255-self.words[MIX])+second*self.words[MIX])&0xffffffff
            osc=common._s16(mixed>>8)
            sample=common._asr32(common._mullo32(osc,amp),16)
            sample=common._asr32(common._mullo32(sample,v.words[0]&255),8)
            out.append(0 if v.words[1] else max(-32768,min(32767,sample)))
        self.words[:34]=v.words
        return out
