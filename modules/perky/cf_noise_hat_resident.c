/* Opt-in pipeline experiment. Evolving inner synthesis state resides on A.
 * The codec is shared with the already qualified original inner offload.
 * Ring/clock/control shadow remain on CF; no per-frame dynamic state returns.
 */
#include "cf_noise_hat_offload.c"
uint32_t pk_nhr_enabled=1,pk_nhr_sequence,pk_nhr_dma_reads,pk_nhr_dma_done;
uint32_t pk_nhr_failures,pk_nhr_consumed,pk_nhr_packet_words,pk_nhr_initializations;
uint32_t pk_nhr_lag_min=0xffffffffu,pk_nhr_lag_max;
volatile uint16_t pk_nhr_mail[24];
#ifdef __mcoldfire__
#define NHR8(a) (*(volatile uint8_t*)(uintptr_t)(a))
#define NHR32(a) (*(volatile uint32_t*)(uintptr_t)(a))
/* Called after the stock A read-back completes, before the stock B pull.
 * Audio samples are 24 bits packed into 32. The low byte is discarded by
 * the stock unpacker. Remove the carrier bytes before ANY stock CF reader.
 * The original eDMA word count, command sequence and bank handshake remain.
 */
int pk_nhr_dma_step(void)
{
    if(!pk_nhr_enabled||!pk_nhr_sequence)return 0;
    uint32_t at=0x80003390u+NHR32(0x800000e0u)*0x400u;
    for(unsigned i=0;i<24;i++){
        uint16_t hi=NHR8(at+8*i+3),lo=NHR8(at+8*i+7);
        pk_nhr_mail[i]=(uint16_t)((hi<<8)|lo);
        NHR8(at+8*i+3)=0;NHR8(at+8*i+7)=0;
    }
    pk_nhr_dma_reads++;pk_nhr_dma_done++;return 0;
}
#endif

void pk_nhr_delay(uint8_t*s,int16_t*pcm,unsigned n,int mix)
{
    nh_delay_c d;nh_delay_load(&d,s);d.mix=mix;
    for(unsigned i=0;i<n;i++)pcm[i]=(int16_t)nh_delay_step(s,&d,pcm[i]);
    w16(s,NH_IDX,(uint16_t)d.index);
}
/* Read-only observer boundary: host qualification follows controls without
 * adding a second target renderer to the timing workload. */
__attribute__((noinline)) void pk_nhr_expect(uint8_t*s,unsigned n,unsigned mode,
    const pk_cf_nh_tables*t,pk_cf_nh_rng*rng,pk_cf_nh_hold hold,int init,int trig)
{(void)s;(void)n;(void)mode;(void)t;(void)rng;(void)hold;(void)init;(void)trig;__asm__ volatile("":::"memory");}
