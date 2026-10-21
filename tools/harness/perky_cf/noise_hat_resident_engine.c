/* Included in placement translation unit: original control functions remain
 * the oracle for the control shadow; inner dynamic histories live on DSP-A. */
extern uint32_t pk_nhr_enabled,pk_nhr_sequence,pk_nhr_failures,pk_nhr_consumed;
extern uint32_t pk_nhr_packet_words,pk_nhr_initializations,pk_nhr_lag_min,pk_nhr_lag_max;
extern volatile uint16_t pk_nhr_mail[24];
extern void pk_nha_codec(uint8_t*,unsigned,uint16_t*,int);
static unsigned nhr_initialized;
static const uint8_t nhr_control0[]={1,6,11,12,15,16,21,22,27,28,33,34,39,40,45,46};
static const uint8_t nhr_control1[]={81,86,91,92,97,104,107};
static const uint8_t nhr_control2[]={0,5,10,11,40,41,42,43,44,45,46,47,48,49,50,51,54,55,58};
typedef struct {unsigned start,end,mode,need,reset,mute;int mix;} nhr_segment;
typedef struct {unsigned sequence,split; nhr_segment seg[2];} nhr_job;
static nhr_job nhr_jobs[8];
static nhr_job *nhr_previous;
static unsigned nhr_last_consumed;
static pk_cf_native_clock nhr_schedule_clock;
static uint16_t nhr_commands[88];
static unsigned nhr_used;
static void nhr_put(unsigned v){if(nhr_used<88)nhr_commands[nhr_used++]=(uint16_t)v;else pk_nhr_failures++;}
static void nhr_patch(unsigned mode,unsigned k,unsigned value)
{nhr_put((mode==2?0x3879:0x3800)+k);nhr_put(value);}
static unsigned nhr_needed(unsigned n)
{
    if(!n)return 0;
    unsigned needed=pk_cf_native_needed(&nhr_schedule_clock,n);
    unsigned sum=nhr_schedule_clock.phase+13*n;
    nhr_schedule_clock.phase=sum%147;nhr_schedule_clock.have=nhr_schedule_clock.phase>=13;
    return needed;
}
/* A distinct completion boundary for the external native-PCM witness. */
__attribute__((noinline)) void pk_nhr_accept(const int16_t *pcm,unsigned n)
{(void)pcm;(void)n;__asm__ volatile("":::"memory");}
static void nhr_finish_previous(void)
{
    unsigned sequence=pk_nhr_mail[1];
    if(pk_nhr_mail[0]!=0x4e52){
        if(nhr_last_consumed)pk_nhr_failures++;
        for(unsigned i=0;i<16;i++)placement_output[3][i]=0;
        return;
    }
    nhr_previous=&nhr_jobs[sequence&7];
    if(!sequence||nhr_previous->sequence!=sequence||sequence==nhr_last_consumed){
        pk_nhr_failures++;for(unsigned i=0;i<16;i++)placement_output[3][i]=0;
        return;
    }
    unsigned lag=pk_nhr_sequence-sequence;
    if(lag<pk_nhr_lag_min)pk_nhr_lag_min=lag;
    if(lag>pk_nhr_lag_max)pk_nhr_lag_max=lag;
    nhr_last_consumed=sequence;
    int16_t native[20];unsigned total=pk_nhr_mail[2];
    if(total>20){pk_nhr_failures++;return;}
    for(unsigned i=0;i<total;i++)native[i]=(int16_t)pk_nhr_mail[4+i];
    pk_nhr_accept(native,total);
    unsigned offset=0;pk4_track*t=&placement_engine.tracks[3];
    for(unsigned j=0;j<2;j++){
        nhr_segment*s=&nhr_previous->seg[j];unsigned n=s->end-s->start;
        if(s->reset)pk_cf_native_reset(&placement_clocks[3]);
        if(!n)continue;
        int16_t data[20];unsigned have=placement_clocks[3].have;
        if(have)data[0]=(int16_t)placement_clocks[3].carry;
        for(unsigned i=0;i<s->need;i++)data[have+i]=native[offset+i];
        if(s->mode<2&&!s->mute){
            /* Delay input is the exact original native inner PCM. */
            extern void pk_nhr_delay(uint8_t*,int16_t*,unsigned,int);
            pk_nhr_delay(t->nh,data+have,s->need,s->mix);
        }
        offset+=s->need;
        pk_cf_native_convert(&placement_clocks[3],data,n,placement_output[3]+s->start);
        placement_native_samples[3]+=s->need;
    }
    if(offset!=total)pk_nhr_failures++;
    pk_nhr_consumed++;
}
static void nhr_emit(unsigned mode,unsigned need,int init,int trig,int apply)
{
    pk4_track*t=&placement_engine.tracks[3];uint16_t w[121];
    pk_nha_codec(t->nh+(mode==2?NH_PULSE:0),mode,w,0);
    if(need){
        extern void pk_nhr_expect(uint8_t*,unsigned,unsigned,const pk_cf_nh_tables*,pk_cf_nh_rng*,pk_cf_nh_hold,int,int);
        pk_cf_nh_tables tables={placement_assets.envelope1,placement_assets.envelope2};
        pk_cf_nh_rng rng={t->rng_low,t->rng_high};
        pk_nhr_expect(t->nh+(mode==2?NH_PULSE:0),need,mode,&tables,&rng,placement_engine.nh_hold,init,trig);
    }
    nhr_put(need|(mode<<5));
    if(init)pk_nhr_initializations++;
    if(!need||!apply){nhr_put(0);return;}
    const uint8_t*keys=mode==0?nhr_control0:mode==1?nhr_control1:nhr_control2;
    unsigned count=mode==0?sizeof(nhr_control0):mode==1?sizeof(nhr_control1):sizeof(nhr_control2);
    /* Trigger sets state/hold, and resets value only when the original
     * envelope's reset byte requests it. Never send stale evolving fields. */
    unsigned env=mode==0?2:mode==1?82:1;
    uint8_t*raw=t->nh+(mode==2?NH_PULSE:nh_limb(mode));
    int reset=trig&&raw[0x7c];
    nhr_put(count+(trig?2:0)+(reset?2:0));
    for(unsigned i=0;i<count;i++)nhr_patch(mode,keys[i],w[keys[i]]);
    if(trig){nhr_patch(mode,env,w[env]);nhr_patch(mode,env+7,w[env+7]);}
    if(reset){nhr_patch(mode,env+5,w[env+5]);nhr_patch(mode,env+6,w[env+6]);}
}
void pk_nhr_frame(unsigned split,volatile uint32_t *slot)
{
    if(!pk_nhr_enabled){
        if(!placement_segment(3,0,split,0)||!placement_prepare(3,placement_inputs[3],placement_inputs[3][9]!=0)||
           !placement_segment(3,split,16,1))placement_status=0;
        placement_pack(3,split);for(unsigned i=0;i<40;i++)slot[i]=placement_packets[3][i];return;
    }
    nhr_finish_previous();
    placement_pack(3,split);for(unsigned i=0;i<40;i++)slot[i]=placement_packets[3][i];
    pk4_track*t=&placement_engine.tracks[3];
    unsigned oldmode=nh_mode(t->active_mode),trig=placement_inputs[3][9]!=0;
    nhr_used=0;nhr_put(0x4e52);nhr_put((++pk_nhr_sequence)&65535);
    nhr_previous=&nhr_jobs[pk_nhr_sequence&7];
    nhr_previous->sequence=pk_nhr_sequence;nhr_previous->split=split;
    for(unsigned j=0;j<2;j++){
        nhr_segment*s=&nhr_previous->seg[j];s->start=j?split:0;s->end=j?16:split;
        if(j){
            pk_cf_native_clock clock=placement_clocks[3];
            if(!placement_prepare(3,placement_inputs[3],trig))placement_status=0;
            placement_clocks[3]=clock;
        }
        s->mode=j?nh_mode(t->active_mode):oldmode;
        s->reset=j&&trig;if(s->reset)pk_cf_native_reset(&nhr_schedule_clock);
        s->mute=s->mode<2&&t->nh[0xb8];s->mix=(int16_t)pk_cf_ld16(t->nh,0x2dd4);
        s->need=nhr_needed(s->end-s->start);
        int init=s->need&&!(nhr_initialized&(1u<<s->mode));
        nhr_emit(s->mode,s->need,init,j&&trig,j!=0);
        if(init)nhr_initialized|=1u<<s->mode;
    }
    pk_nhr_packet_words+=nhr_used;
    volatile uint16_t*tail=(volatile uint16_t*)(slot+40);
    for(unsigned i=0;i<nhr_used;i++)tail[i]=nhr_commands[i];
}
