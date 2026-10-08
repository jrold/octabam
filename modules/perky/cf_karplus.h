#ifndef OCTABAM_PERKY_CF_KARPLUS_H
#define OCTABAM_PERKY_CF_KARPLUS_H
#include <stdint.h>
#define PK_CF_KARPLUS_STATE_BYTES 0x10e0u
#define PK_CF_KARPLUS_ENV_BYTES 4096u
typedef struct { const uint8_t *envelope1; const uint8_t *envelope2; } pk_cf_karplus_tables;
typedef struct { uint32_t low; uint32_t high; } pk_cf_karplus_rng;
int pk_cf_karplus_render(uint8_t *state, int16_t *destination, uint32_t sample_count,
                         const pk_cf_karplus_tables *tables, pk_cf_karplus_rng *rng);
#endif
