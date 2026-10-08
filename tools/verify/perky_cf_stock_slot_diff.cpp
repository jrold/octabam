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
int pk_render(unsigned, unsigned, unsigned, unsigned);
void pk_stock_pool_open(void) {}
int pk_stock_validate(void *) { return 1; }
}

#define U8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define U16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))

static void map_region(uintptr_t at, size_t size)
{
    void *p = mmap((void *)at, size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p != (void *)at) { perror("mmap"); std::exit(2); }
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
    constexpr uintptr_t staging = 0x80008000u;
    constexpr std::array<unsigned,4> tracks = {0u,1u,4u,5u};
    constexpr size_t slot_bytes = 336u;
    constexpr size_t source_bytes = 160u;
    constexpr size_t tail_bytes = slot_bytes - source_bytes;
    constexpr unsigned rounds = 32u;

    U32(0x46c82456u) = bank;
    U8(0x100b14cfu) = 0u;
    U32(0x800062a8u) = staging;
    for (unsigned t : tracks) sign_track(part, t);

    uint64_t cases = 0;
    for (unsigned round=0; round<rounds; ++round) {
        for (unsigned voice=0; voice<tracks.size(); ++voice) {
            unsigned track=tracks[voice];
            for (unsigned ping=0; ping<2; ++ping) {
                for (unsigned split=0; split<16; ++split) {
                    const unsigned algo=(round+voice+split)&3u;
                    const unsigned mode=(round*2u+voice+split)%3u;
                    const uint8_t src[6] = {
                        (uint8_t)((17u*round + 11u*split + voice)&127u),
                        (uint8_t)((29u*round + 7u*split + voice)&127u),
                        (uint8_t)((43u*round + 5u*split + voice)&127u),
                        (uint8_t)((61u*round + 3u*split + voice)&127u),
                        (uint8_t)mode, (uint8_t)algo
                    };
                    for (unsigned i=0;i<6;++i) U16(staging+2u*i)=(uint16_t)src[i]<<8;
                    U8(0x46104d0cu+track)=16u;

                    const uintptr_t slot = 0x80001c90u + (uintptr_t)ping*0xa80u
                                         + (uintptr_t)slot_bytes*track;
                    std::memset((void *)slot, 0xa5, slot_bytes);
                    U32(0x80001c80u)=(uint32_t)slot;

                    if (pk_render(track,ping,0u,split)!=0 ||
                        pk_render(track,ping,split,16u)!=0) {
                        std::cerr << "render failure track="<<track<<" ping="<<ping<<" split="<<split<<"\n";
                        return 3;
                    }
                    if (U32(0x80001c80u) != slot + source_bytes) {
                        std::cerr << "cursor overflow/underflow track="<<track<<" ping="<<ping
                                  <<" split="<<split<<" got=0x"<<std::hex<<U32(0x80001c80u)
                                  <<" want=0x"<<(slot+source_bytes)<<std::dec<<"\n";
                        return 4;
                    }
                    const uint8_t *tail=(const uint8_t *)(slot+source_bytes);
                    for (size_t i=0;i<tail_bytes;++i) {
                        if (tail[i] != 0xa5) {
                            std::cerr << "slot tail clobber track="<<track<<" ping="<<ping
                                      <<" split="<<split<<" at tail+"<<i<<"\n";
                            return 5;
                        }
                    }
                    ++cases;
                }
            }
        }
    }
    std::cout << "PERKY stock packer slot isolation: PASS " << cases << " cases\n"
              << "  T1/T2/T5/T6; both ping buffers; all 16 event splits\n"
              << "  source callback consumes exactly 160/336 bytes; trailing 176 bytes untouched\n";
    return 0;
}
