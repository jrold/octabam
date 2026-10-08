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

static void map_region(uintptr_t at, size_t size) {
    void *p = mmap((void *)at, size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p != (void *)at) { perror("mmap"); std::exit(2); }
}

static unsigned source_offset(unsigned track, unsigned slot) {
    return (slot < 6u ? 0x2au : 0x1dau) + 30u * track + 6u + slot % 6u;
}

static void sign_track(uintptr_t part, unsigned track) {
    U8(part + 0x22u + track) = 1u;
    U8(part + 60u + 30u * track) = 'P';
    U8(part + 61u + 30u * track) = 'K';
    U8(part + 62u + 30u * track) = 1u;
}

static pk4_assets make_assets() {
    pk4_assets a{};
    a.pitch = pk_asset_pitch;
    a.chromatic = pk_asset_chromatic;
    a.envelope1 = pk_asset_envelope1;
    a.envelope2 = pk_asset_envelope2;
    a.waves[0] = {0x080222a0u, pk_asset_wave0};
    a.waves[1] = {0x080224a0u, pk_asset_wave1};
    a.waves[2] = {0x080226a0u, pk_asset_wave2};
    a.waves[3] = {0x080228a0u, pk_asset_wave3};
    a.m1_wave = pk_asset_m1_wave;
    a.m1_wave_address = 0x080310e0u;
    return a;
}

static std::array<uint8_t, 6> to_engine_src(const uint8_t page[6]) {
    return {page[1], page[0], page[3], page[4], page[5], page[2]};
}

static void stage(const uint8_t src[6]) {
    constexpr uintptr_t stage_base = 0x80008000u;
    U32(0x800062a8u) = stage_base;
    for (unsigned i = 0; i < 6u; ++i)
        U16(stage_base + 2u * i) = (uint16_t)src[i] << 8;
}

static bool stage_unchanged(const uint8_t src[6]) {
    constexpr uintptr_t stage_base = 0x80008000u;
    for (unsigned i = 0; i < 6u; ++i)
        if (U16(stage_base + 2u * i) != (uint16_t)src[i] << 8)
            return false;
    return true;
}

static int one_event(pk4_engine &reference, unsigned voice, unsigned track,
                     const uint8_t src[6], uintptr_t cursor) {
    std::array<int16_t, 16> pcm{};
    std::array<uint32_t, 36> expected{};
    const auto engine = to_engine_src(src);
    if (!pk4_process_segment(&reference, voice, engine.data(), 1, 1, 255u, 45u,
                             pcm.data(), 16u))
        return 20;
    if (pk4_encode_stock_segment(expected.data(), pcm.data(), 16u) != 36u)
        return 21;

    stage(src);
    U8(0x46104d0cu + track) = 16u;
    U32(0x80001c80u) = (uint32_t)cursor;
    std::memset((void *)cursor, 0xa5, 192u);
    if (pk_render(track, 0u, 0u, 16u) != 0)
        return 22;
    U8(0x46104d0cu + track) = 0u;
    if (std::memcmp((void *)cursor, expected.data(), 36u * 4u))
        return 23;
    if (U32(0x80001c80u) != cursor + 36u * 4u)
        return 24;
    if (!stage_unchanged(src))
        return 25;
    return 0;
}

int main() {
    map_region(0x10000000u, 0x00200000u);
    map_region(0x46000000u, 0x04000000u);
    map_region(0x80000000u, 0x01000000u);

    constexpr uint32_t bank_a = 0x48000000u;
    constexpr uint32_t bank_b = 0x49000000u;
    constexpr uintptr_t part_off = 0x8ed80u;
    constexpr uintptr_t cursor = 0x80010000u;
    constexpr std::array<unsigned, 4> tracks = {0u, 1u, 4u, 5u};
    const pk4_assets assets = make_assets();

    for (uint32_t bank : {bank_a, bank_b})
        for (unsigned track : tracks)
            sign_track(bank + part_off, track);

    uint64_t cases = 0, events = 0, samples = 0;
    for (unsigned voice = 0; voice < 4u; ++voice) {
        const unsigned track = tracks[voice];
        const uint8_t default_algo = (uint8_t)((voice + 1u) & 3u);
        const uint8_t default_mode = (uint8_t)((voice + 1u) % 3u);
        /* Shipping page order: tune,decay,algo,p1,p2,mode. */
        const uint8_t defaults[6] = {
            (uint8_t)(51u + voice * 7u),
            (uint8_t)(37u + voice * 9u),
            default_algo,
            (uint8_t)(65u + voice * 5u),
            (uint8_t)(79u + voice * 3u),
            default_mode,
        };

        for (unsigned locked_algo = 0; locked_algo < 4u; ++locked_algo) {
            for (unsigned locked_mode = 0; locked_mode < 3u; ++locked_mode) {
                if (locked_algo == default_algo && locked_mode == default_mode)
                    continue;

                /* Alternate bank every case so the shipping global runtime starts cold. */
                const uint32_t bank = (cases & 1u) ? bank_b : bank_a;
                const uintptr_t part = bank + part_off;
                U32(0x46c82456u) = bank;
                U8(0x100b14cfu) = 0u;

                for (unsigned i = 0; i < 6u; ++i)
                    U8(part + source_offset(track, i)) = defaults[i];
                std::array<uint8_t, 6> persistent{};
                for (unsigned i = 0; i < 6u; ++i)
                    persistent[i] = U8(part + source_offset(track, i));

                pk4_engine reference{};
                pk4_init(&reference, &assets);

                int rc = one_event(reference, voice, track, defaults, cursor);
                if (rc) {
                    std::cerr << "default-before failed voice=" << voice
                              << " algo=" << locked_algo << " mode=" << locked_mode
                              << " rc=" << rc << '\n';
                    return rc;
                }

                uint8_t locked[6];
                std::memcpy(locked, defaults, sizeof locked);
                locked[0] ^= 0x1fu;
                locked[3] ^= 0x35u;
                locked[2] = (uint8_t)locked_algo;
                locked[5] = (uint8_t)locked_mode;
                rc = one_event(reference, voice, track, locked, cursor);
                if (rc) {
                    std::cerr << "locked failed voice=" << voice
                              << " algo=" << locked_algo << " mode=" << locked_mode
                              << " rc=" << rc << '\n';
                    return 30 + rc;
                }

                rc = one_event(reference, voice, track, defaults, cursor);
                if (rc) {
                    std::cerr << "default-after failed voice=" << voice
                              << " algo=" << locked_algo << " mode=" << locked_mode
                              << " rc=" << rc << '\n';
                    return 60 + rc;
                }

                for (unsigned i = 0; i < 6u; ++i) {
                    const uint8_t got = U8(part + source_offset(track, i));
                    if (got != persistent[i]) {
                        std::cerr << "persistent SRC mutation voice=" << voice
                                  << " slot=" << i << " got=" << (unsigned)got
                                  << " want=" << (unsigned)persistent[i] << '\n';
                        return 100;
                    }
                }
                ++cases;
                events += 3u;
                samples += 48u;
            }
        }
    }

    if (cases != 44u) {
        std::cerr << "coverage mismatch cases=" << cases << '\n';
        return 110;
    }
    std::cout << "PERKY p-lock reversion: PASS " << cases << " voice/lock cases / "
              << events << " events / " << samples << " exact samples\n"
              << "  default -> locked Algo/Mode -> default returned to reference PCM; "
                 "shipping callback did not mutate staging or persistent SRC defaults\n";
    return 0;
}
