// Compare the ColdFire Resonant Drums renderer against the real firmware's own
// captured PCM/state/RNG for engine 7, all three control corners.
//
//   engine-7-mode-1 = panel M1 = Resonant Snare object at wrapper + 0x2734
//   engine-7-mode-2 = panel M2 = Resonant Bass  object at wrapper + 0x39E8
//   panel M3 reuses the shared Noise/Tone renderer (gated elsewhere)
//
// usage: perky_cf_resonant_diff <fixture-dir> <asset-dir>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

extern "C" {
#include "cf_resonant.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

struct Shape {
    const char* name;
    unsigned mode;
    std::size_t offset;
    std::size_t bytes;
    bool bass;
};

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::fprintf(stderr, "usage: perky_cf_resonant_diff <fixture-dir> <asset-dir>\n");
        return 2;
    }
    const std::string fd = argv[1], ad = argv[2];
    auto e1 = read_file(ad + "/envelope1.bin");
    auto e2 = read_file(ad + "/envelope2.bin");
    auto ia = read_file(ad + "/interp_a.bin");
    auto ib = read_file(ad + "/interp_b.bin");
    if (e1.size() != PK_CF_RES_ENV_BYTES || e2.size() != PK_CF_RES_ENV_BYTES
        || ia.size() != PK_CF_RES_INTERP_BYTES || ib.size() != PK_CF_RES_INTERP_BYTES)
        return 3;
    pk_cf_res_tables tables{e1.data(), e2.data(), ia.data(), ib.data()};

    const Shape shapes[] = {
        {"snare(M1)", 1, 0x2734, PK_CF_RES_SNARE_STATE_BYTES, false},
        {"bass(M2)", 2, 0x39E8, PK_CF_RES_BASS_STATE_BYTES, true},
    };
    constexpr unsigned kBlocks = 16, kBlock = 16;
    std::uint64_t total = 0;
    for (const Shape& sh : shapes) {
        for (unsigned corner = 0; corner < 3; ++corner) {
            const std::string dir = fd + "/engine-7-mode-" + std::to_string(sh.mode)
                                  + "-corner-" + std::to_string(corner);
            const auto after = read_file(dir + "/wrapper-window-after.bin");
            const auto cont = read_file(dir + "/wrapper-window-continuation-after.bin");
            const auto want = read_file(dir + "/arm-pcm-continuation.bin");
            const auto rng_before = read_file(dir + "/rng-continuation-before.bin");
            const auto rng_after = read_file(dir + "/rng-continuation-after.bin");
            if (want.size() != kBlocks * kBlock * 2 || rng_before.size() != 8)
                return 4;
            if (after.size() < sh.offset + sh.bytes || cont.size() < sh.offset + sh.bytes)
                return 5;

            std::vector<std::uint8_t> state(after.begin() + sh.offset,
                                            after.begin() + sh.offset + sh.bytes);
            pk_cf_res_rng rng;
            std::memcpy(&rng, rng_before.data(), 8);
            std::array<std::int16_t, kBlocks * kBlock> got{};
            for (unsigned b = 0; b < kBlocks; ++b) {
                const int ok = sh.bass
                    ? pk_cf_res_bass_render(state.data(), got.data() + b * kBlock,
                                            kBlock, &tables, &rng)
                    : pk_cf_res_snare_render(state.data(), got.data() + b * kBlock,
                                             kBlock, &tables, &rng);
                if (!ok) return 6;
            }
            if (std::memcmp(got.data(), want.data(), want.size()) != 0) {
                for (unsigned i = 0; i < got.size(); ++i) {
                    std::int16_t w;
                    std::memcpy(&w, want.data() + 2 * i, 2);
                    if (got[i] != w) {
                        std::fprintf(stderr, "%s corner %u: PCM mismatch at %u got %d want %d\n",
                                     sh.name, corner, i, got[i], w);
                        return 10;
                    }
                }
                return 10;
            }
            if (std::memcmp(state.data(), cont.data() + sh.offset, sh.bytes) != 0) {
                std::fprintf(stderr, "%s corner %u: final state mismatch\n", sh.name, corner);
                return 11;
            }
            if (std::memcmp(&rng, rng_after.data(), 8) != 0) {
                std::fprintf(stderr, "%s corner %u: RNG mismatch\n", sh.name, corner);
                return 12;
            }
            total += kBlocks * kBlock;
            std::printf("  %-10s corner %u: 256 samples PCM/state/RNG exact\n", sh.name, corner);
        }
    }
    std::printf("Resonant Drums: PASS %llu exact samples (snare M1 + bass M2, 3 corners each)\n",
                (unsigned long long)total);
    return 0;
}
