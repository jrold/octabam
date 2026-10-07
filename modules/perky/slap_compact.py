"""Compact exact v1.2.1 Slap renderer with external delay-ring storage.

The original ARM object is 0x2670 bytes mostly because it embeds a 4,805
sample delay ring.  The hot control/filter state is only 40 DSP words; the ring
is represented separately so an Octatrack port can place it in reclaimed Y.
"""
from __future__ import annotations
from dataclasses import dataclass
import resonator_compact as c

RING_LEN = 0x12C5
WORDS = 40
VELOCITY = 0
AMP_ENV = 1                 # 11 common envelope words
ENV_RESET = AMP_ENV + c.ENV_WORDS  # raw envelope +8 retrigger-reset byte
NOISE = ENV_RESET + 1       # 3 words
FILTER = NOISE + 3          # 8 words
F_DAMP, F_COEFF, F_FIRST, F_SECOND, F_VELOCITY = 0,1,2,4,6
COUNTERS = FILTER + 8       # first, second, second target, first target
TAPS = COUNTERS + 4         # 5 delays, 5 gains
INDEX = TAPS + 10
MIX = INDEX + 1
assert MIX + 1 == WORDS


def _filter_from_arm(w, raw):
    w[FILTER+F_DAMP] = c.u16(raw, 0xA8)
    w[FILTER+F_COEFF] = c.u16(raw, 0xAA)
    c.set_u32(w, FILTER+F_FIRST, c.u32(raw, 0xAC))
    c.set_u32(w, FILTER+F_SECOND, c.u32(raw, 0xB0))
    c.set_u32(w, FILTER+F_VELOCITY, c.u32(raw, 0xB4))


def _filter_to_arm(w, raw):
    c.put16(raw, 0xA8, w[FILTER+F_DAMP])
    c.put16(raw, 0xAA, w[FILTER+F_COEFF])
    c.put32(raw, 0xAC, c.get_u32(w, FILTER+F_FIRST))
    c.put32(raw, 0xB0, c.get_u32(w, FILTER+F_SECOND))
    c.put32(raw, 0xB4, c.get_u32(w, FILTER+F_VELOCITY))


def _advance_filter(w, input_value):
    coeff = w[FILTER+F_COEFF]
    velocity = c.s32(c.get_u32(w, FILTER+F_VELOCITY))
    product = c.mullo(velocity, coeff)
    if product < 0:
        product = c.s32(c.u32bits(product) + 0xFFFF)
    first = c.add(c.s32(c.get_u32(w, FILTER+F_FIRST)), c.asr(product, 16))
    first = max(-32767, min(32767, first))
    c.set_u32(w, FILTER+F_FIRST, first)
    second = c.sub(input_value, first)
    second = c.sub(second, c.asr(c.mullo(velocity, w[FILTER+F_DAMP]), 10))
    second = max(-32767, min(32767, second))
    c.set_u32(w, FILTER+F_SECOND, second)
    feedback = c.mullo(second, coeff)
    if feedback < 0:
        feedback = c.s32(c.u32bits(feedback) + 0xFFFF)
    velocity = c.add(velocity, c.asr(feedback, 16))
    velocity = max(-32767, min(32767, velocity))
    c.set_u32(w, FILTER+F_VELOCITY, velocity)


def _retrigger(w):
    # Native: state[env+0x10]=1; state[env]=1; if state[env+8] value=0.
    hold = c.get_u32(w, AMP_ENV + c.ENV_HOLD)
    c.set_u32(w, AMP_ENV + c.ENV_HOLD, (hold & 0xFFFFFF00) | 1)
    w[AMP_ENV + c.ENV_STATE] = 1
    if w[ENV_RESET]:
        c.set_u32(w, AMP_ENV + c.ENV_VALUE, 0)


@dataclass
class Slap:
    words: list[int]
    ring: list[int]

    def __post_init__(self):
        if len(self.words) != WORDS: raise ValueError(f"Slap state must be {WORDS} words")
        if len(self.ring) != RING_LEN: raise ValueError(f"Slap ring must be {RING_LEN} samples")
        self.words=[int(v)&c.MASK16 for v in self.words]
        self.ring=[int(v)&c.MASK16 for v in self.ring]

    @classmethod
    def from_arm(cls, raw):
        if len(raw)!=0x2670: raise ValueError("Slap ARM state must be 0x2670 bytes")
        w=[0]*WORDS
        w[VELOCITY]=raw[6]
        c.copy_env_from_arm(w,AMP_ENV,raw,0x74)
        w[ENV_RESET]=raw[0x7C]
        c.copy_noise_from_arm(w,NOISE,raw)
        _filter_from_arm(w,raw)
        for i,off in enumerate((0xC2,0xC4,0xC6,0xCA)): w[COUNTERS+i]=c.u16(raw,off)
        for i in range(5):
            w[TAPS+i]=c.u16(raw,0xCC+2*i)
            w[TAPS+5+i]=c.u16(raw,0xD6+2*i)
        ring=[c.u16(raw,0xE0+2*i) for i in range(RING_LEN)]
        w[INDEX]=c.u16(raw,0x266A)
        w[MIX]=c.u16(raw,0x266C)
        return cls(w,ring)

    def apply_to_arm(self,template):
        if len(template)!=0x2670: raise ValueError("Slap template must be 0x2670 bytes")
        raw=bytearray(template);w=self.words
        raw[6]=w[VELOCITY]&0xff
        c.copy_env_to_arm(w,AMP_ENV,raw,0x74);raw[0x7C]=w[ENV_RESET]&0xff
        c.copy_noise_to_arm(w,NOISE,raw);_filter_to_arm(w,raw)
        for i,off in enumerate((0xC2,0xC4,0xC6,0xCA)): c.put16(raw,off,w[COUNTERS+i])
        for i in range(5):
            c.put16(raw,0xCC+2*i,w[TAPS+i]);c.put16(raw,0xD6+2*i,w[TAPS+5+i])
        for i,v in enumerate(self.ring): c.put16(raw,0xE0+2*i,v)
        c.put16(raw,0x266A,w[INDEX]);c.put16(raw,0x266C,w[MIX])
        return bytes(raw)

    def _delay(self,input_value):
        w=self.words;index=w[INDEX];next_index=index+1
        if next_index>RING_LEN-1: next_index=0
        stage=input_value
        for tap in range(5):
            delay=w[TAPS+tap];gain=w[TAPS+5+tap]
            acc=c.mullo(stage,c.s32(gain)-0x10)
            ri=index-delay if index>=delay else RING_LEN+index-delay
            delayed=c.s16(self.ring[ri])
            acc=c.add(acc,c.mullo(gain,delayed))
            stage=c.asr(acc,4);stage=max(-32767,min(32767,stage))
        self.ring[next_index]=stage&c.MASK16;w[INDEX]=next_index
        mix=c.s16(w[MIX]);wet=c.asr(c.mullo(stage,5),1)
        output=c.mullo(input_value,0x0FFF-mix)
        output=c.add(output,c.mullo(mix,wet))
        return c.asr(output,12)

    def render(self,n,envelope1,envelope2,rng):
        if len(rng)!=2: raise ValueError("rng must be [low32,high32]")
        w=self.words;out=[]
        for _ in range(n):
            noise=c.render_noise(w,NOISE,rng);_advance_filter(w,noise);_advance_filter(w,noise)
            first=w[COUNTERS]
            if w[COUNTERS+3]>first:w[COUNTERS]=(first+1)&c.MASK16
            else:
                second=w[COUNTERS+1]
                if w[COUNTERS+2]>second:
                    w[COUNTERS+1]=(second+1)&c.MASK16;w[COUNTERS]=0;_retrigger(w)
            amp=c.render_envelope(w,AMP_ENV,envelope1,envelope2)
            scaled=c.asr(c.mullo(c.s32(c.get_u32(w,FILTER+F_FIRST)),amp),16)
            out.append(c.velocity_scale(w[VELOCITY],self._delay(scaled)))
        return out
