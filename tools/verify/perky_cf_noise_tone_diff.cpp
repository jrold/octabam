#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
#include <vector>

#include "NativeV121NoiseTone.h"
#include "NativeV121NoiseToneShared.h"
extern "C" {
#include "cf_noise_tone.h"
}

static std::vector<uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f)
        throw std::runtime_error("cannot open " + path);
    return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)), {});
}

static void wr16(uint8_t* p, uint16_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}

static void wr32(uint8_t* p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::cerr << "usage: perky_cf_noise_tone_diff <asset-dir>\n";
        return 2;
    }
    const std::string dir = argv[1];
    auto e1v = read_file(dir + "/envelope1.bin");
    auto e2v = read_file(dir + "/envelope2.bin");
    auto m1v = read_file(dir + "/m1.bin");
    std::array<std::vector<uint8_t>, 4> wv = {
        read_file(dir + "/w0.bin"), read_file(dir + "/w1.bin"),
        read_file(dir + "/w2.bin"), read_file(dir + "/w3.bin")
    };
    if (e1v.size() != 4096 || e2v.size() != 4096 || m1v.size() != 4096)
        return 3;
    for (const auto& w : wv)
        if (w.size() != 512)
            return 3;

    NativeV121NoiseToneShared::EnvelopeTable e1 {}, e2 {};
    NativeV121NoiseToneWaveform2::WaveTable m1a {}, m1b {};
    std::memcpy(e1.data(), e1v.data(), 4096);
    std::memcpy(e2.data(), e2v.data(), 4096);
    std::memcpy(m1a.data(), m1v.data(), 4096);
    std::memcpy(m1b.data(), m1v.data(), 4096);
    // A second legal-address table exercises current/next switching independently
    // of the one authentic M1 table used by v1.2.1.
    for (size_t i = 0; i < m1b.size(); i += 2) {
        int16_t s = (int16_t)((uint16_t)m1b[i] | ((uint16_t)m1b[i + 1] << 8));
        s = (int16_t)-s;
        m1b[i] = (uint8_t)s;
        m1b[i + 1] = (uint8_t)((uint16_t)s >> 8);
    }

    std::array<NativeV121NoiseToneShared::WaveTable, 4> waves {};
    for (int i = 0; i < 4; ++i)
        std::memcpy(waves[(size_t)i].data(), wv[(size_t)i].data(), 512);
    constexpr std::array<uint32_t, 4> addrs = {
        0x080222a0u, 0x080224a0u, 0x080226a0u, 0x080228a0u
    };
    NativeV121NoiseToneShared::Tables rt {};
    rt.envelope1 = &e1; rt.envelope2 = &e2;
    pk_cf_nt_shared_tables ct {};
    ct.envelope1 = e1v.data(); ct.envelope2 = e2v.data();
    for (int i = 0; i < 4; ++i) {
        rt.waves[(size_t)i] = {addrs[(size_t)i], &waves[(size_t)i]};
        ct.waves[(size_t)i] = {addrs[(size_t)i], wv[(size_t)i].data()};
    }

    std::mt19937 random(0x5045524b);
    auto byte = [&]() { return (uint8_t)(random() & 0xffu); };
    auto u16 = [&]() { return (uint16_t)random(); };
    auto u32 = [&]() { return (uint32_t)random(); };
    constexpr int cases = 1000;
    constexpr int samples = 128;

    for (int tc = 0; tc < cases; ++tc) {
        NativeV121NoiseToneShared::State a {};
        for (auto& x : a) x = byte();
        a[0x74] = (uint8_t)(random() % 5); a[0x75] = (uint8_t)(random() % 3);
        a[0x78] = (uint8_t)(random() & 1); a[0x7a] = (uint8_t)(random() & 1);
        a[0x7b] = (uint8_t)(random() & 1); a[0x84] = (uint8_t)(random() & 1);
        wr32(a.data() + 0x80, u32() % 0x110000u);
        wr16(a.data() + 0x94, u16()); wr16(a.data() + 0x96, u16());
        wr16(a.data() + 0x60, (uint16_t)(random() % 32));
        wr16(a.data() + 0x62, (uint16_t)(random() % 32));
        wr16(a.data() + 0x70, u16());
        wr16(a.data() + 0xa8, u16()); wr16(a.data() + 0xaa, u16());
        wr32(a.data() + 0xac, (uint32_t)(int32_t)(int16_t)u16());
        wr32(a.data() + 0xb0, (uint32_t)(int32_t)(int16_t)u16());
        wr32(a.data() + 0xb4, (uint32_t)(int32_t)(int16_t)u16());
        wr32(a.data() + 0xf8, random() % 4096u);
        a[6] = (uint8_t)(1 + random() % 255);
        for (size_t base : {size_t(0x2c), size_t(0xc4)}) {
            wr32(a.data() + base + 4, random() % 0x100001u);
            wr32(a.data() + base + 8, random() % 0x40000u);
            wr32(a.data() + base + 0x0c, addrs[random() % 4]);
            wr32(a.data() + base + 0x10, addrs[random() % 4]);
        }
        auto b = a;
        NativeV121NoiseToneShared::RngState rr {u32(), u32()};
        pk_cf_nt_rng cr {rr.low, rr.high};
        std::array<int16_t, samples> ro {}, co {};
        const bool okr = NativeV121NoiseToneShared::renderBlock(a, ro.data(), samples, rt, rr);
        const int okc = pk_cf_nt_shared_render(b.data(), co.data(), samples, &ct, &cr);
        if (!okr || !okc || ro != co || a != b || rr.low != cr.low || rr.high != cr.high) {
            std::cerr << "shared mismatch case " << tc << "\n";
            return 10;
        }
    }
    std::cout << "shared: " << cases * samples << " samples bit-exact PCM/state/RNG\n";

    constexpr uint32_t ma = 0x080310e0u, mb = 0x080320e0u;
    for (int tc = 0; tc < cases; ++tc) {
        NativeV121NoiseToneWaveform2::State a {};
        for (auto& x : a) x = byte();
        a[0x75] = 0; a[0x74] = (uint8_t)(random() % 5);
        a[0x78] = (uint8_t)(random() & 1); a[0x7a] = (uint8_t)(random() & 1);
        a[0x7b] = (uint8_t)(random() & 1); a[0x84] = (uint8_t)(random() & 1);
        a[0xb8] = (uint8_t)((random() % 20) == 0);
        wr32(a.data() + 0x80, u32() % 0x110000u);
        wr16(a.data() + 0x94, u16()); wr16(a.data() + 0x96, u16());
        a[6] = (uint8_t)(1 + random() % 255);
        wr32(a.data() + 0xc8, random() % 0x20000u);
        wr32(a.data() + 0xd8, random() % 0x100001u);
        wr32(a.data() + 0xdc, random() % 0x40000u);
        wr32(a.data() + 0xe0, random() % 0x100001u);
        wr32(a.data() + 0xe4, (random() & 1) ? ma : mb);
        wr32(a.data() + 0xe8, (random() & 1) ? ma : mb);
        auto b = a;
        std::array<int16_t, samples> ro {}, co {};
        const bool okr = NativeV121NoiseToneWaveform2::renderBlock(
            a, ro.data(), samples, m1a, ma, m1b, mb);
        const int okc = pk_cf_nt_m1_render(
            b.data(), co.data(), samples, m1v.data(), ma, m1b.data(), mb);
        if (!okr || !okc || ro != co || a != b) {
            std::cerr << "M1 mismatch case " << tc << "\n";
            return 11;
        }
    }
    std::cout << "M1: " << cases * samples << " samples bit-exact PCM/state\n";
    std::cout << "PERKY ColdFire Noise/Tone native differential: PASS\n";
    return 0;
}
