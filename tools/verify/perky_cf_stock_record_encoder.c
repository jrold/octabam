/* Independent ABI oracle: never derive expected bytes through the encoder. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "cf_perky4.h"

int main(void) {
    const int16_t values[] = {-32768, -1, 0, 1, 32767};
    int16_t pcm[16];
    uint32_t guarded[40];
    for (unsigned v = 0; v < 5; ++v) {
        for (unsigned i = 0; i < 16; ++i) pcm[i] = values[(i + v) % 5];
        for (unsigned n = 0; n <= 16; ++n) {
            for (unsigned i = 0; i < 40; ++i) guarded[i] = 0xa55a1234u;
            uint32_t *d = guarded + 1;
            assert(pk4_encode_stock_segment(d, pcm, n) == 4 + 2 * n);
            assert(d[0] == n * 257u && d[1] == 0);
            assert(d[2] == 0x04000000u && d[3] == 0);
            for (unsigned i = 0; i < n; ++i) {
                uint32_t expected = (uint32_t)((int64_t)pcm[i] * 65536);
                assert(d[4 + 2 * i] == expected && d[5 + 2 * i] == expected);
            }
            assert(guarded[0] == 0xa55a1234u);
            for (unsigned i = 5 + 2 * n; i < 40; ++i)
                assert(guarded[i] == 0xa55a1234u);
        }
    }
    for (unsigned i = 0; i < 40; ++i) guarded[i] = 0xa55a1234u;
    assert(pk4_encode_stock_segment(guarded, pcm, 17) == 0);
    assert(pk4_encode_stock_segment(guarded, 0, 16) == 0);
    assert(pk4_encode_stock_segment(0, pcm, 16) == 0);
    for (unsigned i = 0; i < 40; ++i) assert(guarded[i] == 0xa55a1234u);
    puts("stock encoder executable: PASS (85 records, signed endpoints, counts 0..16, invalid arguments, sentinels)");
}
