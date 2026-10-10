#ifndef OCTABAM_PERKY_CF_SIMPLE_DRUM_H
#define OCTABAM_PERKY_CF_SIMPLE_DRUM_H

#include <stdint.h>
#include "cf_fold.h"

/* PĒRKONS v1.2.1 Simple Drum -- family V1 algorithm 3.
 *
 * One oscillator, the same common envelope pair the other engines use, and the
 * firmware's 0x120-byte ARM object at its own offsets.  Panel controls are
 * TUNE / DECAY / ENV / MIX: ENV drives the pitch envelope's decay and MIX its
 * amount, while DECAY drives the amplitude envelope.
 *
 * The object was located in the whole-firmware captures by rendering every
 * 0x120-byte window of the wrapper snapshot through the already-qualified
 * compact model and keeping the one that reproduced the firmware's own PCM:
 * wrapper + 0x1F8, exact for all three modes and all three control corners,
 * first block, continuation, final state and active retrigger.
 */
#define PK_CF_SD_STATE_BYTES 0x120u

/* The oscillator starts on the family's base wave and swaps to the selected
 * one when its phase wraps.  These are the firmware's own wave addresses; the
 * shipping asset view already carries all four tables. */
#define PK_CF_SD_OSC_BASE_WAVE 0x080228a0u
#define PK_CF_SD_WAVE_M1       0x080222a0u
#define PK_CF_SD_WAVE_M2       0x080226a0u
#define PK_CF_SD_WAVE_M3       0x080228a0u
/* Guard byte: the firmware's simple-oscillator render entry, the same one Fold
 * Drum uses, so a wrong object can never be rendered as Simple Drum. */
#define PK_CF_SD_OSC_RENDER    0x0802819du

/* Constant envelope configuration from the captured init state. */
#define PK_CF_SD_AMP_ATTACK    10922u
#define PK_CF_SD_PITCH_ATTACK  21845u

void pk_cf_sd_init(uint8_t *state, uint8_t panel_mode, uint8_t velocity, uint8_t note);

/* One authentic control-update pass: DECAY -> amplitude-envelope rate,
 * ENV -> pitch-envelope rate, TUNE -> the 12-bit raw pitch, MIX -> the
 * pitch-envelope amount.  The four smoothed control words are read from the
 * object's own prepared slots at 0x1C/0x20/0x24/0x28 (tune, decay, env, mix),
 * which is exactly where the firmware keeps them. */
void pk_cf_sd_update(uint8_t *state, uint8_t panel_mode, const uint8_t *pitch_table);

void pk_cf_sd_trigger(uint8_t *state, uint8_t velocity, uint8_t note);

int pk_cf_sd_render(uint8_t *state, int16_t *dst, uint32_t n,
                    const pk_cf_fold_tables *tables);

#endif
