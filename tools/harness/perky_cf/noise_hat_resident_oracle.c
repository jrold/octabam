/* Compile beside a copy of the qualified CF renderer with only the wrapper
 * delay call removed: the transport returns INNER samples. Control setters
 * retain their original CF implementation. Dynamic state is kept here. */
#include "cf_noise_hat_offload.c"
static uint8_t resident_classic[0x2dd8],resident_pulse[0x160];
static pk_cf_nh_rng resident_rng;
static uint16_t resident_hold[2];
static unsigned initialized;
static const uint8_t keys0[]={1,6,11,12,15,16,21,22,27,28,33,34,39,40,45,46};
static const uint8_t keys1[]={81,86,91,92,97,104,107};
static const uint8_t keys2[]={0,5,10,11,40,41,42,43,44,45,46,47,48,49,50,51,54,55,58};
int pk_nhr_oracle(const uint8_t*controls,unsigned n,unsigned mode,const pk_cf_nh_tables*t,
    const pk_cf_nh_rng*rng,const uint16_t*hold,int init,int trig,int16_t*out,uint16_t*state)
{
    uint8_t*s=mode==2?resident_pulse:resident_classic;
    uint16_t old[121]={0},next[121]={0};
    pk_nha_codec(s,mode,old,0);pk_nha_codec((uint8_t*)controls,mode,next,0);
    if(init){
        unsigned first=mode==1?81:0,count=mode==0?81:mode==1?28:59;
        for(unsigned i=first;i<first+count;i++)old[i]=next[i];
        if(mode==1){resident_rng=*rng;resident_hold[0]=hold[0];resident_hold[1]=hold[1];}
        initialized|=1u<<mode;
    }else{
        const uint8_t*k=mode==0?keys0:mode==1?keys1:keys2;
        unsigned count=mode==0?sizeof(keys0):mode==1?sizeof(keys1):sizeof(keys2);
        for(unsigned i=0;i<count;i++)old[k[i]]=next[k[i]];
        unsigned env=mode==0?2:mode==1?82:1;
        if(trig){old[env]=next[env];old[env+7]=next[env+7];
            size_t b=mode==0?0xc4:mode==1?0x318:0;
            if(controls[b+0x7c]){old[env+5]=next[env+5];old[env+6]=next[env+6];}}
    }
    pk_nha_codec(s,mode,old,1);
    if(mode<2)s[0xb8]=controls[0xb8];
    if(!pk_nha_unused_renderer(s,out,n,mode,t,&resident_rng,resident_hold))return 0;
    pk_nha_codec(s,mode,state,0);
    state[121]=resident_hold[0];state[122]=resident_hold[1];
    state[123]=resident_rng.low;state[124]=resident_rng.low>>16;
    state[125]=resident_rng.high;state[126]=resident_rng.high>>16;
    return 1;
}
