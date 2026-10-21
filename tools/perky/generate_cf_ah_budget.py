"""Opt-in Acoustic Hats state caching; exact float arithmetic stays intact.

All controls and histories are loaded at each render call. The engine has no
callbacks and its private state is published at that same call boundary. An
ended sample still advances the envelope but freezes sample/filter history,
as in the original. No cross-call initialization invariant is assumed.
"""
import hashlib
from pathlib import Path

ORIGINAL_SHA256 = 'b097e7220708c930a5fe3efaf4513994756a97c8bad53410bf07b0a8026249e0'


def generate(source, destination, *, cached_state=True, native_arithmetic=True):
    source, destination = Path(source), Path(destination)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ORIGINAL_SHA256, 'Acoustic Hats original drift'
    text = source.read_text()
    if native_arithmetic:
        for before, after in (
            ('static int16_t s16(uint16_t u){return (u&0x8000u)?(int16_t)(-1-(int16_t)(uint16_t)~u):(int16_t)u;}',
             'static int16_t s16(uint16_t u){return (int16_t)u;}'),
            ('static int32_t s32(uint32_t u){return (u&0x80000000u)?-1-(int32_t)~u:(int32_t)u;}',
             'static int32_t s32(uint32_t u){return (int32_t)u;}'),
            ('static uint32_t u32(int32_t s){return s>=0?(uint32_t)s:~(uint32_t)(-1-s);}',
             'static uint32_t u32(int32_t s){return (uint32_t)s;}'),
            ('static int32_t asr(int32_t v,unsigned n){uint32_t b;if(!n)return v;b=u32(v)>>n;if(v<0)b|=(~0u)<<(32u-n);return s32(b);}',
             'static int32_t asr(int32_t v,unsigned n){return v>>n;}'),
        ):
            assert text.count(before) == 1, before
            text = text.replace(before, after, 1)
    if cached_state:
        begin = text.index('int pk_cf_ah_render(')
        prefix, body = text[:begin], text[begin:]
        before = '    length=r32(s,0xfc);'
        after = before + '''
    uint32_t current_index=r32(s,0xc4),fraction=r32(s,0xc8),hold_left=r32(s,0xdc);
    const uint32_t mask=r32(s,0xd4),shift=s[0xd0],rate=r32(s,0xcc),reload=r32(s,0xd8);
    uint32_t decayed=r32(s,0x104),integer_history=r32(s,0x100);
    int32_t current_hold=*hold;
    uint8_t seed=s[0x108];const uint8_t mute=s[0xb8],velocity=s[6];
'''
        assert body.count(before) == 1
        body = body.replace(before, after, 1)
        for before, after in (
            ('        const uint32_t index=r32(s,0xc4);', '        const uint32_t index=current_index;'),
            ('        uint32_t fraction,mask,shift,hold_left,advanced;', '        uint32_t advanced;'),
            ('            fraction=r32(s,0xc8);mask=r32(s,0xd4);shift=(uint32_t)s[0xd0];hold_left=r32(s,0xdc);', ''),
            ('interpolated=s32((uint32_t)*hold);', 'interpolated=current_hold;'),
            ('                *hold=interpolated;', '                current_hold=interpolated;'),
            ('hold_left=r32(s,0xd8);', 'hold_left=reload;'),
            ('            w32(s,0xdc,hold_left);', ''),
            ('advanced=(fraction+r32(s,0xcc))&0xffffffffu;', 'advanced=(fraction+rate)&0xffffffffu;'),
            ('w32(s,0xc4,(index+(advanced>>shift))&0xffffffffu);', 'current_index=(index+(advanced>>shift))&0xffffffffu;'),
            ('w32(s,0xc8,advanced&mask);', 'fraction=advanced&mask;'),
            ('if(s[0x108]){previous=pk_cf_i32_to_f32(s32(r32(s,0x100)));s[0x108]=0u;}',
             'if(seed){previous=pk_cf_i32_to_f32(s32(integer_history));seed=0u;}'),
            ('else previous=r32(s,0x104);', 'else previous=decayed;'),
            ('w32(s,0x104,pk_cf_f32_mul(previous,PK_CF_AH_DECAY_BITS));', 'decayed=pk_cf_f32_mul(previous,PK_CF_AH_DECAY_BITS);'),
            ('w32(s,0x100,(uint32_t)filtered);', 'integer_history=(uint32_t)filtered;'),
            ('if(s[0xb8])', 'if(mute)'),
            ('(int32_t)(s[6]&0xffu)', '(int32_t)velocity'),
            ('    return 1;', '''    w32(s,0xc4,current_index);w32(s,0xc8,fraction);w32(s,0xdc,hold_left);
    w32(s,0x104,decayed);w32(s,0x100,integer_history);s[0x108]=seed;*hold=current_hold;
    return 1;'''),
        ):
            assert body.count(before) == 1, before
            body = body.replace(before, after, 1)
        text = prefix + body
    destination.write_text(text)
    return destination


def transform(work, source_path):
    return generate(source_path, Path(work) / 'acoustic-hats-native-state.c')
