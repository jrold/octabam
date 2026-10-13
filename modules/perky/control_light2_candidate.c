/* Two-voice light-engine PERKY control: T1 on one DSP core, T5 on the other.
 *
 * Derived from control_hw4_candidate.c (the six-control hw4 implementation, which
 * is the donor for this UI), reduced to the shipping target:
 *
 *   - exactly TWO PERKY voices: track 1 and track 5, one per DSP core
 *     (payload B serves tracks 1-4, payload A serves 5-8, so T1 and T5 are on
 *     different cores by construction -- no second voice on either core);
 *   - T2/T3/T4 and T6/T7/T8 stay ordinary stock tracks;
 *   - one algorithm runs at a time per voice;
 *   - the light engine pool, with Resonant Bass/Snare retired entirely.
 *
 * SRC page 1, in this exact order, all six staged for p-lock/LFO by the
 * descriptor's 0x1c6 mask:
 *
 *   A TUNE / B DECAY / C ALGO / D PARAM1 / E PARAM2 / F MODE
 *
 * The target ABI is unchanged from hw4: p[0]=tune, p[1]=decay, p[6]=mode,
 * p[11]=engine id. ALGO selects the engine, and because ALGO is a first-page
 * staged parameter, a trig p-lock on ALGO changes the engine for that trig
 * alone and the track's base ALGO resumes on the next unlocked trig -- that is
 * the ordinary Octatrack parameter path, not a special case.
 *
 * ALGO is INDIRECT: the four light engines do not occupy ids 0..3 (Fold Drum 1
 * is 0, Simple Drum is 2, Fold Drum 2 is 3, Noise/Tone is 10), so a direct
 * `p[11] = algo` would select the wrong engine for three of the four values.
 * ALGO_ENGINE below is the one place that mapping lives.
 */
#define PK_FOLD_CANDIDATE 1
#define pk_defaults pk_defaults_light2_base
#define page_for page_for_light2_base
#define pk_track_page pk_track_page_light2_base
#define pk_ui_tick pk_ui_tick_light2_base
#define pk_render pk_render_light2_base
#define pk_admit_track pk_admit_track_light2_base
#include "control.c"
#undef pk_admit_track
#undef pk_render
#undef pk_ui_tick
#undef pk_track_page
#undef page_for
#undef pk_defaults

/* SRC page 1, left to right: A TUNE / B DECAY / C ALGO / D PARAM1 / E PARAM2 /
 * F MODE. These are the Part's page-slot indices, and they are NOT the engine
 * ABI's indices -- pk_light2_src_to_transport does that remap explicitly. */
#define TUNE_SLOT 0u
#define DECAY_SLOT 1u
#define ALGO_SLOT 2u
#define PARAM1_SLOT 3u
#define PARAM2_SLOT 4u
#define MODE_SLOT_FINAL 5u

/* The shipping light engines, in ALGO order. Wavetable is deliberately absent:
 * its asset bank needs a separate shared-memory project and is deferred. */
#define ENGINE_FOLD1 0u
#define ENGINE_SIMPLE 2u
#define ENGINE_FOLD2 3u
#define ENGINE_NOISETONE 10u
#define ALGO_COUNT 4u

/* ALGO value -> engine id. The only place the indirection lives: the engines do
 * NOT occupy ids 0..3, so a direct p[11] = algo would select the wrong one. */
static const uint8_t ALGO_ENGINE[ALGO_COUNT] = {
    ENGINE_FOLD1, ENGINE_FOLD2, ENGINE_SIMPLE, ENGINE_NOISETONE
};

/* The one PERKY track on each core. Track numbering here is zero-based:
 * 0 = T1 (core B), 4 = T5 (core A). Nothing else is admitted. */
#define PERKY_TRACK_LOW 0u
#define PERKY_TRACK_HIGH 4u

/* Machine creation seeds these exact first-page values. */
const uint8_t pk_defaults[12] = {
    64,              /* A TUNE  */
    64,              /* B DECAY */
    ENGINE_FOLD1,    /* C ALGO  -- an INDEX into ALGO_ENGINE; 0 = Fold Drum 1 */
    64,              /* D PARAM1 */
    64,              /* E PARAM2 */
    0,               /* F MODE  */
    0, 0, 0, 0, 0, 0
};

/* Patch the cloned stock descriptor after the legacy page initializer runs.
 * Descriptor text fields are five visible characters plus NUL, hence PAR1/PAR2.
 */
static uint32_t pk_light2_page(void)
{
    static const char *const names[6] = {
        "TUNE", "DECAY", "ALGO", "PAR1", "PAR2", "MODE"
    };
    (void)page_for_light2_base(ENGINE_FOLD1);
    text(desc + 0x41, "PERKY MACH", 13);
    for (unsigned i = 0; i < 6u; ++i)
    {
        text(desc + 0x4e + 6u * i, names[i], 6);
        desc[0x96 + i] = pk_defaults[i];
        put32(desc + 0xa2 + 4u * i, 0);
        /* The two select slots are ALGO (C) and MODE (F); the other four are
         * full-range knobs. ALGO is bounded by the engine count, not by the 12
         * the hw4 donor used, so an ALGO outside the pool is not selectable. */
        put32(desc + 0xd2 + 4u * i,
              i == ALGO_SLOT ? ALGO_COUNT
                             : (i == MODE_SLOT_FINAL ? 3u : 128u));
        put32(desc + 0x102 + 4u * i,
              (i == ALGO_SLOT || i == MODE_SLOT_FINAL) ? MODE_FORMATTER : 0);
        put32(desc + 0x132 + 4u * i,
              i == MODE_SLOT_FINAL ? MODE_WIDGET : 0);
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
    return pk_light2_page();
}

void pk_ui_tick(void)
{
    U32(0x400d5f38u + PERKY_ROW * 4u) = pk_light2_page();
}

/* Map the final SRC order onto the stable engine-preparation ABI:
 *   p[0] TUNE, p[1] DECAY, p[6] MODE, p[11] engine id.
 * MODE is clamped to its 3 positions; ALGO is clamped to the pool and then
 * resolved through ALGO_ENGINE, so an out-of-range stored value can never
 * select an engine that is not in the shipping pool.
 */
static void pk_light2_src_to_transport(uint8_t *p)
{
    /* Read every source slot BEFORE writing any ABI slot: the page order and
     * the ABI order overlap, so an in-place copy would clobber itself. */
    const uint8_t tune = p[TUNE_SLOT];
    const uint8_t decay = p[DECAY_SLOT];
    const uint8_t p1 = p[PARAM1_SLOT];
    const uint8_t p2 = p[PARAM2_SLOT];
    const uint8_t mode = p[MODE_SLOT_FINAL] > 2u ? 2u : p[MODE_SLOT_FINAL];
    const unsigned algo = p[ALGO_SLOT] < ALGO_COUNT ? p[ALGO_SLOT] : 0u;

    /* The engine ABI is the long-standing one: p[0..3] are the four smoothed
     * controls in the order the engine laws expect (TUNE, DECAY, P1, P2), p[6]
     * is MODE and p[11] the engine id. The page order is a PRODUCT choice and
     * is free to differ -- which it now does. Under the previous page order
     * (DECAY,TUNE,PAR1,PAR2,MODE,ALGO) p[2]/p[3] happened to be PAR1/PAR2
     * already, so leaving them alone worked by coincidence; with ALGO at slot 2
     * that coincidence is gone, and NOT remapping here would silently make
     * PAR1 drive ALGO and PAR2 drive PAR1. */
    p[0] = tune;
    p[1] = decay;
    p[2] = p1;
    p[3] = p2;
    p[6] = mode;
    p[11] = ALGO_ENGINE[algo];
}

/* Exactly one PERKY track per core, and only those two. */
unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return track == PERKY_TRACK_LOW || track == PERKY_TRACK_HIGH;
}

/* Fold Drum 2 shares Fold Drum 1's authentic control law -- the reference's rate
 * expressions are literally identical -- so it reuses pk_fold_prepare and is
 * distinguished only by the engine byte. */
static void pk_light2_fold2_prepare(PKSimpleControl *s, uint8_t *p,
                                    unsigned trig)
{
    pk_fold_prepare(s, p, trig);
    p[11] = ENGINE_FOLD2;
}

/* Full-resolution live-control transport for Noise/Tone, matching the
 * already-qualified Simple/Fold transport exactly at both endpoints:
 *     0..126 -> value << 5
 *     127    -> 4095
 */
static unsigned pk_light2_target(unsigned value)
{
    value &= 0x7fu;
    return value == 127u ? 4095u : value << 5;
}

static void pk_light2_full_prepare(uint8_t *p, unsigned engine)
{
    const unsigned mode = p[6] > 2u ? 2u : p[6];
    const unsigned raw[4] = { p[0], p[1], p[2], p[3] };

    for (unsigned i = 0; i < 4u; ++i)
    {
        const unsigned value = pk_light2_target(raw[i]);
        p[2u * i] = (uint8_t)(value >> 8);
        p[2u * i + 1u] = (uint8_t)value;
    }

    p[8] = (uint8_t)mode;
    p[9] = 0;
    p[10] = 0;
    p[11] = (uint8_t)engine;
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
    pk_light2_src_to_transport(p);

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

            if (p[11] == ENGINE_FOLD1)
                pk_fold_prepare(&simple_controls[track], p, trig);
            else if (p[11] == ENGINE_FOLD2)
                pk_light2_fold2_prepare(&simple_controls[track], p, trig);
            else if (p[11] == ENGINE_SIMPLE)
                pk_simple_prepare(&simple_controls[track], p, trig);
            else if (p[11] == ENGINE_NOISETONE)
            {
                simple_controls[track].valid = 0;
                pk_light2_full_prepare(p, ENGINE_NOISETONE);
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
