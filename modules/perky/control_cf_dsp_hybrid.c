/* PERKY DSP+ColdFire Hybrid Profiling Probe Control Runtime.
 *
 * Nonnegotiable track & engine contract:
 *   - T1 (zero-based firmware track 0, DSP core B) and
 *     T5 (zero-based firmware track 4, DSP core A):
 *     native DSP Fold1/Fold2/Simple/Complex and original ALGO indices (0..3).
 *   - T2 (zero-based firmware track 1, CF instance 0) and
 *     T6 (zero-based firmware track 5, CF instance 1):
 *     ColdFire ALGO 0 Wavetable V1, ALGO 1 Wavetable V2, ALGO 2 Resonant with
 *     authentic snare (MODE 0) / bass (MODE 1) / original Noise-Tone third
 *     mode (MODE 2).
 *   - T3/T4/T7/T8 (zero-based firmware tracks 2,3,6,7): untouched stock sampler.
 *
 * One exported source dispatcher (`pk_render`), one machine-hook set, one
 * registration/admission owner, and one bounded hardware-readable DTIM3 profiler.
 *
 * Reuse the exact original DSP-native control producer (`control_four_candidate.c` /
 * `control_three_candidate.c`) by including `control_four_candidate.c` once and
 * binding its active entry points via GCC `__asm__` symbol labels before the
 * preprocessor `#undef`s in `control_three_candidate.c` take effect. This
 * prevents duplicate `control.c` copies and avoids conflicting macro remaps.
 */

#include <stdint.h>

extern unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
    __asm__("pk_dsp_admit_track_orig");
extern uint32_t pk_track_page(const volatile uint8_t *type_ptr)
    __asm__("pk_dsp_track_page_orig");
extern void pk_ui_tick(void)
    __asm__("pk_dsp_ui_tick_orig");
extern int pk_render(unsigned track, unsigned ping, unsigned start, unsigned end)
    __asm__("pk_dsp_render_orig") __attribute__((noinline));
extern uint32_t pk_machine_glyph(unsigned track, uint32_t original)
    __asm__("pk_dsp_machine_glyph_orig");
extern unsigned pk_ui_playing(unsigned track, unsigned original)
    __asm__("pk_dsp_ui_playing_orig");

#include "control_four_candidate.c"

/* Include cf_perky4.c with narrow static linkage so its internal wt_init,
 * res_init_snare, res_init_bass, res_init_nt, prepare_wt, prepare_res_family
 * and pk4_encode_stock_segment helpers are reused directly. Their optimized
 * behavior is checked against the frozen pre-optimization reference; unused
 * CF engines are discarded from the linked object.
 */
#include "cf_perky4.h"
static void __attribute__((unused)) pk4_unused_init_orig(pk4_engine *e, const pk4_assets *a);
static void __attribute__((unused)) pk4_unused_preinit_voice_orig(pk4_engine *e, unsigned tr, uint8_t vel, uint8_t note);
static int __attribute__((unused)) pk4_unused_prepare_event_orig(pk4_engine *e, unsigned tr, uint8_t decay, uint8_t tune, uint8_t p1, uint8_t p2, uint8_t mode, uint8_t algo, uint8_t vel, uint8_t note, int trig);
static int __attribute__((unused)) pk4_unused_render_orig(pk4_engine *e, unsigned tr, int16_t *d, uint32_t n);
static int __attribute__((unused)) pk4_unused_process_segment_orig(pk4_engine *e, unsigned tr, const uint8_t src[6], int event_boundary, int trig, uint8_t vel, uint8_t note, int16_t *d, uint32_t n);
#define pk4_init pk4_unused_init_orig
#define pk4_preinit_voice pk4_unused_preinit_voice_orig
#define pk4_prepare_event pk4_unused_prepare_event_orig
#define pk4_render pk4_unused_render_orig
#define pk4_process_segment pk4_unused_process_segment_orig
#include "cf_perky4.c"
#undef pk4_process_segment
#undef pk4_render
#undef pk4_prepare_event
#undef pk4_preinit_voice
#undef pk4_init

#include "cf_pcm_rice.h"

#define PK_HYB_CF_INSTANCE_COUNT 2u
#define PK_HYB_CF_ALGO_COUNT 3u
#define PK_HYB_DSP_ALGO_COUNT 4u
#define PK_HYB_NOTE 45u
#define PK_HYB_VELOCITY 255u
#define PK_HYB_BLOCK_SAMPLES 16u
#define PK_HYB_SLOT_BYTES 336u
#define PK_HYB_PING_BYTES 0xa80u
#define PK_HYB_SLOT_BASE 0x80001c90u

/* Hardware free-running 132 MHz DMA timer 3 (initialized at boot by 0x400209c0). */
#define PK_HYB_DTCN3 (*(volatile const uint32_t *)(uintptr_t)0xfc07c00cu)
#define PK_HYB_DTMR3 (*(volatile const uint16_t *)(uintptr_t)0xfc07c000u)
#define PK_HYB_DTRR3 (*(volatile const uint32_t *)(uintptr_t)0xfc07c004u)

/* Generated at build time from the SHA-pinned user-supplied PĒRKONS v1.2.1 image. */
extern const uint8_t pk_asset_pitch[];
extern const uint8_t pk_asset_chromatic[];
extern const uint8_t pk_asset_envelope1[];
extern const uint8_t pk_asset_envelope2[];
extern const uint8_t pk_asset_m1_wave[];
extern const uint8_t pk_asset_wave0[];
extern const uint8_t pk_asset_wave1[];
extern const uint8_t pk_asset_wave2[];
extern const uint8_t pk_asset_wave3[];
extern const uint8_t pk_asset_res_interp_a[];
extern const uint8_t pk_asset_res_interp_b[];
extern const uint8_t pk_asset_pcm_rice[];
extern const uint8_t pk_asset_pcm_rice_end[];

/* Decoded Wavetable PCM storage in BSS (4,096 B base + 196,608 B bank = 200,704 B). */
extern uint8_t pk_pcm_wt_base[];
extern uint8_t pk_pcm_wt_bank[];

static const pk4_assets pk_hybrid_assets = {
    .pitch = pk_asset_pitch,
    .chromatic = pk_asset_chromatic,
    .envelope1 = pk_asset_envelope1,
    .envelope2 = pk_asset_envelope2,
    .waves = {
        {0x080222a0u, pk_asset_wave0},
        {0x080224a0u, pk_asset_wave1},
        {0x080226a0u, pk_asset_wave2},
        {0x080228a0u, pk_asset_wave3},
    },
    .m1_wave = pk_asset_m1_wave,
    .m1_wave_address = 0x080310e0u,
    .res_interp_a = pk_asset_res_interp_a,
    .res_interp_b = pk_asset_res_interp_b,
    .wt_base = pk_pcm_wt_base,
    .wt_bank = pk_pcm_wt_bank,
};

/* Compact two-instance CF synthesis state for T2 (instance 0) and T6 (instance 1).
 * Only the required families are allocated and preinitialized:
 *   - ALGO 0: Wavetable V1 (`wt[0]`, `control[0]`)
 *   - ALGO 1: Wavetable V2 (`wt[1]`, `control[1]`)
 *   - ALGO 2: Resonant Drums (`snare`, `bass`, `nt`, `control[2]`)
 */
typedef struct {
    uint8_t wt[2][PK_CF_WT_STATE_BYTES];
    uint8_t snare[PK_CF_RES_SNARE_STATE_BYTES];
    uint8_t bass[PK_CF_RES_SNARE_STATE_BYTES];
    uint8_t nt[PK_CF_NT_STATE_BYTES];
    pk4_control control[3];
    uint32_t rng_low;
    uint32_t rng_high;
    uint8_t active_algo;
    uint8_t active_mode;
    uint8_t pad0;
    uint8_t pad1;
} pk_hybrid_cf_voice;

/* Hardware-readable fixed-size profiler structure in DRAM.
 * Exported via symbol `pk_hybrid_prof` and copied out-of-band in `pk_ui_tick`
 * to `pk_hybrid_prof_export`. Uses only 32-bit counters (low/high split for
 * cumulative sums) to guarantee zero 64-bit libgcc helpers.
 */
#define PK_HYB_PROF_MAGIC 0x504b4850u /* "PKHP" */
#define PK_HYB_PROF_RING_LEN 64u
#define PK_HYB_FRAME_TICKS_132MHZ 47891u /* floor(16 * 132 MHz / 44100) */
#define PK_HYB_GATE80_TICKS_132MHZ 38312u /* floor(0.8 * 16 * 132 MHz / 44100) */

typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t profiler_enabled;
    uint32_t cf_armed;
    uint32_t dtim3_hz;
    uint32_t read_overhead_ticks;
    uint32_t frame_count;
    uint32_t cf_active_frames;
    uint32_t dsp_active_frames;
    uint32_t cf_sample_count;
    uint32_t active_voice_mask;
    uint32_t active_cf_voices;
    uint32_t active_dsp_voices;
    uint32_t ui_tick_count;
    uint32_t handoff_generation;
    uint32_t handoff_pending_frames;
    uint32_t deadline_misses_100pct;
    uint32_t margin_exceeded_80pct;
    uint32_t max_full_frame_ticks;
    uint32_t max_cf_callback_ticks;
    uint32_t max_cf_control_ticks;
    uint32_t max_cf_render_ticks;
    uint32_t max_cf_pack_ticks;
    uint32_t max_dsp_callback_ticks;
    uint32_t sum_full_frame_lo;
    uint32_t sum_full_frame_hi;
    uint32_t sum_cf_callback_lo;
    uint32_t sum_cf_callback_hi;
    uint32_t sum_cf_control_lo;
    uint32_t sum_cf_control_hi;
    uint32_t sum_cf_render_lo;
    uint32_t sum_cf_render_hi;
    uint32_t sum_cf_pack_lo;
    uint32_t sum_cf_pack_hi;
    uint32_t sum_dsp_callback_lo;
    uint32_t sum_dsp_callback_hi;
    uint32_t inst_calls[PK_HYB_CF_INSTANCE_COUNT];
    uint32_t inst_trigs[PK_HYB_CF_INSTANCE_COUNT];
    uint32_t inst_max_ticks[PK_HYB_CF_INSTANCE_COUNT];
    uint32_t inst_max_control_ticks[PK_HYB_CF_INSTANCE_COUNT];
    uint32_t inst_max_render_ticks[PK_HYB_CF_INSTANCE_COUNT];
    uint32_t inst_max_pack_ticks[PK_HYB_CF_INSTANCE_COUNT];
    uint32_t ring_write_idx;
    uint32_t ring_full_ticks[PK_HYB_PROF_RING_LEN];
    uint32_t ring_cf_ticks[PK_HYB_PROF_RING_LEN];
    uint32_t ring_ctrl_ticks[PK_HYB_PROF_RING_LEN];
    uint32_t ring_rend_ticks[PK_HYB_PROF_RING_LEN];
    uint32_t ring_pack_ticks[PK_HYB_PROF_RING_LEN];
    uint32_t histogram[64]; /* full-frame span; 1024 timer ticks per bin */
    uint32_t period_min_ticks;
    uint32_t period_max_ticks;
    uint32_t reset_max_ticks;
    uint32_t reset_count;
    uint32_t readiness_faults;
    uint32_t snapshot_retries;
    uint32_t wait_loop_max_ticks[2];
    uint32_t wait_loop_sum_lo[2];
    uint32_t wait_loop_sum_hi[2];
} pk_hybrid_profiler;

/* Loaded .data cookies (the Octabam loader does not zero BSS). */
#define PK_HYB_PCM_COLD 0x504b5043u
#define PK_HYB_PCM_READY 0x504b5052u
#define PK_HYB_RT_COLD 0x504b4843u
#define PK_HYB_RT_READY 0x504b4852u
#define PK_HYB_PROF_COLD 0x504b5443u
#define PK_HYB_PROF_READY 0x504b5452u

uint32_t pk_hybrid_pcm_cookie = PK_HYB_PCM_COLD;
uint32_t pk_hybrid_rt_cookie = PK_HYB_RT_COLD;
uint32_t pk_hybrid_prof_cookie = PK_HYB_PROF_COLD;
uint32_t pk_hybrid_profiler_enable = 1u;
uint32_t pk_hybrid_cf_arm = 1u;

pk_hybrid_cf_voice pk_hybrid_voices[PK_HYB_CF_INSTANCE_COUNT];
/* Audio ISR owns active state and generation; UI never resets it. */
static pk_hybrid_cf_voice pk_hybrid_pristine;
static uint32_t pk_hybrid_voice_generation[PK_HYB_CF_INSTANCE_COUNT];
static uint32_t pk_hybrid_generation;
static uint32_t pk_hybrid_bank = 0xffffffffu;
static uint8_t pk_hybrid_part = 0xffu;
static uint8_t pk_hybrid_trigger_latch[PK_HYB_CF_INSTANCE_COUNT];
static int16_t pk_hybrid_frame_pcm[PK_HYB_CF_INSTANCE_COUNT][PK_HYB_BLOCK_SAMPLES];
static uint8_t pk_hybrid_frame_started[PK_HYB_CF_INSTANCE_COUNT];
static uint8_t pk_hybrid_frame_ping[PK_HYB_CF_INSTANCE_COUNT];
static uint8_t pk_hybrid_cf_ui_pending[PK_HYB_CF_INSTANCE_COUNT];
static uint32_t pk_hybrid_cf_ui_bank[PK_HYB_CF_INSTANCE_COUNT];
static uint8_t pk_hybrid_cf_ui_part[PK_HYB_CF_INSTANCE_COUNT];

/* Per-frame accumulators flushed once per 16-sample audio frame. */
static uint32_t pk_hybrid_cur_cf_ticks = 0u;
static uint32_t pk_hybrid_cur_ctrl_ticks = 0u;
static uint32_t pk_hybrid_cur_rend_ticks = 0u;
static uint32_t pk_hybrid_cur_pack_ticks = 0u;
static uint32_t pk_hybrid_cur_dsp_ticks = 0u;
static uint32_t pk_hybrid_cur_voice_mask = 0u;
static uint32_t pk_hybrid_cur_has_data = 0u;

pk_hybrid_profiler pk_hybrid_prof;
pk_hybrid_profiler pk_hybrid_prof_export;
static pk_hybrid_profiler pk_hybrid_snapshot;
volatile uint32_t pk_hybrid_prof_seq = 0u;
volatile uint32_t pk_hybrid_export_seq = 0u;
uint32_t pk_hybrid_isr_enter_ticks = 0u;
uint32_t pk_hybrid_wait_ticks[2] = {0u, 0u};
static uint32_t pk_hybrid_previous_enter;
static uint32_t pk_hybrid_previous_enter_valid;
static uint32_t pk_hybrid_timer_calibrated;
static uint32_t pk_hybrid_seen_running;
static unsigned pk_hybrid_export_index;
int32_t pk_hybrid_export_status = 0;
extern const char pk_hybrid_source_id[65];

static inline uint32_t pk_hybrid_timer_now(void)
{
    return PK_HYB_DTCN3;
}

static inline void pk_hybrid_add64(uint32_t *lo, uint32_t *hi, uint32_t add)
{
    uint32_t old = *lo;
    uint32_t next = old + add;
    *lo = next;
    if (next < old)
        *hi += 1u;
}

static void pk_hybrid_zero_u32(void *dst, uint32_t bytes)
{
    typedef uint32_t __attribute__((may_alias)) u32a;
    u32a *p = (u32a *)dst;
    uint32_t n = bytes >> 2;
    for (uint32_t i = 0; i < n; ++i)
        p[i] = 0u;
    for (uint32_t i = n * 4u; i < bytes; ++i) ((uint8_t *)dst)[i] = 0u;
}

static void pk_hybrid_copy_u32(void *dst, const void *src, uint32_t bytes)
{
    typedef uint32_t __attribute__((may_alias)) u32a;
    u32a *d = (u32a *)dst;
    const u32a *s = (const u32a *)src;
    uint32_t n = bytes >> 2;
    for (uint32_t i = 0; i < n; ++i)
        d[i] = s[i];
    for (uint32_t i = n * 4u; i < bytes; ++i) ((uint8_t *)dst)[i] = ((const uint8_t *)src)[i];
}

void pk_hybrid_reset_profiler(void)
{
    pk_hybrid_zero_u32(&pk_hybrid_prof, sizeof(pk_hybrid_profiler));
    pk_hybrid_zero_u32(&pk_hybrid_prof_export, sizeof(pk_hybrid_profiler));
    pk_hybrid_prof.magic = PK_HYB_PROF_MAGIC;
    pk_hybrid_prof.version = 2u;
    pk_hybrid_prof.profiler_enabled = pk_hybrid_profiler_enable;
    pk_hybrid_prof.cf_armed = pk_hybrid_cf_arm;
    pk_hybrid_prof.dtim3_hz = 132000000u;
    pk_hybrid_prof.period_min_ticks = 0xffffffffu;
    /* Stock enables DTIM3 later. Zero means unmeasured, not a free read. */
    pk_hybrid_timer_calibrated = 0u;
    pk_hybrid_cur_cf_ticks = 0u;
    pk_hybrid_cur_ctrl_ticks = 0u;
    pk_hybrid_cur_rend_ticks = 0u;
    pk_hybrid_cur_pack_ticks = 0u;
    pk_hybrid_cur_dsp_ticks = 0u;
    pk_hybrid_cur_voice_mask = 0u;
    pk_hybrid_cur_has_data = 0u;
    pk_hybrid_previous_enter_valid = 0u;
    pk_hybrid_prof_seq = 0u;
    pk_hybrid_export_seq = 0u;
    pk_hybrid_wait_ticks[0] = pk_hybrid_wait_ticks[1] = 0u;
    pk_hybrid_prof_cookie = PK_HYB_PROF_READY;
}

static void pk_hybrid_flush_frame_acc(void)
{
    uint32_t cf_t = pk_hybrid_cur_cf_ticks;
    uint32_t dsp_t = pk_hybrid_cur_dsp_ticks;
    uint32_t full_t;
    uint32_t ctrl_t = pk_hybrid_cur_ctrl_ticks;
    uint32_t rend_t = pk_hybrid_cur_rend_ticks;
    uint32_t pack_t = pk_hybrid_cur_pack_ticks;
    uint32_t vmask = pk_hybrid_cur_voice_mask;

    ++pk_hybrid_prof.frame_count;
    if (vmask & 0x22u)
        ++pk_hybrid_prof.cf_active_frames;
    if (vmask & 0x11u)
        ++pk_hybrid_prof.dsp_active_frames;
    pk_hybrid_prof.active_voice_mask = vmask;
    pk_hybrid_prof.active_cf_voices =
        ((vmask >> 1) & 1u) + ((vmask >> 5) & 1u);
    pk_hybrid_prof.active_dsp_voices =
        ((vmask >> 0) & 1u) + ((vmask >> 4) & 1u);

    if (cf_t > pk_hybrid_prof.max_cf_callback_ticks)
        pk_hybrid_prof.max_cf_callback_ticks = cf_t;
    if (ctrl_t > pk_hybrid_prof.max_cf_control_ticks)
        pk_hybrid_prof.max_cf_control_ticks = ctrl_t;
    if (rend_t > pk_hybrid_prof.max_cf_render_ticks)
        pk_hybrid_prof.max_cf_render_ticks = rend_t;
    if (pack_t > pk_hybrid_prof.max_cf_pack_ticks)
        pk_hybrid_prof.max_cf_pack_ticks = pack_t;
    if (dsp_t > pk_hybrid_prof.max_dsp_callback_ticks)
        pk_hybrid_prof.max_dsp_callback_ticks = dsp_t;

    pk_hybrid_add64(&pk_hybrid_prof.sum_cf_callback_lo, &pk_hybrid_prof.sum_cf_callback_hi, cf_t);
    pk_hybrid_add64(&pk_hybrid_prof.sum_cf_control_lo, &pk_hybrid_prof.sum_cf_control_hi, ctrl_t);
    pk_hybrid_add64(&pk_hybrid_prof.sum_cf_render_lo, &pk_hybrid_prof.sum_cf_render_hi, rend_t);
    pk_hybrid_add64(&pk_hybrid_prof.sum_cf_pack_lo, &pk_hybrid_prof.sum_cf_pack_hi, pack_t);
    pk_hybrid_add64(&pk_hybrid_prof.sum_dsp_callback_lo, &pk_hybrid_prof.sum_dsp_callback_hi, dsp_t);

    uint32_t idx = pk_hybrid_prof.ring_write_idx & (PK_HYB_PROF_RING_LEN - 1u);
    pk_hybrid_prof.ring_cf_ticks[idx] = cf_t;
    pk_hybrid_prof.ring_ctrl_ticks[idx] = ctrl_t;
    pk_hybrid_prof.ring_rend_ticks[idx] = rend_t;
    pk_hybrid_prof.ring_pack_ticks[idx] = pack_t;
    pk_hybrid_prof.ring_write_idx = idx + 1u;

    for (unsigned k = 0; k < 2u; ++k) {
        uint32_t dt = pk_hybrid_wait_ticks[k];
        if (dt > pk_hybrid_prof.wait_loop_max_ticks[k])
            pk_hybrid_prof.wait_loop_max_ticks[k] = dt;
        pk_hybrid_add64(&pk_hybrid_prof.wait_loop_sum_lo[k], &pk_hybrid_prof.wait_loop_sum_hi[k], dt);
    }
    /* Stamp after the counter/ring work so its cost is included. The small
     * post-stamp tail is accounted separately by the on/off overhead gate. */
    full_t = pk_hybrid_timer_now() - pk_hybrid_isr_enter_ticks;
    pk_hybrid_prof.ring_full_ticks[idx] = full_t;
    if (full_t > pk_hybrid_prof.max_full_frame_ticks)
        pk_hybrid_prof.max_full_frame_ticks = full_t;
    if (full_t > PK_HYB_FRAME_TICKS_132MHZ)
        ++pk_hybrid_prof.deadline_misses_100pct;
    if (full_t > PK_HYB_GATE80_TICKS_132MHZ)
        ++pk_hybrid_prof.margin_exceeded_80pct;
    pk_hybrid_add64(&pk_hybrid_prof.sum_full_frame_lo, &pk_hybrid_prof.sum_full_frame_hi, full_t);
    unsigned bin = full_t >> 10;
    ++pk_hybrid_prof.histogram[bin < 64u ? bin : 63u];
}

/* Called once by the vector-0x41 wrapper; no source callback groups frames. */
void pk_hybrid_frame_begin(void)
{
    if (!pk_hybrid_profiler_enable || pk_hybrid_prof_cookie != PK_HYB_PROF_READY)
        return;
    ++pk_hybrid_prof_seq; /* odd for the entire ISR, including callbacks */
    uint32_t now = pk_hybrid_isr_enter_ticks;
    if (pk_hybrid_previous_enter_valid) {
        uint32_t period = now - pk_hybrid_previous_enter;
        if (period < pk_hybrid_prof.period_min_ticks) pk_hybrid_prof.period_min_ticks = period;
        if (period > pk_hybrid_prof.period_max_ticks) pk_hybrid_prof.period_max_ticks = period;
    }
    pk_hybrid_previous_enter = now;
    pk_hybrid_previous_enter_valid = 1u;
    pk_hybrid_cur_cf_ticks = pk_hybrid_cur_ctrl_ticks = pk_hybrid_cur_rend_ticks = 0u;
    pk_hybrid_cur_pack_ticks = pk_hybrid_cur_dsp_ticks = pk_hybrid_cur_voice_mask = 0u;
    pk_hybrid_cur_has_data = 0u;
    pk_hybrid_wait_ticks[0] = pk_hybrid_wait_ticks[1] = 0u;
    pk_hybrid_prof.profiler_enabled = 1u;
    pk_hybrid_prof.cf_armed = pk_hybrid_cf_arm;
}

void pk_hybrid_frame_end(void)
{
    if (!pk_hybrid_profiler_enable || pk_hybrid_prof_cookie != PK_HYB_PROF_READY)
        return;
    pk_hybrid_flush_frame_acc();
    ++pk_hybrid_prof_seq; /* even: UI may attempt a nonblocking snapshot */
}

/* Track classification:
 *   Octatrack panel track 1..8 -> zero-based firmware track index 0..7.
 *   T1 = index 0 (DSP core B)
 *   T5 = index 4 (DSP core A)
 *   T2 = index 1 -> CF instance 0
 *   T6 = index 5 -> CF instance 1
 *   T3/T4/T7/T8 = indices 2,3,6,7 -> stock only (-1).
 */
static inline int pk_hybrid_is_dsp_track(unsigned track)
{
    return track == 0u || track == 4u;
}

static inline int pk_hybrid_cf_instance(unsigned track)
{
    if (track == 1u)
        return 0;
    if (track == 5u)
        return 1;
    return -1;
}

static inline int pk_hybrid_supported_track(unsigned track)
{
    return pk_hybrid_is_dsp_track(track) || pk_hybrid_cf_instance(track) >= 0;
}

/* Decode PKR1 stream once into BSS before real-time synthesis. */
static void pk_hybrid_decode_pcm(void)
{
    static const pk_cf_rice_target targets[2] = {
        { 2048u,  (int16_t *)(void *)pk_pcm_wt_base },
        { 98304u, (int16_t *)(void *)pk_pcm_wt_bank },
    };
    if (pk_cf_rice_unpack_le(
            pk_asset_pcm_rice,
            (uint32_t)(pk_asset_pcm_rice_end - pk_asset_pcm_rice),
            targets, 2u)) {
        pk_hybrid_pcm_cookie = PK_HYB_PCM_READY;
    }
}

int pk_hybrid_ensure_pcm(void)
{
    if (pk_hybrid_pcm_cookie != PK_HYB_PCM_READY)
        pk_hybrid_decode_pcm();
    return pk_hybrid_pcm_cookie == PK_HYB_PCM_READY;
}

/* Initialize a single CF instance's three supported algorithms (WT V1, WT V2,
 * Resonant snare/bass/nt) and RNG (1, 0), matching Phase 1 `hybrid_cf_bench.c`
 * byte-for-byte. */
static void pk_hybrid_init_voice(pk_hybrid_cf_voice *v)
{
    pk_hybrid_zero_u32(v, sizeof(*v));
    wt_init(v->wt[0], PK_HYB_VELOCITY, PK_HYB_NOTE);
    wt_init(v->wt[1], PK_HYB_VELOCITY, PK_HYB_NOTE);
    res_init_snare(v->snare, PK_HYB_VELOCITY, 63u);
    res_init_bass(v->bass, PK_HYB_VELOCITY, 63u);
    res_init_nt(v->nt, PK_HYB_VELOCITY, 63u, &pk_hybrid_assets);
    v->rng_low = 1u;
    v->rng_high = 0u;
    v->active_algo = 0xffu;
    v->active_mode = 0xffu;
}

static void pk_hybrid_init_all_cf_voices(void)
{
    for (unsigned inst = 0; inst < PK_HYB_CF_INSTANCE_COUNT; ++inst) {
        pk_hybrid_init_voice(&pk_hybrid_voices[inst]);
        pk_hybrid_trigger_latch[inst] = 0u;
        pk_hybrid_frame_started[inst] = 0u;
        pk_hybrid_frame_ping[inst] = 0u;
        pk_hybrid_cf_ui_pending[inst] = 0u;
        pk_hybrid_cf_ui_bank[inst] = 0xffffffffu;
        pk_hybrid_cf_ui_part[inst] = 0xffu;
        for (unsigned i = 0; i < PK_HYB_BLOCK_SAMPLES; ++i)
            pk_hybrid_frame_pcm[inst][i] = 0;
    }
}

/* Called by the hybrid loader after hash-verified depacking, before RTOS
 * handoff and before any machine callback. Failure sends the loader to fatal. */
int pk_hybrid_boot_init(void)
{
    if (!pk_hybrid_ensure_pcm()) return 0;
    pk_hybrid_reset_profiler();
    /* The loader does not clear BSS. Native control history can survive with
     * the same Bank/Part and family, bypassing its lazy invalidation. Clear
     * it here, before audio/UI; preserve the native producer's arithmetic. */
    pk_hybrid_zero_u32(simple_controls, sizeof(simple_controls));
    pk_hybrid_zero_u32(pk_prefix_controls, sizeof(pk_prefix_controls));
    pk_hybrid_zero_u32(pk_prefix_valid, sizeof(pk_prefix_valid));
    pk_hybrid_zero_u32(pk_trig_last, sizeof(pk_trig_last));
    pk_hybrid_zero_u32(pk_trig_count, sizeof(pk_trig_count));
    pk_hybrid_zero_u32(pk_ui_pending, sizeof(pk_ui_pending));
    pk_hybrid_zero_u32(pk_ui_bank, sizeof(pk_ui_bank));
    pk_hybrid_zero_u32(pk_ui_part, sizeof(pk_ui_part));
    simple_bank = 0u;
    simple_part = 0u;
    pk_hybrid_init_voice(&pk_hybrid_pristine);
    pk_hybrid_init_all_cf_voices();
    pk_hybrid_generation = 0u;
    pk_hybrid_voice_generation[0] = pk_hybrid_voice_generation[1] = 0u;
    pk_hybrid_bank = 0xffffffffu;
    pk_hybrid_part = 0xffu;
    pk_hybrid_seen_running = 0u;
    pk_hybrid_export_status = 0;
    pk_hybrid_export_index = 0u;
    pk_hybrid_rt_cookie = PK_HYB_RT_READY; /* publish last, loaded cookie */
    return 1;
}

static void pk_hybrid_observe_generation(void)
{
    uint32_t bank = U32(BANK);
    uint8_t part = U8(PART_IDX) & 3u;
    if (pk_hybrid_bank != bank || pk_hybrid_part != part) {
        pk_hybrid_bank = bank;
        pk_hybrid_part = part;
        ++pk_hybrid_generation;
        pk_hybrid_prof.handoff_generation = pk_hybrid_generation;
    }
}

static void pk_hybrid_reset_at_event(unsigned inst)
{
    if (pk_hybrid_voice_generation[inst] == pk_hybrid_generation) return;
    uint32_t t0 = pk_hybrid_timer_now();
    /* Fixed-size state copy, not decoder/constructor work. Keep the already
     * rendered pre-event PCM and latched trigger; consume the trigger once. */
    pk_hybrid_copy_u32(&pk_hybrid_voices[inst], &pk_hybrid_pristine, sizeof(pk_hybrid_cf_voice));
    pk_hybrid_voice_generation[inst] = pk_hybrid_generation;
    uint32_t dt = pk_hybrid_timer_now() - t0;
    if (dt > pk_hybrid_prof.reset_max_ticks) pk_hybrid_prof.reset_max_ticks = dt;
    ++pk_hybrid_prof.reset_count;
}

/* Explicit tested control-order adapter:
 *   UI SRC page order: A TUNE (0), B DECAY (1), C ALGO (2), D PAR1 (3), E PAR2 (4), F MODE (5).
 *   Internal recovered engine order: decay, tune, p1, p2, mode, algo (where raw[0]=tune, raw[1]=decay, raw[2]=p1, raw[3]=p2).
 */
int __attribute__((noinline)) pk_hybrid_cf_prepare_event(unsigned inst,
                               uint8_t decay, uint8_t tune,
                               uint8_t p1, uint8_t p2,
                               uint8_t mode, uint8_t algo,
                               uint8_t vel, uint8_t note, int trig)
{
    if (inst >= PK_HYB_CF_INSTANCE_COUNT)
        return 0;
    if (algo >= PK_HYB_CF_ALGO_COUNT)
        algo = PK_HYB_CF_ALGO_COUNT - 1u;
    if (mode > 2u)
        mode = 2u;
    pk_hybrid_cf_voice *v = &pk_hybrid_voices[inst];
    uint8_t raw[4] = { tune, decay, p1, p2 };
    if (algo < 2u) {
        prepare_wt(&v->control[algo], v->wt[algo], raw, mode, vel, note, trig, &pk_hybrid_assets);
    } else {
        prepare_res_family(&v->control[2], v->snare, v->bass, v->nt, raw, mode, vel, note, trig, &pk_hybrid_assets);
    }
    v->active_algo = algo;
    v->active_mode = mode;
    return 1;
}

int __attribute__((noinline)) pk_hybrid_cf_render_segment(unsigned inst, int16_t *dst, uint32_t count)
{
    if (inst >= PK_HYB_CF_INSTANCE_COUNT || !dst || count > PK_HYB_BLOCK_SAMPLES)
        return 0;
    pk_hybrid_cf_voice *v = &pk_hybrid_voices[inst];
    if (v->active_algo < 2u) {
        pk_cf_wt_tables t = {
            pk_hybrid_assets.pitch,
            pk_hybrid_assets.envelope1,
            pk_hybrid_assets.envelope2,
            pk_hybrid_assets.wt_base,
            pk_hybrid_assets.wt_bank,
        };
        return pk_cf_wt_render(v->wt[v->active_algo], dst, count, &t);
    }
    if (v->active_algo == 2u) {
        if (v->active_mode < 2u) {
            pk_cf_res_tables rt = {
                pk_hybrid_assets.envelope1,
                pk_hybrid_assets.envelope2,
                pk_hybrid_assets.res_interp_a,
                pk_hybrid_assets.res_interp_b,
            };
            pk_cf_res_rng rr = { v->rng_low, v->rng_high };
            int ok = (v->active_mode == 0u)
                ? pk_cf_res_snare_render(v->snare, dst, count, &rt, &rr)
                : pk_cf_res_bass_render(v->bass, dst, count, &rt, &rr);
            if (!ok)
                return 0;
            v->rng_low = rr.low;
            v->rng_high = rr.high;
            return 1;
        }
        if (v->active_mode == 2u) {
            pk_cf_nt_shared_tables nt;
            pk_cf_nt_rng nr = { v->rng_low, v->rng_high };
            nt.envelope1 = pk_hybrid_assets.envelope1;
            nt.envelope2 = pk_hybrid_assets.envelope2;
            for (unsigned i = 0; i < 4u; ++i) {
                nt.waves[i].address = pk_hybrid_assets.waves[i].address;
                nt.waves[i].table = pk_hybrid_assets.waves[i].table;
            }
            if (!pk_cf_nt_shared_render(v->nt, dst, count, &nt, &nr))
                return 0;
            v->rng_low = nr.low;
            v->rng_high = nr.high;
            return 1;
        }
    }
    return 0;
}

static volatile uint32_t *pk_hybrid_fixed_slot(unsigned track, unsigned ping)
{
    return (volatile uint32_t *)(uintptr_t)(
        PK_HYB_SLOT_BASE + (ping & 1u) * PK_HYB_PING_BYTES
        + PK_HYB_SLOT_BYTES * track
    );
}

static void __attribute__((noinline))
pk_hybrid_commit_longs(volatile uint32_t *dst, const uint32_t *src, uint32_t count)
{
    for (uint32_t i = 0; i < count; ++i)
        dst[i] = src[i];
}

/* Same stock FLEX record as pk4_encode_stock_segment, published directly to
 * the owned fixed slot. Keep volatile long stores and a separate call: GCC
 * otherwise duplicates the variable-length encoder throughout pk_render. */
static uint32_t __attribute__((noinline))
pk_hybrid_encode_slot(volatile uint32_t *dst, const int16_t *pcm, uint32_t count)
{
    if (!dst || !pcm || count > PK_HYB_BLOCK_SAMPLES) return 0u;
    dst[0] = (count << 8) | count;
    dst[1] = 0u;
    dst[2] = 0x04000000u;
    dst[3] = 0u;
    for (uint32_t i = 0; i < count; ++i) {
        uint32_t sample = (uint32_t)(int32_t)pcm[i] << 16;
        dst[4u + 2u*i] = sample;
        dst[5u + 2u*i] = sample;
    }
    return 4u + 2u*count;
}

/* Dynamic SRC page builder for hybrid tracks:
 *   T1/T5 (DSP): ALGO max = 4 (Fold1, Fold2, Simple, Complex)
 *   T2/T6 (CF):  ALGO max = 3 (WT V1, WT V2, Resonant)
 *   All six controls: TUNE, DECAY, ALGO, PAR1, PAR2, MODE.
 */
static uint32_t pk_hybrid_page(unsigned track)
{
    uint32_t page = pk_light2_page();
    uint32_t algo_max = (pk_hybrid_cf_instance(track) >= 0)
        ? PK_HYB_CF_ALGO_COUNT
        : PK_HYB_DSP_ALGO_COUNT;
    put32(desc + 0xd2 + 4u * ALGO_SLOT, algo_max);
    return page;
}

/* ---- Exported Machine Hooks (bound to public `pk_*` symbols) ------------ */

unsigned pk_hybrid_admit_track(const volatile uint8_t *part, unsigned track)
    __asm__("pk_admit_track");
unsigned pk_hybrid_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return pk_hybrid_supported_track(track) ? 1u : 0u;
}

uint32_t pk_hybrid_track_page(const volatile uint8_t *type_ptr)
    __asm__("pk_track_page");
uint32_t pk_hybrid_track_page(const volatile uint8_t *type_ptr)
{
    volatile uint8_t *part = part_base();
    const uintptr_t track = (uintptr_t)type_ptr - (uintptr_t)(part + 0x22u);
    return pk_hybrid_page(track < 8u ? (unsigned)track : 0u);
}

uint32_t pk_hybrid_machine_glyph(unsigned track, uint32_t original)
    __asm__("pk_machine_glyph");
uint32_t pk_hybrid_machine_glyph(unsigned track, uint32_t original)
{
    const volatile uint8_t *part = (const volatile uint8_t *)(uintptr_t)
        (U32(BANK) + PART_OFF + (U8(0x80000003u) & 3u) * PART_STRIDE);
    if (track < 8u && pk_hybrid_supported_track(track) && signed_track(part, track))
        return U32(0x400a81a4u + 4u * 4u); /* stock Pickup P bitmap only */
    return original;
}

unsigned pk_hybrid_ui_playing(unsigned track, unsigned original)
    __asm__("pk_ui_playing");
unsigned pk_hybrid_ui_playing(unsigned track, unsigned original)
{
    if (original)
        return original;
    const unsigned part_index = U8(0x80000003u) & 3u;
    const volatile uint8_t *part = (const volatile uint8_t *)(uintptr_t)
        (U32(BANK) + PART_OFF + part_index * PART_STRIDE);
    if (track >= 8u || !pk_hybrid_supported_track(track) || !signed_track(part, track))
        return original;
    int inst = pk_hybrid_cf_instance(track);
    if (inst >= 0) {
        unsigned fired = pk_hybrid_cf_ui_pending[inst]
                      && pk_hybrid_cf_ui_bank[inst] == U32(BANK)
                      && pk_hybrid_cf_ui_part[inst] == part_index;
        pk_hybrid_cf_ui_pending[inst] = 0u;
        return fired;
    }
    return pk_ui_playing(track, original);
}

/* The UI task is the sole snapshot/file writer. No interrupt masking or
 * filesystem call is permitted in the audio callback. A failed seqlock read
 * is retried on a later UI tick, never in a spin loop. */
static uint32_t pk_hybrid_file_object[6];
static uint32_t pk_hybrid_file_buffer[1024];
static struct {
    uint32_t magic, version, bytes, sequence;
    char source_id[68];
    pk_hybrid_profiler profile;
} pk_hybrid_export_record;

static int pk_hybrid_write_profile(void)
{
    typedef int (*open_fn)(void *, const char *, const char *, void *, uint32_t);
    typedef int (*write_fn)(void *, const void *, uint32_t);
    typedef int (*close_fn)(void *);
    open_fn open_file = (open_fn)0x40016864u;
    write_fn write_file = (write_fn)0x400166b8u;
    close_fn close_file = (close_fn)0x4001677cu;
    char path[] = "/PKH20000.PRF";
    /* Reserve a fresh diagnostic name; never truncate an existing export. */
    for (unsigned attempt = 0; attempt < 32u; ++attempt) {
        unsigned index = pk_hybrid_export_index++;
        if (index > 9999u) return -2;
        for (unsigned digit = 0; digit < 4u; ++digit) {
            path[8u - digit] = (char)('0' + index % 10u);
            index /= 10u;
        }
        if (open_file(pk_hybrid_file_object, path, "r", pk_hybrid_file_buffer,
                      sizeof(pk_hybrid_file_buffer)) >= 0) {
            close_file(pk_hybrid_file_object);
            continue;
        }
        if (open_file(pk_hybrid_file_object, path, "w", pk_hybrid_file_buffer,
                      sizeof(pk_hybrid_file_buffer)) < 0) return -3;
        pk_hybrid_export_record.magic = 0x504b5032u; /* PKP2 */
        pk_hybrid_export_record.version = 2u;
        pk_hybrid_export_record.bytes = sizeof(pk_hybrid_export_record);
        pk_hybrid_export_record.sequence = pk_hybrid_export_seq;
        for (unsigned j = 0; j < 68u; ++j)
            pk_hybrid_export_record.source_id[j] = j < 64u ? pk_hybrid_source_id[j] : 0;
        pk_hybrid_copy_u32(&pk_hybrid_export_record.profile, &pk_hybrid_prof_export,
                           sizeof(pk_hybrid_profiler));
        int ok = write_file(pk_hybrid_file_object, &pk_hybrid_export_record,
                            sizeof(pk_hybrid_export_record)) == 1;
        int closed = close_file(pk_hybrid_file_object);
        return ok && closed >= 0 ? 1 : -4;
    }
    return -5;
}

static void pk_hybrid_snapshot_and_export(void)
{
    uint32_t before = pk_hybrid_prof_seq;
    if (before & 1u) return;
    pk_hybrid_copy_u32(&pk_hybrid_snapshot, &pk_hybrid_prof, sizeof(pk_hybrid_profiler));
    __asm__ volatile ("" ::: "memory");
    if (before != pk_hybrid_prof_seq) {
        /* UI owns this diagnostic count; ISR does not read/write it. */
        ++pk_hybrid_prof.snapshot_retries;
        return;
    }
    pk_hybrid_snapshot.profiler_enabled = pk_hybrid_profiler_enable;
    pk_hybrid_snapshot.cf_armed = pk_hybrid_cf_arm;
    ++pk_hybrid_export_seq;
    pk_hybrid_copy_u32(&pk_hybrid_prof_export, &pk_hybrid_snapshot, sizeof(pk_hybrid_profiler));
    ++pk_hybrid_export_seq;
    if (U32(0x800065b8u) == 1u) {
        pk_hybrid_seen_running = 1u;
    } else if (pk_hybrid_seen_running) {
        pk_hybrid_seen_running = 0u; /* at most one write per real stop */
        pk_hybrid_export_status = pk_hybrid_write_profile();
    }
}

void pk_hybrid_ui_tick(void)
    __asm__("pk_ui_tick");
void pk_hybrid_ui_tick(void)
{
    if (pk_hybrid_rt_cookie != PK_HYB_RT_READY) return;
    /* One bounded pair in task context after stock timer setup. This is the
     * observed read-to-read interval, not total instrumentation overhead or
     * a silicon WCET bound. Never reprogram/reset stock's timer. */
    if (!pk_hybrid_timer_calibrated && PK_HYB_DTMR3 == 0x000bu
        && PK_HYB_DTRR3 == 0xffffffffu) {
        uint32_t t0 = pk_hybrid_timer_now();
        uint32_t t1 = pk_hybrid_timer_now();
        pk_hybrid_prof.read_overhead_ticks = t1 - t0;
        pk_hybrid_timer_calibrated = 1u;
    }
    unsigned cur_track = (unsigned)U8(0x100b14ccu) & 7u;
    U32(0x400d5f38u + PERKY_ROW * 4u) = pk_hybrid_page(cur_track);

    ++pk_hybrid_prof.ui_tick_count;
    pk_hybrid_snapshot_and_export();
}

/* ---- Unified Exported Source Dispatcher (`pk_render`) ------------------ */

int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)
    __asm__("pk_render");
int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    unsigned prof_on = pk_hybrid_profiler_enable != 0u;
    uint32_t t_entry = prof_on ? pk_hybrid_timer_now() : 0u;

    /* Unsupported track or unsigned / non-PERKY track: untouched stock continuation. */
    if (track >= 8u || !pk_hybrid_supported_track(track)
        || !signed_track(part_base(), track)) {
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);
    }

    if (end < start || end > PK_HYB_BLOCK_SAMPLES)
        return 0;

    /* Route 1: Signed T1 (track 0, core B) or T5 (track 4, core A) -> Original DSP-native producer. */
    if (pk_hybrid_is_dsp_track(track)) {
        int rc = pk_render(track, ping, start, end);
        if (prof_on) {
            uint32_t dt = pk_hybrid_timer_now() - t_entry;
            pk_hybrid_cur_dsp_ticks += dt;
            pk_hybrid_cur_voice_mask |= (1u << track);
            pk_hybrid_cur_has_data = 1u;
        }
        return rc;
    }

    /* Route 2: Signed T2 (track 1 -> inst 0) or T6 (track 5 -> inst 1) -> ColdFire runtime. */
    int inst_s = pk_hybrid_cf_instance(track);
    if (inst_s < 0) {
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);
    }
    unsigned inst = (unsigned)inst_s;

    if (pk_hybrid_pcm_cookie != PK_HYB_PCM_READY || pk_hybrid_rt_cookie != PK_HYB_RT_READY) {
        ++pk_hybrid_prof.readiness_faults;
        /* Unreachable after a successful loader; never decode in real time. */
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);
    }

    uint32_t count = end - start;
    uint32_t cursor_longs = 4u + 2u * count;
    int event_boundary = (end == PK_HYB_BLOCK_SAMPLES);
    volatile uint32_t *cursor = (volatile uint32_t *)(uintptr_t)U32(0x80001c80u);

    /* Armed/disarmed CF comparison mode without changing frozen DSP bytes. */
    if (!pk_hybrid_cf_arm) {
        for (uint32_t i = 0; i < cursor_longs; ++i)
            cursor[i] = 0u;
        U32(0x80001c80u) = (uint32_t)(uintptr_t)(cursor + cursor_longs);
        if (event_boundary) {
            int16_t zeros[PK_HYB_BLOCK_SAMPLES] = { 0 };
            uint32_t encoded[40];
            uint32_t pre_longs = pk4_encode_stock_segment(encoded, zeros, start);
            volatile uint32_t *record = pk_hybrid_fixed_slot(track, ping);
            pk_hybrid_commit_longs(record, encoded, pre_longs);
            uint32_t post_longs = pk4_encode_stock_segment(encoded, zeros, PK_HYB_BLOCK_SAMPLES - start);
            pk_hybrid_commit_longs(record + pre_longs, encoded, post_longs);
        }
        if (prof_on) {
            uint32_t dt = pk_hybrid_timer_now() - t_entry;
            pk_hybrid_cur_cf_ticks += dt;
            pk_hybrid_cur_voice_mask |= (1u << track);
            pk_hybrid_cur_has_data = 1u;
        }
        return 0;
    }

    pk_hybrid_observe_generation();

    uint32_t t_ctrl0 = prof_on ? pk_hybrid_timer_now() : 0u;

    /* Frame cache management: never compare `ping` for logical frame identity,
     * because the stock source packer flips `ping` between pre-event and
     * post-event callbacks of the same 16-sample frame. */
    if (start == 0u) {
        for (unsigned i = 0; i < PK_HYB_BLOCK_SAMPLES; ++i)
            pk_hybrid_frame_pcm[inst][i] = 0;
        pk_hybrid_frame_started[inst] = 1u;
        pk_hybrid_frame_ping[inst] = (uint8_t)(ping & 1u);
    } else if (event_boundary && !pk_hybrid_frame_started[inst]) {
        /* Cold mid-frame handoff: prefix was not rendered by PERKY CF, silence it. */
        for (unsigned i = 0; i < start; ++i)
            pk_hybrid_frame_pcm[inst][i] = 0;
        pk_hybrid_frame_started[inst] = 1u;
        pk_hybrid_frame_ping[inst] = (uint8_t)(ping & 1u);
    }

    /* Latch trigger observations across both halves of the split callback. */
    if ((U8(0x46104d0cu + track) & 16u) != 0u)
        pk_hybrid_trigger_latch[inst] = 1u;
    int trig = event_boundary && (pk_hybrid_trigger_latch[inst] != 0u);

    if (event_boundary) {
        pk_hybrid_reset_at_event(inst);
        volatile uint16_t *fp = (volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
        uint8_t src[6];
        for (unsigned i = 0; i < 6u; ++i)
            src[i] = (uint8_t)(fp[i] >> 8);
        uint8_t tune = src[TUNE_SLOT];
        uint8_t decay = src[DECAY_SLOT];
        uint8_t algo = src[ALGO_SLOT] < PK_HYB_CF_ALGO_COUNT
            ? src[ALGO_SLOT]
            : (PK_HYB_CF_ALGO_COUNT - 1u);
        uint8_t p1 = src[PARAM1_SLOT];
        uint8_t p2 = src[PARAM2_SLOT];
        uint8_t mode = src[MODE_SLOT_FINAL] > 2u ? 2u : src[MODE_SLOT_FINAL];

        (void)pk_hybrid_cf_prepare_event(
            inst, decay, tune, p1, p2, mode, algo,
            PK_HYB_VELOCITY, PK_HYB_NOTE, trig
        );
    }
    uint32_t t_ctrl1 = prof_on ? pk_hybrid_timer_now() : 0u;

    /* Render straight into the retained frame slice. The two stock callbacks
     * own disjoint sample ranges; their concatenation is encoded only at the
     * event boundary. This removes the temporary PCM and its copy. */
    int16_t *pcm = pk_hybrid_frame_pcm[inst] + start;
    if (!pk_hybrid_cf_render_segment(inst, pcm, count)) {
        for (unsigned i = 0; i < count; ++i)
            pcm[i] = 0;
    }
    uint32_t t_rend1 = prof_on ? pk_hybrid_timer_now() : 0u;

    /* The final callback publishes all 40 fixed-slot words before returning.
     * Preserve cursor reservation, but avoid zero writes that this very
     * callback immediately overwrites. Prefix callbacks still clear every
     * reserved word, including when the stock packer changes ping. */
    uintptr_t record_begin = (uintptr_t)pk_hybrid_fixed_slot(track, ping);
    uintptr_t record_end = record_begin + 40u * sizeof(uint32_t);
    uintptr_t cursor_begin = (uintptr_t)cursor;
    uintptr_t cursor_end = (uintptr_t)(cursor + cursor_longs);
    if (!event_boundary || cursor_end <= record_begin || cursor_begin >= record_end) {
        for (uint32_t i = 0; i < cursor_longs; ++i)
            cursor[i] = 0u;
    } else {
        for (uintptr_t address = cursor_begin; address < record_begin; address += 4u)
            *(volatile uint32_t *)address = 0u;
        for (uintptr_t address = record_end; address < cursor_end; address += 4u)
            *(volatile uint32_t *)address = 0u;
    }
    U32(0x80001c80u) = (uint32_t)(uintptr_t)(cursor + cursor_longs);

    if (event_boundary) {
        volatile uint32_t *record = pk_hybrid_fixed_slot(track, ping);
        const unsigned split = start;
        uint32_t pre_longs = pk_hybrid_encode_slot(
            record, pk_hybrid_frame_pcm[inst], split
        );
        if (!pre_longs)
            return 0;
        uint32_t post_longs = pk_hybrid_encode_slot(
            record + pre_longs, pk_hybrid_frame_pcm[inst] + split,
            PK_HYB_BLOCK_SAMPLES - split
        );
        if (!post_longs)
            return 0;
        if (pre_longs + post_longs != 40u)
            return 0;

        pk_hybrid_trigger_latch[inst] = 0u;
        pk_hybrid_frame_started[inst] = 0u;
    }

    ++pk_render_calls;
    if (trig) {
        ++pk_hits;
        pk_hybrid_cf_ui_bank[inst] = U32(BANK);
        pk_hybrid_cf_ui_part[inst] = U8(PART_IDX) & 3u;
        pk_hybrid_cf_ui_pending[inst] = 1u;
    }

    if (prof_on) {
        uint32_t t_end = pk_hybrid_timer_now();
        uint32_t dt_total = t_end - t_entry;
        uint32_t dt_ctrl = t_ctrl1 - t_ctrl0;
        uint32_t dt_rend = t_rend1 - t_ctrl1;
        uint32_t dt_pack = t_end - t_rend1;

        pk_hybrid_cur_cf_ticks += dt_total;
        pk_hybrid_cur_ctrl_ticks += dt_ctrl;
        pk_hybrid_cur_rend_ticks += dt_rend;
        pk_hybrid_cur_pack_ticks += dt_pack;
        pk_hybrid_cur_voice_mask |= (1u << track);
        pk_hybrid_cur_has_data = 1u;

        ++pk_hybrid_prof.inst_calls[inst];
        if (trig)
            ++pk_hybrid_prof.inst_trigs[inst];
        pk_hybrid_prof.cf_sample_count += count;

        if (dt_total > pk_hybrid_prof.inst_max_ticks[inst])
            pk_hybrid_prof.inst_max_ticks[inst] = dt_total;
        if (dt_ctrl > pk_hybrid_prof.inst_max_control_ticks[inst])
            pk_hybrid_prof.inst_max_control_ticks[inst] = dt_ctrl;
        if (dt_rend > pk_hybrid_prof.inst_max_render_ticks[inst])
            pk_hybrid_prof.inst_max_render_ticks[inst] = dt_rend;
        if (dt_pack > pk_hybrid_prof.inst_max_pack_ticks[inst])
            pk_hybrid_prof.inst_max_pack_ticks[inst] = dt_pack;

    }

    return 0;
}
