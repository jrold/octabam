// Compare the ColdFire Acoustic Hats renderer (PĒRKONS family V4 algorithm 3)
// against the real firmware's own captured PCM, object and global held sample.
//
//   wrapper-window-before            -> arm-pcm              (first block, hold 0)
//   wrapper-window-after             -> arm-pcm-continuation (continuation)
//   wrapper-window-retrigger-before  -> arm-pcm-retrigger    (active retrigger)
//
// usage: perky_cf_acoustic_hats_diff <fixture-dir> <asset-dir>
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
#include "cf_acoustic_hats.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

namespace {

constexpr std::size_t kOffset = 0x2A80;
constexpr unsigned kBlocks = 16, kBlock = 16;

struct Block {
    const char* in;
    const char* pcm;
    const char* state_after;
    const char* hold_before;   // nullptr when the block starts from a zero hold
    const char* hold_after;    // nullptr when the block has no hold evidence
};

constexpr Block kBlocksUsed[] = {
    {"wrapper-window-before.bin", "arm-pcm.bin", "wrapper-window-after.bin",
     nullptr, nullptr},
    {"wrapper-window-after.bin", "arm-pcm-continuation.bin",
     "wrapper-window-continuation-after.bin", "acoustic-hold-continuation-before.bin",
     "acoustic-hold-continuation-after.bin"},
    {"wrapper-window-retrigger-before.bin", "arm-pcm-retrigger.bin",
     "wrapper-window-retrigger-after.bin", "acoustic-hold-retrigger-before.bin",
     "acoustic-hold-retrigger-after.bin"},
};

std::int32_t hold_from(const std::vector<std::uint8_t>& b)
{
    std::int32_t v;
    std::memcpy(&v, b.data(), 4);
    return v;
}

int run_case(const std::string& dir, const char* label, const pk_cf_ah_tables& tables,
             std::uint64_t& total)
{
    for (const Block& c : kBlocksUsed) {
        const auto window = read_file(dir + "/" + c.in);
        const auto want = read_file(dir + "/" + c.pcm);
        const auto after = read_file(dir + "/" + c.state_after);
        if (window.size() < kOffset + PK_CF_AH_STATE_BYTES
            || after.size() < kOffset + PK_CF_AH_STATE_BYTES) return 4;
        if (want.size() != kBlocks * kBlock * 2) return 4;

        std::vector<std::uint8_t> state(window.begin() + kOffset,
                                        window.begin() + kOffset + PK_CF_AH_STATE_BYTES);
        std::int32_t hold = c.hold_before ? hold_from(read_file(dir + "/" + c.hold_before)) : 0;
        std::array<std::int16_t, kBlocks * kBlock> got{};
        for (unsigned b = 0; b < kBlocks; ++b)
            if (!pk_cf_ah_render(state.data(), got.data() + b * kBlock, kBlock, &tables, &hold))
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
        if (std::memcmp(state.data(), after.data() + kOffset, PK_CF_AH_STATE_BYTES) != 0) {
            for (std::size_t i = 0; i < PK_CF_AH_STATE_BYTES; ++i)
                if (state[i] != after[kOffset + i]) {
                    std::fprintf(stderr,
                                 "%s %s: final state differs at +0x%zx got 0x%02x want 0x%02x\n",
                                 label, c.state_after, i, state[i], after[kOffset + i]);
                    break;
                }
            return 11;
        }
        if (c.hold_after) {
            const std::int32_t want_hold = hold_from(read_file(dir + "/" + c.hold_after));
            if (hold != want_hold) {
                std::fprintf(stderr, "%s %s: global hold %d, want %d\n",
                             label, c.hold_after, hold, want_hold);
                return 12;
            }
        }
        total += got.size();
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::fprintf(stderr,
                     "usage: perky_cf_acoustic_hats_diff <fixture-dir> <asset-dir>\n");
        return 2;
    }
    const std::string fd = argv[1], ad = argv[2];
    try {
        auto e1 = read_file(ad + "/envelope1.bin");
        auto e2 = read_file(ad + "/envelope2.bin");
        auto closed = read_file(ad + "/closed.bin");
        auto open = read_file(ad + "/open.bin");
        auto ride = read_file(ad + "/ride.bin");
        if (e1.size() != 4096u || e2.size() != 4096u
            || closed.size() != PK_CF_AH_CLOSED_BYTES
            || open.size() != PK_CF_AH_OPEN_BYTES
            || ride.size() != PK_CF_AH_RIDE_BYTES)
            return 3;
        pk_cf_ah_tables tables{};
        tables.envelope1 = e1.data();
        tables.envelope2 = e2.data();
        tables.samples[0] = {PK_CF_AH_CLOSED_ADDR, closed.data(), PK_CF_AH_CLOSED_BYTES};
        tables.samples[1] = {PK_CF_AH_OPEN_ADDR, open.data(), PK_CF_AH_OPEN_BYTES};
        tables.samples[2] = {PK_CF_AH_RIDE_ADDR, ride.data(), PK_CF_AH_RIDE_BYTES};

        std::uint64_t total = 0;
        for (unsigned mode = 1; mode <= 3; ++mode) {
            for (unsigned corner = 0; corner < 3; ++corner) {
                const std::string dir = fd + "/engine-12-mode-" + std::to_string(mode)
                                      + "-corner-" + std::to_string(corner);
                char label[40];
                std::snprintf(label, sizeof label, "AcousticHats mode%u corner%u", mode, corner);
                const int rc = run_case(dir, label, tables, total);
                if (rc) return rc;
                std::printf("  %-34s 3 blocks PCM+state+hold exact\n", label);
            }
        }
        std::printf("Acoustic Hats: PASS %llu exact samples "
                    "(M1/M2/M3, 3 control corners, first + continuation + retrigger)\n",
                    (unsigned long long)total);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "%s\n", e.what());
        return 7;
    }
    return 0;
}
