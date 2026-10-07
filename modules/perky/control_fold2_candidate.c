/* Fold Drum 2 production-transport candidate.
 *
 * Keep the stable PERKY4 control/browser path in control.c unchanged while
 * qualifying Voice 2 / A1.  This translation unit includes that exact path,
 * renames its renderer entry, then exports a candidate pk_render which adds
 * only zero-based engine 3 to the already-qualified Fold-family control law.
 *
 * Fold Drum 2 is deliberately NOT added to engine_labels/handlers here.  The
 * Octatrack browser therefore remains Fold1 + Simple + Noise/Tone until the
 * original-ARM active-retrigger delta has been regenerated and the DSP trigger
 * seam is qualified.
 */
#define PK_FOLD_CANDIDATE 1
#define pk_render pk_render_fold2_base
#include "control.c"
#undef pk_render

/* Voice 2 / A1 shares the original Fold-family update/smoothing law.  Feed the
 * raw engine byte (3) through pk_fold_prepare so PKSimpleControl.family sees
 * the real family before pk_simple_prepare rewrites the prepared record, then
 * restore the Fold2 catalog index in the outgoing PK/Y1 record.
 */
static void pk_fold2_prepare_candidate(PKSimpleControl *s, uint8_t *p,
                                       unsigned trig)
{
    pk_fold_prepare(s, p, trig);
    p[11] = 3u;
}

/* Candidate copy of the production source-renderer ABI.  The only behavioral
 * delta from control.c is the engine==3 branch below; record packing, reset
 * behavior, trigger sampling and cursor accounting remain identical.
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

            const unsigned bank = U32(BANK), part = U8(PART_IDX) & 3u;
            if (simple_bank != bank || simple_part != part)
            {
                for (unsigned t = 0; t < 8; ++t)
                    simple_controls[t].valid = 0;
                simple_bank = bank;
                simple_part = part;
                for (unsigned t = 0; t < 8; ++t)
                    for (unsigned k = 0; k < 4; ++k)
                    {
                        simple_controls[t].prepared[k] = 0;
                        simple_controls[t].targets[k] = 0;
                    }
            }

            if (p[11] == 2u)
                pk_simple_prepare(&simple_controls[track], p, trig);
            else if (p[11] == 0u)
                pk_fold_prepare(&simple_controls[track], p, trig);
            else if (p[11] == 3u)
                pk_fold2_prepare_candidate(&simple_controls[track], p, trig);
            else
            {
                simple_controls[track].valid = 0;
                for (unsigned k = 0; k < 4; ++k)
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
