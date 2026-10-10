#ifndef OCTABAM_PERKY_CF_PERKY4_H
#define OCTABAM_PERKY_CF_PERKY4_H
#include <stdint.h>
#include "cf_fold.h"
#include "cf_karplus.h"
#include "cf_noise_tone.h"
#include "cf_resonant.h"
#include "cf_noise_hat.h"
#include "cf_simple_drum.h"
#include "cf_complex_drum.h"
#include "cf_slap.h"
#include "cf_wavetable.h"
#include "cf_acoustic_hats.h"
#ifdef __cplusplus
extern "C" {
#endif

enum {
    PK4_ALGO_FOLD1 = 0,
    PK4_ALGO_FOLD2 = 1,
    PK4_ALGO_KARPLUS = 2,
    PK4_ALGO_NOISE_TONE = 3,
    PK4_ALGO_RESONANT = 4,
    PK4_ALGO_NOISE_HAT = 5,
    PK4_ALGO_SIMPLE_DRUM = 6,
    PK4_ALGO_COMPLEX_DRUM = 7,
    PK4_ALGO_SLAP = 8,
    PK4_ALGO_WAVETABLE = 9,
    PK4_ALGO_ACOUSTIC_HATS = 10,
    PK4_ALGO_COUNT = 11,
    PK4_TRACK_COUNT = 4
};

/* ---- PĒRKONS voice map: the hardware algorithm silo ---------------------
 * The drum has four voices and each voice owns three algorithms.  The port
 * keeps that shape: Octatrack T1..T4 are V1..V4, and a track's ALGO control
 * ranges over its own family only.  The staged ALGO byte is a FAMILY-LOCAL
 * index (0..len-1); the shipping control adapter maps it through this table,
 * so the ALGO knob, the p-lock staging and the engine core all agree, and no
 * patch can put an algorithm on a voice the hardware would not offer it on.
 *
 * Only the algorithms this port implements are listed, compacted into a
 * contiguous knob range; PK4_VOICE_LEN is what the SRC page publishes as the
 * ALGO maximum.  The entries past the length are unreachable padding that
 * keeps the table rectangular -- never read them.
 *
 * Adding an engine means putting it in its family slot and bumping the
 * length.  That SHIFTS the local indices after it, so a project saved with an
 * older image can change which algorithm a slot selects; the SRC page clamp
 * keeps the value in range, and the release note has to say so.
 */
#define PK4_VOICE_COUNT 4
static const uint8_t pk4_family_engines[PK4_VOICE_COUNT][3] = {
    { PK4_ALGO_FOLD1,     PK4_ALGO_WAVETABLE,  PK4_ALGO_SIMPLE_DRUM }, /* V1 */
    { PK4_ALGO_FOLD2,     PK4_ALGO_WAVETABLE,  PK4_ALGO_COMPLEX_DRUM }, /* V2 */
    { PK4_ALGO_RESONANT,  PK4_ALGO_SLAP,       PK4_ALGO_KARPLUS },     /* V3 */
    { PK4_ALGO_NOISE_HAT, PK4_ALGO_NOISE_TONE, PK4_ALGO_ACOUSTIC_HATS }, /* V4 */
};
static const uint8_t pk4_family_len[PK4_VOICE_COUNT] = { 3u, 3u, 3u, 3u };

static inline unsigned pk4_voice_len(unsigned voice)
{
    return voice < PK4_VOICE_COUNT ? (unsigned)pk4_family_len[voice] : 1u;
}

static inline uint8_t pk4_voice_engine(unsigned voice, unsigned local)
{
    const unsigned len = pk4_voice_len(voice);
    if (local >= len)
        local = len - 1u;
    return pk4_family_engines[voice < PK4_VOICE_COUNT ? voice : 0u][local];
}

typedef struct {
    const uint8_t *pitch;      /* 4096 little-endian u16 */
    const uint8_t *chromatic;  /* 12 little-endian u16 */
    const uint8_t *envelope1;  /* 2048 little-endian u16 */
    const uint8_t *envelope2;  /* 2048 little-endian u16 */
    pk_cf_fold_wave_view waves[4];
    const uint8_t *m1_wave;    /* 2048 little-endian s16 */
    uint32_t m1_wave_address;
    const uint8_t *res_interp_a; /* 257 little-endian u16 */
    const uint8_t *res_interp_b; /* 257 little-endian u16 */
    const uint8_t *wt_base;    /* 4096-byte Wavetable primary table */
    const uint8_t *wt_bank;    /* 48 contiguous 4096-byte crossfade tables */
    const uint8_t *ah_closed;  /* Acoustic Hats' three samples */
    const uint8_t *ah_open;
    const uint8_t *ah_ride;
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
    /* Resonant Drums: the firmware keeps a separate object per panel mode.
     * The family object is 0x1d4 even for the bass prefix (its update writes
     * 0x17C), so both use the snare-sized bytes. */
    uint8_t res_snare[PK_CF_RES_SNARE_STATE_BYTES];
    uint8_t res_bass[PK_CF_RES_SNARE_STATE_BYTES];
    uint8_t res_nt[PK_CF_NT_STATE_BYTES];
    /* Noise Hat: one Voice-4 wrapper object holds both classic limbs, the
     * post-engine delay and the overlapping pulse-stack limb. MODE 0 selects
     * metallic, 1 white, 2 the pulse stack. */
    uint8_t nh[PK_CF_NH_WRAPPER_BYTES];
    /* Simple Drum: one 0x120-byte ARM object, one oscillator. */
    uint8_t sd[PK_CF_SD_STATE_BYTES];
    uint8_t cd[PK_CF_CD_STATE_BYTES];
    uint8_t slap[PK_CF_SLAP_STATE_BYTES];
    uint8_t wt[PK_CF_WT_STATE_BYTES];
    uint8_t ah[PK_CF_AH_STATE_BYTES];
    pk4_control fold1_ctl, fold2_ctl, karplus_ctl, nt_m1_ctl, nt_shared_ctl;
    pk4_control res_snare_ctl, res_bass_ctl, res_nt_ctl;
    pk4_control nh_ctl;
    pk4_control sd_ctl, cd_ctl, slap_ctl;
    pk4_control wt_ctl;
    pk4_control ah_ctl;
    uint32_t rng_low, rng_high;
    /* One bit per engine kind, and there are now ten of them: Slap (8) and
     * Wavetable (9) do not fit an 8-bit mask.  With a uint8_t the bit for
     * algo>=8 became zero, so every event re-initialised the object and the
     * committed control state was thrown away -- the first block after a trig
     * sounded and the rest of the bar was silent. */
    uint16_t initialized_mask;
    uint8_t active_algo;
    uint8_t active_mode;
} pk4_track;

typedef struct {
    pk4_track tracks[PK4_TRACK_COUNT];
    const pk4_assets *assets;
    /* The firmware owns ONE 16-bit noise sample/hold for the held-hat limb,
     * shared by every voice -- not a per-track field. */
    uint16_t nh_hold[2];
    /* Acoustic Hats' firmware-global held sample, at 0x20007598 on the unit:
     * one value shared by every voice. */
    int32_t ah_hold;
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
