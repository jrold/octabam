#ifndef OCTABAM_PERKY_CF_SLAP_H
#define OCTABAM_PERKY_CF_SLAP_H

#include <stdint.h>
#include "cf_fold.h"

/* PĒRKONS v1.2.1 Slap -- family V3 algorithm 2.
 *
 * One noise source, two filter stages per sample, a five-tap feedback delay
 * ring and one amplitude envelope, on the firmware's own 0x2670-byte object at
 * wrapper + 0xC4 (the ring is 0x12C5 words at object +0xE0).
 *
 * The renderer mirrors modules/perky/slap_compact.py, which reproduces the
 * firmware's captured PCM, the full object AND the RNG.  The control path is
 * recovered in modules/perky/CONTROL_RECOVERY.md: seven closed-form laws plus
 * the filter-coefficient curve, which is not a closed form and is pinned as
 * captured data over the complete 12-bit domain in slap_coeff_table.py.
 */
#define PK_CF_SLAP_STATE_BYTES 0x2670u
#define PK_CF_SLAP_RING_LEN    0x12c5u
#define PK_CF_SLAP_RING_OFF    0x00e0u

/* Panel MODE sets the delay counter's target; recovered from the captures as
 * 336 * (mode + 1). */
#define PK_CF_SLAP_MODE_STRIDE 336u
/* Constant amplitude-envelope attack rate from the captured init state. */
#define PK_CF_SLAP_AMP_ATTACK  10922u
/* TUNE is biased into the 12-bit raw pitch, exactly as Complex Drum's is. */
#define PK_CF_SLAP_TUNE_BIAS   768u

void pk_cf_slap_init(uint8_t *state, uint8_t panel_mode, uint8_t velocity, uint8_t note);
void pk_cf_slap_update(uint8_t *state, uint8_t panel_mode, const uint8_t *pitch_table);
void pk_cf_slap_trigger(uint8_t *state, uint8_t velocity, uint8_t note);
int pk_cf_slap_render(uint8_t *state, int16_t *dst, uint32_t n,
                      const pk_cf_fold_tables *tables, pk_cf_fold_rng *rng);

#endif
