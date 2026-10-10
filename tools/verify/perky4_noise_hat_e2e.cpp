// Noise Hat C control path vs the real firmware's captured prepared states:
// cold init -> sixteen control updates (pre-trigger), then trigger + one update
// (post-trigger), for all three panel modes and all three control corners.
//
// usage: perky4_noise_hat_e2e <fixture-dir> <asset-dir>
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
#include "cf_perky4.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::fprintf(stderr, "usage: perky4_noise_hat_e2e <fixture-dir> <asset-dir>\n");
        return 2;
    }
    const std::string fd = argv[1], ad = argv[2];
    auto pitch = read_file(ad + "/pitch.bin");
    auto chrom = read_file(ad + "/chromatic.bin");
    auto e1 = read_file(ad + "/envelope1.bin");
    auto e2 = read_file(ad + "/envelope2.bin");
    auto m1 = read_file(ad + "/m1.bin");
    std::array<std::vector<std::uint8_t>, 4> wv = {
        read_file(ad + "/w0.bin"), read_file(ad + "/w1.bin"),
        read_file(ad + "/w2.bin"), read_file(ad + "/w3.bin")};
    constexpr std::array<std::uint32_t, 4> addrs = {
        0x080222a0u, 0x080224a0u, 0x080226a0u, 0x080228a0u};
    pk4_assets assets{};
    assets.pitch = pitch.data();
    assets.chromatic = chrom.data();
    assets.envelope1 = e1.data();
    assets.envelope2 = e2.data();
    assets.m1_wave = m1.data();
    assets.m1_wave_address = 0x080310e0u;
    for (unsigned i = 0; i < 4; ++i) assets.waves[i] = {addrs[i], wv[i].data()};

    /* panel mode -> firmware limb -> comparison window (interior fields only) */
    struct Case { unsigned panel; unsigned fw; std::size_t base; std::size_t bytes; };
    const Case cases[] = {
        {1, 1, 0x318, 0x140},   /* white     */
        {2, 0, 0x0C4, 0x140},   /* metallic  */
        {3, 2, 0x2C98, 0x11C},  /* pulse     */
    };
    const std::uint8_t raws[3] = {0, 64, 127};
    std::uint64_t stages = 0;

    for (const Case& c : cases) {
        for (unsigned corner = 0; corner < 3; ++corner) {
            const std::string dir = fd + "/engine-10-mode-" + std::to_string(c.panel)
                                  + "-corner-" + std::to_string(corner);
            const auto pre = read_file(dir + "/wrapper-window-pre-trigger.bin");
            const auto bef = read_file(dir + "/wrapper-window-before.bin");
            const std::uint8_t r = raws[corner];
            pk4_engine e{};
            pk4_init(&e, &assets);
            if (!pk4_prepare_event(&e, 0, r, r, r, r,
                                   (std::uint8_t)(c.panel - 1), PK4_ALGO_NOISE_HAT,
                                   255, 63, 0))
                return 5;
            auto cmp = [&](const std::vector<std::uint8_t>& want, const char* what) {
                for (std::size_t i = 0x20; i < c.bytes; ++i) {
                    if (e.tracks[0].nh[c.base + i] != want[c.base + i]) {
                        std::fprintf(stderr,
                                     "M%u corner %u: %s mismatch at limb+0x%zx got 0x%02x want 0x%02x\n",
                                     c.panel, corner, what, i,
                                     e.tracks[0].nh[c.base + i], want[c.base + i]);
                        return false;
                    }
                }
                ++stages;
                return true;
            };
            if (!cmp(pre, "pre-trigger")) return 10;
            if (!pk4_prepare_event(&e, 0, r, r, r, r,
                                   (std::uint8_t)(c.panel - 1), PK4_ALGO_NOISE_HAT,
                                   255, 45, 1))
                return 6;
            if (!cmp(bef, "post-trigger")) return 11;
            std::printf("  M%u (fw %u) corner %u: pre/post-trigger state exact\n",
                        c.panel, c.fw, corner);
        }
    }
    std::printf("Noise Hat control path: PASS (%llu state stages vs firmware captures)\n",
                (unsigned long long)stages);
    return 0;
}
