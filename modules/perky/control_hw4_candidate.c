/* Four-track Perky Machines control candidate.
 *
 * T1/T2/T5/T6 are independent PERKY tracks. SRC A..F are locked to:
 *   A DECAY / B TUNE / C PARAM1 / D PARAM2 / E MODE / F ALGO.
 * MODE and ALGO are first-page source parameters, so the Octatrack's ordinary
 * p-lock staging can change both on the exact trig being rendered.
 *
 * Keep the older generic control.c canary untouched. Rename the pieces whose
 * five-control/hidden-model contract must be replaced for the final HW4 path.
 */
#define PK_FOLD_CANDIDATE 1
#define pk_defaults pk_defaults_hw4_base
#define page_for page_for_hw4_base
#define pk_track_page pk_track_page_hw4_base
#define pk_ui_tick pk_ui_tick_hw4_base
#define pk_render pk_render_hw4_base
#define pk_admit_track pk_admit_track_hw4_base
#include "control.c"
#undef pk_admit_track
#undef pk_render
#undef pk_ui_tick
#undef pk_track_page
#undef page_for
#undef pk_defaults

#define DECAY_SLOT 0u
#define TUNE_SLOT 1u
#define PARAM1_SLOT 2u
#define PARAM2_SLOT 3u
#define FINAL_MODE_SLOT 4u
#define ALGO_SLOT 5u
#define ALGO_COUNT 12u

/* Machine creation seeds these exact first-page values. */
const uint8_t pk_defaults[12] = {
    64, 64, 64, 64, 0, DEFAULT_ENGINE,
    0, 0, 0, 0, 0, 0
};

/* Patch the cloned stock descriptor after the legacy page initializer runs.
 * Descriptor text fields are five visible characters plus NUL, hence PAR1/PAR2.
 */
static uint32_t pk_hw4_page(void)
{
    static const char *const names[6] = {
        "DECAY", "TUNE", "PAR1", "PAR2", "MODE", "ALGO"
    };
    (void)page_for_hw4_base(DEFAULT_ENGINE);
    text(desc + 0x41, "PERKY MACH", 13);
    for (unsigned i = 0; i < 6u; ++i)
    {
        text(desc + 0x4e + 6u * i, names[i], 6);
        desc[0x96 + i] = pk_defaults[i];
        put32(desc + 0xa2 + 4u * i, 0);
        put32(desc + 0xd2 + 4u * i,
              i < 4u ? 128u : (i == FINAL_MODE_SLOT ? 3u : ALGO_COUNT));
        put32(desc + 0x102 + 4u * i,
              i >= FINAL_MODE_SLOT ? MODE_FORMATTER : 0);
        put32(desc + 0x132 + 4u * i,
              i == FINAL_MODE_SLOT ? MODE_WIDGET : 0);
        put32(desc + 0x162 + 4u * i, 0);
    }
    /* Enable exactly A..F for p-lock/LFO/source staging. */
    put32(desc + 0x1c2, 0x00000000u);
    put32(desc + 0x1c6, 0x00111111u);
    pk_desc_p = (uint32_t)(uintptr_t)(desc + 0x38);
    return pk_desc_p;
}

uint32_t pk_track_page(const volatile uint8_t *type_ptr)
{
    (void)type_ptr;
    return pk_hw4_page();
}

void pk_ui_tick(void)
{
    U32(0x400d5f38u + PERKY_ROW * 4u) = pk_hw4_page();
}

/* Convert final SRC order into the stable engine-preparation ABI:
 * TUNE / DECAY / P1 / P2 / legacy MODE byte / ... / engine id.
 */
static void pk_hw4_src_to_transport(uint8_t *p)
{
    const uint8_t decay = p[DECAY_SLOT];
    const uint8_t tune = p[TUNE_SLOT];
    const uint8_t mode = p[FINAL_MODE_SLOT] > 2u ? 2u : p[FINAL_MODE_SLOT];
    const uint8_t algo = p[ALGO_SLOT] < ALGO_COUNT ? p[ALGO_SLOT] : DEFAULT_ENGINE;
    p[0] = tune;
    p[1] = decay;
    p[6] = mode;
    p[11] = algo;
}

unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return track == 0u || track == 1u || track == 4u || track == 5u;
}

static void pk_hw4_fold2_prepare(PKSimpleControl *s, uint8_t *p,
                                 unsigned trig)
{
    pk_fold_prepare(s, p, trig);
    p[11] = 3u;
}

/* HW4 full-resolution live-control transport for Karplus and Noise/Tone.
 *
 * The Octatrack publishes four 0..127 source controls. Map those onto the
 * PĒRKONS prepared-control domain exactly at both endpoints, matching the
 * already-qualified Simple/Fold transport:
 *
 *     0..126 -> value << 5
 *     127    -> 4095
 *
 * The DSP-side Karplus and authentic Noise/Tone seams consume four full u16
 * prepared values plus physical MODE. Transition smoothing is deliberately not
 * hidden here: this hardware profile is endpoint-exact and immediate, which is
 * also the useful behavior for Octatrack p-locks.
 *
 * PK/Y1 payload after either full-resolution prepare routine:
 *   +08/+09 control 1 prepared u16 (TUNE)
 *   +0a/+0b control 2 prepared u16 (DECAY)
 *   +0c/+0d control 3 prepared u16 (EDGE for Karplus, ENV for Noise/Tone)
 *   +0e/+0f control 4 prepared u16 (TWANG for Karplus, MIX for Noise/Tone)
 *   +10      MODE physical panel index 0/1/2
 *   +11      spare (0)
 *   +12      engine id lives in p[11] / record packing word 9 low byte
 */
static unsigned pk_hw4_target(unsigned value)
{
    value &= 0x7fu;
    return value == 127u ? 4095u : value << 5;
}

static void pk_hw4_full_prepare(uint8_t *p, unsigned engine)
{
    const unsigned mode = p[6] > 2u ? 2u : p[6];
    const unsigned raw[4] = { p[0], p[1], p[2], p[3] };

    for (unsigned i = 0; i < 4u; ++i)
    {
        const unsigned value = pk_hw4_target(raw[i]);
        p[2u * i] = (uint8_t)(value >> 8);
        p[2u * i + 1u] = (uint8_t)value;
    }

    p[8] = (uint8_t)mode;
    p[9] = 0;
    p[10] = 0;
    p[11] = (uint8_t)engine;
}

static void pk_hw4_karplus_prepare(uint8_t *p)
{
    pk_hw4_full_prepare(p, 8u);
}

static void pk_hw4_noise_tone_prepare(uint8_t *p)
{
    pk_hw4_full_prepare(p, 10u);
}

int pk_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    if (track >= 8u || !pk_admit_track(part_base(), track)
        || !signed_track(part_base(), track))
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
    pk_hw4_src_to_transport(p);

    {
        const unsigned count = end > start && end <= 16u ? end - start : 0u;
        for (unsigned i = 0; i < 4u + 2u * count; ++i)
            cursor[i] = 0;

        if (end == 16u)
        {
            volatile uint32_t *record = (volatile uint32_t *)(uintptr_t)
                (0x80001c90u + (ping & 1u) * 0xa80u + 336u * track);
            const unsigned trig = (U8(0x46104d0cu + track) & 16u) != 0u;
            const unsigned bank = U32(BANK), part = U8(PART_IDX) & 3u;

            if (simple_bank != bank || simple_part != part)
            {
                for (unsigned t = 0; t < 8u; ++t)
                    simple_controls[t].valid = 0;
                simple_bank = bank;
                simple_part = part;
                for (unsigned t = 0; t < 8u; ++t)
                    for (unsigned k = 0; k < 4u; ++k)
                    {
                        simple_controls[t].prepared[k] = 0;
                        simple_controls[t].targets[k] = 0;
                    }
            }

            if (p[11] == 0u)
                pk_fold_prepare(&simple_controls[track], p, trig);
            else if (p[11] == 3u)
                pk_hw4_fold2_prepare(&simple_controls[track], p, trig);
            else if (p[11] == 8u)
            {
                simple_controls[track].valid = 0;
                pk_hw4_karplus_prepare(p);
            }
            else if (p[11] == 10u)
            {
                simple_controls[track].valid = 0;
                pk_hw4_noise_tone_prepare(p);
            }
            else
            {
                simple_controls[track].valid = 0;
                for (unsigned k = 0; k < 4u; ++k)
                {
                    simple_controls[track].prepared[k] = 0;
                    simple_controls[track].targets[k] = 0;
                }
            }

            record[0] = 0x504b0000u;
            record[1] = 0x59310000u | trig;
            record[2] = record[3] = 0;
            for (unsigned k = 0; k < 6u; ++k)
                record[4u + k] = ((uint32_t)p[2u * k] << 16)
                               | p[2u * k + 1u];

            if (trig)
                ++pk_hits;
        }

        U32(0x80001c80u) =
            (uint32_t)(uintptr_t)(cursor + 4u + 2u * count);
        return 0;
    }
}
