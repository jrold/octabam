#ifndef OCTABAM_PERKY_CF_COMPLEX_DRUM_H
#define OCTABAM_PERKY_CF_COMPLEX_DRUM_H

#include <stdint.h>
#include "cf_fold.h"

/* PĒRKONS v1.2.1 Complex Drum -- family V2 algorithm 3.
 *
 * Simple Drum's envelope and oscillator machinery plus a modulation
 * oscillator whose output is added to the main oscillator's frequency.  The
 * firmware object is 0x140 bytes at wrapper + 0x1F8; the renderer and the
 * control laws are both recovered exactly (see modules/perky/CONTROL_RECOVERY.md
 * and tools/harness/perky_cf/capture_control_sweep.cpp).
 */
#define PK_CF_CD_STATE_BYTES 0x140u

#define PK_CF_CD_MAIN_BASE_WAVE 0x080222a0u
#define PK_CF_CD_MOD_WAVE       0x080226a0u
#define PK_CF_CD_WAVE_M1        0x080222a0u
#define PK_CF_CD_WAVE_M2        0x080224a0u
#define PK_CF_CD_WAVE_M3        0x080228a0u
#define PK_CF_CD_OSC_RENDER     0x0802819du

#define PK_CF_CD_AMP_ATTACK     10922u
#define PK_CF_CD_PITCH_ATTACK   21845u

/* The TUNE control is biased: raw pitch = min(prepared_tune + 768, 4095). */
#define PK_CF_CD_TUNE_BIAS      768u

void pk_cf_cd_init(uint8_t *state, uint8_t panel_mode, uint8_t velocity, uint8_t note);
void pk_cf_cd_update(uint8_t *state, uint8_t panel_mode, const uint8_t *pitch_table);
void pk_cf_cd_trigger(uint8_t *state, uint8_t velocity, uint8_t note);
int pk_cf_cd_render(uint8_t *state, int16_t *dst, uint32_t n,
                    const pk_cf_fold_tables *tables);

#endif
