#ifndef OCTABAM_PERKY_CF_ACOUSTIC_HATS_H
#define OCTABAM_PERKY_CF_ACOUSTIC_HATS_H

#include <stdint.h>

/* PĒRKONS v1.2.1 Acoustic Hats -- family V4 algorithm 3.
 *
 * The object is 0x10C bytes at wrapper + 0x2A80: the common amplitude envelope
 * at +0x74, a sample player (+0xC4 index, +0xC8 fraction, +0xCC increment,
 * +0xD0 shift, +0xD4 mask, +0xD8 hold reload, +0xDC hold) and a one-pole
 * filter at +0x100 (integer history) / +0x104 (single-precision history bits)
 * / +0x108 (dirty).
 *
 * The renderer is a bit-exact translation of modules/perky/acoustic_hats_compact.py
 * (PCM, the 35-word state, the IEEE754 filter history and the firmware-global
 * held sample, for all nine engine-12 captures).  It is the only engine whose
 * arithmetic is float, computed exactly with cf_softfloat.h.
 *
 * The three hat samples are ordinary firmware assets, selected by PANEL MODE.
 */
#define PK_CF_AH_STATE_BYTES 0x10Cu

#define PK_CF_AH_CLOSED_ADDR  0x080cbef0u
#define PK_CF_AH_OPEN_ADDR    0x080a1bf0u
#define PK_CF_AH_RIDE_ADDR    0x080627ccu
#define PK_CF_AH_CLOSED_BYTES 20202u
#define PK_CF_AH_OPEN_BYTES   172800u
#define PK_CF_AH_RIDE_BYTES   259106u

/* The trigger arms the filter to re-seed from the integer history. */
typedef struct {
    uint32_t address;
    const uint8_t *data;
    uint32_t bytes;
} pk_cf_ah_sample;

typedef struct {
    const uint8_t *envelope1;  /* 2048 little-endian u16 */
    const uint8_t *envelope2;  /* 2048 little-endian u16 */
    pk_cf_ah_sample samples[3];
} pk_cf_ah_tables;

void pk_cf_ah_init(uint8_t *state, uint8_t panel_mode);

/* One authentic control-update pass: the shared smoother's prepared words are
 * already in the object (0x1C/0x20/0x24/0x28); this derives the raw pitch and
 * its increment, the amplitude-envelope rate, the sample-and-hold reload and
 * the selected sample. */
void pk_cf_ah_update(uint8_t *state, uint8_t panel_mode,
                     const uint8_t *pitch_table, const uint8_t *chromatic);

void pk_cf_ah_trigger(uint8_t *state, uint8_t velocity, uint8_t note);

/* `hold` is the firmware-global held sample (0x20007598), shared by every
 * voice; it is carried as a signed 32-bit value. */
int pk_cf_ah_render(uint8_t *state, int16_t *dst, uint32_t n,
                    const pk_cf_ah_tables *tables, int32_t *hold);

#endif
