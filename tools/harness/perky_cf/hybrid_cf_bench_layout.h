#ifndef OCTABAM_HYBRID_CF_BENCH_LAYOUT_H
#define OCTABAM_HYBRID_CF_BENCH_LAYOUT_H
#include <stddef.h>
#include "hybrid_cf_shadow.h"

/* Metadata only: retain with --undefined=bench_layout. Reading it on the host
 * executes no target instructions and does not perturb predictor state. */
const uint32_t bench_layout[HYB_LAYOUT_WORDS] = {
    0x48594231u, sizeof(bench_voice), offsetof(bench_voice, wt),
    offsetof(bench_voice, snare), offsetof(bench_voice, bass),
    offsetof(bench_voice, nt), offsetof(bench_voice, control),
    sizeof(((bench_voice *)0)->control) / sizeof(pk4_control),
    sizeof(pk4_control), offsetof(pk4_control, targets),
    offsetof(pk4_control, last_raw), offsetof(pk4_control, last_mode),
    offsetof(pk4_control, valid), offsetof(bench_voice, rng_low),
    offsetof(bench_voice, rng_high), sizeof(((bench_voice *)0)->wt[0]),
    sizeof(((bench_voice *)0)->snare), sizeof(((bench_voice *)0)->bass),
    sizeof(((bench_voice *)0)->nt)
};
#endif
