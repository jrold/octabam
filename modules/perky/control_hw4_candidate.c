/* Static four-track HW4 audition control candidate.
 *
 * First physical four-voice audition: pin one authentic engine per PĒRKONS
 * hardware voice so stale Part/browser bytes cannot make the test ambiguous.
 *
 *   OT T1 -> V1 -> engine  0 Fold Drum 1
 *   OT T2 -> V3 -> engine  8 Karplus
 *   OT T5 -> V2 -> engine  3 Fold Drum 2
 *   OT T6 -> V4 -> engine 10 Noise / Tone
 *
 * The normal browser is intentionally not expanded. This file changes the
 * outgoing PK/Y1 engine byte by track; it does not pretend the other eight
 * production paths are ready.
 */
#define PK_FOLD_CANDIDATE 1
#define pk_render pk_render_hw4_base
#define pk_admit_track pk_admit_track_hw4_base
#include "control.c"
#undef pk_admit_track
#undef pk_render

unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return track == 0u || track == 1u || track == 4u || track == 5u;
}

static unsigned pk_hw4_engine(unsigned track)
{
    if (track == 0u) return 0u;   /* V1 Fold Drum 1 */
    if (track == 1u) return 8u;   /* V3 Karplus */
    if (track == 4u) return 3u;   /* V2 Fold Drum 2 */
    if (track == 5u) return 10u;  /* V4 Noise / Tone */
    return 0xffu;
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
    const unsigned mode = p[MODE_SLOT] > 2u ? 2u : p[MODE_SLOT];
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
    /* MODE is the fifth main SRC-page control. Keep the established PK/Y1 ABI
     * for Fold by mirroring it into slot 6 first. Karplus and Noise/Tone then
     * repack slot 6/7 as their fourth full-width control and carry MODE in byte 8.
     */
    p[6] = p[MODE_SLOT];

    /* Engine identity is structural for the first HW4 audition, not a stored
     * user choice. This guards against stale browser/model bytes.
     */
    p[11] = (uint8_t)pk_hw4_engine(track);

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
