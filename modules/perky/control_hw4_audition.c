/* First four-voice HW4 hardware-audition control path.
 *
 * Reuse the stable PERKY machine/signature/UI plumbing but pin one translated
 * PĒRKONS family to each admitted Octatrack track:
 *   T1 -> engine 0  Fold Drum 1
 *   T2 -> engine 8  Karplus
 *   T5 -> engine 3  Fold Drum 2
 *   T6 -> engine 10 Noise / Tone
 * T3/T4/T7/T8 refuse PERKY. Karplus controls stay intentionally frozen in the
 * first DSP audition candidate; its exact ARM-derived state/trigger/renderer
 * path is tested before EDGE/TWANG transport is added.
 */
#define PK_FOLD_CANDIDATE 1
#define pk_render pk_render_hw4_base
#define pk_admit_track pk_admit_track_hw4_base
#include "control.c"
#undef pk_render
#undef pk_admit_track

static unsigned pk_hw4_engine(unsigned track)
{
    switch (track)
    {
        case 0u: return 0u;
        case 1u: return 8u;
        case 4u: return 3u;
        case 5u: return 10u;
        default: return 0xffu;
    }
}

unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return pk_hw4_engine(track) != 0xffu;
}

static void pk_hw4_fold2_prepare(PKSimpleControl *s, uint8_t *p,
                                 unsigned trig)
{
    pk_fold_prepare(s, p, trig);
    p[11] = 3u;
}

static void pk_hw4_reset_smoother(PKSimpleControl *s)
{
    s->valid = 0;
    for (unsigned k = 0; k < 4u; ++k)
    {
        s->prepared[k] = 0;
        s->targets[k] = 0;
    }
}

int pk_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    if (track >= 8u || !signed_track(part_base(), track))
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);

    const unsigned forced = pk_hw4_engine(track);
    if (forced == 0xffu)
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))0x40004008u)
            (track, ping, start, end);

    ++pk_render_calls;
    volatile uint32_t *cursor =
        (volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    volatile uint16_t *fp =
        (volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
    uint8_t p[12];

    for (unsigned k = 0; k < 12u; ++k)
        p[k] = k < 6u ? (uint8_t)(fp[k] >> 8)
                      : U8(0x80000810u + 72u * track + 0x20u + k - 6u);
    p[11] = (uint8_t)forced;

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
                        simple_controls[t].prepared[k] =
                        simple_controls[t].targets[k] = 0;
            }

            if (forced == 0u)
                pk_fold_prepare(&simple_controls[track], p, trig);
            else if (forced == 3u)
                pk_hw4_fold2_prepare(&simple_controls[track], p, trig);
            else
            {
                pk_hw4_reset_smoother(&simple_controls[track]);
                p[11] = (uint8_t)forced;
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
