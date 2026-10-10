// Compare the ColdFire Slap renderer (PĒRKONS family V3 algorithm 2) against
// the real firmware's own captured PCM, object AND RNG.
//
//   wrapper-window-after            + rng-continuation-before
//     -> arm-pcm-continuation, wrapper-window-continuation-after,
//        rng-continuation-after
//   wrapper-window-retrigger-before + rng-retrigger-before
//     -> arm-pcm-retrigger, wrapper-window-retrigger-after, rng-retrigger-after
//
// Slap consumes the shared 32-bit PRNG, so the continuation block is the
// first block the captures record a "before" RNG for.
//
// usage: perky_cf_slap_diff <fixture-dir> <asset-dir>
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
#include "cf_slap.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

namespace {

constexpr std::size_t kOffset = 0xC4;
constexpr std::size_t kBytes = PK_CF_SLAP_STATE_BYTES;
constexpr unsigned kBlocks = 16, kBlock = 16;

struct Block {
    const char* in;
    const char* rng_before;
    const char* pcm;
    const char* state_after;
    const char* rng_after;
};

constexpr Block kBlocksUsed[] = {
    {"wrapper-window-after.bin", "rng-continuation-before.bin",
     "arm-pcm-continuation.bin", "wrapper-window-continuation-after.bin",
     "rng-continuation-after.bin"},
    {"wrapper-window-retrigger-before.bin", "rng-retrigger-before.bin",
     "arm-pcm-retrigger.bin", "wrapper-window-retrigger-after.bin",
     "rng-retrigger-after.bin"},
};

int run_case(const std::string& dir, const char* label,
             const pk_cf_fold_tables& tables, std::uint64_t& total)
{
    for (const Block& c : kBlocksUsed) {
        const auto window = read_file(dir + "/" + c.in);
        const auto rng_before = read_file(dir + "/" + c.rng_before);
        const auto want = read_file(dir + "/" + c.pcm);
        const auto after = read_file(dir + "/" + c.state_after);
        const auto rng_after = read_file(dir + "/" + c.rng_after);
        if (window.size() < kOffset + kBytes || after.size() < kOffset + kBytes) return 4;
        if (want.size() != kBlocks * kBlock * 2 || rng_before.size() != 8) return 4;

        std::vector<std::uint8_t> state(window.begin() + kOffset,
                                        window.begin() + kOffset + kBytes);
        pk_cf_fold_rng rng{};
        std::memcpy(&rng, rng_before.data(), 8);
        std::array<std::int16_t, kBlocks * kBlock> got{};
        for (unsigned b = 0; b < kBlocks; ++b)
            if (!pk_cf_slap_render(state.data(), got.data() + b * kBlock, kBlock,
                                   &tables, &rng))
                return 5;

        for (unsigned i = 0; i < got.size(); ++i) {
            std::int16_t w;
            std::memcpy(&w, want.data() + 2 * i, 2);
            if (got[i] != w) {
                std::fprintf(stderr, "%s %s: PCM mismatch at %u got %d want %d\n",
                             label, c.pcm, i, got[i], w);
                return 10;
            }
        }
        if (std::memcmp(&rng, rng_after.data(), 8) != 0) {
            std::fprintf(stderr, "%s %s: RNG mismatch\n", label, c.rng_after);
            return 12;
        }
        if (std::memcmp(state.data(), after.data() + kOffset, kBytes) != 0) {
            for (std::size_t i = 0; i < kBytes; ++i)
                if (state[i] != after[kOffset + i]) {
                    std::fprintf(stderr,
                                 "%s %s: final state differs at +0x%zx got 0x%02x want 0x%02x\n",
                                 label, c.state_after, i, state[i], after[kOffset + i]);
                    break;
                }
            return 11;
        }
        total += got.size();
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::fprintf(stderr, "usage: perky_cf_slap_diff <fixture-dir> <asset-dir>\n");
        return 2;
    }
    const std::string fd = argv[1], ad = argv[2];
    try {
        auto e1 = read_file(ad + "/envelope1.bin");
        auto e2 = read_file(ad + "/envelope2.bin");
        if (e1.size() != PK_CF_FOLD_ENV_BYTES || e2.size() != PK_CF_FOLD_ENV_BYTES)
            return 3;
        pk_cf_fold_tables tables{};
        tables.envelope1 = e1.data();
        tables.envelope2 = e2.data();

        std::uint64_t total = 0;
        for (unsigned mode = 1; mode <= 3; ++mode) {
            for (unsigned corner = 0; corner < 3; ++corner) {
                const std::string dir = fd + "/engine-8-mode-" + std::to_string(mode)
                                      + "-corner-" + std::to_string(corner);
                char label[32];
                std::snprintf(label, sizeof label, "Slap mode%u corner%u", mode, corner);
                const int rc = run_case(dir, label, tables, total);
                if (rc) return rc;
                std::printf("  %-24s 2 blocks PCM+state+RNG exact\n", label);
            }
        }
        std::printf("Slap: PASS %llu exact samples "
                    "(M1/M2/M3, 3 control corners, continuation + retrigger)\n",
                    (unsigned long long)total);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "%s\n", e.what());
        return 7;
    }
    return 0;
}
