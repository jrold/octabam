/* Diagnostic entry only. Production uses the same guarded control helper. */
#ifndef PK_HYBRID_NATIVE_HW_DIV
#define PK_HYBRID_NATIVE_HW_DIV 1
#endif
#ifndef PK_HYBRID_NATIVE_FAST_SMOOTH
#define PK_HYBRID_NATIVE_FAST_SMOOTH 1
#endif
#ifndef PK_HYBRID_NATIVE_SKIP_DERIVE
#define PK_HYBRID_NATIVE_SKIP_DERIVE 1
#endif
#ifndef PK_HYBRID_NATIVE_SHARED_RATE
#define PK_HYBRID_NATIVE_SHARED_RATE 1
#endif
#include "control_four_candidate.c"
uint32_t native_math_checks,native_math_failures;
static unsigned original_native_div(unsigned n,unsigned d){
    unsigned q=0,r=0;
    for(unsigned i=20;i!=0;--i){r=(r<<1)|((n>>(i-1))&1u);q<<=1;if(r>=d){r-=d;q|=1;}}
    return q;
}
unsigned bench_native_div(unsigned n,unsigned d){return simple_div(n,d);}
unsigned bench_original_native_div(unsigned n,unsigned d){return original_native_div(n,d);}
int bench_native_math_probe(void){
    uint32_t i,j,seed=0x17235a9du;
    const uint32_t nums[]={0u,1u,0xfffffu,0xffffffffu};
    native_math_checks=native_math_failures=0;
#if PK_HYBRID_NATIVE_SHARED_RATE
    for(i=0;i<4096u;i++){
        if(pk_hybrid_native_fold_rate(i)!=simple_rate(simple_time(i),50u,7280u))++native_math_failures;
        ++native_math_checks;
    }
#endif
    for(j=0;j<4;j++)for(i=0;i<65536u;i++){
        if(simple_div(nums[j],i)!=original_native_div(nums[j],i))++native_math_failures;
        ++native_math_checks;
    }
    for(i=0;i<65536u;i++){
        uint32_t n,d;
        seed=1664525u*seed+1013904223u;n=seed;
        seed=1664525u*seed+1013904223u;d=(i&1u)?seed:0x100000u+(seed&0xfffffu);
        if(simple_div(n,d)!=original_native_div(n,d))++native_math_failures;
        ++native_math_checks;
    }
    return native_math_failures==0;
}

PKSimpleControl native_control;
uint8_t native_packet[12];
unsigned bench_native_control_size(void){return sizeof(native_control);}
void bench_native_prepare(unsigned family,unsigned tune,unsigned decay,
                          unsigned p1,unsigned p2,unsigned mode,unsigned trig){
    unsigned i;for(i=0;i<12;i++)native_packet[i]=0xa5;
    native_packet[0]=(uint8_t)tune;native_packet[1]=(uint8_t)decay;
    native_packet[2]=(uint8_t)p1;native_packet[3]=(uint8_t)p2;
    native_packet[6]=(uint8_t)mode;native_packet[11]=(uint8_t)family;
    if(family==0)pk_fold_prepare(&native_control,native_packet,trig);
    else if(family==3)pk_light2_fold2_prepare(&native_control,native_packet,trig);
    else if(family==5)pk_complex_prepare(&native_control,native_packet,trig);
    else pk_simple_prepare(&native_control,native_packet,trig);
}
