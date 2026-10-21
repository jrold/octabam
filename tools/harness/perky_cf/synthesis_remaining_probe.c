/* Standalone linked-CF malformed-state/length/ABI gate. No shipped data. */
#include "cf_resonant.h"
#include "cf_slap.h"

uint8_t remaining_state[PK_CF_SLAP_STATE_BYTES];
int16_t remaining_output[66];
pk_cf_res_tables remaining_res_tables;
pk_cf_fold_tables remaining_slap_tables;
pk_cf_res_rng remaining_rng;
uint32_t remaining_n,remaining_kind,remaining_status,remaining_mac_mode;
uint32_t remaining_mac_before[7],remaining_mac_after[7];

static void capture(uint32_t *out){
    uint32_t status;
    __asm__ volatile("move.l %%macsr,%0\n\tmove.l #0,%%macsr":"=d"(status)::"cc","memory");
    out[0]=status;
    __asm__ volatile("move.l %%acc0,%0":"=d"(out[1]));
    __asm__ volatile("move.l %%acc1,%0":"=d"(out[2]));
    __asm__ volatile("move.l %%acc2,%0":"=d"(out[3]));
    __asm__ volatile("move.l %%acc3,%0":"=d"(out[4]));
    __asm__ volatile("move.l %%accext01,%0":"=d"(out[5]));
    __asm__ volatile("move.l %%accext23,%0":"=d"(out[6]));
    __asm__ volatile("move.l %0,%%macsr"::"d"(status):"cc","memory");
}

void remaining_direct(void){
    __asm__ volatile("move.l #0,%%macsr\n\t"
        "move.l #0x12345678,%%acc0\n\tmove.l #0xfedcba98,%%acc1\n\t"
        "move.l #0x89abcdef,%%acc2\n\tmove.l #0x76543210,%%acc3\n\t"
        "move.l #0xdeadbeef,%%accext01\n\tmove.l #0xabcdef01,%%accext23\n\t"
        "move.l %0,%%macsr"::"d"(remaining_mac_mode):"cc","memory");
    capture(remaining_mac_before);
    if(remaining_kind==0)
        remaining_status=pk_cf_res_snare_render(remaining_state,remaining_output,
            remaining_n,&remaining_res_tables,&remaining_rng);
    else if(remaining_kind==1)
        remaining_status=pk_cf_res_bass_render(remaining_state,remaining_output,
            remaining_n,&remaining_res_tables,&remaining_rng);
    else
        remaining_status=pk_cf_slap_render(remaining_state,remaining_output,
            remaining_n,&remaining_slap_tables,(pk_cf_fold_rng*)&remaining_rng);
    capture(remaining_mac_after);
}
