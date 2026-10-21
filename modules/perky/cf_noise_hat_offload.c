/* Experimental DSP-A inner-synthesis offload. The original CF delay body is
 * included verbatim; its ring and the raw original object remain CF-owned.
 * The transport is injected so host gates exercise this very codec/delay.
 */
#define pk_cf_nh_render pk_nha_unused_renderer
#include "cf_noise_hat.c"
#undef pk_cf_nh_render

typedef int (*pk_nha_transport)(unsigned,uint16_t *,uint32_t,uint16_t *,int16_t *);
pk_nha_transport pk_nha_exchange;
uint32_t pk_nha_enabled=1;
uint32_t pk_nha_calls,pk_nha_samples,pk_nha_failures;
volatile uint32_t pk_nha_phase;

static void nha_word(uint8_t *s,size_t o,uint16_t *w,unsigned k,unsigned bytes,int write)
{
    if(write){if(bytes==1)s[o]=(uint8_t)w[k];else if(bytes==2)w16(s,o,w[k]);
        else w32(s,o,(uint32_t)w[k]|((uint32_t)w[k+1]<<16));}
    else {uint32_t v=bytes==1?s[o]:bytes==2?r16(s,o):r32(s,o);w[k]=(uint16_t)v;
        if(bytes==4)w[k+1]=(uint16_t)(v>>16);}
}
static void nha_env(uint8_t*s,size_t b,uint16_t*w,unsigned k,int write)
{
    static const uint8_t offsets[]={0,1,4,6,7,12,16,32,34};
    static const uint8_t widths[]={1,1,1,1,1,4,4,2,2};
    for(unsigned i=0;i<9;i++){nha_word(s,b+offsets[i],w,k,widths[i],write);k+=widths[i]==4?2:1;}
}
static void nha_filter(uint8_t*s,size_t b,uint16_t*w,unsigned k,int write)
{
    nha_word(s,b+12,w,k,2,write);nha_word(s,b+14,w,k+1,2,write);
    for(unsigned i=0;i<3;i++)nha_word(s,b+16+4*i,w,k+2+2*i,4,write);
}
void pk_nha_codec(uint8_t*s,unsigned mode,uint16_t*w,int write)
{
    if(mode==0){
        nha_word(s,NH_MUTE,w,0,1,write);nha_word(s,NH_C0+6,w,1,1,write);
        nha_env(s,NH_C0+0x74,w,2,write);
        for(unsigned i=0;i<6;i++){
            size_t b=NH_C0+0x118+0x34*i;unsigned k=13+6*i;
            nha_word(s,b+4,w,k,4,write);nha_word(s,b+8,w,k+2,4,write);
            nha_word(s,b+0x24,w,k+4,2,write);nha_word(s,b+0x26,w,k+5,2,write);
        }
        static const uint16_t bases[]={0x9c,0xc4,0xe0,0xfc};
        for(unsigned i=0;i<4;i++)nha_filter(s,NH_C0+bases[i],w,49+8*i,write);
    }else if(mode==1){
        nha_word(s,NH_C1+6,w,81,1,write);nha_env(s,NH_C1+0x74,w,82,write);
        nha_word(s,NH_C1+0x60,w,93,2,write);nha_word(s,NH_C1+0x62,w,94,2,write);
        nha_word(s,NH_C1+0x70,w,95,2,write);nha_filter(s,NH_C1+0x9c,w,96,write);
        nha_word(s,NH_C1+0xc2,w,104,1,write);nha_word(s,NH_C1+0xb8,w,105,1,write);
        nha_word(s,NH_C1+0xc4,w,106,2,write);nha_word(s,NH_C1+0xc6,w,107,2,write);
        nha_word(s,NH_C1+0xc8,w,108,2,write);
    }else{
        nha_word(s,6,w,0,1,write);nha_env(s,0x74,w,1,write);
        nha_filter(s,0xc4,w,12,write);nha_filter(s,0xe0,w,20,write);
        static const uint16_t ph[]={0x100,0xfc,0x104,0x108,0x10c,0x110};
        static const uint16_t inc[]={0x11c,0x118,0x120,0x124,0x128,0x12c};
        for(unsigned i=0;i<6;i++){nha_word(s,ph[i],w,28+2*i,4,write);nha_word(s,inc[i],w,40+2*i,4,write);}
        nha_word(s,0x114,w,52,4,write);nha_word(s,0x130,w,54,4,write);
        nha_word(s,0x134,w,56,4,write);nha_word(s,0x138,w,58,2,write);
    }
}

int pk_cf_nh_offload(uint8_t*s,int16_t*dst,uint32_t n,unsigned mode,
    const pk_cf_nh_tables*t,pk_cf_nh_rng*rng,pk_cf_nh_hold hold)
{
    if(!pk_nha_enabled)return pk_nha_unused_renderer(s,dst,n,mode,t,rng,hold);
    if(!n)return 1;
    if(mode>2||n>20||!pk_nha_exchange)return 0;
    if(mode<2&&s[NH_MUTE]){for(unsigned i=0;i<n;i++)dst[i]=0;return 1;}
    uint16_t words[121],side[6]={hold[0],hold[1],(uint16_t)rng->low,(uint16_t)(rng->low>>16),
        (uint16_t)rng->high,(uint16_t)(rng->high>>16)};
    pk_nha_codec(s,mode,words,0);
    if(!pk_nha_exchange(mode,words,n,side,dst)){pk_nha_failures++;return 0;}
    pk_nha_codec(s,mode,words,1);
    hold[0]=side[0];hold[1]=side[1];rng->low=(uint32_t)side[2]|((uint32_t)side[3]<<16);
    rng->high=(uint32_t)side[4]|((uint32_t)side[5]<<16);
    if(mode<2){nh_delay_c d;nh_delay_load(&d,s);
        for(unsigned i=0;i<n;i++)dst[i]=(int16_t)nh_delay_step(s,&d,dst[i]);
        w16(s,NH_IDX,(uint16_t)d.index);}
    pk_nha_calls++;pk_nha_samples+=n;return 1;
}

#ifdef __mcoldfire__
#define NHA_IO(o) (*(volatile uint16_t *)(uintptr_t)(0x20000000u+(o)))
static void nha_send(uint32_t v)
{
    while((NHA_IO(8)&6u)!=6u){}
    /* CS2 is a 16-bit bus: a halfword writes the addressed byte and its
     * predecessor. Preserve the middle lane on the final TXM:TXL cycle. */
    NHA_IO(0x18)=(uint16_t)(v>>8);NHA_IO(0x1c)=(uint16_t)v;
}
static uint32_t nha_receive(void)
{
    while(!(NHA_IO(8)&1u)){}
    uint32_t a=NHA_IO(0x14)&255u,b=NHA_IO(0x18)&255u,c=NHA_IO(0x1c)&255u;
    return (a<<16)|(b<<8)|c;
}
static int nha_port(unsigned mode,uint16_t*w,uint32_t n,uint16_t*side,int16_t*pcm)
{
    uint16_t saved_sr;
    /* The stock level-6 transfer ISR also selects this host port. Its
     * selector must not change in the middle of a polled transaction. */
    __asm__ volatile("move.w %%sr,%0\n\tmove.w #0x2700,%%sr":"=d"(saved_sr)::"memory","cc");
    volatile uint8_t *select=(volatile uint8_t *)(uintptr_t)0xfc0a400cu;
    pk_nha_phase=1;
    uint8_t previous=*select;*select=0;
    while(NHA_IO(4)&128u){}
    uint16_t icr=NHA_IO(0)&255u;
    NHA_IO(4)=(uint16_t)((icr<<8)|0x96u); /* ICR:CVR share one bus cycle */
    while(NHA_IO(4)&128u){} /* core is parked inside our ISR before we drain */
    unsigned pending=(NHA_IO(8)&1u)!=0;
    uint32_t stock_word=pending?nha_receive():0;
    pk_nha_phase=2;nha_send(mode);nha_send(n);nha_send(pending);nha_send(stock_word);
    unsigned begin=mode==1?81:0,count=mode==0?81:mode==1?28:59;
    for(unsigned i=0;i<count;i++)nha_send(w[begin+i]);
    for(unsigned i=0;i<6;i++)nha_send(side[i]);
    pk_nha_phase=3;uint32_t tag=nha_receive();
    pk_nha_phase=4;
    for(unsigned i=0;i<count;i++)w[begin+i]=(uint16_t)nha_receive();
    pk_nha_phase=5;for(unsigned i=0;i<6;i++)side[i]=(uint16_t)nha_receive();
    pk_nha_phase=6;for(unsigned i=0;i<n;i++)pcm[i]=(int16_t)nha_receive();
    pk_nha_phase=7;uint32_t end=nha_receive();
    if(pending)while(!(NHA_IO(8)&1u)){} /* original HOTX word restored */
    NHA_IO(0)=icr;*select=previous;pk_nha_phase=8;
    __asm__ volatile("move.w %0,%%sr"::"d"(saved_sr):"memory","cc");
    return tag==(0x4e4800u|(mode<<5)|n)&&end==0x4e4844u;
}
void pk_nha_bind_port(void){pk_nha_exchange=nha_port;}
#endif
