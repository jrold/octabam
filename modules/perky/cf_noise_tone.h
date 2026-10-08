#ifndef OCTABAM_PERKY_CF_NOISE_TONE_H
#define OCTABAM_PERKY_CF_NOISE_TONE_H
#include <stddef.h>
#include <stdint.h>
#define PK_CF_NT_STATE_BYTES 0x120u
#define PK_CF_NT_SHARED_WAVE_BYTES 512u
#define PK_CF_NT_M1_WAVE_BYTES 4096u
#define PK_CF_NT_ENV_BYTES 4096u
typedef struct { uint32_t address; const uint8_t *table; } pk_cf_nt_wave_view;
typedef struct { const uint8_t *envelope1; const uint8_t *envelope2; pk_cf_nt_wave_view waves[4]; } pk_cf_nt_shared_tables;
typedef struct { uint32_t low; uint32_t high; } pk_cf_nt_rng;
int pk_cf_nt_m1_render(uint8_t *state,int16_t *destination,uint32_t sample_count,const uint8_t *wave_a,uint32_t wave_a_address,const uint8_t *wave_b,uint32_t wave_b_address);
int pk_cf_nt_shared_render(uint8_t *state,int16_t *destination,uint32_t sample_count,const pk_cf_nt_shared_tables *tables,pk_cf_nt_rng *rng);
#endif
