#ifndef OCTABAM_PERKY_CF_WAVETABLE_H
#define OCTABAM_PERKY_CF_WAVETABLE_H

#include <stdint.h>

/* PĒRKONS v1.2.1 Wavetable Drum -- family V1/V2 algorithm 2.
 *
 * Two oscillators read 4,096-byte (2048 s16) tables and crossfade: the primary
 * oscillator stays on the shared 0x080222A0 table, the secondary walks a
 * 48-table bank while its mix fraction is stepped.  The firmware keeps the
 * object as 0x150 bytes at wrapper + 0x2E8 (V1) / wrapper + 0x31C (V2); the
 * renderer is a bit-exact translation of modules/perky/wavetable_drum_compact.py,
 * which reproduces the captured firmware PCM and full object for all nine
 * engine-2 and all nine engine-5 cases.
 *
 * Unlike Simple/Complex/Fold, the shared 256-entry wave views are NOT enough:
 * the bank tables are 2048 s16 and the oscillator indexes phase bits 9..20.
 */
#define PK_CF_WT_STATE_BYTES 0x150u

/* Bank geometry, measured from the firmware's P1 crossfade walk. */
#define PK_CF_WT_BANK_BASE   0x080327CCu
#define PK_CF_WT_BANK_STRIDE 0x1000u
#define PK_CF_WT_BANK_COUNT  48u
#define PK_CF_WT_TABLE_BYTES 4096u
/* The primary oscillator's fixed table, also required at 4,096 bytes. */
#define PK_CF_WT_BASE_WAVE   0x080222A0u

typedef struct {
    const uint8_t *pitch;      /* 4096 little-endian u16 */
    const uint8_t *envelope1;  /* 2048 little-endian u16 */
    const uint8_t *envelope2;  /* 2048 little-endian u16 */
    const uint8_t *base_wave;  /* PK_CF_WT_TABLE_BYTES at PK_CF_WT_BASE_WAVE */
    const uint8_t *bank;       /* PK_CF_WT_BANK_COUNT contiguous 4096-byte tables */
} pk_cf_wt_tables;

/* Render one block through the original object at its real offsets.  Returns 0
 * when the object asks for a wave address the shipping bank does not carry, so
 * a mis-placed object can never be rendered as Wavetable. */
int pk_cf_wt_render(uint8_t *state, int16_t *dst, uint32_t n,
                    const pk_cf_wt_tables *tables);

/* Resolve one firmware wave address to its 4,096-byte table, or NULL. */
const uint8_t *pk_cf_wt_wave(const pk_cf_wt_tables *tables, uint32_t address);

#endif
