#ifndef OCTABAM_PERKY_CF_RESONANT_H
#define OCTABAM_PERKY_CF_RESONANT_H
#include <stddef.h>
#include <stdint.h>
#define PK_CF_RES_BASS_STATE_BYTES  0x178u
#define PK_CF_RES_SNARE_STATE_BYTES 0x1d4u
#define PK_CF_RES_ENV_BYTES   (2048u*2u)   /* one envelope curve  */
#define PK_CF_RES_INTERP_BYTES (257u*2u)   /* 257 u16 entries     */

typedef struct {
    const uint8_t *envelope1;   /* 2048 little-endian u16 */
    const uint8_t *envelope2;   /* 2048 little-endian u16 */
    const uint8_t *interp_a;    /* 257 little-endian u16  */
    const uint8_t *interp_b;    /* 257 little-endian u16  */
} pk_cf_res_tables;

typedef struct { uint32_t low,high; } pk_cf_res_rng;

int pk_cf_res_bass_render(uint8_t *state,int16_t *dst,uint32_t n,
                          const pk_cf_res_tables *t,pk_cf_res_rng *rng);
int pk_cf_res_snare_render(uint8_t *state,int16_t *dst,uint32_t n,
                           const pk_cf_res_tables *t,pk_cf_res_rng *rng);
#endif
