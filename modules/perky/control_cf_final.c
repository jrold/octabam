/* Final Perky Machines ColdFire source-machine integration.
 *
 * Locked SRC page:
 *   A TUNE / B DECAY / C ALGO / D PRM1 / E PRM2 / F MODE
 *
 * Four independent voices live on OT tracks 1,2,3,4 (zero-based 0,1,2,3).
 * The native PĒRKONS renderers run on ColdFire and publish ordinary stock
 * unity-rate source segments.  No DSP synth hook, DSP code replacement, FX
 * memory claim, or FX dispatch change is used by this final architecture.
 */

/* Reuse the measured machine-admission/UI/validator surface from control.c,
 * but replace its old five-control page, hidden Algo browser and DSP-record
 * renderer below. */
#define pk_defaults pk_defaults_cf_legacy
#define pk_admit_track pk_admit_track_cf_legacy
#define page_for page_for_cf_legacy
#define pk_track_page pk_track_page_cf_legacy
#define pk_ui_tick pk_ui_tick_cf_legacy
#define pk_render pk_render_cf_legacy
#define pk_engine_select pk_engine_select_cf_legacy
#define pk_engine_draw pk_engine_draw_cf_legacy
#define pk_engine_open pk_engine_open_cf_legacy
#define pk_engine_left pk_engine_left_cf_legacy
#define pk_engine_right pk_engine_right_cf_legacy
#include "control.c"
#undef pk_engine_right
#undef pk_engine_left
#undef pk_engine_open
#undef pk_engine_draw
#undef pk_engine_select
#undef pk_render
#undef pk_ui_tick
#undef pk_track_page
#undef page_for
#undef pk_admit_track
#undef pk_defaults

#include "cf_perky4.h"

#define PK_FINAL_TUNE 0u
#define PK_FINAL_DECAY 1u
#define PK_FINAL_ALGO 2u
#define PK_FINAL_PARAM1 3u
#define PK_FINAL_PARAM2 4u
#define PK_FINAL_MODE 5u
/* Machine families exposed by the ALGO control: 0 Fold1, 1 Fold2, 2 Karplus,
 * 3 Noise/Tone, 4 Resonant Drums. */
#define PK_FINAL_ALGO_COUNT 6u
#define PK_FINAL_NOTE 45u
#define PK_FINAL_VELOCITY 255u
#define PK_FINAL_BLOCK_SAMPLES 16u
#define PK_FINAL_SLOT_BYTES 336u
#define PK_FINAL_PING_BYTES 0xa80u
#define PK_FINAL_SLOT_BASE 0x80001c90u

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
extern const uint8_t pk_asset_wt_base[];
extern const uint8_t pk_asset_wt_bank[];

const uint8_t pk_defaults[12] = {
    64, 64, 0, 64, 64, 0,
    0, 0, 0, 0, 0, 0
};

static pk4_engine pk_final_engine;
static uint32_t pk_final_bank;
static uint8_t pk_final_part;
static uint8_t pk_final_trigger_latch[4];
static int16_t pk_final_frame_pcm[4][PK_FINAL_BLOCK_SAMPLES];
static uint8_t pk_final_frame_started[4];
static uint8_t pk_final_frame_ping[4];
#define PK_FINAL_RUNTIME_COLD 0x504b434fu
#define PK_FINAL_RUNTIME_READY 0x504b5244u
static uint32_t pk_final_runtime_cookie = PK_FINAL_RUNTIME_COLD;

static const pk4_assets pk_final_assets = {
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
    .res_interp_a = pk_asset_res_interp_a,
    .res_interp_b = pk_asset_res_interp_b,
    .wt_base = pk_asset_wt_base,
    .wt_bank = pk_asset_wt_bank,
    .m1_wave_address = 0x080310e0u,
};

static int pk_final_voice_index(unsigned track)
{
    switch (track) {
    case 0u: return 0;
    case 1u: return 1;
    case 2u: return 2;
    case 3u: return 3;
    default: return -1;
    }
}

static volatile uint32_t *pk_final_fixed_slot(unsigned track, unsigned ping)
{
    return (volatile uint32_t *)(uintptr_t)
        (PK_FINAL_SLOT_BASE + (ping & 1u) * PK_FINAL_PING_BYTES
         + PK_FINAL_SLOT_BYTES * track);
}

static void pk_final_reset_runtime_if_needed(void)
{
    const uint32_t bank = U32(BANK);
    const uint8_t part = U8(PART_IDX) & 3u;
    if (pk_final_runtime_cookie != PK_FINAL_RUNTIME_READY
        || pk_final_bank != bank || pk_final_part != part) {
        pk4_init(&pk_final_engine, &pk_final_assets);
        for (unsigned voice = 0; voice < 4u; ++voice) {
            pk_final_trigger_latch[voice] = 0u;
            pk_final_frame_started[voice] = 0u;
            pk_final_frame_ping[voice] = 0u;
            for (unsigned sample = 0; sample < PK_FINAL_BLOCK_SAMPLES; ++sample)
                pk_final_frame_pcm[voice][sample] = 0;
        }
        pk_final_bank = bank;
        pk_final_part = part;
        pk_final_runtime_cookie = PK_FINAL_RUNTIME_READY;
    }
}

/* The ALGO row is PER-VOICE.  T1..T4 are PĒRKONS voices V1..V4 and each
 * track's ALGO knob ranges over only its own family (see cf_perky4.h), so the
 * descriptor's ALGO maximum is (re)published on every call -- the descriptor
 * buffer itself is a single static page that the stock editor reads live. */
static uint32_t pk_final_page(unsigned track)
{
    static const char *const names[6] = {
        "TUNE", "DECAY", "ALGO", "PRM1", "PRM2", "MODE"
    };
    const unsigned voice = track < PK4_VOICE_COUNT ? track : 0u;
    (void)page_for_cf_legacy(DEFAULT_ENGINE);
    text(desc + 0x41, "PERKY MACH", 13);
    for (unsigned i = 0; i < 6u; ++i) {
        uint32_t maximum = 128u;
        uint32_t formatter = 0u;
        uint32_t widget = 0u;
        if (i == PK_FINAL_ALGO) {
            maximum = pk4_voice_len(voice);
            formatter = MODE_FORMATTER;
        } else if (i == PK_FINAL_MODE) {
            maximum = 3u;
            formatter = MODE_FORMATTER;
            widget = MODE_WIDGET;
        }
        text(desc + 0x4e + 6u * i, names[i], 6);
        desc[0x96 + i] = pk_defaults[i];
        put32(desc + 0xa2 + 4u * i, 0);
        put32(desc + 0xd2 + 4u * i, maximum);
        put32(desc + 0x102 + 4u * i, formatter);
        put32(desc + 0x132 + 4u * i, widget);
        put32(desc + 0x162 + 4u * i, 0);
    }
    /* Publish exactly A..F to the normal source/p-lock staging path. */
    put32(desc + 0x1c2, 0x00000000u);
    put32(desc + 0x1c6, 0x00111111u);
    pk_desc_p = (uint32_t)(uintptr_t)(desc + 0x38);
    return pk_desc_p;
}

unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return pk_final_voice_index(track) >= 0;
}

uint32_t pk_track_page(const volatile uint8_t *type_ptr)
{
    /* The stock passes the address of this track's machine-type byte, exactly
     * the way the legacy control.c page builder recovers the track. */
    volatile uint8_t *part = part_base();
    const uintptr_t track = (uintptr_t)type_ptr - (uintptr_t)(part + 0x22u);
    return pk_final_page(track < 8u ? (unsigned)track : 0u);
}

void pk_ui_tick(void)
{
    /* 0x100b14cc is the stock "current track" byte the legacy builder used. */
    U32(0x400d5f38u + PERKY_ROW * 4u) = pk_final_page((unsigned)U8(0x100b14ccu) & 7u);
}

int pk_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    volatile uint32_t *cursor;
    volatile uint16_t *fp;
    uint8_t src[6];
    uint8_t engine_src[6];
    int16_t pcm[PK_FINAL_BLOCK_SAMPLES];
    uint32_t encoded[4u + 2u * PK_FINAL_BLOCK_SAMPLES];
    uint32_t cursor_longs;
    unsigned count;
    int voice;
    int trig;
    int event_boundary;

    voice = pk_final_voice_index(track);
    if (track >= 8u || voice < 0 || !signed_track(part_base(), track))
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);

    if (end < start || end > PK_FINAL_BLOCK_SAMPLES)
        return 0;
    count = end - start;
    cursor = (volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    event_boundary = end == PK_FINAL_BLOCK_SAMPLES;

    pk_final_reset_runtime_if_needed();

    /* The stock source packer owns a moving cursor while it constructs each
     * 336-byte per-track DMA slot.  A renderer is called twice around the event
     * split.  The proven ANALOG BD seam advances/reserves that moving cursor,
     * but commits its completed record through the fixed per-track slot because
     * the first callback of a newly-selected source may still have been stock
     * FLEX.  Do the same here: render into a 16-sample frame cache, reserve the
     * caller's cursor span on each callback, then atomically replace the first
     * 160 bytes of the fixed slot when the boundary callback arrives. */
    if (start == 0u) {
        for (unsigned i = 0; i < PK_FINAL_BLOCK_SAMPLES; ++i)
            pk_final_frame_pcm[voice][i] = 0;
        pk_final_frame_started[voice] = 1u;
        pk_final_frame_ping[voice] = (uint8_t)(ping & 1u);
    } else if (event_boundary && !pk_final_frame_started[voice]) {
        /* First-hit handoff: the pre-event half may have been rendered by the
         * stock FLEX function before the PK/1 signature became active.  The
         * synth was silent before its first trigger, so make that unavailable
         * prefix explicitly silent instead of reusing stale PCM.
         *
         * ⚠️ THE GUARD IS `!started` ALONE -- DO NOT COMPARE `ping` HERE.
         * Measured on the emulator 9 Oct 2026 (--watch-pc 0x40abc67a, the
         * stock's two source callbacks per 16-sample frame): the stock passes
         * (track,ping,start,end) = (0,P,0,split) and (0,P^1,split,16) -- the
         * ping bit FLIPS BETWEEN THE TWO HALVES OF THE SAME FRAME.  The old
         * `|| pk_final_frame_ping[voice] != (ping & 1u)` therefore fired on
         * EVERY split frame and zeroed frame_pcm[0..split), throwing away the
         * pre-event half the first callback had just rendered.  `split` is the
         * trig's sample offset inside the frame (measured 0,3,5,8,11,13 for
         * trigs at steps 1/7/11 at 120 BPM, held until the next trig), so the
         * hardware symptom was "first hit good, later hits thinner and quieter,
         * snaps back when the song reaches a 16-aligned trig" -- i.e. silence
         * blanked over `split` of every 16 samples.  The first callback always
         * arrives with start==0, so `!started` still catches the real FLEX
         * handoff and needs no ping term.  A regression gate pins this:
         * tools/verify/verify_perky_cf_seq_drift.py. */
        for (unsigned i = 0; i < start; ++i)
            pk_final_frame_pcm[voice][i] = 0;
        pk_final_frame_started[voice] = 1u;
        pk_final_frame_ping[voice] = (uint8_t)(ping & 1u);
    }

    /* The first segment precedes the trig/event split. It must continue the
     * already-active voice unchanged even though the staging buffer may already
     * contain this trig's p-locks. Only the segment ending at 16 consumes A..F
     * and triggers the newly selected Algo/Mode. */
    if (event_boundary) {
        fp = (volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
        for (unsigned i = 0; i < 6u; ++i)
            src[i] = (uint8_t)(fp[i] >> 8);
        if (src[PK_FINAL_MODE] > 2u)
            src[PK_FINAL_MODE] = 2u;
        /* ALGO arrives as a family-local knob position and becomes the global
         * engine id here -- the one place the voice silo is enforced, so a
         * p-locked or stale byte can never select an algorithm the hardware
         * would not offer this voice. */
        src[PK_FINAL_ALGO] = pk4_voice_engine((unsigned)voice, src[PK_FINAL_ALGO]);

        /* The synthesis core deliberately retains its recovered firmware
         * argument order: decay,tune,p1,p2,mode,algo. Keep the Octatrack page
         * order independent by remapping only at this adapter boundary. */
        engine_src[0] = src[PK_FINAL_DECAY];
        engine_src[1] = src[PK_FINAL_TUNE];
        engine_src[2] = src[PK_FINAL_PARAM1];
        engine_src[3] = src[PK_FINAL_PARAM2];
        engine_src[4] = src[PK_FINAL_MODE];
        engine_src[5] = src[PK_FINAL_ALGO];
    }

    /* Real hardware may expose the stock trig bit during either half of the
     * split source callback. Latch any observation until the event-boundary
     * half consumes it, instead of requiring the bit to still be live at 16. */
    if ((U8(0x46104d0cu + track) & 16u) != 0u)
        pk_final_trigger_latch[voice] = 1u;
    trig = event_boundary && pk_final_trigger_latch[voice];

    if (!pk4_process_segment(
            &pk_final_engine, (unsigned)voice,
            event_boundary ? engine_src : (const uint8_t *)0,
            event_boundary, trig, PK_FINAL_VELOCITY, PK_FINAL_NOTE,
            pcm, count)) {
        for (unsigned i = 0; i < count; ++i)
            pcm[i] = 0;
    }
    for (unsigned i = 0; i < count; ++i)
        pk_final_frame_pcm[voice][start + i] = pcm[i];

    /* Preserve the exact stock cursor contract.  At unity rate each callback
     * reserves one four-long header plus two longs per source sample.  The
     * fixed-slot commit below is separate from cursor ownership. */
    cursor_longs = 4u + 2u * count;
    for (uint32_t i = 0; i < cursor_longs; ++i)
        cursor[i] = 0u;
    U32(0x80001c80u) = (uint32_t)(uintptr_t)(cursor + cursor_longs);

    if (event_boundary) {
        volatile uint32_t *record = pk_final_fixed_slot(track, ping);
        const unsigned split = start;
        uint32_t pre_longs = pk4_encode_stock_segment(
            encoded, pk_final_frame_pcm[voice], split);
        if (!pre_longs)
            return 0;
        for (uint32_t i = 0; i < pre_longs; ++i)
            record[i] = encoded[i];

        uint32_t post_longs = pk4_encode_stock_segment(
            encoded, pk_final_frame_pcm[voice] + split,
            PK_FINAL_BLOCK_SAMPLES - split);
        if (!post_longs)
            return 0;
        for (uint32_t i = 0; i < post_longs; ++i)
            record[pre_longs + i] = encoded[i];

        /* Two unity-rate callbacks must occupy exactly 40 longs / 160 bytes.
         * Leave the remaining 176 bytes of the stock 336-byte track slot alone. */
        if (pre_longs + post_longs != 40u)
            return 0;

        pk_final_trigger_latch[voice] = 0u;
        pk_final_frame_started[voice] = 0u;
    }

    ++pk_render_calls;
    if (trig)
        ++pk_hits;
    return 0;
}

/* ALGO is a first-class, p-lockable SRC parameter. The old PERKY four-item
 * double-tap/right-arrow engine browser is intentionally disabled so there is
 * only one Algo selection path. Keep these symbols because machine.s and the
 * measured stock hook surface still reference them. */
void pk_engine_select(unsigned algo)
{
    (void)algo;
}

unsigned pk_engine_draw(void)
{
    return 0u;
}

void pk_engine_open(void)
{
}

void pk_engine_left(void)
{
}

void pk_engine_right(unsigned key, unsigned value)
{
    if (U32(0x460e70e0u) && !U32(0x460e739au)
        && U32(0x460e738eu) == PERKY_ROW && pk_selected_source())
        return;
    ((void (*)(unsigned, unsigned))0x4007909cu)(key, value);
}
