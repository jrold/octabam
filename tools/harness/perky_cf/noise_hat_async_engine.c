/* Included after placement_cf_engine.c in the opt-in translation unit. */
extern void pk_nhaa_begin(uint8_t*,int16_t*,uint32_t,unsigned,const pk_cf_nh_tables*,pk_cf_nh_rng*,pk_cf_nh_hold);
extern void pk_nhaa_poll(void);
extern void pk_nhaa_drain(void);
static struct {unsigned stage,split,start,end,have,need;int16_t data[20];pk_cf_nh_rng rng;pk_cf_nh_tables tables;} nha_job;
uint32_t pk_nhaa_frame_done;

static void nha_next(void);
void pk_nhaa_ready(void)
{
    pk4_track*t=&placement_engine.tracks[3];
    t->rng_low=nha_job.rng.low;t->rng_high=nha_job.rng.high;
    pk_cf_native_convert(&placement_clocks[3],nha_job.data,nha_job.end-nha_job.start,placement_output[3]+nha_job.start);
    placement_native_samples[3]+=nha_job.need;
    nha_job.stage++;nha_next();
}
static void nha_next(void)
{
    if(nha_job.stage==1){
        if(!placement_prepare(3,placement_inputs[3],placement_inputs[3][9]!=0))placement_status=0;
    }
    if(nha_job.stage>=2){pk_nhaa_frame_done=1;return;}
    nha_job.start=nha_job.stage? nha_job.split:0;
    nha_job.end=nha_job.stage?16:nha_job.split;
    if(nha_job.start==nha_job.end){nha_job.stage++;nha_next();return;}
    pk4_track*t=&placement_engine.tracks[3];
    if(t->active_algo!=PK4_ALGO_NOISE_HAT){
        if(!placement_segment(3,nha_job.start,nha_job.end,nha_job.stage))placement_status=0;
        nha_job.stage++;nha_next();return;
    }
    pk_cf_native_clock*c=&placement_clocks[3];nha_job.have=c->have;
    nha_job.need=pk_cf_native_needed(c,nha_job.end-nha_job.start);
    if(nha_job.have)nha_job.data[0]=(int16_t)c->carry;
    nha_job.rng.low=t->rng_low;nha_job.rng.high=t->rng_high;
    nha_job.tables.envelope1=placement_assets.envelope1;nha_job.tables.envelope2=placement_assets.envelope2;
    unsigned mode=nh_mode(t->active_mode);
    pk_nhaa_begin(t->nh+(mode==2?NH_PULSE:0),nha_job.data+nha_job.have,nha_job.need,mode,&nha_job.tables,&nha_job.rng,placement_engine.nh_hold);
}
void pk_nhaa_frame_start(unsigned split)
{
    pk_nhaa_frame_done=0;nha_job.stage=0;nha_job.split=split;nha_next();pk_nhaa_poll();
}
