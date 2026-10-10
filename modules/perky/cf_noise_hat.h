#ifndef OCTABAM_PERKY_CF_NOISE_HAT_H
#define OCTABAM_PERKY_CF_NOISE_HAT_H
#include <stddef.h>
#include <stdint.h>

/* Engine 010 Noise Hat, original ARM object sizes.  The classic wrapper owns a
 * 4,805-sample post-engine delay ring, so its object is 0x2dd8 bytes; panel M3
 * is the separate Pulse Stack limb at 0x160 bytes. */
#define PK_CF_NH_CLASSIC_STATE_BYTES 0x2dd8u
#define PK_CF_NH_PULSE_STATE_BYTES   0x160u
/* The Voice-4 wrapper object: both classic limbs, the 4,805-sample delay ring
 * and the pulse-stack limb that overlaps its tail at +0x2C98. */
#define PK_CF_NH_WRAPPER_BYTES       0x2df8u
#define PK_CF_NH_ENV_BYTES          (2048u*2u)

typedef struct {
    const uint8_t *envelope1;   /* 2048 little-endian u16 */
    const uint8_t *envelope2;   /* 2048 little-endian u16 */
} pk_cf_nh_tables;

typedef struct { uint32_t low,high; } pk_cf_nh_rng;

/* The classic white-noise mode keeps a 16-bit sample/hold that the firmware
 * owns globally, not per voice: [count, held sample]. */
typedef uint16_t pk_cf_nh_hold[2];

/* firmware_mode 0 = metallic, 1 = white noise, 2 = pulse stack. */
int pk_cf_nh_render(uint8_t *state,int16_t *dst,uint32_t n,unsigned firmware_mode,
                    const pk_cf_nh_tables *t,pk_cf_nh_rng *rng,pk_cf_nh_hold hold);
#endif
