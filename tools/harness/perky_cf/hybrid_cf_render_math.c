/* Diagnostic only: the original software high product is an independent
 * target-code oracle. Preserve every raw EMAC register across render math. */
#include "cf_render_math.h"

uint32_t render_math_checks,render_math_failures;
static void capture(uint32_t *p){
    uint32_t status,a,b,c,d,lo,hi;
    __asm__ volatile("move.l %%macsr,%0\n\tmove.l #0,%%macsr\n\t"
        "move.l %%acc0,%1\n\tmove.l %%acc1,%2\n\tmove.l %%acc2,%3\n\tmove.l %%acc3,%4\n\t"
        "move.l %%accext01,%5\n\tmove.l %%accext23,%6\n\tmove.l %0,%%macsr"
        : "=&d"(status),"=&d"(a),"=&d"(b),"=&d"(c),"=&d"(d),"=&d"(lo),"=&d"(hi)
        :: "cc","memory");
    p[0]=status;p[1]=a;p[2]=b;p[3]=c;p[4]=d;p[5]=lo;p[6]=hi;
}
int bench_math_probe(void){
    static const uint32_t modes[]={0,0x20,0x40,0x60,0xb0,0xf0};
    static const uint32_t edges[]={0,1,2,0xffff,0x10000,0x7fffffff,0x80000000,0x80000001,0xfffffffe,0xffffffff};
    uint32_t m,i,a,before[7],after[7];
    render_math_checks=render_math_failures=0;
    for(m=0;m<6;m++){
        __asm__ volatile("move.l #0,%%macsr\n\t"
            "move.l #0x12345678,%%acc0\n\tmove.l #0xfedcba98,%%acc1\n\t"
            "move.l #0x89abcdef,%%acc2\n\tmove.l #0x76543210,%%acc3\n\t"
            "move.l #0xdeadbeef,%%accext01\n\tmove.l #0xabcdef01,%%accext23\n\t"
            "move.l %0,%%macsr" :: "d"(modes[m]) : "cc","memory");
        capture(before);
        pk_cf_render_math_context context=pk_cf_render_math_begin();
        for(i=0;i<4096;i++){
            int32_t value=(int32_t)(i<<20);
            if(pk_cf_render_frequency_hi(value)!=pk_cf_mul_hi_s32(value,0x057619f1))++render_math_failures;
            ++render_math_checks;
        }
        a=1;
        for(i=0;i<32768;i++){
            a=i<10?edges[i]:a*1664525u+1013904223u;
            if(pk_cf_render_rng_hi(a)!=pk_cf_mul_hi_u32(a,0x4c957f2du))++render_math_failures;
            ++render_math_checks;
        }
        pk_cf_render_math_end(context);
        capture(after);
        for(i=0;i<7;i++)if(before[i]!=after[i])++render_math_failures;
    }
    return render_math_failures==0;
}
