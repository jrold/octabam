/* Decode a PKR1 stream with the production ColdFire decoder and write the
 * assets out for byte comparison.
 *
 * usage: perky_cf_pcm_rice_check <packed.bin> <out-dir> <count0> <count1> ...
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cf_pcm_rice.h"

int main(int argc, char **argv)
{
    FILE *f;
    long size;
    uint8_t *packed;
    int i;
    if (argc < 4)
        return 2;
    f = fopen(argv[1], "rb");
    if (!f)
        return 3;
    fseek(f, 0, SEEK_END);
    size = ftell(f);
    fseek(f, 0, SEEK_SET);
    packed = (uint8_t *)malloc((size_t)size);
    if (!packed || fread(packed, 1, (size_t)size, f) != (size_t)size) {
        fclose(f);
        return 3;
    }
    fclose(f);
    {
        const int n = argc - 3;
        pk_cf_rice_target *targets = (pk_cf_rice_target *)calloc((size_t)n, sizeof *targets);
        if (!targets)
            return 4;
        for (i = 0; i < n; ++i) {
            const uint32_t count = (uint32_t)strtoul(argv[3 + i], NULL, 0);
            targets[i].count = count;
            targets[i].dst = (int16_t *)calloc(count ? count : 1, sizeof(int16_t));
            if (!targets[i].dst)
                return 4;
        }
        if (!pk_cf_rice_unpack(packed, (uint32_t)size, targets, (unsigned)n)) {
            fprintf(stderr, "pk_cf_rice_unpack failed\n");
            return 5;
        }
        for (i = 0; i < n; ++i) {
            char path[1024];
            snprintf(path, sizeof path, "%s/asset-%02d.bin", argv[2], i);
            {
                FILE *g = fopen(path, "wb");
                if (!g)
                    return 6;
                fwrite(targets[i].dst, sizeof(int16_t),
                       targets[i].count, g);
                fclose(g);
            }
        }
        printf("pcm-rice host decode: PASS (%d assets, %ld stream bytes)\n", n, size);
    }
    return 0;
}
