"""Compact exact v1.2.1 Karplus renderer with external 2K delay ring."""
from __future__ import annotations
from dataclasses import dataclass
import resonator_compact as c

RING_LEN=0x800
WORDS=32
VELOCITY=0;MUTE=1;MODE=2;AMP_ENV=3
NOISE=AMP_ENV+c.ENV_WORDS
FILTER=NOISE+3
F_DAMP,F_COEFF,F_FIRST,F_SECOND,F_VELOCITY=0,1,2,4,6
EXCITE_TARGET=FILTER+8;EXCITE_COUNT=EXCITE_TARGET+1
DELAY=EXCITE_COUNT+1;WRITE_INDEX=DELAY+2;AGE=WRITE_INDEX+1
assert AGE+2==WORDS

def _filter_from_arm(w,raw):
 w[FILTER]=c.u16(raw,0xA8);w[FILTER+1]=c.u16(raw,0xAA)
 c.set_u32(w,FILTER+2,c.u32(raw,0xAC));c.set_u32(w,FILTER+4,c.u32(raw,0xB0));c.set_u32(w,FILTER+6,c.u32(raw,0xB4))
def _filter_to_arm(w,raw):
 c.put16(raw,0xA8,w[FILTER]);c.put16(raw,0xAA,w[FILTER+1]);c.put32(raw,0xAC,c.get_u32(w,FILTER+2));c.put32(raw,0xB0,c.get_u32(w,FILTER+4));c.put32(raw,0xB4,c.get_u32(w,FILTER+6))
def _advance_filter(w,input_value):
 coeff=w[FILTER+F_COEFF];velocity=c.s32(c.get_u32(w,FILTER+F_VELOCITY))
 product=c.mullo(velocity,coeff)
 if product<0:product=c.s32(c.u32bits(product)+0xFFFF)
 first=c.add(c.s32(c.get_u32(w,FILTER+F_FIRST)),c.asr(product,16));first=max(-32767,min(32767,first));c.set_u32(w,FILTER+F_FIRST,first)
 second=c.sub(input_value,first);second=c.sub(second,c.asr(c.mullo(velocity,w[FILTER+F_DAMP]),10));second=max(-32767,min(32767,second));c.set_u32(w,FILTER+F_SECOND,second)
 feedback=c.mullo(second,coeff)
 if feedback<0:feedback=c.s32(c.u32bits(feedback)+0xFFFF)
 velocity=c.add(velocity,c.asr(feedback,16));velocity=max(-32767,min(32767,velocity));c.set_u32(w,FILTER+F_VELOCITY,velocity)
def _signed_bitfield(value,lsb,width):
 mask=(1<<width)-1;bits=(c.u32bits(value)>>lsb)&mask;sign=1<<(width-1)
 if bits&sign:bits|=~mask
 return c.s32(bits)
def _sat16(v):return max(-32768,min(32767,v))

@dataclass
class Karplus:
 words:list[int];ring:list[int]
 def __post_init__(self):
  if len(self.words)!=WORDS:raise ValueError(f'Karplus state must be {WORDS} words')
  if len(self.ring)!=RING_LEN:raise ValueError(f'Karplus ring must be {RING_LEN} samples')
  self.words=[int(v)&c.MASK16 for v in self.words];self.ring=[int(v)&c.MASK16 for v in self.ring]
 @classmethod
 def from_arm(cls,raw):
  if len(raw)!=0x10E0:raise ValueError('Karplus ARM state must be 0x10e0 bytes')
  w=[0]*WORDS;w[VELOCITY]=raw[6];w[MUTE]=raw[0xB8];w[MODE]=raw[5]
  c.copy_env_from_arm(w,AMP_ENV,raw,0x74);c.copy_noise_from_arm(w,NOISE,raw);_filter_from_arm(w,raw)
  w[EXCITE_TARGET]=c.u16(raw,0xC2);w[EXCITE_COUNT]=c.u16(raw,0xC4);c.set_u32(w,DELAY,c.u32(raw,0x10C8));w[WRITE_INDEX]=c.u16(raw,0x10D4);c.set_u32(w,AGE,c.u32(raw,0x10D8))
  ring=[c.u16(raw,0xC6+2*i) for i in range(RING_LEN)]
  return cls(w,ring)
 def apply_to_arm(self,template):
  if len(template)!=0x10E0:raise ValueError('Karplus template must be 0x10e0 bytes')
  raw=bytearray(template);w=self.words;raw[6]=w[VELOCITY]&0xff;raw[0xB8]=w[MUTE]&0xff;raw[5]=w[MODE]&0xff
  c.copy_env_to_arm(w,AMP_ENV,raw,0x74);c.copy_noise_to_arm(w,NOISE,raw);_filter_to_arm(w,raw);c.put16(raw,0xC2,w[EXCITE_TARGET]);c.put16(raw,0xC4,w[EXCITE_COUNT])
  for i,v in enumerate(self.ring):c.put16(raw,0xC6+2*i,v)
  c.put32(raw,0x10C8,c.get_u32(w,DELAY));c.put16(raw,0x10D4,w[WRITE_INDEX]);c.put32(raw,0x10D8,c.get_u32(w,AGE));return bytes(raw)
 def render(self,n,envelope1,envelope2,rng):
  if len(rng)!=2:raise ValueError('rng must be [low32,high32]')
  w=self.words;out=[]
  for _ in range(n):
   amp=c.render_envelope(w,AMP_ENV,envelope1,envelope2);counter=w[EXCITE_COUNT];target=w[EXCITE_TARGET];excitation=0
   if target>counter:w[EXCITE_COUNT]=(counter+1)&c.MASK16;excitation=c.render_noise(w,NOISE,rng)
   else:w[EXCITE_COUNT]=0xFFFF
   delay=c.get_u32(w,DELAY);wi=w[WRITE_INDEX];ri=(wi-delay)&0x7FF;ring_sample=self.ring[ri]  # unsigned load is intentional
   _advance_filter(w,c.s32((ring_sample+excitation)&c.MASK32))
   wi=w[WRITE_INDEX];age=c.get_u32(w,AGE);ring_index=wi&0x7FF;sample=c.s32(c.get_u32(w,FILTER+F_FIRST));self.ring[ring_index]=sample&c.MASK16;w[WRITE_INDEX]=(wi+1)&c.MASK16
   if age<=0x210:
    mode=w[MODE]&0xff
    if mode==0:
     noise=c.render_noise(w,NOISE,rng)
     if age<=0x110:
      if age<=0x8F:
       transient=c.add(noise,c.mullo(noise,4));transient=c.add(noise,c.mullo(transient,2));transient=_signed_bitfield(transient,4,26);sample=c.add(sample,transient)
      else:
       tapered=c.mullo(0x110-age,noise);logical=c.u32bits(tapered)>>8;scaled=c.mullo(44,c.s32(logical));sample=c.add(sample,c.asr(scaled,6))
      age=(age+1)&c.MASK32;sample=_sat16(sample)
     else:age=(age+1)&c.MASK32;sample=_sat16(sample)
    elif mode==2:
     noise=c.render_noise(w,NOISE,rng)
     if age<=0x2F0:
      if age<=0xEF:
       transient=c.add(noise,c.mullo(noise,4));transient=c.add(noise,c.mullo(transient,2));transient=_signed_bitfield(transient,4,26);sample=c.add(sample,transient)
      else:
       tapered=c.mullo(0x2F0-age,noise);logical=c.u32bits(tapered)>>10;scaled=c.mullo(44,c.s32(logical));sample=c.add(sample,c.asr(scaled,6))
      sample=max(-32767,min(32767,sample))
     age=(age+1)&c.MASK32
    else:age=(age+1)&c.MASK32
   c.set_u32(w,AGE,age)
   if w[MUTE]:out.append(0);continue
   value=c.asr(c.mullo(sample,amp),16);out.append(c.velocity_scale(w[VELOCITY],value))
  return out
