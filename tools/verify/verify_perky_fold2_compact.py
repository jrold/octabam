#!/usr/bin/env python3
"""Exact host gate for the v1.2.1 Fold Drum 2 compact renderer.

Uses the existing external ARM fixture captures and native PerkyBits source.
No firmware blobs/assets are committed; this script consumes the same local
out/perky assets used by the Fold1/Simple qualification gates.
"""
from __future__ import annotations

from pathlib import Path
import os
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))

import fold_drum2_compact as fold2

OUT = ROOT / "out/perky/fold-drum2-compact"
FIX = ROOT / "out/perky/engine-fixtures"
ASSET = ROOT / "out/perky/simple-drum-assets"
NATIVE = Path(
    os.environ.get("PERKYBITS_SOURCE", "/Users/jrold/Downloads/perkybits/Source")
)

WAVE_IDS = (0x080222A0, 0x080224A0, 0x080226A0, 0x080228A0)

NATIVE_RUNNER = r'''
#include "NativeV121FoldDrums.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <string>
using N = NativeV121FoldDrums;

template<class T>
void load(const std::string& p, T& v) {
    std::ifstream f(p, std::ios::binary);
    f.read(reinterpret_cast<char*>(v.data()), v.size());
    if (!f) throw p;
}
static std::uint32_t rd32(const N::Fold2State& s, unsigned o) {
    return std::uint32_t(s[o])
         | (std::uint32_t(s[o+1]) << 8)
         | (std::uint32_t(s[o+2]) << 16)
         | (std::uint32_t(s[o+3]) << 24);
}
int main(int argc, char** argv) {
    if (argc != 4) return 2;
    const std::string d = argv[1];

    N::PitchTable p;
    N::EnvelopeTable e1, e2;
    N::WaveTable w[4];
    load(d + "/pitch.bin", p);
    load(d + "/envelope1.bin", e1);
    load(d + "/envelope2.bin", e2);

    const unsigned ids[] = {
        0x080222a0u, 0x080224a0u, 0x080226a0u, 0x080228a0u
    };
    const char* names[] = {
        "wave_080222a0.bin", "wave_080224a0.bin",
        "wave_080226a0.bin", "wave_080228a0.bin"
    };
    N::Tables t;
    t.pitch = &p;
    t.envelope1 = &e1;
    t.envelope2 = &e2;
    for (int i = 0; i < 4; ++i) {
        load(d + "/" + names[i], w[i]);
        t.waves[i] = {ids[i], &w[i]};
    }

    std::ifstream f(argv[2], std::ios::binary);
    std::ofstream g(argv[3], std::ios::binary);
    N::Fold2State s;
    N::RngState rng;
    while (f.read(reinterpret_cast<char*>(s.data()), s.size())) {
        f.read(reinterpret_cast<char*>(&rng), sizeof(rng));
        if (!f) return 4;
        const auto p1 = rd32(s, 0x128);
        const auto p2 = rd32(s, 0x12c);
        const auto object = std::min(p1, p2) - 0x2cu;
        short pcm[16];
        if (!N::renderFold2(s, object, pcm, 16, t, rng)) return 3;
        g.write(reinterpret_cast<char*>(pcm), sizeof(pcm));
        g.write(reinterpret_cast<char*>(s.data()), s.size());
        g.write(reinterpret_cast<char*>(&rng), sizeof(rng));
    }
    return 0;
}
'''


def assets():
    pitch = (ASSET / "pitch.bin").read_bytes()
    e1 = (ASSET / "envelope1.bin").read_bytes()
    e2 = (ASSET / "envelope2.bin").read_bytes()
    waves = {
        address: (ASSET / f"wave_{address:08x}.bin").read_bytes()
        for address in WAVE_IDS
    }
    return pitch, e1, e2, waves


def fixture_state(case: Path, name: str) -> bytes:
    blob = (case / name).read_bytes()
    return blob[0xC4:0xC4 + 0x134]


def render_python(raw: bytes, count: int, rng_bytes: bytes):
    pitch, e1, e2, waves = assets()
    voice = fold2.FoldDrum2.from_arm(raw)
    rng = list(struct.unpack("<II", rng_bytes))
    pcm = voice.render(count, waves, pitch, e1, e2, rng)
    return pcm, voice, struct.pack("<II", *rng)


def captured_gate():
    checked = 0
    for mode in range(1, 4):
        for corner in range(3):
            case = FIX / f"engine-4-mode-{mode}-corner-{corner}"
            if not case.exists():
                raise FileNotFoundError(case)

            # As with the qualified Fold1 gate, the first block is exact-gated
            # only for the two non-random transient modes. The capture harness
            # does not expose the lazy RNG seed before the first random mode
            # block; all three modes are exact-gated from explicit continuation
            # RNG state below.
            if mode in (1, 3):
                raw = fixture_state(case, "wrapper-window-before.bin")
                pcm, voice, _ = render_python(
                    raw, 256, struct.pack("<II", 0, 0)
                )
                want_pcm = list(struct.unpack(
                    "<256h", (case / "arm-pcm.bin").read_bytes()
                ))
                assert pcm == want_pcm, (mode, corner, "triggered PCM")
                want_state = fold2.FoldDrum2.from_arm(
                    fixture_state(case, "wrapper-window-after.bin")
                ).words
                assert voice.words == want_state, (
                    mode, corner, "triggered state"
                )
                checked += 1

            raw = fixture_state(case, "wrapper-window-after.bin")
            pcm, voice, rng_after = render_python(
                raw, 256, (case / "rng-continuation-before.bin").read_bytes()
            )
            want_pcm = list(struct.unpack(
                "<256h", (case / "arm-pcm-continuation.bin").read_bytes()
            ))
            assert pcm == want_pcm, (mode, corner, "continuation PCM")
            want_state = fold2.FoldDrum2.from_arm(
                fixture_state(case, "wrapper-window-continuation-after.bin")
            ).words
            assert voice.words == want_state, (mode, corner, "continuation state")
            assert rng_after == (case / "rng-continuation-after.bin").read_bytes(), (
                mode, corner, "continuation RNG"
            )
            checked += 1
    return checked


def native_random_gate():
    if not NATIVE.exists():
        raise FileNotFoundError(
            f"PerkyBits native source not found at {NATIVE}; "
            "set PERKYBITS_SOURCE to Source/"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    runner = OUT / "native_fold2.cpp"
    exe = OUT / "native_fold2"
    runner.write_text(NATIVE_RUNNER)
    subprocess.run(
        [
            "c++", "-std=c++20", "-O2", "-I" + str(NATIVE),
            str(runner), str(NATIVE / "NativeV121FoldDrums.cpp"),
            "-o", str(exe),
        ],
        check=True,
        capture_output=True,
    )

    template_case = FIX / "engine-4-mode-2-corner-1"
    template = fixture_state(template_case, "wrapper-window-before.bin")
    seed = random.Random(0xF02D)
    records: list[tuple[bytes, bytes]] = []

    for i in range(400):
        v = fold2.FoldDrum2.from_arm(template)
        v.words[fold2.VELOCITY] = seed.choice((0, 1, 63, 127, 255))
        v.words[fold2.MUTE] = int(i % 31 == 0)
        v.words[fold2.MODE] = i % 3
        v.words[fold2.COUNTER] = seed.choice(
            (0, 0x8F, 0x90, 0x110, 0x111, 0x210, 0x211, 0xFFFF)
        )
        v.words[fold2.FOLD] = seed.randrange(0x10000)
        v.words[fold2.NOISE_COUNT] = seed.choice((0, 1, 2, 0xFFFF))
        v.words[fold2.NOISE_RATE] = seed.choice((0, 1, 2, 0xFFFF))
        v.words[fold2.NOISE_SAMPLE] = seed.randrange(0x10000)
        v.words[fold2.FADE] = seed.choice(
            (0, 1, 0x87, 0x88, 0x89, 0x100, 0x7FFF, 0xFFFF)
        )
        v.words[fold2.FADE_SAVED] = seed.randrange(0x10000)
        v.words[fold2.PRIMARY] = i & 1
        v.words[fold2.RAW_PITCH] = seed.randrange(4096)
        v.words[fold2.PITCH_AMOUNT] = seed.randrange(4096)

        raw = v.apply_to_arm(template)
        rng = struct.pack("<II", seed.getrandbits(32), seed.getrandbits(32))
        records.append((raw, rng))

    native_in = OUT / "native-input.bin"
    native_out = OUT / "native-output.bin"
    native_in.write_bytes(b"".join(raw + rng for raw, rng in records))
    subprocess.run(
        [str(exe), str(ASSET), str(native_in), str(native_out)],
        check=True,
    )

    pitch, e1, e2, waves = assets()
    blob = native_out.read_bytes()
    record_bytes = 16 * 2 + 0x134 + 8
    assert len(blob) == record_bytes * len(records)

    for i, (raw, rng_bytes) in enumerate(records):
        at = i * record_bytes
        want_pcm = list(struct.unpack("<16h", blob[at:at + 32]))
        want_raw = blob[at + 32:at + 32 + 0x134]
        want_rng = blob[at + 32 + 0x134:at + record_bytes]

        voice = fold2.FoldDrum2.from_arm(raw)
        rng = list(struct.unpack("<II", rng_bytes))
        got_pcm = voice.render(16, waves, pitch, e1, e2, rng)
        assert got_pcm == want_pcm, (i, "PCM")
        assert voice.words == fold2.FoldDrum2.from_arm(want_raw).words, (i, "state")
        assert struct.pack("<II", *rng) == want_rng, (i, "RNG")

    return len(records)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    captured = captured_gate()
    randomized = native_random_gate()
    print(
        "Fold Drum 2 compact: PASS "
        f"({captured} captured ARM blocks + {randomized} randomized native blocks; "
        "exact PCM/state/RNG)"
    )


if __name__ == "__main__":
    main()
