/* PERKY4: preserve PERKY3R's control smoother, prefix record and admission.
 * Complex adds the recovered V2/A3 laws, not a new update schedule.
 */
#define PK_COMPLEX_CANDIDATE 1
#include "control_three_candidate.c"

static void pk_complex_prepare(PKSimpleControl *s, uint8_t *p, unsigned trig)
{
    pk_simple_prepare(s, p, trig);
    unsigned tune = s->prepared[0] + 768u;
    unsigned values[4] = {
        tune > 4095u ? 4095u : tune,
        simple_rate(simple_time(s->prepared[1]), 50u, 7280u),
        simple_div(0xfffffu, (43244160u - 9552u*s->prepared[2]) >> 12),
        s->prepared[3]
    };
    for (unsigned i = 0; i < 4u; ++i) {
        p[2u*i] = (uint8_t)(values[i] >> 8);
        p[2u*i+1u] = (uint8_t)values[i];
    }
    p[9] = 0; /* Original Complex update has no Simple maximum-decay gate. */
    p[11] = ENGINE_COMPLEX;
}

uint32_t pk_machine_glyph(unsigned track, uint32_t original)
{
    const volatile uint8_t *part = (const volatile uint8_t *)(uintptr_t)
        (U32(BANK) + PART_OFF + (U8(0x80000003u)&3u)*PART_STRIDE);
    if (track < 8u && pk_admit_track(part, track) && signed_track(part, track))
        return U32(0x400a81a4u + 4u*4u); /* stock Pickup P bitmap only */
    return original;
}

/* UI event latch, separate from the stock sample-player/sequencer flags.
 * The producer sets it only after publishing a true post-event PK/Y1 record.
 * One repaint consumes it; LCD refresh can coalesce fast trigs just as stock.
 */
static uint8_t pk_ui_pending[8];
static uint32_t pk_ui_bank[8];
static uint8_t pk_ui_part[8];

static void pk_ui_note_trig(unsigned track)
{
    pk_ui_bank[track] = U32(BANK);
    pk_ui_part[track] = U8(PART_IDX)&3u;
    pk_ui_pending[track] = 1u;
}

unsigned pk_ui_playing(unsigned track, unsigned original)
{
    const unsigned part_index = U8(0x80000003u)&3u;
    const volatile uint8_t *part = (const volatile uint8_t *)(uintptr_t)
        (U32(BANK) + PART_OFF + part_index*PART_STRIDE);
    if (track >= 8u || !pk_admit_track(part,track) || !signed_track(part,track))
        return original;
    unsigned fired = pk_ui_pending[track] && pk_ui_bank[track]==U32(BANK)
                     && pk_ui_part[track]==part_index;
    pk_ui_pending[track] = 0u;
    return fired;
}
