/* Static four-track HW4 audition control candidate.
 *
 * Reuse the exact Fold2 production-transport candidate, but expose PERKY as a
 * machine only on the four globally pinned Octatrack tracks:
 *
 *   T1 -> PĒRKONS V1
 *   T2 -> PĒRKONS V3
 *   T5 -> PĒRKONS V2
 *   T6 -> PĒRKONS V4
 *
 * The engine browser is intentionally NOT expanded here.  New algorithm rows
 * are only added after their production renderer/control/trigger path is wired.
 */
#define pk_admit_track pk_admit_track_hw4_base
#include "control_fold2_candidate.c"
#undef pk_admit_track

unsigned pk_admit_track(const volatile uint8_t *part, unsigned track)
{
    (void)part;
    return track == 0u || track == 1u || track == 4u || track == 5u;
}
