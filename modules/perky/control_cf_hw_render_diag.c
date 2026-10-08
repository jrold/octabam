/* Hardware-only Perky renderer diagnostic.
 *
 * This file is intentionally NOT the production/PCM-qualified control source.
 * The diagnostic builder swaps only the generated pkcontrol unit to this file
 * after the complete production qualification suite has passed.
 *
 * Diagnostic behavior on Octatrack T1 (zero-based track 0):
 *   - bypass signed_track();
 *   - ignore the stock trig flag;
 *   - ignore staged SRC controls;
 *   - use fixed known-good Fold1 controls;
 *   - auto-trigger periodically.
 *
 * All other eligible tracks retain the production signature/trig path. Stock
 * FLEX tracks outside the four PERKY-capable tracks still fall through normally.
 */

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
#define PK_FINAL_ALGO_COUNT 4u
#define PK_FINAL_NOTE 45u
#define PK_FINAL_VELOCITY 255u
#define PK_FINAL_BLOCK_SAMPLES 16u
#define PK_FINAL_HW_DIAG_TRACK 0u
#define PK_FINAL_HW_DIAG_PERIOD 2048u

extern const uint8_t pk_asset_pitch[];
extern const uint8_t pk_asset_chromatic[];
extern const uint8_t pk_asset_envelope1[];
extern const uint8_t pk_asset_envelope2[];
extern const uint8_t pk_asset_m1_wave[];
extern const uint8_t pk_asset_wave0[];
extern const uint8_t pk_asset_wave1[];
extern const uint8_t pk_asset_wave2[];
extern const uint8_t pk_asset_wave3[];

const uint8_t pk_defaults[12] = {
    64, 64, 0, 64, 64, 0,
    0, 0, 0, 0, 0, 0
};

static pk4_engine pk_final_engine;
static uint32_t pk_final_bank;
static uint8_t pk_final_part;
static uint8_t pk_final_trigger_latch[4];
static uint32_t pk_final_diag_counter[4];
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
    .m1_wave_address = 0x080310e0u,
};

static int pk_final_voice_index(unsigned track)
{
    switch (track) {
    case 0u: return 0;
    case 1u: return 1;
    case 4u: return 2;
    case 5u: return 3;
    default: return -1;
    }
}

static void pk_final_reset_runtime_if_needed(void)
{
    const uint32_t bank = U32(BANK);
    const uint8_t part = U8(PART_IDX) & 3u;
    if (pk_final_runtime_cookie != PK_FINAL_RUNTIME_READY
        || pk_final_bank != bank || pk_final_part != part) {
        pk4_init(&pk_final_engine, &pk_final_assets);
        for (unsigned i = 0; i < 4u; ++i) {
            pk_final_trigger_latch[i] = 0u;
            pk_final_diag_counter[i] = 0u;
        }
        pk_final_bank = bank;
        pk_final_part = part;
        pk_final_runtime_cookie = PK_FINAL_RUNTIME_READY;
    }
}

static uint32_t pk_final_page(void)
{
    static const char *const names[6] = {
        "TUNE", "DECAY", "ALGO", "PRM1", "PRM2", "MODE"
    };
    (void)page_for_cf_legacy(DEFAULT_ENGINE);
    text(desc + 0x41, "PERKY MACH", 13);
    for (unsigned i = 0; i < 6u; ++i) {
        uint32_t maximum = 128u;
        uint32_t formatter = 0u;
        uint32_t widget = 0u;
        if (i == PK_FINAL_ALGO) {
            maximum = PK_FINAL_ALGO_COUNT;
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
    (void)type_ptr;
    return pk_final_page();
}

void pk_ui_tick(void)
{
    U32(0x400d5f38u + PERKY_ROW * 4u) = pk_final_page();
}

int pk_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    volatile uint32_t *cursor;
    volatile uint16_t *fp;
    uint8_t src[6];
    uint8_t engine_src[6];
    int16_t pcm[PK_FINAL_BLOCK_SAMPLES];
    uint32_t record[4u + 2u * PK_FINAL_BLOCK_SAMPLES];
    uint32_t longs;
    unsigned count;
    int voice;
    int trig;
    int event_boundary;
    int diag_track;

    (void)ping;
    voice = pk_final_voice_index(track);
    diag_track = track == PK_FINAL_HW_DIAG_TRACK;

    if (track >= 8u || voice < 0
        || (!diag_track && !signed_track(part_base(), track)))
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);

    if (end < start || end > PK_FINAL_BLOCK_SAMPLES)
        return 0;
    count = end - start;
    cursor = (volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    event_boundary = end == PK_FINAL_BLOCK_SAMPLES;

    if (event_boundary) {
        if (diag_track) {
            /* Recovered core ABI: decay,tune,p1,p2,mode,algo. */
            engine_src[0] = 64u;
            engine_src[1] = 64u;
            engine_src[2] = 64u;
            engine_src[3] = 64u;
            engine_src[4] = 0u;
            engine_src[5] = 0u;
        } else {
            fp = (volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
            for (unsigned i = 0; i < 6u; ++i)
                src[i] = (uint8_t)(fp[i] >> 8);
            if (src[PK_FINAL_MODE] > 2u)
                src[PK_FINAL_MODE] = 2u;
            if (src[PK_FINAL_ALGO] >= PK_FINAL_ALGO_COUNT)
                src[PK_FINAL_ALGO] = 0u;
            engine_src[0] = src[PK_FINAL_DECAY];
            engine_src[1] = src[PK_FINAL_TUNE];
            engine_src[2] = src[PK_FINAL_PARAM1];
            engine_src[3] = src[PK_FINAL_PARAM2];
            engine_src[4] = src[PK_FINAL_MODE];
            engine_src[5] = src[PK_FINAL_ALGO];
        }
    }

    pk_final_reset_runtime_if_needed();

    if (diag_track) {
        trig = event_boundary
            && ((pk_final_diag_counter[voice]++ & (PK_FINAL_HW_DIAG_PERIOD - 1u)) == 0u);
    } else {
        if ((U8(0x46104d0cu + track) & 16u) != 0u)
            pk_final_trigger_latch[voice] = 1u;
        trig = event_boundary && pk_final_trigger_latch[voice];
    }

    if (!pk4_process_segment(
            &pk_final_engine, (unsigned)voice,
            event_boundary ? engine_src : (const uint8_t *)0,
            event_boundary, trig, PK_FINAL_VELOCITY, PK_FINAL_NOTE,
            pcm, count)) {
        for (unsigned i = 0; i < count; ++i)
            pcm[i] = 0;
    }
    if (event_boundary && !diag_track)
        pk_final_trigger_latch[voice] = 0u;

    longs = pk4_encode_stock_segment(record, pcm, count);
    if (!longs)
        return 0;
    for (uint32_t i = 0; i < longs; ++i)
        cursor[i] = record[i];
    U32(0x80001c80u) = (uint32_t)(uintptr_t)(cursor + longs);

    ++pk_render_calls;
    if (trig)
        ++pk_hits;
    return 0;
}

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
