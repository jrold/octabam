// Compare the ColdFire Wavetable renderer (PĒRKONS family V1/V2 algorithm 2)
// against the real firmware's own captured PCM and object bytes.
//
//   wrapper-window-before            -> arm-pcm              (first block)
//   wrapper-window-after             -> arm-pcm-continuation (continuation)
//   wrapper-window-retrigger-before  -> arm-pcm-retrigger    (active retrigger)
//
// usage: perky_cf_wavetable_diff <fixture-dir> <asset-dir> <engine-index> <object-offset-hex>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

extern "C" {
#include "cf_wavetable.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

namespace {

constexpr unsigned kBlocks = 16, kBlock = 16;

struct Block {
    const char* in;
    const char* pcm;
    const char* state_after;
};

constexpr Block kBlocksUsed[] = {
    {"wrapper-window-before.bin", "arm-pcm.bin", "wrapper-window-after.bin"},
    {"wrapper-window-after.bin", "arm-pcm-continuation.bin",
     "wrapper-window-continuation-after.bin"},
    {"wrapper-window-retrigger-before.bin", "arm-pcm-retrigger.bin",
     "wrapper-window-retrigger-after.bin"},
};

int run_case(const std::string& dir, const char* label, std::size_t offset,
             const pk_cf_wt_tables& tables, std::uint64_t& total)
{
    for (const Block& c : kBlocksUsed) {
        const auto window = read_file(dir + "/" + c.in);
        const auto want = read_file(dir + "/" + c.pcm);
        const auto after = read_file(dir + "/" + c.state_after);
        if (window.size() < offset + PK_CF_WT_STATE_BYTES
            || after.size() < offset + PK_CF_WT_STATE_BYTES) return 4;
        if (want.size() != kBlocks * kBlock * 2) return 4;

        std::vector<std::uint8_t> state(window.begin() + offset,
                                        window.begin() + offset + PK_CF_WT_STATE_BYTES);
        std::array<std::int16_t, kBlocks * kBlock> got{};
        for (unsigned b = 0; b < kBlocks; ++b)
            if (!pk_cf_wt_render(state.data(), got.data() + b * kBlock, kBlock, &tables))
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
        if (std::memcmp(state.data(), after.data() + offset, PK_CF_WT_STATE_BYTES) != 0) {
            for (std::size_t i = 0; i < PK_CF_WT_STATE_BYTES; ++i)
                if (state[i] != after[offset + i]) {
                    std::fprintf(stderr,
                                 "%s %s: final state differs at +0x%zx got 0x%02x want 0x%02x\n",
                                 label, c.state_after, i, state[i], after[offset + i]);
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
    if (argc != 5) {
        std::fprintf(stderr,
                     "usage: perky_cf_wavetable_diff <fixture-dir> <asset-dir> <engine-index> <object-offset-hex>\n");
        return 2;
    }
    const std::string fd = argv[1], ad = argv[2];
    const unsigned engine = static_cast<unsigned>(std::strtoul(argv[3], nullptr, 0));
    const std::size_t offset = static_cast<std::size_t>(std::strtoul(argv[4], nullptr, 0));
    try {
        auto pitch = read_file(ad + "/pitch.bin");
        auto e1 = read_file(ad + "/envelope1.bin");
        auto e2 = read_file(ad + "/envelope2.bin");
        auto base = read_file(ad + "/base_wave.bin");
        auto bank = read_file(ad + "/bank.bin");
        if (pitch.size() != 8192u || e1.size() != 4096u
            || e2.size() != 4096u || base.size() != PK_CF_WT_TABLE_BYTES
            || bank.size() != static_cast<std::size_t>(PK_CF_WT_BANK_COUNT) * PK_CF_WT_TABLE_BYTES)
            return 3;
        pk_cf_wt_tables tables{};
        tables.pitch = pitch.data();
        tables.envelope1 = e1.data();
        tables.envelope2 = e2.data();
        tables.base_wave = base.data();
        tables.bank = bank.data();

        std::uint64_t total = 0;
        for (unsigned mode = 1; mode <= 3; ++mode) {
            for (unsigned corner = 0; corner < 3; ++corner) {
                const std::string dir = fd + "/engine-" + std::to_string(engine) + "-mode-" + std::to_string(mode)
                                      + "-corner-" + std::to_string(corner);
                char label[40];
                std::snprintf(label, sizeof label, "Wavetable engine%u mode%u corner%u", engine, mode, corner);
                const int rc = run_case(dir, label, offset, tables, total);
                if (rc) return rc;
                std::printf("  %-34s 3 blocks PCM+state exact\n", label);
            }
        }
        std::printf("Wavetable engine %u: PASS %llu exact samples "
                    "(M1/M2/M3, 3 control corners, first + continuation + retrigger)\n",
                    engine, (unsigned long long)total);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "%s\n", e.what());
        return 7;
    }
    return 0;
}
