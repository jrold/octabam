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
    constexpr std::array<unsigned, 4> tracks = {0u, 1u, 4u, 5u};

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
    std::array<std::array<uint64_t, 4>, 4> matrix{};
    std::array<std::array<uint16_t, 4>, 4> split_mask{};
    uint64_t samples = 0;

    for (unsigned frame = 0; frame < frames; ++frame) {
        U32(0x80001c80u) = cursor_base;
        std::memset((void *)cursor_base, 0xa5, 1024u);

        for (unsigned voice = 0; voice < 4u; ++voice) {
            const unsigned event = frame * 4u + voice;
            const unsigned track = tracks[voice];
            const unsigned step = frame;
            const unsigned algo = (step + voice * 3u) & 3u;
            const unsigned mode = (step * 2u + voice) % 3u;
            const unsigned split = ((step >> 2) + voice * 3u + algo * 5u) & 15u;
            const int trig = (event % 5u) != 0u;
            const uint8_t src[6] = {
                (uint8_t)((step * 17u + voice * 11u) & 127u),
                (uint8_t)((step * 29u + voice * 7u) & 127u),
                (uint8_t)((step * 43u + voice * 5u) & 127u),
                (uint8_t)((step * 61u + voice * 3u) & 127u),
                (uint8_t)mode,
                (uint8_t)algo,
            };

            for (unsigned i = 0; i < 6u; ++i)
                U16(0x80008000u + 2u * i) = (uint16_t)src[i] << 8;
            U8(0x46104d0cu + track) = trig ? 16u : 0u;
            const uintptr_t voice_cursor = U32(0x80001c80u);

            std::array<int16_t, 16> pre{}, post{};
            std::array<uint32_t, 36> expected_pre{}, expected_post{};
            if (!pk4_process_segment(&reference, voice, nullptr, 0, trig,
                                     255u, 45u, pre.data(), split))
                return 3;
            if (!pk4_process_segment(&reference, voice, src, 1, trig,
                                     255u, 45u, post.data(), 16u - split))
                return 4;
            const uint32_t pre_longs =
                pk4_encode_stock_segment(expected_pre.data(), pre.data(), split);
            const uint32_t post_longs =
                pk4_encode_stock_segment(expected_post.data(), post.data(), 16u - split);

            if (pk_render(track, event & 1u, 0u, split) != 0
                || pk_render(track, event & 1u, split, 16u) != 0) {
                std::cerr << "pk_render failed event=" << event << '\n';
                return 5;
            }
            if (std::memcmp((void *)voice_cursor, expected_pre.data(), pre_longs * 4u)) {
                std::cerr << "pre record mismatch event=" << event
                          << " track=" << track << " algo=" << algo
                          << " mode=" << mode << " split=" << split << '\n';
                return 10;
            }
            if (std::memcmp((void *)(voice_cursor + pre_longs * 4u),
                            expected_post.data(), post_longs * 4u)) {
                std::cerr << "post record mismatch event=" << event
                          << " track=" << track << " algo=" << algo
                          << " mode=" << mode << " split=" << split << '\n';
                return 11;
            }
            if (U32(0x80001c80u) != voice_cursor + (pre_longs + post_longs) * 4u)
                return 12;
            if (pre_longs + post_longs != 40u)
                return 13;

            matrix[voice][algo] += 16u;
            split_mask[voice][algo] |= (uint16_t)(1u << split);
            samples += 16u;
        }
        if (U32(0x80001c80u) != cursor_base + 4u * 160u) {
            std::cerr << "four-voice frame span mismatch frame=" << frame << '\n';
            return 14;
        }
    }

    std::cout << "PERKY production pk_render integration: PASS " << frames
              << " four-voice frames / " << events << " voice events / "
              << samples << " samples\n";
    std::cout << "  exact two-segment stock records; 160 bytes/voice and 640-byte four-voice frame span preserved\n";
    for (unsigned voice = 0; voice < 4u; ++voice) {
        std::cout << "  voice " << voice << ':';
        for (unsigned algo = 0; algo < 4u; ++algo) {
            if (!matrix[voice][algo] || split_mask[voice][algo] != 0xffffu) {
                std::cerr << "\ncoverage failure voice=" << voice
                          << " algo=" << algo << " splitmask=0x" << std::hex
                          << split_mask[voice][algo] << std::dec << '\n';
                return 20;
            }
            std::cout << " algo" << algo << '=' << matrix[voice][algo];
        }
        std::cout << " samples; all 16 split offsets\n";
    }
    return 0;
}
