#!/usr/bin/env python3
"""Generate arithmetic-only high-half quotients for exact division by 147."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MAX_AUDIO_DIVIDEND=65535*32*146+146
LOW_RECIPROCAL=((1<<23)+146)//147
assert LOW_RECIPROCAL==57066
# For t <= 65535+146, multiplication fits u32 and ceil reciprocal's
# positive error is smaller than one remainder step (1/147).
assert (65535+146)*LOW_RECIPROCAL < 1<<32
assert (65535+146)*(147*LOW_RECIPROCAL-(1<<23)) < 1<<23
def generate(path):
 words=[]
 for high in range((MAX_AUDIO_DIVIDEND>>16)+1):
  q,r=divmod(high<<16,147);assert r<256 and q<1<<24
  words.append((q<<8)|r)
 path=Path(path);path.write_text('/* Generated integer arithmetic; contains no firmware data. */\nconst uint32_t nhb_div147_high[]={\n'+''.join(' '+','.join(f'0x{v:08x}u' for v in words[i:i+8])+',\n' for i in range(0,len(words),8))+'};\n')
 return dict(words=len(words),bytes=4*len(words),maximum_dividend=MAX_AUDIO_DIVIDEND,low_reciprocal=LOW_RECIPROCAL)
