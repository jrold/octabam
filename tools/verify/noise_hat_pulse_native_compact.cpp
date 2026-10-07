// Local native-layout vs compact-state PCM differential for PĒRKONS v1.2.1
// Noise Hat / Pulse Stack. No firmware blob and no GitHub CI required.
//
// The left side intentionally uses the recovered ARM 0x160-byte object layout;
// the right side uses Octabam's 59-word compact layout.  In particular, ARM
// +0x136 is not separate state: it aliases the high 16 bits of the local u32
// LCG at +0x134.  This regression exists because treating +0x136 independently
// produced a real same-sample PCM/state bug when the LCG advanced.
#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>

using ArmState = std::array<std::uint8_t, 0x160>;
using EnvTable = std::array<std::uint8_t, 4096>;
using Compact = std::array<std::uint16_t, 59>;

static std::uint16_t u16(const ArmState& s, std::size_t o) {
    return std::uint16_t(s[o]) | std::uint16_t(s[o + 1] << 8);
}
static std::uint32_t u32(const ArmState& s, std::size_t o) {
    return std::uint32_t(u16(s, o)) | (std::uint32_t(u16(s, o + 2)) << 16);
}
static void put16(ArmState& s, std::size_t o, std::uint16_t v) {
    s[o] = v & 255; s[o + 1] = v >> 8;
}
static void put32(ArmState& s, std::size_t o, std::uint32_t v) {
    put16(s, o, v); put16(s, o + 2, v >> 16);
}
static std::int16_t s16(std::uint16_t v) { return std::bit_cast<std::int16_t>(v); }
static std::int32_t s32(std::uint32_t v) { return std::bit_cast<std::int32_t>(v); }
static std::uint32_t ubits(std::int32_t v) { return std::bit_cast<std::uint32_t>(v); }
static std::int32_t add32(std::int32_t a, std::int32_t b) {
    return s32(ubits(a) + ubits(b));
}
static std::int32_t sub32(std::int32_t a, std::int32_t b) {
    return s32(ubits(a) - ubits(b));
}
static std::int32_t asr32(std::int32_t v, unsigned n) {
    if (!n) return v;
    auto x = ubits(v) >> n;
    if (v < 0) x |= (~std::uint32_t{0}) << (32 - n);
    return s32(x);
}
static std::int32_t mullo(std::int32_t a, std::int32_t b) {
    return s32(std::uint32_t(std::uint64_t(ubits(a)) * std::uint64_t(ubits(b))));
}
static std::uint16_t table16(const EnvTable& t, std::size_t i) {
    const auto o = 2 * i;
    return std::uint16_t(t[o]) | std::uint16_t(t[o + 1] << 8);
}

// Independent ARM-layout oracle, corresponding to the recovered native
// v1.2.1 Pulse Stack renderer rather than to the compact implementation.
static std::uint16_t armEnvelope(ArmState& s, std::size_t b,
                                 const EnvTable& e1, const EnvTable& e2) {
    const auto state = s[b];
    auto value = s32(u32(s, b + 0x0c));
    switch (state) {
    case 0:
        if (s[b + 7] || s[b + 4]) s[b] = 1;
        break;
    case 1:
        value = s32(ubits(value) + std::uint32_t(u16(s, b + 0x20)));
        put32(s, b + 0x0c, ubits(value));
        if (s[b + 4]) {
            if (value > 0x000ffffe) {
                s[b] = 4;
                if (value >= 0x00100000) {
                    value = 0x000fffff;
                    put32(s, b + 0x0c, ubits(value));
                }
            }
        } else if (value > 0x000ffffe) {
            s[b] = s[b + 6] == 0 ? 3 : 4;
            if (value >= 0x00100000) {
                value = 0x000fffff;
                put32(s, b + 0x0c, ubits(value));
            }
        }
        break;
    case 2:
        break;
    case 3:
        if (s[b + 7] == 0 && (s[b + 4] != 0 || s[b + 0x10] == 0)) s[b] = 4;
        break;
    case 4:
        if (s[b + 7]) {
            s[b] = 1;
        } else {
            value = s32(ubits(value) - std::uint32_t(u16(s, b + 0x22)));
            put32(s, b + 0x0c, ubits(value));
            if (value <= 0) {
                value = 0;
                put32(s, b + 0x0c, 0);
                s[b] = s[b + 4] ? 1 : 0;
            }
        }
        break;
    default:
        break;
    }

    const auto shape = s[b + 1];
    if (shape != 1 && shape != 2)
        return std::uint16_t((ubits(value) >> 4) & 0xffff);
    const auto& table = shape == 1 ? e1 : e2;
    const auto raw = ubits(value);
    const auto index = std::size_t((raw >> 10) & 0x7ff);
    const auto next = (index + 1) & 0x7ff;
    const auto fraction = std::int32_t(raw & 0x3ff);
    const auto a = std::int32_t(table16(table, index));
    const auto bval = std::int32_t(table16(table, next));
    return std::uint16_t(a + asr32(mullo(bval - a, fraction), 10));
}

static void armFilter(ArmState& s, std::size_t b, std::int32_t input) {
    const auto coefficient = u16(s, b + 0x0e);
    auto velocity = s32(u32(s, b + 0x18));

    auto product = mullo(velocity, std::int32_t(coefficient));
    if (product < 0) product = s32(ubits(product) + 0xffff);
    auto first = add32(s32(u32(s, b + 0x10)), asr32(product, 16));
    first = std::clamp(first, -32767, 32767);
    put32(s, b + 0x10, ubits(first));

    auto second = sub32(input, first);
    second = sub32(second, asr32(mullo(velocity, std::int32_t(u16(s, b + 0x0c))), 10));
    second = std::clamp(second, -32767, 32767);
    put32(s, b + 0x14, ubits(second));

    auto feedback = mullo(second, std::int32_t(coefficient));
    if (feedback < 0) feedback = s32(ubits(feedback) + 0xffff);
    velocity = add32(velocity, asr32(feedback, 16));
    velocity = std::clamp(velocity, -32767, 32767);
    put32(s, b + 0x18, ubits(velocity));
}

static std::vector<std::int16_t> armRender(ArmState& s, int n,
                                           const EnvTable& e1,
                                           const EnvTable& e2) {
    std::vector<std::int16_t> out;
    out.reserve(n);
    const std::size_t phaseOff[6] = {0x100, 0xfc, 0x104, 0x108, 0x10c, 0x110};
    const std::size_t incOff[6] = {0x11c, 0x118, 0x120, 0x124, 0x128, 0x12c};
    for (int i = 0; i < n; ++i) {
        const auto old = u32(s, 0x114);
        const auto phase = old + u32(s, 0x130);
        put32(s, 0x114, phase);
        if (phase < old)
            put32(s, 0x134, std::uint32_t(
                std::uint64_t(u32(s, 0x134)) * 0x0019660dull + 0x3c6ef35full));

        std::uint32_t signCount = 0;
        for (int k = 0; k < 6; ++k) {
            const auto p = u32(s, phaseOff[k]) + u32(s, incOff[k]);
            put32(s, phaseOff[k], p);
            signCount += p >> 31;
        }
        const auto pulse = mullo(s32(signCount - 3u), 0x1555);
        armFilter(s, 0xc4, pulse);

        // Crucial alias: +0x136 is high16(u32 at +0x134), including any LCG
        // update that happened at the top of this same sample.
        const auto secondInput = std::int32_t(u16(s, 0x136)) - 0x8000;
        const auto previous = s32(u32(s, 0xdc));
        armFilter(s, 0xe0, secondInput);

        const auto target = s32(u32(s, 0xf4));
        const auto mix = std::int32_t(s16(u16(s, 0x138)));
        const auto delta = sub32(target, previous);
        const auto filtered = add32(previous, asr32(mullo(mix, delta), 15));
        const auto amplitude = armEnvelope(s, 0x74, e1, e2);
        auto value = asr32(mullo(filtered, std::int32_t(amplitude)), 16);
        value = asr32(mullo(value, std::int32_t(s[6])), 8);
        value = std::clamp(value, -32768, 32767);
        out.push_back(std::int16_t(value));
    }
    return out;
}

static std::uint32_t word32(const Compact& w, int o) {
    return std::uint32_t(w[o]) | (std::uint32_t(w[o + 1]) << 16);
}
static void putWord32(Compact& w, int o, std::uint32_t v) {
    w[o] = v & 0xffff; w[o + 1] = v >> 16;
}

static Compact compactFromArm(const ArmState& s) {
    Compact w{};
    w[0] = s[6];
    w[1] = s[0x74]; w[2] = s[0x75]; w[3] = s[0x78]; w[4] = s[0x7a]; w[5] = s[0x7b];
    putWord32(w, 6, u32(s, 0x80)); putWord32(w, 8, u32(s, 0x84));
    w[10] = u16(s, 0x94); w[11] = u16(s, 0x96);
    auto filter = [&](int d, std::size_t b) {
        w[d] = u16(s, b + 0x0c); w[d + 1] = u16(s, b + 0x0e);
        putWord32(w, d + 2, u32(s, b + 0x10));
        putWord32(w, d + 4, u32(s, b + 0x14));
        putWord32(w, d + 6, u32(s, b + 0x18));
    };
    filter(12, 0xc4); filter(20, 0xe0);
    const std::size_t phaseOff[6] = {0x100, 0xfc, 0x104, 0x108, 0x10c, 0x110};
    const std::size_t incOff[6] = {0x11c, 0x118, 0x120, 0x124, 0x128, 0x12c};
    for (int i = 0; i < 6; ++i) {
        putWord32(w, 28 + 2 * i, u32(s, phaseOff[i]));
        putWord32(w, 40 + 2 * i, u32(s, incOff[i]));
    }
    putWord32(w, 52, u32(s, 0x114));
    putWord32(w, 54, u32(s, 0x130));
    putWord32(w, 56, u32(s, 0x134));
    // Compact word 57 is both RNG high and second-input, just like ARM +0x136.
    w[58] = u16(s, 0x138);
    return w;
}

static std::uint16_t compactEnvelope(Compact& w,
                                     const EnvTable& e1,
                                     const EnvTable& e2) {
    const int b = 1;
    const auto state = w[b];
    const auto shape = w[b + 1] & 0xff;
    auto value = s32(word32(w, b + 5));
    if (state == 0) {
        if (w[b + 4] || w[b + 2]) w[b] = 1;
    } else if (state == 1) {
        value = add32(value, w[b + 9]);
        putWord32(w, b + 5, ubits(value));
        if (w[b + 2]) {
            if (value > 0xffffe) {
                w[b] = 4;
                if (value >= 0x100000) {
                    value = 0xfffff; putWord32(w, b + 5, ubits(value));
                }
            }
        } else if (value > 0xffffe) {
            w[b] = w[b + 3] ? 4 : 3;
            if (value >= 0x100000) {
                value = 0xfffff; putWord32(w, b + 5, ubits(value));
            }
        }
    } else if (state == 3) {
        if (!w[b + 4] && (w[b + 2] || (w[b + 7] & 0xff) == 0)) w[b] = 4;
    } else if (state == 4) {
        if (w[b + 4]) w[b] = 1;
        else {
            value = sub32(value, w[b + 10]);
            putWord32(w, b + 5, ubits(value));
            if (value <= 0) {
                value = 0; putWord32(w, b + 5, 0); w[b] = w[b + 2] ? 1 : 0;
            }
        }
    }
    if (shape != 1 && shape != 2)
        return std::uint16_t((ubits(value) >> 4) & 0xffff);
    const auto& table = shape == 1 ? e1 : e2;
    const auto raw = ubits(value);
    const auto index = std::size_t((raw >> 10) & 0x7ff);
    const auto next = (index + 1) & 0x7ff;
    const auto fraction = std::int32_t(raw & 0x3ff);
    const auto a = std::int32_t(table16(table, index));
    const auto bval = std::int32_t(table16(table, next));
    return std::uint16_t(a + asr32(mullo(bval - a, fraction), 10));
}

static void compactFilter(Compact& w, int b, std::int32_t input) {
    const auto damping = w[b];
    const auto coefficient = w[b + 1];
    auto velocity = s32(word32(w, b + 6));
    auto product = mullo(velocity, coefficient);
    if (product < 0) product = s32(ubits(product) + 0xffff);
    auto first = add32(s32(word32(w, b + 2)), asr32(product, 16));
    first = std::clamp(first, -32767, 32767);
    putWord32(w, b + 2, ubits(first));
    auto second = sub32(input, first);
    second = sub32(second, asr32(mullo(velocity, damping), 10));
    second = std::clamp(second, -32767, 32767);
    putWord32(w, b + 4, ubits(second));
    auto feedback = mullo(second, coefficient);
    if (feedback < 0) feedback = s32(ubits(feedback) + 0xffff);
    velocity = add32(velocity, asr32(feedback, 16));
    velocity = std::clamp(velocity, -32767, 32767);
    putWord32(w, b + 6, ubits(velocity));
}

static std::vector<std::int16_t> compactRender(Compact& w, int n,
                                               const EnvTable& e1,
                                               const EnvTable& e2) {
    std::vector<std::int16_t> out;
    out.reserve(n);
    for (int sample = 0; sample < n; ++sample) {
        const auto old = word32(w, 52);
        const auto randomPhase = old + word32(w, 54);
        putWord32(w, 52, randomPhase);
        if (randomPhase < old)
            putWord32(w, 56, std::uint32_t(
                std::uint64_t(word32(w, 56)) * 0x0019660dull + 0x3c6ef35full));

        std::uint32_t signCount = 0;
        for (int i = 0; i < 6; ++i) {
            const auto phase = word32(w, 28 + 2 * i) + word32(w, 40 + 2 * i);
            putWord32(w, 28 + 2 * i, phase);
            signCount += phase >> 31;
        }
        const auto pulse = mullo(s32(signCount - 3u), 0x1555);
        compactFilter(w, 12, pulse);
        const auto previous = s32(word32(w, 18));
        compactFilter(w, 20, std::int32_t(w[57]) - 0x8000);
        const auto target = s32(word32(w, 24));
        const auto mix = std::int32_t(s16(w[58]));
        const auto filtered = add32(previous,
            asr32(mullo(mix, sub32(target, previous)), 15));
        const auto amplitude = compactEnvelope(w, e1, e2);
        auto value = asr32(mullo(filtered, amplitude), 16);
        value = asr32(mullo(value, w[0] & 0xff), 8);
        value = std::clamp(value, -32768, 32767);
        out.push_back(std::int16_t(value));
    }
    return out;
}

static void putTable(EnvTable& t, std::size_t i, std::uint16_t v) {
    t[2 * i] = v & 255; t[2 * i + 1] = v >> 8;
}
static void putSigned32(ArmState& s, std::size_t o, std::int32_t v) {
    put32(s, o, ubits(v));
}

int main() {
    std::mt19937_64 rng(0x50434d484154ULL);
    EnvTable env1{}, env2{};
    for (std::size_t i = 0; i < 2048; ++i) {
        putTable(env1, i, std::uint16_t((i * 31u + (i * i * 7u)) & 0xffff));
        putTable(env2, i, std::uint16_t((0xffffu - ((i * 197u) ^ (i >> 2))) & 0xffff));
    }

    constexpr int cases = 2000;
    constexpr int blocks = 4;
    constexpr int frames = 16;
    std::size_t pcmChecked = 0, stateChecked = 0, lcgWrapSamples = 0;

    for (int tc = 0; tc < cases; ++tc) {
        ArmState arm{};
        for (auto& b : arm) b = std::uint8_t(rng());
        arm[6] = std::uint8_t(rng());

        const std::size_t eb = 0x74;
        arm[eb] = std::array<std::uint8_t, 4>{0, 1, 3, 4}[rng() % 4];
        arm[eb + 1] = std::uint8_t(rng() % 3);
        arm[eb + 4] = rng() & 1; arm[eb + 6] = rng() & 1; arm[eb + 7] = rng() & 1;
        put32(arm, eb + 0x0c, std::uint32_t(rng() % 0x100000));
        put32(arm, eb + 0x10, std::uint32_t(rng()));
        put16(arm, eb + 0x20, std::uint16_t(rng()));
        put16(arm, eb + 0x22, std::uint16_t(rng()));

        for (const auto fb : {std::size_t(0xc4), std::size_t(0xe0)}) {
            put16(arm, fb + 0x0c, std::uint16_t(rng()));
            put16(arm, fb + 0x0e, std::uint16_t(rng()));
            putSigned32(arm, fb + 0x10, std::int32_t(int(rng() % 65535) - 32767));
            putSigned32(arm, fb + 0x14, std::int32_t(int(rng() % 65535) - 32767));
            putSigned32(arm, fb + 0x18, std::int32_t(int(rng() % 65535) - 32767));
        }

        for (const auto o : {std::size_t(0x100), std::size_t(0xfc), std::size_t(0x104),
                             std::size_t(0x108), std::size_t(0x10c), std::size_t(0x110),
                             std::size_t(0x11c), std::size_t(0x118), std::size_t(0x120),
                             std::size_t(0x124), std::size_t(0x128), std::size_t(0x12c)})
            put32(arm, o, std::uint32_t(rng()));

        // Force plenty of same-sample LCG/input-alias transitions.
        if ((tc & 3) == 0) {
            put32(arm, 0x114, 0xfffffff0u);
            put32(arm, 0x130, 0x40u);
        } else {
            put32(arm, 0x114, std::uint32_t(rng()));
            put32(arm, 0x130, std::uint32_t(rng()));
        }
        put32(arm, 0x134, std::uint32_t(rng()));
        put16(arm, 0x138, std::uint16_t(rng()));

        auto compact = compactFromArm(arm);
        for (int block = 0; block < blocks; ++block) {
            const auto oldClock = u32(arm, 0x114);
            const auto clockInc = u32(arm, 0x130);
            if ((oldClock + clockInc) < oldClock) ++lcgWrapSamples;

            const auto armPcm = armRender(arm, frames, env1, env2);
            const auto compactPcm = compactRender(compact, frames, env1, env2);
            if (armPcm != compactPcm) {
                for (int i = 0; i < frames; ++i) {
                    if (armPcm[i] != compactPcm[i]) {
                        std::fprintf(stderr,
                            "PCM mismatch case=%d block=%d sample=%d arm=%d compact=%d\n",
                            tc, block, i, armPcm[i], compactPcm[i]);
                        return 1;
                    }
                }
            }
            pcmChecked += frames;

            const auto mapped = compactFromArm(arm);
            if (mapped != compact) {
                for (int i = 0; i < int(compact.size()); ++i) {
                    if (mapped[i] != compact[i]) {
                        std::fprintf(stderr,
                            "STATE mismatch case=%d block=%d word=%d arm=%04x compact=%04x\n",
                            tc, block, i, mapped[i], compact[i]);
                        return 2;
                    }
                }
            }
            stateChecked += compact.size();
        }
    }

    if (!lcgWrapSamples) {
        std::fprintf(stderr, "No LCG wrap/input-alias transitions were exercised\n");
        return 3;
    }

    std::printf(
        "Pulse Stack native-vs-compact PCM: PASS "
        "(%d cases x %d blocks x %d = %zu exact samples; "
        "%zu exact continuation words; %zu blocks begin with an LCG wrap)\n",
        cases, blocks, frames, pcmChecked, stateChecked, lcgWrapSamples);
    return 0;
}
