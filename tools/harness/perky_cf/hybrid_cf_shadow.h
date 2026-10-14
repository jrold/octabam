#ifndef OCTABAM_HYBRID_CF_SHADOW_H
#define OCTABAM_HYBRID_CF_SHADOW_H
#include <stdint.h>

/* Compiler-emitted offsets let the host inspect target state without assuming
 * that native and m68k aggregate padding/alignment are identical. */
enum {
    HYB_LAYOUT_MAGIC, HYB_VOICE_SIZE, HYB_WT_OFFSET, HYB_SNARE_OFFSET,
    HYB_BASS_OFFSET, HYB_NT_OFFSET, HYB_CONTROL_OFFSET, HYB_CONTROL_COUNT,
    HYB_CONTROL_SIZE, HYB_TARGETS_OFFSET, HYB_RAW_OFFSET, HYB_MODE_OFFSET,
    HYB_VALID_OFFSET, HYB_RNG_LOW_OFFSET, HYB_RNG_HIGH_OFFSET,
    HYB_WT_BYTES, HYB_SNARE_BYTES, HYB_BASS_BYTES, HYB_NT_BYTES,
    HYB_LAYOUT_WORDS
};
enum { HYB_INIT, HYB_PREPARE, HYB_RENDER };
#ifdef __cplusplus
extern "C" {
#endif
void hybrid_shadow_bind(const uint8_t *const assets_in[13]);
void hybrid_shadow_step(unsigned action, const uint32_t inputs[14]);
unsigned hybrid_shadow_snapshot(uint8_t *destination, unsigned capacity);
#ifdef __cplusplus
}
#endif
#endif
