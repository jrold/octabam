/* Firmware-free regression for the PERKY PKR1 cold-boot decoder.
 * Build locally: cc -std=c99 -O2 -Wall -Wextra -Werror \
 *   tools/verify/test_perky_cf_rice_boot.c -o /tmp/perky-rice-boot && /tmp/perky-rice-boot
 * This suite does not certify the MKII loader or fix a hardware boot race. */
#include "../../modules/perky/cf_pcm_rice.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Also compile against the pre-patch header to prove the regression fails. */
#ifndef PK_CF_RICE_MAX_RESIDUAL
#define PK_CF_RICE_MAX_RESIDUAL 262140u
#endif

#define CAPACITY (1024u * 1024u)
#define LIMIT 100000u

static uint8_t packed[CAPACITY];
static size_t bitpos;
static unsigned long checks;
static int valid_only;
static uint32_t rnd_state = 0x13572468u;

static void require(int yes, const char *message)
{
    if (!yes) { fprintf(stderr, "FAIL: %s (case %lu)\n", message, checks); exit(1); }
}

static uint32_t random32(void)
{
    rnd_state = rnd_state * 1664525u + 1013904223u;
    return rnd_state;
}

static void emit(unsigned value, unsigned bits)
{
    while (bits--) {
        size_t byte = bitpos >> 3;
        require(byte < CAPACITY, "encoder capacity");
        if ((value >> bits) & 1u)
            packed[byte] |= (uint8_t)(0x80u >> (bitpos & 7u));
        ++bitpos;
    }
}

static void pad(void)
{
    bitpos = (bitpos + 7u) & ~(size_t)7u;
}

static void begin(unsigned assets)
{
    memset(packed, 0, sizeof(packed)); bitpos = 0;
    emit('P', 8); emit('K', 8); emit('R', 8); emit('1', 8);
    emit(assets & 255u, 8); emit((assets >> 8) & 255u, 8);
    emit(0, 16);
}

static void emit_asset(const int16_t *samples, unsigned count, unsigned k)
{
    require(count >= 2u && k <= 16u, "fixture parameters");
    for (unsigned i = 0; i != 4u; ++i) emit((count >> (i * 8u)) & 255u, 8);
    emit((uint16_t)samples[0], 16);
    emit((uint16_t)samples[1], 16);
    for (unsigned start = 2u; start < count;) {
        unsigned end = count - start > PK_CF_RICE_BLOCK ? start + PK_CF_RICE_BLOCK : count;
        emit(k, 8);
        for (unsigned i = start; i < end; ++i) {
            int32_t pred = 2 * (int32_t)samples[i - 1] - samples[i - 2];
            int32_t delta = (int32_t)samples[i] - pred;
            uint32_t code = delta < 0 ? (uint32_t)(-2 * delta - 1) : (uint32_t)(2 * delta);
            require(code <= PK_CF_RICE_MAX_RESIDUAL, "residual within 16-bit range");
            for (uint32_t j = code >> k; j; --j) emit(0, 1);
            emit(1, 1);
            if (k) emit(code & ((1u << k) - 1u), k);
        }
        start = end;
    }
    pad();
}

static size_t length(void) { return bitpos / 8u; }

/* Independently verify little-endian PCM and guard words. Invalid/corrupt
 * streams may partially modify sample data, but must never modify guards. */
static void check_decode(size_t bytes, const int16_t *s0, unsigned n0,
                         const int16_t *s1, unsigned n1, int expect)
{
    int16_t *out0 = calloc((size_t)n0 + 2u, sizeof(int16_t));
    int16_t *out1 = calloc((size_t)n1 + 2u, sizeof(int16_t));
    pk_cf_rice_target targets[2];
    int ok;
    require(out0 && out1, "allocate outputs");
    out0[0] = (int16_t)0x41b1; out0[n0 + 1] = (int16_t)0x7543;
    out1[0] = (int16_t)0x6197; out1[n1 + 1] = (int16_t)0x2abc;
    targets[0].count = n0; targets[0].dst = out0 + 1;
    targets[1].count = n1; targets[1].dst = out1 + 1;
    ok = pk_cf_rice_unpack_le(packed, (uint32_t)bytes, targets, 2u);
    ++checks;
    if (expect >= 0) require(ok == expect, "decode return status");
    require(out0[0] == (int16_t)0x41b1 && out0[n0 + 1] == (int16_t)0x7543,
            "first object guard intact");
    require(out1[0] == (int16_t)0x6197 && out1[n1 + 1] == (int16_t)0x2abc,
            "second object guard intact");
    if (ok && expect == 1) {
        for (unsigned asset = 0; asset != 2u; ++asset) {
            const int16_t *src = asset ? s1 : s0;
            const int16_t *dst = (asset ? out1 : out0) + 1;
            unsigned n = asset ? n1 : n0;
            const uint8_t *pcm = (const uint8_t *)(const void *)dst;
            for (unsigned i = 0; i < n; ++i) {
                uint16_t v = (uint16_t)src[i];
                require(pcm[2u * i] == (uint8_t)v &&
                        pcm[2u * i + 1u] == (uint8_t)(v >> 8),
                        "exact little-endian PCM");
            }
        }
    }
    free(out1); free(out0);
}

static void valid_case(unsigned n0, unsigned n1, unsigned k)
{
    int16_t *s0 = malloc(n0 * sizeof(*s0)), *s1 = malloc(n1 * sizeof(*s1));
    require(s0 && s1 && n0 <= LIMIT && n1 <= LIMIT, "valid sample sizes");
    for (unsigned i = 0; i < n0; ++i) s0[i] = (int16_t)(uint16_t)random32();
    for (unsigned i = 0; i < n1; ++i) s1[i] = (int16_t)(uint16_t)random32();
    begin(2);
    emit_asset(s0, n0, k);
    emit_asset(s1, n1, k);
    check_decode(length(), s0, n0, s1, n1, 1);
    if (valid_only) { free(s0); free(s1); return; }

    /* Every possible length of the small fixture must fail, including an
     * incomplete unary run that previously read infinite fabricated zeros. */
    size_t whole = length();
    if (whole <= 1024) {
        for (size_t cut = 0; cut < whole; ++cut)
            check_decode(cut, s0, n0, s1, n1, 0);
    } else {
        for (size_t cut = 0; cut < 120; ++cut) {
            check_decode(cut, s0, n0, s1, n1, 0);
            check_decode(whole - 1u - cut, s0, n0, s1, n1, 0);
        }
    }
    /* Fixed-length corruption where a valid code can decode to different
     * samples is allowed, but it must always terminate and stay in-bounds. */
    for (unsigned i = 0; i < 600u; ++i) {
        size_t at = random32() % whole;
        uint8_t prev = packed[at];
        packed[at] ^= (uint8_t)(1u << (random32() & 7u));
        check_decode(whole, s0, n0, s1, n1, -1);
        packed[at] = prev;
    }
    /* The residual k field is at byte 16 of the first asset. */
    if (n0 >= 3u) {
        uint8_t old = packed[16];
        packed[16] = 255u;
        check_decode(whole, s0, n0, s1, n1, 0);
        packed[16] = old;
    }
    free(s0); free(s1);
}

static void malformed_rice(void)
{
    const int16_t seeds[] = {0, 0, 0};
    const int16_t dummy[] = {0, 0};
    size_t used;
    begin(2);
    emit(3u, 8); emit(0, 24); /* count, little-endian */
    emit(0, 16); emit(0, 16); emit(0, 8); /* k = 0 */
    used = length();
    memset(packed + used, 0, 64);
    check_decode(used + 64, seeds, 3, dummy, 2, 0); /* no unary 1 */

    begin(2);
    emit(3u, 8); emit(0, 24); emit(0, 16); emit(0, 16);
    emit(16, 8);
    for (unsigned j = 0; j < 4; ++j) emit(0, 1);
    emit(1, 1); emit(0, 16);
    pad();
    check_decode(length(), seeds, 3, dummy, 2, 0); /* q=4,k=16 invalid */

    begin(2);
    emit(3u, 8); emit(0, 24); emit(0, 16); emit(0, 16);
    emit(0, 8);
    for (unsigned j = 0; j < PK_CF_RICE_MAX_RESIDUAL + 1u; ++j) emit(0, 1);
    emit(1, 1); pad();
    check_decode(length(), seeds, 3, dummy, 2, 0); /* bounded overlarge unary */
}

int main(int argc, char **argv)
{
    valid_only = argc > 1 && strcmp(argv[1], "--valid-only") == 0;
    valid_case(2, 2, 16);
    valid_case(3, 3, 16);
    valid_case(31, 17, 16);
    valid_case(100, 111, 14);
    valid_case(4099, 13, 16); /* crosses encoder block boundary */
    valid_case(2048, 98304, 16); /* exact hybrid asset counts */
    if (!valid_only) malformed_rice();
    printf("PASS: %lu decoder cases including 2048 + 98304 samples%s\n",
           checks, valid_only ? "" : ", EOF and unary failures");
    return 0;
}
