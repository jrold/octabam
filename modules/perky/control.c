/* PERKY source-machine control path.
 *
 * Readable C is the authority; generate.py emits the freestanding ColdFire
 * assembly used by the active module. The hook/descriptor ABI follows the
 * measured ANALOG BD source-machine route. Milestone 0 exposes only Noise /
 * Tone and packs a PERKY control record for probe_glue.asm.
 */
#include <stdint.h>

#define U8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))

#define BANK 0x46c82456u
#define PART_IDX 0x100b14cfu
#define PART_OFF 0x8ed80u
#define PART_STRIDE 0x18b2u
#define SIG 60u
#define DESC_SIZE 0x1cau
#define PERKY_ROW 5u
#define DEFAULT_ENGINE 10u /* zero-based catalog index: Noise / Tone */
#define MODEL_SLOT 11u     /* hidden persisted source parameter */

/* PERKY needs five visible source controls: TUNE, DECAY, P1, P2 and MODE.
 * Keep the engine-family selector in the known persisted parameter arena rather
 * than assuming a fourth byte after the proven three-byte PK/1 signature is
 * unused. Slot 11 is hidden from the page and browser-owned.
 */
const uint8_t pk_defaults[12] = {
    64, /* TUNE  */
    64, /* DECAY */
    64, /* P1 / envelope amount */
    64, /* P2 / noise-tone mix */
    0,
    0,
    0,  /* MODE: waveform 1 */
    0,
    0,
    0,
    0,
    DEFAULT_ENGINE
};

static uint8_t desc[DESC_SIZE] = {0};
uint32_t pk_desc_p = 0;
uint32_t pk_render_calls = 0;
uint32_t pk_hits = 0;

static unsigned source_offset(unsigned track, unsigned slot)
{
    return (slot < 6u ? 0x2au : 0x1dau)
         + 30u * track + 6u + slot % 6u;
}

static unsigned signed_track(const volatile uint8_t *part, unsigned track)
{
    const volatile uint8_t *signature = part + SIG + 30u * track;
    return track < 8u
        && part[0x22u + track] == 1u /* underlying FLEX */
        && signature[0] == 'P'
        && signature[1] == 'K'
        && signature[2] == 1u;
}

unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return track < 8u;
}

static volatile uint8_t *part_base(void)
{
    return (volatile uint8_t *)(uintptr_t)
        (U32(BANK) + PART_OFF + (U8(PART_IDX) & 3u) * PART_STRIDE);
}

unsigned pk_selected_source(void)
{
    const unsigned track = U8(0x100b14ccu);
    return !U8(0x80000015u)
        && track < 8u
        && signed_track(part_base(), track);
}

unsigned pk_type(unsigned type, const volatile uint8_t *ptr)
{
    volatile uint8_t *part = part_base();
    const uintptr_t track = (uintptr_t)ptr - (uintptr_t)(part + 0x22u);
    return type == 1u && track < 8u && signed_track(part, (unsigned)track)
        ? PERKY_ROW
        : type;
}

static void put32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)value;
}

static void text(uint8_t *p, const char *s, unsigned n)
{
    unsigned i = 0;
    for (; i + 1u < n && s[i]; ++i)
        p[i] = (uint8_t)s[i];
    for (; i < n; ++i)
        p[i] = 0;
}

/* One descriptor is enough for milestone-0 Noise / Tone. The hidden family
 * byte already has final storage, so this can grow to one descriptor per
 * family without another Part-layout migration.
 */
static uint32_t page_for(unsigned model)
{
    (void)model;
    if (!pk_desc_p)
    {
        const volatile uint8_t *src = (const volatile uint8_t *)0x400d3176u;
        static const char *const names[12] = {
            "TUNE", "DECAY", "ENV", "MIX", "---", "---",
            "MODE", "---", "---", "---", "---", "---"
        };

        for (unsigned i = 0; i < DESC_SIZE; ++i)
            desc[i] = src[i];

        text(desc + 0x3c, "PRK", 5);
        text(desc + 0x41, "NOISE/TONE", 13);

        for (unsigned i = 0; i < 12u; ++i)
        {
            text(desc + 0x4e + 6u * i, names[i], 6);
            desc[0x96 + i] = pk_defaults[i];
            put32(desc + 0xa2 + 4u * i, 0);

            if (i < 4u)
                put32(desc + 0xd2 + 4u * i, 128);
            else if (i == 6u)
                put32(desc + 0xd2 + 4u * i, 3);
            else
                put32(desc + 0xd2 + 4u * i, 0);

            put32(desc + 0x102 + 4u * i, 0);
            put32(desc + 0x132 + 4u * i, 0);
            put32(desc + 0x162 + 4u * i, 0);
        }

        /* P+0x18a = params 8..11; P+0x18e = params 0..7, one nibble each.
         * Only TUNE/DECAY/P1/P2/MODE are published. MODEL (slot 11) remains
         * persisted but browser-owned and invisible to p-lock/LFO staging.
         */
        put32(desc + 0x1c2, 0x00000000u);
        put32(desc + 0x1c6, 0x01001111u);
        pk_desc_p = (uint32_t)(uintptr_t)(desc + 0x38);
    }
    return (uint32_t)(uintptr_t)(desc + 0x38);
}

uint32_t pk_track_page(const volatile uint8_t *type_ptr)
{
    volatile uint8_t *part = part_base();
    const uintptr_t track = (uintptr_t)type_ptr - (uintptr_t)(part + 0x22u);
    const unsigned model = track < 8u
        ? part[source_offset((unsigned)track, MODEL_SLOT)]
        : DEFAULT_ENGINE;
    return page_for(model);
}

void pk_ui_tick(void)
{
    if (U32(BANK) < 0x40000000u || U32(BANK) >= 0x48000000u)
    {
        U32(0x400d5f38u + PERKY_ROW * 4u) = page_for(DEFAULT_ENGINE);
        return;
    }

    volatile uint8_t *part = part_base();
    U32(0x400d5f38u + PERKY_ROW * 4u) =
        pk_track_page(part + 0x22u + (U8(0x100b14ccu) & 7u));
}

/* Stock validates the underlying FLEX parameter ranges, not our descriptor.
 * Temporarily substitute stock FLEX defaults, then restore all twelve bytes.
 */
extern int pk_stock_validate(void *part);
int pk_validate_part(uint8_t *part)
{
    uint8_t saved[8][12];
    unsigned mask = 0;
    const volatile uint8_t *stock = (const volatile uint8_t *)0x400d320cu;

    for (unsigned track = 0; track < 8u; ++track)
    {
        if (!signed_track(part, track))
            continue;

        mask |= 1u << track;
        for (unsigned k = 0; k < 12u; ++k)
        {
            const unsigned at = source_offset(track, k);
            saved[track][k] = part[at];
            part[at] = stock[k];
        }
    }

    const int result = pk_stock_validate(part);

    for (unsigned track = 0; track < 8u; ++track)
    {
        if (!(mask & (1u << track)))
            continue;
        for (unsigned k = 0; k < 12u; ++k)
            part[source_offset(track, k)] = saved[track][k];
    }
    return result;
}

/* Native source renderer ABI at 0x4000d430/0x4000d518. Milestone 0 does not
 * synthesize here: it reserves exactly FLEX's record span, then replaces the
 * fixed per-track record with PERKY magic + trigger flag + twelve source bytes.
 * probe_glue.asm turns that record into one timing impulse on the DSP.
 */
int pk_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    if (track >= 8u || !signed_track(part_base(), track))
    {
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);
    }

    ++pk_render_calls;
    volatile uint32_t *cursor =
        (volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    volatile uint16_t *fp =
        (volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
    uint8_t p[12];

    for (unsigned k = 0; k < 12u; ++k)
    {
        p[k] = k < 6u
            ? (uint8_t)(fp[k] >> 8)
            : U8(0x80000810u + 72u * track + 0x20u + k - 6u);
    }

    {
        const unsigned count = end > start && end <= 16u ? end - start : 0u;
        for (unsigned i = 0; i < 4u + 2u * count; ++i)
            cursor[i] = 0;

        if (end == 16u)
        {
            volatile uint32_t *record = (volatile uint32_t *)(uintptr_t)
                (0x80001c90u + (ping & 1u) * 0xa80u + 336u * track);
            const unsigned trig = (U8(0x46104d0cu + track) & 16u) != 0u;

            /* Transport splits each CF long high/low into DSP words: w0 sees
             * 'PK', w2 sees 'Y1', w3 sees the trigger flag.
             */
            record[0] = 0x504b0000u;
            record[1] = 0x59310000u | trig;
            record[2] = record[3] = 0;
            for (unsigned k = 0; k < 6u; ++k)
                record[4u + k] = ((uint32_t)p[2u * k] << 16) | p[2u * k + 1u];

            if (trig)
                ++pk_hits;
        }

        U32(0x80001c80u) = (uint32_t)(uintptr_t)(cursor + 4u + 2u * count);
        return 0;
    }
}

/* Engine-family browser. Slot 11 is the persisted browser-owned model byte;
 * slot 6 remains the visible three-way MODE parameter.
 */
static uint32_t engine_bank = 0;
static unsigned engine_part = 0;
static unsigned engine_track = 0;

void pk_engine_select(unsigned model)
{
    const unsigned track = engine_track;
    const unsigned part = engine_part;
    if (model > 11u
        || U32(BANK) != engine_bank
        || (U8(PART_IDX) & 3u) != part
        || U8(0x100b14ccu) != track
        || !pk_selected_source())
        return;

    const unsigned offset = source_offset(track, MODEL_SLOT);
    part_base()[offset] = (uint8_t)model;
    U8(0x100a4eceu + PART_STRIDE * part + offset) = (uint8_t)model;
    U8(0x80000810u + 72u * track + 0x20u + MODEL_SLOT - 6u) = (uint8_t)model;

    U8(engine_bank + 0x95048u) |= (uint8_t)(1u << part);
    U8(0x100b145eu) |= (uint8_t)(1u << part);
    U32(engine_bank + 0x9b332u) = 1;
    U32(0x100f8598u) = 1;
    ((void (*)(void))0x40027e00u)();
    pk_ui_tick();
    ((void (*)(void))0x4004d948u)();
}

static void engine_noise_tone(void) { pk_engine_select(DEFAULT_ENGINE); }
static const char *const engine_labels[] = { "011 NOISE/TONE" };

unsigned pk_engine_draw(void)
{
    const uint32_t window = U32(0x460e5e30u);
    if (!window || U32(0x460e5e2cu) != (uint32_t)(uintptr_t)engine_labels)
        return 0;

    void *surface = (void *)(uintptr_t)(window + 0x24u);
    ((void (*)(void *))0x4003567cu)(surface);
    const int height = (int)U32(window + 0x28u);

    for (unsigned row = 0; row < sizeof(engine_labels) / sizeof(engine_labels[0]); ++row)
    {
        const int y = height - 23 - 7 * (int)row;
        ((void (*)(uint32_t, void *, int, int, int, const char *))0x40012bd8u)
            (0x400ba876u, surface, 5, y, -1, engine_labels[row]);
        if (row == U32(0x460e5e40u))
            ((void (*)(void *, int, int, int, int, int))0x40012254u)
                (surface, 3, y - 1, (int)U32(window + 0x24u) - 5, y + 5, -1);
    }

    U32(0x46c7c72cu) = 1;
    return 1;
}

void pk_engine_open(void)
{
    static void (*const handlers[])(void) = { engine_noise_tone };
    if (!pk_selected_source() || U32(0x460e5e30u))
        return;

    engine_bank = U32(BANK);
    engine_part = U8(PART_IDX) & 3u;
    engine_track = U8(0x100b14ccu);

    ((void (*)(uint32_t, unsigned, unsigned))0x4007ec60u)
        (0x460e5e38u, 6, sizeof(engine_labels) / sizeof(engine_labels[0]));
    ((void (*)(uint32_t, unsigned))0x4007edb0u)(0x460e5e38u, 0);
    U32(0x460e5e28u) = (uint32_t)(uintptr_t)handlers;
    U32(0x460e5e2cu) = (uint32_t)(uintptr_t)engine_labels;
    U32(0x460e5e34u) = 0;

    const uint32_t window =
        ((uint32_t (*)(int, int, int, int, int, uint32_t))0x4005829cu)
            (110, 64, -1, 0, 1, 0x4006d754u);
    U32(0x460e5e30u) = window;
    if (!window)
        return;

    ((void (*)(uint32_t, const char *, unsigned))0x400570b8u)
        (window, "\xab MACHINE:PERKY", 0);
    ((void (*)(uint32_t))0x40031494u)(0x400ce0c4u);
    pk_engine_draw();
}

extern void pk_stock_pool_open(void);
void pk_engine_left(void)
{
    if (!U32(0x460e5e30u)
        || U32(0x460e5e2cu) != (uint32_t)(uintptr_t)engine_labels)
        return;

    ((void (*)(void))0x4006d754u)();
    pk_stock_pool_open();
    ((void (*)(void))0x4007893cu)();
}

void pk_engine_right(unsigned key, unsigned value)
{
    if (U32(0x460e70e0u)
        && !U32(0x460e739au)
        && U32(0x460e738eu) == PERKY_ROW
        && pk_selected_source())
    {
        ((void (*)(void))0x400789e4u)();
        pk_engine_open();
        return;
    }

    ((void (*)(unsigned, unsigned))0x4007909cu)(key, value);
}
