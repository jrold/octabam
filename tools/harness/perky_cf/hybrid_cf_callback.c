/* Include the shipping control translation unit so this probe calls the actual
 * private readiness guard and loaded cookie. Unrelated callbacks are discarded
 * by section GC; this does not build an OS image or replace production code. */
#include "control_cf_final.c"

uint8_t pk_pcm_wt_base[4096] __attribute__((aligned(4)));
uint8_t pk_pcm_wt_bank[196608] __attribute__((aligned(4)));

int bench_callback_pcm(void)
{
    return pk_final_ensure_pcm();
}
