#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sys/mman.h>

#ifndef MAP_ANONYMOUS
#define MAP_ANONYMOUS MAP_ANON
#endif

extern "C" {
#include "cf_perky4.h"
int pk_render(unsigned, unsigned, unsigned, unsigned);
void pk_stock_pool_open(void) {}
int pk_stock_validate(void *) { return 1; }
extern const uint8_t pk_asset_pitch[];
extern const uint8_t pk_asset_chromatic[];
extern const uint8_t pk_asset_envelope1[];
extern const uint8_t pk_asset_envelope2[];
extern const uint8_t pk_asset_m1_wave[];
extern const uint8_t pk_asset_wave0[];
extern const uint8_t pk_asset_wave1[];
extern const uint8_t pk_asset_wave2[];
extern const uint8_t pk_asset_wave3[];
}

#define U8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define U16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))

static void map_region(uintptr_t at, size_t size)
{
    void *p = mmap((void *)at, size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p != (void *)at) {
        perror("mmap");
        std::exit(2);
    }
}

static void sign_track(uintptr_t part, unsigned track)
{
    U8(part + 0x22u + track) = 1u;
    U8(part + 60u + 30u * track) = 'P';
    U8(part + 61u + 30u * track) = 'K';
    U8(part + 62u + 30u * track) = 1u;
}

static uintptr_t fixed_slot(unsigned track, unsigned ping)
{
    return 0x80001c90u + (uintptr_t)(ping & 1u) * 0xa80u
         + (uintptr_t)336u * track;
}

int main()
{
    map_region(0x10000000u, 0x00200000u);
    map_region(0x46000000u, 0x04000000u);
    map_region(0x80000000u, 0x01000000u);

    constexpr uint32_t bank = 0x48000000u;
    constexpr uintptr_t part = bank + 0x8ed80u;
    constexpr uintptr_t cursor_base = 0x80010000u;
    constexpr unsigned frames = 1024u;
    constexpr unsigned events = frames * 4u;
    constexpr std::array<unsigned, 4> tracks = {0u, 1u, 2u, 3u};

    U32(0x46c82456u) = bank;
    U8(0x100b14cfu) = 0u;
    U32(0x800062a8u) = 0x80008000u;
    for (unsigned track : tracks)
        sign_track(part, track);

    pk4_assets assets{};
    assets.pitch = pk_asset_pitch;
    assets.chromatic = pk_asset_chromatic;
    assets.envelope1 = pk_asset_envelope1;
    assets.envelope2 = pk_asset_envelope2;
    assets.waves[0] = {0x080222a0u, pk_asset_wave0};
    assets.waves[1] = {0x080224a0u, pk_asset_wave1};
    assets.waves[2] = {0x080226a0u, pk_asset_wave2};
    assets.waves[3] = {0x080228a0u, pk_asset_wave3};
    assets.m1_wave = pk_asset_m1_wave;
    assets.m1_wave_address = 0x080310e0u;

    pk4_engine reference{};
    pk4_init(&reference, &assets);
    /* Coverage is per voice and per ENGINE, not per local knob position: the
     * voice silo (cf_perky4.h) means each track only ever reaches its own
     * family, so every engine in the family has to be exercised. */
    std::array<std::array<uint64_t, PK4_ALGO_COUNT>, 4> matrix{};
    std::array<std::array<uint16_t, PK4_ALGO_COUNT>, 4> split_mask{};
    uint64_t samples = 0;
    uint64_t early_trigger_cases = 0;
    uint64_t boundary_trigger_cases = 0;

    for (unsigned frame = 0; frame < frames; ++frame) {
        U32(0x80001c80u) = cursor_base;
        std::memset((void *)cursor_base, 0xa5, 4096u);

        for (unsigned voice = 0; voice < 4u; ++voice) {
            const unsigned event = frame * 4u + voice;
            const unsigned track = tracks[voice];
            const unsigned ping = event & 1u;
            const unsigned step = frame;
            /* Staged ALGO is a family-local knob position; the driver maps it
             * to the global engine id, and the reference here must use the
             * same mapping -- same inline table, so they cannot drift. */
            const unsigned algo = (step + voice) % pk4_voice_len(voice);
            const unsigned engine = (unsigned)pk4_voice_engine(voice, algo);
            const unsigned mode = (step * 2u + voice) % 3u;
            const unsigned split = ((step >> 2) + voice * 3u + algo * 5u) & 15u;
            const int trig = (event % 5u) != 0u;
            const bool trigger_on_first_half = (event & 1u) == 0u;

            /* The recovered engine ABI stays decay,tune,p1,p2,mode,algo. */
            const uint8_t engine_src[6] = {
                (uint8_t)((step * 17u + voice * 11u) & 127u),
                (uint8_t)((step * 29u + voice * 7u) & 127u),
                (uint8_t)((step * 43u + voice * 5u) & 127u),
                (uint8_t)((step * 61u + voice * 3u) & 127u),
                (uint8_t)mode,
                (uint8_t)engine,
            };
            /* Shipping Octatrack SRC order is tune,decay,algo,p1,p2,mode. */
            const uint8_t page_src[6] = {
                engine_src[1], engine_src[0], (uint8_t)algo,
                engine_src[2], engine_src[3], engine_src[4],
            };

            for (unsigned i = 0; i < 6u; ++i)
                U16(0x80008000u + 2u * i) = (uint16_t)page_src[i] << 8;

            const uintptr_t voice_cursor = U32(0x80001c80u);
            const uintptr_t slot = fixed_slot(track, ping);
            std::memset((void *)slot, 0xa5, 336u);

            std::array<int16_t, 16> pre{}, post{};
            std::array<uint32_t, 36> expected_pre{}, expected_post{};
            if (!pk4_process_segment(&reference, voice, nullptr, 0, trig,
                                     255u, 45u, pre.data(), split))
                return 3;
            if (!pk4_process_segment(&reference, voice, engine_src, 1, trig,
                                     255u, 45u, post.data(), 16u - split))
                return 4;
            const uint32_t pre_longs =
                pk4_encode_stock_segment(expected_pre.data(), pre.data(), split);
            const uint32_t post_longs =
                pk4_encode_stock_segment(expected_post.data(), post.data(), 16u - split);
            if (pre_longs + post_longs != 40u)
                return 5;

            /* Exercise both hardware timing possibilities. For a triggered event
             * the stock flag is visible during exactly one callback half. */
            U8(0x46104d0cu + track) =
                (trig && trigger_on_first_half) ? 16u : 0u;
            if (pk_render(track, ping, 0u, split) != 0) {
                std::cerr << "pk_render pre failed event=" << event << '\n';
                return 6;
            }
            U8(0x46104d0cu + track) =
                (trig && !trigger_on_first_half) ? 16u : 0u;
            if (pk_render(track, ping, split, 16u) != 0) {
                std::cerr << "pk_render post failed event=" << event << '\n';
                return 7;
            }
            U8(0x46104d0cu + track) = 0u;

            if (trig) {
                if (trigger_on_first_half)
                    ++early_trigger_cases;
                else
                    ++boundary_trigger_cases;
            }

            /* The moving builder cursor is reservation only. It deliberately
             * lives nowhere near the track's DMA slot in this fixture, so a
             * renderer that merely appends PCM to the cursor cannot pass. */
            const uint32_t cursor_longs = pre_longs + post_longs;
            if (U32(0x80001c80u) != voice_cursor + cursor_longs * 4u) {
                std::cerr << "cursor span mismatch event=" << event << '\n';
                return 10;
            }
            for (uint32_t i = 0; i < cursor_longs; ++i) {
                if (U32(voice_cursor + i * 4u) != 0u) {
                    std::cerr << "moving cursor payload not reserved/zero event="
                              << event << " long=" << i << '\n';
                    return 11;
                }
            }

            if (std::memcmp((void *)slot, expected_pre.data(), pre_longs * 4u)) {
                std::cerr << "fixed-slot pre mismatch event=" << event
                          << " track=" << track << " algo=" << algo
                          << " mode=" << mode << " split=" << split << '\n';
                return 12;
            }
            if (std::memcmp((void *)(slot + pre_longs * 4u),
                            expected_post.data(), post_longs * 4u)) {
                std::cerr << "fixed-slot post mismatch event=" << event
                          << " track=" << track << " algo=" << algo
                          << " mode=" << mode << " split=" << split << '\n';
                return 13;
            }
            for (size_t i = 160u; i < 336u; ++i) {
                if (*(const uint8_t *)(slot + i) != 0xa5u) {
                    std::cerr << "fixed-slot tail clobber event=" << event
                              << " tail+" << (i - 160u) << '\n';
                    return 14;
                }
            }

            matrix[voice][engine] += 16u;
            split_mask[voice][engine] |= (uint16_t)(1u << split);
            samples += 16u;
        }
        if (U32(0x80001c80u) != cursor_base + 4u * 160u) {
            std::cerr << "four-voice frame span mismatch frame=" << frame << '\n';
            return 15;
        }
    }

    if (!early_trigger_cases || !boundary_trigger_cases) {
        std::cerr << "trigger-half coverage failure early=" << early_trigger_cases
                  << " boundary=" << boundary_trigger_cases << '\n';
        return 16;
    }

    std::cout << "PERKY production pk_render integration: PASS " << frames
              << " four-voice frames / " << events << " voice events / "
              << samples << " samples\n";
    std::cout << "  exact two-segment PCM committed to measured fixed track slot; moving cursor is reservation-only\n";
    std::cout << "  160-byte source payload exact; trailing 176/336 bytes untouched\n";
    std::cout << "  trigger latch covered " << early_trigger_cases
              << " first-half-only and " << boundary_trigger_cases
              << " boundary-half-only triggered events\n";
    for (unsigned voice = 0; voice < 4u; ++voice) {
        std::cout << "  voice " << voice << ':';
        for (unsigned local = 0; local < pk4_voice_len(voice); ++local) {
            const unsigned engine = (unsigned)pk4_voice_engine(voice, local);
            if (!matrix[voice][engine] || split_mask[voice][engine] != 0xffffu) {
                std::cerr << "\ncoverage failure voice=" << voice
                          << " local=" << local << " engine=" << engine
                          << " splitmask=0x" << std::hex
                          << split_mask[voice][engine] << std::dec << '\n';
                return 20;
            }
            std::cout << " algo" << local << "(engine" << engine << ")="
                      << matrix[voice][engine];
        }
        std::cout << " samples; all 16 split offsets\n";
    }
    return 0;
}
