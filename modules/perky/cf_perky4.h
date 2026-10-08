#ifndef OCTABAM_PERKY_CF_PERKY4_H
#define OCTABAM_PERKY_CF_PERKY4_H
#include <stdint.h>
#include "cf_fold.h"
#include "cf_karplus.h"
#include "cf_noise_tone.h"
#ifdef __cplusplus
extern "C" {
#endif

enum {
    PK4_ALGO_FOLD1 = 0,
    PK4_ALGO_FOLD2 = 1,
    PK4_ALGO_KARPLUS = 2,
    PK4_ALGO_NOISE_TONE = 3,
    PK4_ALGO_COUNT = 4,
    PK4_TRACK_COUNT = 4
};

typedef struct {
    const uint8_t *pitch;
    const uint8_t *chromatic;
    const uint8_t *envelope1;
    const uint8_t *envelope2;
    pk_cf_fold_wave_view waves[4];
    const uint8_t *m1_wave;
    uint32_t m1_wave_address;
} pk4_assets;

typedef struct {
    uint32_t targets[4];
    uint8_t last_raw[4];
    uint8_t last_mode;
    uint8_t valid;
} pk4_control;

typedef struct {
    uint8_t fold1[PK_CF_FOLD1_STATE_BYTES];
    uint8_t fold2[PK_CF_FOLD2_STATE_BYTES];
    uint8_t karplus[PK_CF_KARPLUS_STATE_BYTES];
    uint8_t nt_m1[PK_CF_NT_STATE_BYTES];
    uint8_t nt_shared[PK_CF_NT_STATE_BYTES];
    pk4_control fold1_ctl, fold2_ctl, karplus_ctl, nt_m1_ctl, nt_shared_ctl;
    uint32_t rng_low, rng_high;
    uint8_t initialized_mask;
    uint8_t active_algo;
    uint8_t active_mode;
} pk4_track;

typedef struct {
    pk4_track tracks[PK4_TRACK_COUNT];
    const pk4_assets *assets;
} pk4_engine;

void pk4_init(pk4_engine *engine, const pk4_assets *assets);
int pk4_prepare_event(pk4_engine *engine, unsigned track,
                      uint8_t decay, uint8_t tune,
                      uint8_t param1, uint8_t param2,
                      uint8_t mode, uint8_t algo,
                      uint8_t velocity, uint8_t note, int trig);
int pk4_render(pk4_engine *engine, unsigned track,
               int16_t *destination, uint32_t sample_count);
int pk4_process_segment(pk4_engine *engine, unsigned track,
                        const uint8_t src[6], int event_boundary, int trig,
                        uint8_t velocity, uint8_t note,
                        int16_t *destination, uint32_t sample_count);
uint32_t pk4_encode_stock_segment(uint32_t *destination,
                                  const int16_t *mono,
                                  uint32_t sample_count);
#ifdef __cplusplus
}
#endif
#endif
