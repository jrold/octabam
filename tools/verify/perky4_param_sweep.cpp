// Drive the production ColdFire PERKY renderer across every OT knob position
// and measure whether each control actually changes the sound.
//
// This is the gate that would have caught the obj+8 stuck-sustain bug: with the
// envelope pinned at full scale, DECAY changes the release rate of a state the
// engine never reaches, so the rendered PCM is identical at every DECAY value.
//
// usage: perky4_param_sweep <asset-dir> <report-csv>
#include <array>
#include <cmath>
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
#include "cf_perky4.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

namespace {
/* Long enough to contain both the longest attack and the longest release.
 * Noise/Tone M1 maps PARAM2 to attack time; at its default that is ~18k
 * samples, so a short block would measure every DECAY as identical and report a
 * false "dead control". 32768 samples (~0.74 s at 44.1 kHz) clears it. */
constexpr unsigned kBlock = 32768;
constexpr unsigned kModes = 3;
constexpr unsigned kAlgos = 7;
constexpr unsigned kCtl = 4;
const char* kAlgoName[kAlgos] = {"Fold1", "Fold2", "Karplus", "NoiseTone",
                                 "Resonant", "NoiseHat", "SimpleDrum"};
const char* kCtlName[kCtl] = {"TUNE", "DECAY", "PARAM1", "PARAM2"};

struct Render {
    std::array<std::int16_t, kBlock> pcm{};
    double rms = 0.0;
    int peak = 0;
    int zc = 0;
};

Render render_one(const pk4_assets& assets, unsigned algo, unsigned mode,
                  const std::uint8_t raw[4])
{
    pk4_engine engine{};
    pk4_init(&engine, &assets);
    if (!pk4_prepare_event(&engine, 0, raw[1], raw[0], raw[2], raw[3],
                           (std::uint8_t)mode, (std::uint8_t)algo, 255, 45, 1))
        throw std::runtime_error("pk4_prepare_event failed");
    Render r;
    if (!pk4_render(&engine, 0, r.pcm.data(), kBlock))
        throw std::runtime_error("pk4_render failed");
    double acc = 0.0;
    int prev = 0;
    for (unsigned i = 0; i < kBlock; ++i) {
        const int v = r.pcm[i];
        acc += (double)v * (double)v;
        const int a = v < 0 ? -v : v;
        if (a > r.peak) r.peak = a;
        if (i && ((v < 0) != (prev < 0))) ++r.zc;
        prev = v;
    }
    r.rms = std::sqrt(acc / kBlock);
    return r;
}

int max_abs_diff(const Render& a, const Render& b)
{
    int m = 0;
    for (unsigned i = 0; i < kBlock; ++i) {
        int d = (int)a.pcm[i] - (int)b.pcm[i];
        if (d < 0) d = -d;
        if (d > m) m = d;
    }
    return m;
}
}  // namespace

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::fprintf(stderr, "usage: perky4_param_sweep <asset-dir> <report-csv>\n");
        return 2;
    }
    const std::string ad = argv[1];
    auto pitchv = read_file(ad + "/pitch.bin");
    auto chromv = read_file(ad + "/chromatic.bin");
    auto e1v = read_file(ad + "/envelope1.bin");
    auto e2v = read_file(ad + "/envelope2.bin");
    auto m1v = read_file(ad + "/m1.bin");
    std::array<std::vector<std::uint8_t>, 4> wv = {
        read_file(ad + "/w0.bin"), read_file(ad + "/w1.bin"),
        read_file(ad + "/w2.bin"), read_file(ad + "/w3.bin")};
    if (pitchv.size() != 8192 || chromv.size() != 24 || e1v.size() != 4096
        || e2v.size() != 4096 || m1v.size() != 4096)
        return 3;
    for (const auto& w : wv) if (w.size() != 512) return 3;

    constexpr std::array<std::uint32_t, 4> addrs = {
        0x080222a0u, 0x080224a0u, 0x080226a0u, 0x080228a0u};
    pk4_assets assets{};
    assets.pitch = pitchv.data();
    assets.chromatic = chromv.data();
    assets.envelope1 = e1v.data();
    assets.envelope2 = e2v.data();
    assets.m1_wave = m1v.data();
    assets.m1_wave_address = 0x080310e0u;
    auto res_ia = read_file(ad + "/interp_a.bin");
    auto res_ib = read_file(ad + "/interp_b.bin");
    if (res_ia.size() != 514 || res_ib.size() != 514) return 3;
    assets.res_interp_a = res_ia.data();
    assets.res_interp_b = res_ib.data();
    for (unsigned i = 0; i < 4; ++i) assets.waves[i] = {addrs[i], wv[i].data()};

    std::FILE* csv = std::fopen(argv[2], "w");
    if (!csv) return 4;
    std::fprintf(csv, "algo,mode,control,value,rms,peak,zerocross,"
                      "maxdiff_vs_midpoint\n");

    int dead = 0;
    std::printf("%-9s %-6s %-7s %10s %6s %8s  %s\n",
                "algo", "mode", "control", "max|dPCM|", "at", "of peak",
                "verdict");
    std::array<std::array<Render, kModes>, kAlgos> midpoint{};

    for (unsigned algo = 0; algo < kAlgos; ++algo) {
        for (unsigned mode = 0; mode < kModes; ++mode) {
            std::uint8_t mid[4] = {64, 64, 64, 64};
            midpoint[algo][mode] = render_one(assets, algo, mode, mid);
            const Render& ref = midpoint[algo][mode];
            const int scale = ref.peak > 0 ? ref.peak : 1;
            for (unsigned ctl = 0; ctl < kCtl; ++ctl) {
                int best = 0, best_v = -1;
                for (unsigned v = 0; v < 128; ++v) {
                    std::uint8_t raw[4] = {64, 64, 64, 64};
                    /* raw order is firmware order Tune,Decay,P1,P2 */
                    raw[ctl] = (std::uint8_t)v;
                    const Render got = render_one(assets, algo, mode, raw);
                    const int d = max_abs_diff(got, ref);
                    std::fprintf(csv, "%s,%u,%s,%u,%.1f,%d,%d,%d\n",
                                 kAlgoName[algo], mode, kCtlName[ctl], v,
                                 got.rms, got.peak, got.zc, d);
                    if (d > best) { best = d; best_v = (int)v; }
                }
                const double frac = (double)best / scale;
                const bool live = frac >= 0.05;   /* >=5% of the loudest sample */
                if (!live) ++dead;
                std::printf("%-9s %-6u %-7s %10d %6d %7.1f%%  %s\n",
                            kAlgoName[algo], mode, kCtlName[ctl], best, best_v,
                            100.0 * frac, live ? "live" : "*** DEAD ***");
            }
        }
    }

    /* MODE must pick a different renderer path, and the four Algos must not
     * collapse into one sound. */
    int mode_dead = 0;
    for (unsigned algo = 0; algo < kAlgos; ++algo) {
        const int d01 = max_abs_diff(midpoint[algo][0], midpoint[algo][1]);
        const int d02 = max_abs_diff(midpoint[algo][0], midpoint[algo][2]);
        const int d12 = max_abs_diff(midpoint[algo][1], midpoint[algo][2]);
        const bool live = d01 > 0 && d02 > 0 && d12 > 0;
        if (!live) ++mode_dead;
        std::printf("%-9s MODE   m0/m1=%d m0/m2=%d m1/m2=%d  %s\n",
                    kAlgoName[algo], d01, d02, d12,
                    live ? "live" : "*** IDENTICAL ***");
    }
    int algo_dead = 0;
    for (unsigned a = 0; a < kAlgos; ++a)
        for (unsigned b = a + 1; b < kAlgos; ++b) {
            if (max_abs_diff(midpoint[a][0], midpoint[b][0]) == 0) {
                ++algo_dead;
                std::printf("%-9s vs %-9s *** IDENTICAL ***\n",
                            kAlgoName[a], kAlgoName[b]);
            }
        }

    std::fclose(csv);
    std::printf("\ncontrols dead=%d  modes identical=%d  algos collapsed=%d\n",
                dead, mode_dead, algo_dead);
    return (dead || mode_dead || algo_dead) ? 1 : 0;
}
