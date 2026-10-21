/* Same-frame cooperative transport prototype. The DSP packet/codec remain
 * identical to the synchronous experiment. Poll never waits for readiness. */
#define pk_nha_bind_port pk_nha_unused_bind_port
#include "cf_noise_hat_offload.c"
#undef pk_nha_bind_port

extern void pk_nhaa_ready(void);
uint32_t pk_nhaa_polls,pk_nhaa_poll_words,pk_nhaa_cleanup_waits;
static struct {
    uint8_t *raw;int16_t *pcm;uint32_t n;unsigned mode;
    pk_cf_nh_rng *rng;uint16_t *hold;const pk_cf_nh_tables *tables;
    uint16_t words[121],side[6],sr,icr;
    uint8_t select;unsigned phase,tx,rx,count,begin,pending;
    uint32_t stock,tag,end;
} nhaa;

void pk_nhaa_begin(uint8_t*s,int16_t*d,uint32_t n,unsigned mode,
    const pk_cf_nh_tables*t,pk_cf_nh_rng*rng,pk_cf_nh_hold hold)
{
    nhaa.raw=s;nhaa.pcm=d;nhaa.n=n;nhaa.mode=mode;nhaa.tables=t;nhaa.rng=rng;nhaa.hold=hold;
    nhaa.phase=0;nhaa.tx=nhaa.rx=0;
    if(!pk_nha_enabled){pk_nha_unused_renderer(s,d,n,mode,t,rng,hold);nhaa.phase=5;return;}
    if(mode<2&&s[NH_MUTE]){for(unsigned i=0;i<n;i++)d[i]=0;nhaa.phase=5;return;}
    pk_nha_codec(s,mode,nhaa.words,0);
    nhaa.side[0]=hold[0];nhaa.side[1]=hold[1];nhaa.side[2]=(uint16_t)rng->low;nhaa.side[3]=(uint16_t)(rng->low>>16);
    nhaa.side[4]=(uint16_t)rng->high;nhaa.side[5]=(uint16_t)(rng->high>>16);
    nhaa.begin=mode==1?81:0;nhaa.count=mode==0?81:mode==1?28:59;
#ifdef __mcoldfire__
    __asm__ volatile("move.w %%sr,%0\n\tmove.w #0x2700,%%sr":"=d"(nhaa.sr)::"memory","cc");
    volatile uint8_t *sel=(volatile uint8_t *)(uintptr_t)0xfc0a400cu;
    nhaa.select=*sel;*sel=0;nhaa.icr=NHA_IO(0)&255u;nhaa.phase=1;
#endif
}

void __attribute__((noinline)) pk_nhaa_complete(void)
{
    if(nhaa.phase!=5){
        pk_nha_codec(nhaa.raw,nhaa.mode,nhaa.words,1);
        nhaa.hold[0]=nhaa.side[0];nhaa.hold[1]=nhaa.side[1];
        nhaa.rng->low=(uint32_t)nhaa.side[2]|((uint32_t)nhaa.side[3]<<16);
        nhaa.rng->high=(uint32_t)nhaa.side[4]|((uint32_t)nhaa.side[5]<<16);
        if(nhaa.mode<2){nh_delay_c d;nh_delay_load(&d,nhaa.raw);
            for(unsigned i=0;i<nhaa.n;i++)nhaa.pcm[i]=(int16_t)nh_delay_step(nhaa.raw,&d,nhaa.pcm[i]);
            w16(nhaa.raw,NH_IDX,(uint16_t)d.index);}
        pk_nha_calls++;pk_nha_samples+=nhaa.n;
    }
    nhaa.phase=0;
}

void pk_nhaa_poll(void)
{
    pk_nhaa_polls++;
    if(!nhaa.phase)return;
    if(nhaa.phase==5){pk_nhaa_complete();pk_nhaa_ready();return;}
#ifdef __mcoldfire__
    /* Bounded work only while the port advertises readiness. A failed
     * readiness test returns to useful CF rendering immediately. */
    for(unsigned budget=0;budget<256;budget++){
        if(nhaa.phase==1){if(NHA_IO(4)&128u)return;
            NHA_IO(4)=(uint16_t)((nhaa.icr<<8)|0x96u);nhaa.phase=2;return;}
        if(nhaa.phase==2){if(NHA_IO(4)&128u)return;
            nhaa.pending=(NHA_IO(8)&1u)!=0;nhaa.stock=nhaa.pending?nha_receive():0;nhaa.phase=3;}
        if(nhaa.phase==3){
            if(nhaa.tx==4+nhaa.count+6){nhaa.phase=4;continue;}
            if((NHA_IO(8)&6u)!=6u)return;
            unsigned i=nhaa.tx++;uint32_t v=i==0?nhaa.mode:i==1?nhaa.n:i==2?nhaa.pending:i==3?nhaa.stock:
                i<4+nhaa.count?nhaa.words[nhaa.begin+i-4]:nhaa.side[i-4-nhaa.count];
            NHA_IO(0x18)=(uint16_t)(v>>8);NHA_IO(0x1c)=(uint16_t)v;pk_nhaa_poll_words++;continue;
        }
        if(nhaa.rx<2+nhaa.count+6+nhaa.n){
            if(!(NHA_IO(8)&1u))return;
            uint32_t v=nha_receive();unsigned i=nhaa.rx++;pk_nhaa_poll_words++;
            if(!i)nhaa.tag=v;
            else if(i<=nhaa.count)nhaa.words[nhaa.begin+i-1]=(uint16_t)v;
            else if(i<=nhaa.count+6)nhaa.side[i-nhaa.count-1]=(uint16_t)v;
            else if(i<=nhaa.count+6+nhaa.n)nhaa.pcm[i-nhaa.count-7]=(int16_t)v;
            else nhaa.end=v;
            continue;
        }
        if(nhaa.pending&&!(NHA_IO(8)&1u))return;
        NHA_IO(0)=nhaa.icr;*(volatile uint8_t *)(uintptr_t)0xfc0a400cu=nhaa.select;
        __asm__ volatile("move.w %0,%%sr"::"d"(nhaa.sr):"memory","cc");
        if(nhaa.tag!=(0x4e4800u|(nhaa.mode<<5)|nhaa.n)||nhaa.end!=0x4e4844u)pk_nha_failures++;
        pk_nhaa_complete();pk_nhaa_ready();return;
    }
#endif
}
int pk_nhaa_active(void){return nhaa.phase!=0;}
void pk_nhaa_drain(void){if(nhaa.phase)pk_nhaa_cleanup_waits++;while(nhaa.phase)pk_nhaa_poll();}
void pk_nha_bind_port(void){}
