#ifndef PERKY_NOISE_HAT_TAPS_RING_H
#define PERKY_NOISE_HAT_TAPS_RING_H
#include <stdint.h>
/* A tap reads index-delay, while feedback writes index+1. Requiring fewer
 * than 573 uncommitted writes is conservative by one sample and fails before
 * the shortest fixed tap can depend on a pending write. */
static inline int pk_nht_taps_ready(uint32_t pending){return pending<573u;}
#endif
