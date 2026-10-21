"""Slap amplitude envelope through the shared assembly envelope block.

The span renderer's per-sample loop advanced the burst counters and stepped
the object-resident envelope (slap_env) sample by sample. The counters are
independent of the envelope, so this transform walks them first and runs the
shared envelope block (modules/perky/cf_env_block.s) between retrigger
samples. A retrigger applies slap_retrigger's exact effects to the native
context before that sample's step: hold byte 0x84 = 1 (the envelope's f10
flag), state 1, and value 0 when the reset slot 0x7c is armed. The object's
state byte and value are committed once. A curve selector whose table is
absent keeps the original per-sample loop.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = (('pkenvblock', ROOT / 'modules/perky/cf_env_block.s'),)

HELPERS = '''
/* PKFM24: shared assembly envelope block. */
typedef struct { int32_t v; uint32_t st,up,dn; const uint8_t *curve; uint32_t flags; } pk_cf_env_ctx;
extern void pk_cf_env_block(pk_cf_env_ctx*,uint16_t*,uint32_t);
'''

ORIGINAL = '''    for(i=0;i<n;i++){

        uint16_t a;
        int32_t scaled;

        if((uint32_t)target>(uint32_t)first_count){
            first_count=(uint16_t)(first_count+1u);
        }else if((uint32_t)second_limit>(uint32_t)second_count){
            second_count=(uint16_t)(second_count+1u);
            first_count=0u;
            slap_retrigger(s);
        }
        a=slap_env(s,0x74,t);
        scaled=asr(mullo(filtered[i],(int32_t)a),16);
        inner_block[i]=scaled;
    }
'''

REPLACED = '''    {
        const uint8_t curve=s[0x75];
        const uint8_t *table=curve==1?t->envelope1:curve==2?t->envelope2:0;
        if((curve==1||curve==2)&&!table){
            for(i=0;i<n;i++){
                uint16_t a;
                if((uint32_t)target>(uint32_t)first_count){
                    first_count=(uint16_t)(first_count+1u);
                }else if((uint32_t)second_limit>(uint32_t)second_count){
                    second_count=(uint16_t)(second_count+1u);
                    first_count=0u;
                    slap_retrigger(s);
                }
                a=slap_env(s,0x74,t);
                inner_block[i]=asr(mullo(filtered[i],(int32_t)a),16);
            }
        }else{
            uint16_t amps[20];uint32_t start=0;
            pk_cf_env_ctx x={s32(r32(s,0x80)),s[0x74],r16(s,0x94),r16(s,0x96),table,
                (s[0x78]?1u:0u)|(s[0x7a]?2u:0u)|(s[0x7b]?4u:0u)|(s[0x84]?8u:0u)};
            for(i=0;i<n;i++){
                if((uint32_t)target>(uint32_t)first_count){
                    first_count=(uint16_t)(first_count+1u);
                }else if((uint32_t)second_limit>(uint32_t)second_count){
                    second_count=(uint16_t)(second_count+1u);
                    first_count=0u;
                    if(i>start){pk_cf_env_block(&x,amps+start,i-start);start=i;}
                    s[0x84]=1u;x.flags|=8u;x.st=1u;
                    if(s[0x7c])x.v=0;
                }
            }
            if(n>start)pk_cf_env_block(&x,amps+start,n-start);
            s[0x74]=(uint8_t)x.st;w32(s,0x80,u32(x.v));
            for(i=0;i<n;i++)inner_block[i]=asr(mullo(filtered[i],(int32_t)amps[i]),16);
        }
    }
'''


def once(text, old, new):
    assert text.count(old) == 1, ('Slap envelope transform anchor changed', old[:80])
    return text.replace(old, new, 1)


def transform(work, source_path):
    text = Path(source_path).read_text()
    marker = '/* --- shared 32-bit PRNG, identical to cf_fold\'s --------------------------- */'
    text = once(text, marker, HELPERS.lstrip('\n') + '\n' + marker)
    text = once(text, ORIGINAL, REPLACED)
    target = Path(work) / 'slap-env-asm.c'
    target.write_text(text)
    return target
