#ifndef OCTABAM_PERKY_CF_FOLD_H
#define OCTABAM_PERKY_CF_FOLD_H
#include <stddef.h>
#include <stdint.h>
#define PK_CF_FOLD1_STATE_BYTES 0xf4u
#define PK_CF_FOLD2_STATE_BYTES 0x134u
#define PK_CF_FOLD_PITCH_BYTES (4096u*2u)
#define PK_CF_FOLD_ENV_BYTES (2048u*2u)
#define PK_CF_FOLD_WAVE_BYTES (256u*2u)
#define PK_CF_FOLD_SIMPLE_OSC_RENDER 0x0802819du
typedef struct { uint32_t address; const uint8_t *table; } pk_cf_fold_wave_view;
typedef struct { const uint8_t *pitch,*envelope1,*envelope2; pk_cf_fold_wave_view waves[4]; } pk_cf_fold_tables;
typedef struct { uint32_t low,high; } pk_cf_fold_rng;
int pk_cf_fold1_render(uint8_t *state,int16_t *dst,uint32_t n,const pk_cf_fold_tables *t,pk_cf_fold_rng *rng);
int pk_cf_fold2_render(uint8_t *state,uint32_t object_address,int16_t *dst,uint32_t n,const pk_cf_fold_tables *t,pk_cf_fold_rng *rng);
#endif
