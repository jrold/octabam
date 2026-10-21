#include "cf_perky4.c"
/* Stateless reference: input is the complete pre-call target shadow. No cached
 * control, parameter or envelope invariants are assumed. */
void nhf_reference(uint8_t*s,uint32_t*targets,uint8_t*tail,const uint8_t*raw,
    unsigned mode,unsigned vel,unsigned note,int trig,const uint8_t*pitch,const uint8_t*chromatic)
{
    pk4_control ctl;pk4_assets a={0};unsigned i;
    for(i=0;i<4;i++){ctl.targets[i]=targets[i];ctl.last_raw[i]=tail[i];}
    ctl.last_mode=tail[4];ctl.valid=tail[5];a.pitch=pitch;a.chromatic=chromatic;
    prepare_nh(&ctl,s,raw,mode,vel,note,trig,&a);
    for(i=0;i<4;i++){targets[i]=ctl.targets[i];tail[i]=ctl.last_raw[i];}
    tail[4]=ctl.last_mode;tail[5]=ctl.valid;
}
