// Noise Hat ColdFire renderer vs the real firmware's own captured output.
//
//   engine-10 panel M1 = firmware mode 1 = white noise  (classic object)
//   engine-10 panel M2 = firmware mode 0 = metallic    (classic object)
//   engine-10 panel M3 = firmware mode 2 = pulse stack (limb at +0x2C98)
//
// usage: perky_cf_noise_hat_diff <fixture-dir> <asset-dir>
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
#include "cf_noise_hat.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

struct Mode {
    const char* name;
    unsigned panel;       /* fixture directory number */
    unsigned firmware;    /* renderer mode */
    std::size_t offset;
    std::size_t bytes;
};

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::fprintf(stderr, "usage: perky_cf_noise_hat_diff <fixture-dir> <asset-dir>\n");
        return 2;
    }
    const std::string fd = argv[1], ad = argv[2];
    auto e1 = read_file(ad + "/envelope1.bin");
    auto e2 = read_file(ad + "/envelope2.bin");
    if (e1.size() != PK_CF_NH_ENV_BYTES || e2.size() != PK_CF_NH_ENV_BYTES) return 3;
    pk_cf_nh_tables tables{e1.data(), e2.data()};

    const Mode modes[] = {
        {"white(M1)", 1, 1, 0x0000, PK_CF_NH_CLASSIC_STATE_BYTES},
        {"metal(M2)", 2, 0, 0x0000, PK_CF_NH_CLASSIC_STATE_BYTES},
        {"pulse(M3)", 3, 2, 0x2C98, PK_CF_NH_PULSE_STATE_BYTES},
    };
    constexpr unsigned kBlocks = 16, kBlock = 16;
    std::uint64_t samples = 0;
    for (const Mode& m : modes) {
        for (unsigned corner = 0; corner < 3; ++corner) {
            const std::string dir = fd + "/engine-10-mode-" + std::to_string(m.panel)
                                  + "-corner-" + std::to_string(corner);
            const auto aft = read_file(dir + "/wrapper-window-after.bin");
            const auto con = read_file(dir + "/wrapper-window-continuation-after.bin");
            const auto want = read_file(dir + "/arm-pcm-continuation.bin");
            if (want.size() != kBlocks * kBlock * 2) return 4;
            if (aft.size() < m.offset + m.bytes || con.size() < m.offset + m.bytes) return 5;

            std::vector<std::uint8_t> state(aft.begin() + m.offset, aft.begin() + m.offset + m.bytes);
            pk_cf_nh_rng rng{0, 0};
            pk_cf_nh_hold hold = {0, 0};
            std::vector<std::uint8_t> hold_after;
            if (m.firmware != 2) {
                const auto rb = read_file(dir + "/rng-continuation-before.bin");
                const auto hb = read_file(dir + "/noise-hat-hold-continuation-before.bin");
                hold_after = read_file(dir + "/noise-hat-hold-continuation-after.bin");
                std::memcpy(&rng, rb.data(), 8);
                hold[0] = (std::uint16_t)(hb[0] | (hb[1] << 8));
                hold[1] = (std::uint16_t)(hb[2] | (hb[3] << 8));
            }

            std::array<std::int16_t, kBlocks * kBlock> got{};
            for (unsigned b = 0; b < kBlocks; ++b)
                if (!pk_cf_nh_render(state.data(), got.data() + b * kBlock, kBlock,
                                     m.firmware, &tables, &rng, hold))
                    return 6;

            if (std::memcmp(got.data(), want.data(), want.size()) != 0) {
                for (unsigned i = 0; i < got.size(); ++i) {
                    std::int16_t w;
                    std::memcpy(&w, want.data() + 2 * i, 2);
                    if (got[i] != w) {
                        std::fprintf(stderr, "%s corner %u: PCM mismatch at %u got %d want %d\n",
                                     m.name, corner, i, got[i], w);
                        break;
                    }
                }
                return 10;
            }
            if (std::memcmp(state.data(), con.data() + m.offset, m.bytes) != 0) {
                for (std::size_t i = 0; i < m.bytes; ++i)
                    if (state[i] != con[m.offset + i]) {
                        std::fprintf(stderr, "%s corner %u: state mismatch at 0x%zx"
                                             " got 0x%02x want 0x%02x\n",
                                     m.name, corner, i, state[i], con[m.offset + i]);
                        break;
                    }
                return 11;
            }
            if (m.firmware != 2) {
                if (std::memcmp(&rng, read_file(dir + "/rng-continuation-after.bin").data(), 8) != 0) {
                    std::fprintf(stderr, "%s corner %u: RNG mismatch\n", m.name, corner);
                    return 12;
                }
                const std::uint8_t hb[4] = {(std::uint8_t)hold[0], (std::uint8_t)(hold[0] >> 8),
                                            (std::uint8_t)hold[1], (std::uint8_t)(hold[1] >> 8)};
                if (std::memcmp(hb, hold_after.data(), 4) != 0) {
                    std::fprintf(stderr, "%s corner %u: hold mismatch\n", m.name, corner);
                    return 13;
                }
            }
            samples += kBlocks * kBlock;
            std::printf("  %-10s corner %u: 256 samples PCM/state exact\n", m.name, corner);
        }
    }
    std::printf("Noise Hat: PASS %llu exact samples (white, metallic, pulse stack)\n",
                (unsigned long long)samples);
    return 0;
}
