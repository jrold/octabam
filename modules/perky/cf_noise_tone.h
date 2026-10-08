#ifndef OCTABAM_PERKY_CF_NOISE_TONE_H
#define OCTABAM_PERKY_CF_NOISE_TONE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PK_CF_NT_STATE_BYTES 0x120u
#define PK_CF_NT_SHARED_WAVE_BYTES (256u * 2u)
#define PK_CF_NT_M1_WAVE_BYTES (2048u * 2u)
#define PK_CF_NT_ENV_BYTES (2048u * 2u)

typedef struct {
    uint32_t address;
    const uint8_t *table;
} pk_cf_nt_wave_view;

typedef struct {
    const uint8_t *envelope1;
    const uint8_t *envelope2;
    pk_cf_nt_wave_view waves[4];
} pk_cf_nt_shared_tables;

typedef struct {
    uint32_t low;
    uint32_t high;
} pk_cf_nt_rng;

/*
 * Authentic PĒKÔNS v1.2.1 Voice 4 A2 renderer paths, ported from the
 * bit-exact PerkyBits native oracle. State remains the original 0x120-byte
 * ARM object because the ColdFire DRAM runtime has no reason to compress it.
 * Tables are raw little-endian firmware bytes held in DRAM .
 *
 * These routines perform rendering only. The original Voice 4 update/trigger
 * laws remain a separate control-state preparation layer.
 */
int pk_cf_nt_m1_render(uint8_t state[PK_CF_NT_STATE_BYTES],
                       int16_t *destination,
                       uint32_t sample_count,
                       const uint8_t *wave_a,
                       uint32_t wave_a_address,
                       const uint8_t *wave_b,
                       uint32_t wave_b_address);

int pk_cf_nt_shared_render(uint8_t state[PK_CF_NT_STATE_BYTES],
                           int16_t *destination,
                           uint32_t sample_count,
                           const pk_cf_nt_shared_tables *tables,
                           pk_cf_nt_rng *rng);

#ifdef __cplusplus
}
#endif

#endif
