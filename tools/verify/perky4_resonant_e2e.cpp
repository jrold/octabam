// End-to-end Resonant Drums check against the real firmware's own captures:
// init -> control update (x16) -> trigger -> post-trigger update -> render.
//
//   engine-7 mode 1 = panel M1 = snare at wrapper + 0x2734 (0x1d4)
//   engine-7 mode 2 = panel M2 = bass  at wrapper + 0x39E8 (0x1d4 family object)
//
// Every stage is compared: pre-trigger state, post-trigger state, the first
// 256 rendered samples, the state after them, the next 256 and its state.
//
// usage: perky4_resonant_e2e <fixture-dir> <asset-dir>
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

/* 0x00..0x1f is object identity/bookkeeping (vtable + the four control
 * pointers at 0xc..0x18); it is not control-derived and the port model does
 * not carry it. */
static const std::size_t kHeader = 0x20;

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::fprintf(stderr, "usage: perky4_resonant_e2e <fixture-dir> <asset-dir>\n");
        return 2;
    }
    const std::string fd = argv[1], ad = argv[2];
    auto pitch = read_file(ad + "/pitch.bin");
    auto chrom = read_file(ad + "/chromatic.bin");
    auto e1 = read_file(ad + "/envelope1.bin");
    auto e2 = read_file(ad + "/envelope2.bin");
    auto m1 = read_file(ad + "/m1.bin");
    auto ia = read_file(ad + "/interp_a.bin");
    auto ib = read_file(ad + "/interp_b.bin");
    std::array<std::vector<std::uint8_t>, 4> wv = {
        read_file(ad + "/w0.bin"), read_file(ad + "/w1.bin"),
        read_file(ad + "/w2.bin"), read_file(ad + "/w3.bin")};
    if (pitch.size() != 8192 || chrom.size() != 24 || e1.size() != 4096
        || e2.size() != 4096 || m1.size() != 4096
        || ia.size() != 514 || ib.size() != 514)
        return 3;
    for (const auto& w : wv) if (w.size() != 512) return 3;

    constexpr std::array<std::uint32_t, 4> addrs = {
        0x080222a0u, 0x080224a0u, 0x080226a0u, 0x080228a0u};
    pk4_assets assets{};
    assets.pitch = pitch.data();
    assets.chromatic = chrom.data();
    assets.envelope1 = e1.data();
    assets.envelope2 = e2.data();
    assets.m1_wave = m1.data();
    assets.m1_wave_address = 0x080310e0u;
    assets.res_interp_a = ia.data();
    assets.res_interp_b = ib.data();
    for (unsigned i = 0; i < 4; ++i) assets.waves[i] = {addrs[i], wv[i].data()};

    /* `port_mode` is the PORT's 0-based panel mode (M1 -> 0 -> snare,
     * M2 -> 1 -> bass). The fixture directories use the 1-based panel number. */
    /* `cmp_bytes` is how much of the capture is defined: the snare object is
     * 0x1d4; the bass renderer only uses the first 0x178 of the same family
     * object, and the capture slice beyond that is not this object's bytes. */
    struct Shape { const char* name; unsigned fixture_mode; unsigned port_mode;
                   std::size_t offset; std::size_t cmp_bytes; };
    const Shape shapes[] = {
        {"snare(M1)", 1, 0, 0x2734, PK_CF_RES_SNARE_STATE_BYTES},
        {"bass(M2)", 2, 1, 0x39E8, 0x178u},
    };
    const std::size_t size = PK_CF_RES_SNARE_STATE_BYTES;
    const std::uint8_t raws[3] = {0, 64, 127};   /* target7 -> 0, 2048, 4095 */
    std::uint64_t pcm_total = 0, stages = 0;

    for (const Shape& sh : shapes) {
        for (unsigned corner = 0; corner < 3; ++corner) {
            const std::string dir = fd + "/engine-7-mode-" + std::to_string(sh.fixture_mode)
                                  + "-corner-" + std::to_string(corner);
            const auto pre = read_file(dir + "/wrapper-window-pre-trigger.bin");
            const auto bef = read_file(dir + "/wrapper-window-before.bin");
            const auto aft = read_file(dir + "/wrapper-window-after.bin");
            const auto con = read_file(dir + "/wrapper-window-continuation-after.bin");
            const auto pcm0 = read_file(dir + "/arm-pcm.bin");
            const auto pcm1 = read_file(dir + "/arm-pcm-continuation.bin");
            for (const auto* v : {&pre, &bef, &aft, &con})
                if (v->size() < sh.offset + size) return 4;

            const std::uint8_t r = raws[corner];
            pk4_engine engine{};
            pk4_init(&engine, &assets);
            if (!pk4_prepare_event(&engine, 0, r, r, r, r,
                                   (std::uint8_t)sh.port_mode, PK4_ALGO_RESONANT,
                                   255, 63, 0))
                return 5;
            const std::uint8_t* st = sh.port_mode == 0 ? engine.tracks[0].res_snare
                                                       : engine.tracks[0].res_bass;
            auto cmp = [&](const std::vector<std::uint8_t>& want, const char* what) {
                if (std::memcmp(st + kHeader, want.data() + sh.offset + kHeader,
                                sh.cmp_bytes - kHeader) != 0) {
                    std::fprintf(stderr, "%s corner %u: %s state mismatch\n",
                                 sh.name, corner, what);
                    for (std::size_t i = kHeader; i < sh.cmp_bytes; ++i)
                        if (st[i] != want[sh.offset + i]) {
                            std::fprintf(stderr, "   first at 0x%zx got 0x%02x want 0x%02x\n",
                                         i, st[i], want[sh.offset + i]);
                            break;
                        }
                    return false;
                }
                ++stages;
                return true;
            };
            if (!cmp(pre, "pre-trigger")) return 10;

            if (!pk4_prepare_event(&engine, 0, r, r, r, r,
                                   (std::uint8_t)sh.port_mode, PK4_ALGO_RESONANT,
                                   255, 45, 1))
                return 6;
            if (!cmp(bef, "post-trigger")) return 11;

            std::array<std::int16_t, 256> pcm{};
            /* The firmware's RNG object starts at (low=1, high=0); recovered by
             * inverting the generator from the captured continuation state. */
            engine.tracks[0].rng_low = 1u;
            engine.tracks[0].rng_high = 0u;
            if (!pk4_render(&engine, 0, pcm.data(), 256)) return 7;
            if (std::memcmp(pcm.data(), pcm0.data(), 512) != 0) {
                std::fprintf(stderr, "%s corner %u: first-block PCM mismatch\n", sh.name, corner);
                return 12;
            }
            pcm_total += 256;
            if (!cmp(aft, "after first block")) return 13;

            if (!pk4_render(&engine, 0, pcm.data(), 256)) return 8;
            if (std::memcmp(pcm.data(), pcm1.data(), 512) != 0) {
                std::fprintf(stderr, "%s corner %u: second-block PCM mismatch\n", sh.name, corner);
                return 14;
            }
            pcm_total += 256;
            if (!cmp(con, "after second block")) return 15;
            std::printf("  %-10s corner %u: 4 state stages + 512 PCM exact\n",
                        sh.name, corner);
        }
    }
    std::printf("Resonant Drums end-to-end: PASS (%llu sample comparisons, %llu state stages)\n",
                (unsigned long long)pcm_total, (unsigned long long)stages);
    return 0;
}
