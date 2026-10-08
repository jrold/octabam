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
    const uint8_t *pitch;      /* 4096 little-endian u16 */
    const uint8_t *chromatic;  /* 12 little-endian u16 */
    const uint8_t *envelope1;  /* 2048 little-endian u16 */
    const uint8_t *envelope2;  /* 2048 little-endian u16 */
    pk_cf_fold_wave_view waves[4];
    const uint8_t *m1_wave;    /* 2048 little-endian s16 */
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

/* Recovered synthesis-core ABI order is deliberately independent of the
 * Octatrack page layout:
 *   decay, tune, param1, param2, mode, algo.
 * The shipping control adapter remaps SRC A-F
 *   TUNE, DECAY, ALGO, PRM1, PRM2, MODE
 * into this ABI at the event boundary. prepare_event applies any changed
 * controls/mode/algorithm and, when trig != 0, performs the authentic trigger
 * plus mandatory v1.2.1 update-after-trigger.
 */
int pk4_prepare_event(pk4_engine *engine, unsigned track,
                      uint8_t decay, uint8_t tune,
                      uint8_t param1, uint8_t param2,
                      uint8_t mode, uint8_t algo,
                      uint8_t velocity, uint8_t note, int trig);

int pk4_render(pk4_engine *engine, unsigned track,
               int16_t *destination, uint32_t sample_count);

/* Process one stock source-render segment. When event_boundary is false, the
 * currently active algorithm renders unchanged and src may be NULL. When it
 * is true, src is in the recovered synthesis-core ABI order above; the
 * shipping control adapter is responsible for remapping Octatrack SRC A-F.
 */
int pk4_process_segment(pk4_engine *engine, unsigned track,
                        const uint8_t src[6], int event_boundary, int trig,
                        uint8_t velocity, uint8_t note,
                        int16_t *destination, uint32_t sample_count);

/* Encode one stock Octatrack unity-rate source segment. Mono is duplicated L/R.
 * ColdFire long -> DSP transport uses each long's high 24 bits.
 * Returns 4 + 2*sample_count longs, or 0 on invalid input/count.
 */
uint32_t pk4_encode_stock_segment(uint32_t *destination,
                                  const int16_t *mono,
                                  uint32_t sample_count);

#ifdef __cplusplus
}
#endif
#endif
