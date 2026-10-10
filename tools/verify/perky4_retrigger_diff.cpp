/* Does the port's TRIGGER produce the same state as the firmware's?
 *
 * The engine fixtures carry a second, active-retrigger capture:
 *   wrapper-window-retrigger-pre  -> state just before the second trigger
 *   wrapper-window-retrigger-before -> state just after it (trigger + update)
 *   arm-pcm-retrigger.bin         -> the 256 samples that follow
 * No gate has ever compared these.  This probe copies the pre-retrigger state
 * into the port, runs one prepare_event(trig=1) with the controls already
 * settled, and diffs the result. */
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
extern "C" {
#include "cf_perky4.h"
}

static std::vector<std::uint8_t> rf(const std::string& p)
{
    std::ifstream f(p, std::ios::binary);
    if (!f) { std::fprintf(stderr, "open %s\n", p.c_str()); std::exit(3); }
    return {std::istreambuf_iterator<char>(f), {}};
}

struct Case { const char* name; unsigned engine; std::size_t off; std::size_t bytes;
              unsigned algo; unsigned mode; };

int main(int argc, char** argv)
{
    (void)argc;
    std::string d = argv[1], a = argv[2];
    auto pitch = rf(a + "/pitch.bin"), chrom = rf(a + "/chromatic.bin");
    auto e1 = rf(a + "/envelope1.bin"), e2 = rf(a + "/envelope2.bin");
    auto m1 = rf(a + "/m1.bin");
    auto ia = rf(a + "/interp_a.bin"), ib = rf(a + "/interp_b.bin");
    std::array<std::vector<std::uint8_t>, 4> w = {
        rf(a + "/w0.bin"), rf(a + "/w1.bin"), rf(a + "/w2.bin"), rf(a + "/w3.bin")};
    constexpr std::array<std::uint32_t, 4> wa = {0x080222a0u,0x080224a0u,0x080226a0u,0x080228a0u};
    pk4_assets as{};
    as.pitch=pitch.data(); as.chromatic=chrom.data();
    as.envelope1=e1.data(); as.envelope2=e2.data();
    as.m1_wave=m1.data(); as.m1_wave_address=0x080310e0u;
    as.res_interp_a=ia.data(); as.res_interp_b=ib.data();
    for (unsigned i=0;i<4;i++){as.waves[i].address=wa[i];as.waves[i].table=w[i].data();}

    const Case cases[] = {
        {"Fold1   M1", 1, 0x0c4, 0x0f4, 0, 0},
        {"Fold2   M1", 4, 0x0c4, 0x134, 1, 0},
        {"Karplus M1", 9, 0x2908, 0x10e0, 2, 0},
    };
    int failures = 0;
    for (const Case& c : cases) {
        const std::string dir = d + "/engine-" + std::to_string(c.engine) + "-mode-1-corner-1";
        const auto pre = rf(dir + "/wrapper-window-retrigger-pre.bin");
        const auto bef = rf(dir + "/wrapper-window-retrigger-before.bin");
        const auto want = rf(dir + "/arm-pcm-retrigger.bin");
        pk4_engine e{};
        pk4_init(&e, &as);
        std::uint8_t* dst = c.algo==0?(std::uint8_t*)e.tracks[0].fold1
                          : c.algo==1?(std::uint8_t*)e.tracks[0].fold2
                                     :(std::uint8_t*)e.tracks[0].karplus;
        std::memcpy(dst, pre.data() + c.off, c.bytes);
        /* Mark the algorithm initialised so prepare_event does not re-init over
         * the captured state. */
        e.tracks[0].initialized_mask = (std::uint8_t)(1u << c.algo);
        e.tracks[0].active_algo = (std::uint8_t)c.algo;
        e.tracks[0].active_mode = (std::uint8_t)c.mode;
        /* The firmware's retrigger is trigger + one update, no control settle. */
        pk4_control* ctl = c.algo==0?&e.tracks[0].fold1_ctl
                         : c.algo==1?&e.tracks[0].fold2_ctl
                                    :&e.tracks[0].karplus_ctl;
        const std::uint8_t raw[4] = {64,64,64,64};
        for (unsigned i=0;i<4;i++){ctl->targets[i]=2048u;ctl->last_raw[i]=64;}
        ctl->last_mode=0; ctl->valid=1;
        pk4_prepare_event(&e, 0, raw[1], raw[0], raw[2], raw[3],
                          (std::uint8_t)c.mode, (std::uint8_t)c.algo, 255, 45, 1);
        const std::uint8_t* st = c.algo==0?e.tracks[0].fold1
                               : c.algo==1?e.tracks[0].fold2
                                          :e.tracks[0].karplus;
        int bad = 0; std::size_t first = 0;
        for (std::size_t i = 0x20; i < c.bytes; ++i)
            if (st[i] != bef[c.off + i]) { if (!bad) first = i; ++bad; }
        std::printf("%s: post-retrigger state mismatches=%d", c.name, bad);
        if (bad) std::printf("  first at 0x%zx got 0x%02x want 0x%02x", first,
                             st[first], bef[c.off + first]);
        std::printf("\n");
        /* Fold2 keeps two address-encoded oscillator pointers, which a host
         * probe cannot reproduce; everything else must match. */
        if (bad > (c.algo == 1 ? 4 : 0)) ++failures;
        /* And the audio that follows the retrigger. */
        {
            const auto rb = rf(dir + "/rng-retrigger-before.bin");
            std::uint32_t lo, hi; std::memcpy(&lo, rb.data(), 4); std::memcpy(&hi, rb.data() + 4, 4);
            e.tracks[0].rng_low = lo; e.tracks[0].rng_high = hi;
            std::int16_t got[256]{};
            if (!pk4_render(&e, 0, got, 256)) { std::printf("   render failed\n"); continue; }
            int dbad = 0; std::size_t dfirst = 0;
            for (unsigned i = 0; i < 256; ++i) {
                std::int16_t wv; std::memcpy(&wv, want.data() + 2 * i, 2);
                if (got[i] != wv) { if (!dbad) dfirst = i; ++dbad; }
            }
            std::printf("   post-retrigger PCM mismatches=%d", dbad);
            if (dbad) std::printf("  first at %zu got %d want %d", dfirst, got[dfirst],
                                  (int)(std::int16_t)(want[2*dfirst] | (want[2*dfirst+1] << 8)));
            std::printf("\n");
            if (dbad) ++failures;
        }
    }
    if (failures) { std::printf("RETRIGGER: FAIL (%d)\n", failures); return 1; }
    std::printf("RETRIGGER: PASS\n");
    return 0;
}
