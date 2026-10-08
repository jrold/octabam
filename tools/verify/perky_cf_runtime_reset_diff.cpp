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

static void sign_track(uintptr_t part, unsigned track) {
    U8(part + 0x22u + track) = 1u;
    U8(part + 60u + 30u * track) = 'P';
    U8(part + 61u + 30u * track) = 'K';
    U8(part + 62u + 30u * track) = 1u;
}

static uintptr_t fixed_slot(unsigned track, unsigned ping) {
    return 0x80001c90u + (uintptr_t)(ping & 1u) * 0xa80u
         + (uintptr_t)336u * track;
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

static bool render_reference(const pk4_assets &assets, unsigned voice,
                             const uint8_t page_src[6], int trig,
                             std::array<uint32_t, 40> &out) {
    pk4_engine e{};
    pk4_init(&e, &assets);
    const auto engine_src = to_engine_src(page_src);
    std::array<int16_t, 16> pcm{};
    std::array<uint32_t, 4> pre{};
    std::array<uint32_t, 36> post{};
    if (!pk4_process_segment(&e, voice, engine_src.data(), 1, trig,
                             255u, 45u, pcm.data(), 16u))
        return false;
    if (pk4_encode_stock_segment(pre.data(), pcm.data(), 0u) != 4u)
        return false;
    if (pk4_encode_stock_segment(post.data(), pcm.data(), 16u) != 36u)
        return false;
    std::memcpy(out.data(), pre.data(), 4u * sizeof(uint32_t));
    std::memcpy(out.data() + 4u, post.data(), 36u * sizeof(uint32_t));
    return true;
}

static int first_event(const pk4_assets &assets, uint32_t bank, unsigned part_idx,
                       unsigned track, unsigned voice, const uint8_t src[6],
                       uintptr_t cursor_base) {
    constexpr uintptr_t stage = 0x80008000u;
    U32(0x46c82456u) = bank;
    U8(0x100b14cfu) = (uint8_t)part_idx;
    U32(0x800062a8u) = stage;
    for (unsigned i = 0; i < 6; ++i) U16(stage + i * 2u) = (uint16_t)src[i] << 8;
    U8(0x46104d0cu + track) = 16u;
    U32(0x80001c80u) = (uint32_t)cursor_base;
    std::memset((void *)cursor_base, 0xa5, 256u);
    const uintptr_t slot = fixed_slot(track, 0u);
    std::memset((void *)slot, 0xa5, 336u);

    std::array<uint32_t, 40> expected{};
    if (!render_reference(assets, voice, src, 1, expected)) return 30;
    if (pk_render(track, 0u, 0u, 16u) != 0) return 31;
    U8(0x46104d0cu + track) = 0u;
    if (std::memcmp((void *)slot, expected.data(), 40u * 4u)) {
        std::cerr << "cold-reset fixed-slot PCM mismatch part=" << part_idx
                  << " voice=" << voice << " algo=" << (unsigned)src[2] << '\n';
        return 32;
    }
    if (U32(0x80001c80u) != cursor_base + 40u * 4u) return 33;
    for (unsigned i = 0; i < 40u; ++i)
        if (U32(cursor_base + i * 4u) != 0u) return 34;
    for (unsigned i = 160u; i < 336u; ++i)
        if (U8(slot + i) != 0xa5u) return 35;
    return 0;
}

int main() {
    map_region(0x10000000u, 0x00200000u);
    map_region(0x46000000u, 0x04000000u);
    map_region(0x80000000u, 0x01000000u);

    constexpr uint32_t bank_a = 0x48000000u;
    constexpr uint32_t bank_b = 0x49000000u;
    constexpr uintptr_t part_off = 0x8ed80u;
    constexpr uintptr_t part_stride = 0x18b2u;
    constexpr uintptr_t cursor = 0x80010000u;
    constexpr std::array<unsigned,4> tracks={0u,1u,4u,5u};
    const auto assets = make_assets();

    // Sign the four Perky tracks in two Parts of bank A and one Part of bank B.
    for (unsigned pi : {0u,1u})
        for (unsigned t : tracks) sign_track(bank_a + part_off + pi * part_stride, t);
    for (unsigned t : tracks) sign_track(bank_b + part_off, t);

    uint64_t cases = 0;
    for (unsigned voice = 0; voice < 4u; ++voice) {
        const unsigned track = tracks[voice];
        for (unsigned algo = 0; algo < 4u; ++algo) {
            /* Shipping page order: tune,decay,algo,p1,p2,mode. */
            uint8_t src[6] = {
                (uint8_t)(31u + voice * 13u + algo * 3u),
                (uint8_t)(17u + voice * 19u + algo),
                (uint8_t)algo,
                (uint8_t)(47u + voice * 7u + algo * 5u),
                (uint8_t)(61u + voice * 5u + algo * 7u),
                (uint8_t)((voice + algo) % 3u),
            };

            // Establish and dirty Part 0 runtime with two events.
            int rc = first_event(assets, bank_a, 0u, track, voice, src, cursor);
            if (rc) return rc;
            src[0] ^= 0x3fu; src[3] ^= 0x55u;
            for (unsigned i=0;i<6;i++) U16(0x80008000u + i*2u)=(uint16_t)src[i]<<8;
            U8(0x46104d0cu + track)=16u;
            U32(0x80001c80u)=cursor;
            std::memset((void *)cursor, 0xa5, 256u);
            std::memset((void *)fixed_slot(track, 0u), 0xa5, 336u);
            if (pk_render(track,0u,0u,16u)!=0) return 40;
            U8(0x46104d0cu + track)=0u;

            // A Part switch must start from a fresh four-voice runtime.
            src[0] ^= 0x12u; src[1] ^= 0x29u;
            rc = first_event(assets, bank_a, 1u, track, voice, src, cursor);
            if (rc) return rc;

            // Switching back also cold-resets; no state from Part 1 or old Part 0 leaks.
            src[3] ^= 0x21u; src[4] ^= 0x37u;
            rc = first_event(assets, bank_a, 0u, track, voice, src, cursor);
            if (rc) return rc;

            // Bank change is the same invariant.
            src[0] ^= 0x0fu; src[4] ^= 0x1bu;
            rc = first_event(assets, bank_b, 0u, track, voice, src, cursor);
            if (rc) return rc;
            ++cases;
        }
    }

    std::cout << "PERKY production runtime reset: PASS " << cases
              << " voice/algo cases across Part A0->A1->A0 and Bank A->B\n"
              << "  every bank/part transition restarts from exact cold fixed-slot PCM; "
                 "moving cursor remains reservation-only; no cross-Part/Bank leakage\n";
    return 0;
}
