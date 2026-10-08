#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "NativeV121FoldDrums.h"
#include "NativeV121Karplus.h"
#include "NativeV121NoiseTone.h"
#include "NativeV121NoiseToneShared.h"
extern "C" {
#include "cf_perky4.h"
}

static std::vector<std::uint8_t> read_file(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return {std::istreambuf_iterator<char>(f), {}};
}

static std::uint32_t le32(const std::uint8_t* p)
{
    return (std::uint32_t)p[0] | ((std::uint32_t)p[1] << 8)
        | ((std::uint32_t)p[2] << 16) | ((std::uint32_t)p[3] << 24);
}

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::cerr << "usage: perky4_control_pcm_diff <asset-dir> <fixture-dir>\n";
        return 2;
    }
    const std::string ad = argv[1], fd = argv[2];
    auto pitchv = read_file(ad + "/pitch.bin");
    auto chromv = read_file(ad + "/chromatic.bin");
    auto e1v = read_file(ad + "/envelope1.bin");
    auto e2v = read_file(ad + "/envelope2.bin");
    auto m1v = read_file(ad + "/m1.bin");
    std::array<std::vector<std::uint8_t>, 4> wv = {
        read_file(ad + "/w0.bin"), read_file(ad + "/w1.bin"),
        read_file(ad + "/w2.bin"), read_file(ad + "/w3.bin")
    };
    if (pitchv.size() != 8192 || chromv.size() != 24 || e1v.size() != 4096
        || e2v.size() != 4096 || m1v.size() != 4096)
        return 3;
    for (const auto& w : wv) if (w.size() != 512) return 3;

    constexpr std::array<std::uint32_t, 4> addrs = {
        0x080222a0u, 0x080224a0u, 0x080226a0u, 0x080228a0u
    };
    pk4_assets assets{};
    assets.pitch = pitchv.data();
    assets.chromatic = chromv.data();
    assets.envelope1 = e1v.data();
    assets.envelope2 = e2v.data();
    assets.m1_wave = m1v.data();
    assets.m1_wave_address = 0x080310e0u;
    for (unsigned i = 0; i < 4; ++i)
        assets.waves[i] = {addrs[i], wv[i].data()};

    NativeV121FoldDrums::PitchTable fp{};
    NativeV121FoldDrums::EnvelopeTable fe1{}, fe2{};
    std::array<NativeV121FoldDrums::WaveTable, 4> fw{};
    std::memcpy(fp.data(), pitchv.data(), fp.size());
    std::memcpy(fe1.data(), e1v.data(), fe1.size());
    std::memcpy(fe2.data(), e2v.data(), fe2.size());
    NativeV121FoldDrums::Tables ft{};
    ft.pitch = &fp; ft.envelope1 = &fe1; ft.envelope2 = &fe2;
    for (unsigned i = 0; i < 4; ++i) {
        std::memcpy(fw[i].data(), wv[i].data(), fw[i].size());
        ft.waves[i] = {addrs[i], &fw[i]};
    }

    NativeV121Karplus::EnvelopeTable ke1{}, ke2{};
    std::memcpy(ke1.data(), e1v.data(), ke1.size());
    std::memcpy(ke2.data(), e2v.data(), ke2.size());
    NativeV121Karplus::Tables kt{&ke1, &ke2};

    NativeV121NoiseToneShared::EnvelopeTable ne1{}, ne2{};
    std::array<NativeV121NoiseToneShared::WaveTable, 4> nw{};
    std::memcpy(ne1.data(), e1v.data(), ne1.size());
    std::memcpy(ne2.data(), e2v.data(), ne2.size());
    NativeV121NoiseToneShared::Tables nt{};
    nt.envelope1 = &ne1; nt.envelope2 = &ne2;
    for (unsigned i = 0; i < 4; ++i) {
        std::memcpy(nw[i].data(), wv[i].data(), nw[i].size());
        nt.waves[i] = {addrs[i], &nw[i]};
    }
    NativeV121NoiseToneWaveform2::WaveTable m1{};
    std::memcpy(m1.data(), m1v.data(), m1.size());

    constexpr unsigned samples_per_case = 128;
    std::array<std::uint64_t, 4> engine_samples{};
    std::array<std::uint64_t, 3> nt_mode_samples{};

    auto fk = read_file(fd + "/fold_karp_control_fixtures.bin");
    if (fk.size() < 8 || std::memcmp(fk.data(), "PKCT", 4) != 0) return 4;
    std::size_t pos = 8;
    while (pos < fk.size()) {
        if (pos + 8 > fk.size()) return 5;
        const unsigned algo = fk[pos], mode = fk[pos + 1];
        const unsigned ctl = fk[pos + 2], value = fk[pos + 3];
        const std::uint32_t bytes = le32(fk.data() + pos + 4);
        pos += 8;
        if (pos + bytes > fk.size() || algo >= 3) return 5;
        const std::uint8_t* expected = fk.data() + pos;
        pos += bytes;
        std::uint8_t raw[4] = {64, 64, 64, 64};
        raw[ctl] = (std::uint8_t)value;

        pk4_engine e{};
        pk4_init(&e, &assets);
        if (!pk4_prepare_event(&e, 0, raw[1], raw[0], raw[2], raw[3],
                               (std::uint8_t)mode, (std::uint8_t)algo,
                               255, 45, 1))
            return 6;
        pk4_track& track = e.tracks[0];
        const std::uint8_t* got_state = algo == PK4_ALGO_FOLD1 ? track.fold1
            : algo == PK4_ALGO_FOLD2 ? track.fold2 : track.karplus;
        const std::size_t got_bytes = algo == PK4_ALGO_FOLD1 ? sizeof track.fold1
            : algo == PK4_ALGO_FOLD2 ? sizeof track.fold2 : sizeof track.karplus;
        if (got_bytes != bytes || std::memcmp(got_state, expected, bytes) != 0) {
            std::cerr << "production state mismatch algo=" << algo << " mode=" << mode
                      << " ctl=" << ctl << " value=" << value << "\n";
            return 10;
        }

        const std::uint32_t rlo = track.rng_low, rhi = track.rng_high;
        std::array<std::int16_t, samples_per_case> ref{}, got{};
        if (algo == PK4_ALGO_FOLD1) {
            NativeV121FoldDrums::Fold1State s{};
            std::memcpy(s.data(), expected, bytes);
            NativeV121FoldDrums::RngState rng{rlo, rhi};
            if (!NativeV121FoldDrums::renderFold1(s, ref.data(), samples_per_case, ft, rng)
                || !pk4_render(&e, 0, got.data(), samples_per_case)
                || ref != got || std::memcmp(s.data(), track.fold1, bytes) != 0
                || rng.low != track.rng_low || rng.high != track.rng_high)
                return 11;
        } else if (algo == PK4_ALGO_FOLD2) {
            NativeV121FoldDrums::Fold2State s{};
            std::memcpy(s.data(), expected, bytes);
            NativeV121FoldDrums::RngState rng{rlo, rhi};
            if (!NativeV121FoldDrums::renderFold2(s, 0x20000000u, ref.data(), samples_per_case, ft, rng)
                || !pk4_render(&e, 0, got.data(), samples_per_case)
                || ref != got || std::memcmp(s.data(), track.fold2, bytes) != 0
                || rng.low != track.rng_low || rng.high != track.rng_high)
                return 12;
        } else {
            NativeV121Karplus::State s{};
            std::memcpy(s.data(), expected, bytes);
            NativeV121Karplus::RngState rng{rlo, rhi};
            if (!NativeV121Karplus::renderBlock(s, ref.data(), samples_per_case, kt, rng)
                || !pk4_render(&e, 0, got.data(), samples_per_case)
                || ref != got || std::memcmp(s.data(), track.karplus, bytes) != 0
                || rng.low != track.rng_low || rng.high != track.rng_high)
                return 13;
        }
        engine_samples[algo] += samples_per_case;
    }

    auto ntx = read_file(fd + "/nt_control_fixtures.bin");
    if (ntx.size() < 8 || std::memcmp(ntx.data(), "NTC1", 4) != 0) return 20;
    const std::uint32_t nrec = le32(ntx.data() + 4);
    pos = 8;
    for (std::uint32_t rec = 0; rec < nrec; ++rec) {
        if (pos + 4 + PK_CF_NT_STATE_BYTES + 8 > ntx.size()) return 21;
        const unsigned mode = ntx[pos], ctl = ntx[pos + 1], value = ntx[pos + 2];
        pos += 4;
        const std::uint8_t* expected = ntx.data() + pos;
        pos += PK_CF_NT_STATE_BYTES + 8;
        std::uint8_t raw[4] = {64, 64, 64, 64};
        raw[ctl] = (std::uint8_t)value;

        pk4_engine e{};
        pk4_init(&e, &assets);
        if (!pk4_prepare_event(&e, 0, raw[1], raw[0], raw[2], raw[3],
                               (std::uint8_t)mode, PK4_ALGO_NOISE_TONE,
                               255, 45, 1))
            return 22;
        pk4_track& track = e.tracks[0];
        const std::uint8_t* got_state = mode == 0 ? track.nt_m1 : track.nt_shared;
        if (std::memcmp(got_state, expected, PK_CF_NT_STATE_BYTES) != 0) {
            std::cerr << "production Noise/Tone state mismatch mode=" << mode
                      << " ctl=" << ctl << " value=" << value << "\n";
            return 23;
        }

        const std::uint32_t rlo = track.rng_low, rhi = track.rng_high;
        std::array<std::int16_t, samples_per_case> ref{}, got{};
        if (mode == 0) {
            NativeV121NoiseToneWaveform2::State s{};
            std::memcpy(s.data(), expected, s.size());
            if (!NativeV121NoiseToneWaveform2::renderBlock(s, ref.data(), samples_per_case,
                    m1, 0x080310e0u, m1, 0x080310e0u)
                || !pk4_render(&e, 0, got.data(), samples_per_case)
                || ref != got || std::memcmp(s.data(), track.nt_m1, s.size()) != 0
                || track.rng_low != rlo || track.rng_high != rhi)
                return 24;
        } else {
            NativeV121NoiseToneShared::State s{};
            std::memcpy(s.data(), expected, s.size());
            NativeV121NoiseToneShared::RngState rng{rlo, rhi};
            if (!NativeV121NoiseToneShared::renderBlock(s, ref.data(), samples_per_case, nt, rng)
                || !pk4_render(&e, 0, got.data(), samples_per_case)
                || ref != got || std::memcmp(s.data(), track.nt_shared, s.size()) != 0
                || rng.low != track.rng_low || rng.high != track.rng_high)
                return 25;
        }
        engine_samples[PK4_ALGO_NOISE_TONE] += samples_per_case;
        nt_mode_samples[mode] += samples_per_case;
    }
    if (pos != ntx.size()) return 26;

    std::cout << "PERKY4 production OT-control -> PCM differential: PASS\n";
    std::cout << "  Fold1:     " << engine_samples[0] << " samples bit-exact PCM/state/RNG\n";
    std::cout << "  Fold2:     " << engine_samples[1] << " samples bit-exact PCM/state/RNG\n";
    std::cout << "  Karplus:   " << engine_samples[2] << " samples bit-exact PCM/state/RNG\n";
    std::cout << "  NoiseTone: " << engine_samples[3] << " samples bit-exact PCM/state/RNG\n";
    std::cout << "    M1=" << nt_mode_samples[0] << " M2=" << nt_mode_samples[1]
              << " M3=" << nt_mode_samples[2] << "\n";
    return 0;
}
