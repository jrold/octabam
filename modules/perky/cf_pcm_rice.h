#ifndef OCTABAM_PERKY_CF_PCM_RICE_H
#define OCTABAM_PERKY_CF_PCM_RICE_H

#include <stdint.h>

/* Decoder for the PKR1 lossless PCM stream (tools/perky/pcm_rice.py).
 *
 * PerkyMachines' firmware assets include 648 KB of effectively incompressible
 * PCM (the 48-table Wavetable bank and Acoustic Hats' three samples).  The
 * Octatrack's card OS upgrade refuses an ELUP .bin whose payload exceeds 1 MiB
 * (`0x4007f748`: `filesize - 12 > 0x100000` is the error that prints "LENGTH
 * ERROR"), and aPLib gets ~nothing on that PCM, so the payload had to shrink.
 *
 * This is a FLAC-style fixed-predictor + Rice coder: order 2 inside each
 * 4096-sample block, one Rice parameter per block, 16-bit output exactly.  It
 * is lossless and the whole decoder is integer-only and freestanding.
 *
 * Container (little-endian):
 *   "PKR1"                    4 bytes
 *   u32                       asset count
 *   per asset:  u32           sample count
 *               bit stream    sample[0]:16, sample[1]:16, then per block of
 *                             up to 4096 samples: k:8, Rice(residual)
 * Each asset's bit stream is padded to a byte boundary; the bit reader is
 * MSB-first.
 */

#define PK_CF_RICE_MAGIC0 'P'
#define PK_CF_RICE_MAGIC1 'K'
#define PK_CF_RICE_MAGIC2 'R'
#define PK_CF_RICE_MAGIC3 '1'
#define PK_CF_RICE_BLOCK  4096u

typedef struct {
    const uint8_t *data;
    uint32_t bytes;
    uint32_t pos;      /* next byte to pull into the cache */
    uint32_t acc;      /* MSB-first cache, `bits` valid bits in the low end */
    uint32_t bits;
} pk_cf_rice_bits;

typedef struct {
    uint32_t count;    /* samples this target expects */
    int16_t *dst;      /* where to put them (int16, native order) */
} pk_cf_rice_target;

static inline uint32_t pk_cf_rice_u32le(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static inline uint32_t pk_cf_rice_get(pk_cf_rice_bits *b, unsigned n)
{
    uint32_t v;
    while (b->bits < n) {
        const uint32_t byte = b->pos < b->bytes ? b->data[b->pos] : 0u;
        b->acc = (b->acc << 8) | byte;
        ++b->pos;
        b->bits += 8u;
    }
    b->bits -= n;
    v = (b->acc >> b->bits) & ((1u << n) - 1u);
    return v;
}

static inline uint32_t pk_cf_rice_unary(pk_cf_rice_bits *b)
{
    uint32_t q = 0;
    while (pk_cf_rice_get(b, 1u) == 0u)
        ++q;
    return q;
}

static inline int16_t pk_cf_rice_s16(uint32_t u)
{
    return (u & 0x8000u) ? (int16_t)(-1 - (int16_t)(uint16_t)~u) : (int16_t)u;
}

/* Decode one asset.  Returns the byte offset of the next asset, or 0 when the
 * stream is malformed (wrong count / truncated). */
static inline uint32_t pk_cf_rice_asset(const uint8_t *d, uint32_t bytes,
                                       uint32_t off, int16_t *out,
                                       uint32_t count)
{
    pk_cf_rice_bits b;
    uint32_t i = 0;
    if (count == 0 || off > bytes)
        return 0u;
    b.data = d;
    b.bytes = bytes;
    b.pos = off;
    b.acc = 0u;
    b.bits = 0u;
    if (count >= 1u)
        out[i++] = pk_cf_rice_s16(pk_cf_rice_get(&b, 16u));
    if (count >= 2u)
        out[i++] = pk_cf_rice_s16(pk_cf_rice_get(&b, 16u));
    while (i < count) {
        const uint32_t k = pk_cf_rice_get(&b, 8u);
        uint32_t blk = count - i;
        if (blk > PK_CF_RICE_BLOCK)
            blk = PK_CF_RICE_BLOCK;
        if (k > 16u)
            return 0u;                          /* corrupt parameter */
        while (blk--) {
            uint32_t r = pk_cf_rice_unary(&b) << k;
            int32_t pred, delta;
            if (k)
                r |= pk_cf_rice_get(&b, k);
            delta = (int32_t)(r >> 1) ^ -(int32_t)(r & 1u);
            pred = 2 * (int32_t)out[i - 1u] - (int32_t)out[i - 2u];
            out[i] = pk_cf_rice_s16((uint32_t)(pred + delta));
            ++i;
        }
    }
    /* consumed bits = pos*8 - bits; round up to the next byte */
    return ((b.pos * 8u - b.bits) + 7u) / 8u;
}

/* Decode every asset in `packed` into the matching target.  A target whose
 * `count` does not match the stream, or a truncated/corrupt stream, returns 0
 * and leaves the caller's earlier output in place. */
static inline int pk_cf_rice_unpack(const uint8_t *packed, uint32_t bytes,
                                    const pk_cf_rice_target *targets,
                                    unsigned ntargets)
{
    uint32_t count, off = 8u;
    unsigned i;
    if (!packed || bytes < 8u)
        return 0;
    if (packed[0] != PK_CF_RICE_MAGIC0 || packed[1] != PK_CF_RICE_MAGIC1
        || packed[2] != PK_CF_RICE_MAGIC2 || packed[3] != PK_CF_RICE_MAGIC3)
        return 0;
    count = pk_cf_rice_u32le(packed + 4);
    for (i = 0; i < count; ++i) {
        uint32_t n;
        if (off + 4u > bytes)
            return 0;
        n = pk_cf_rice_u32le(packed + off);
        off += 4u;
        if (i < ntargets && targets[i].dst && targets[i].count == n) {
            off = pk_cf_rice_asset(packed, bytes, off, targets[i].dst, n);
        } else {
            return 0;               /* a mismatched count is a caller bug */
        }
        if (off == 0u || off > bytes)
            return 0;
    }
    return off <= bytes ? 1 : 0;
}

#endif
