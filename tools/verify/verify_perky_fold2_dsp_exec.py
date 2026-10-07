#!/usr/bin/env python3
"""Execute the Fold Drum 2 DSP56300 candidate against ARM/native oracles.

This is deliberately a candidate gate only. Passing it qualifies the renderer
math/state/RNG and modeled block timing; production controls, seam integration,
memory placement and hardware remain separate gates.
"""
from __future__ import annotations

from pathlib import Path
import importlib.util
import os
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky")]

import fold_drum2_compact as fold2
import simple_drum_tables as packed
from build_noise_tone_synth_source import (
    force_long_local_jsr,
    relativize_local_conditionals,
)

spec = importlib.util.spec_from_file_location(
    "simplegate", ROOT / "tools/verify/verify_perky_simple_drum_voice_exec.py"
)
simple = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(simple)

OUT = ROOT / "out/perky/fold-drum2-voice"
FIX = ROOT / "out/perky/engine-fixtures"
ASSETS = ROOT / "out/perky/simple-drum-assets"
NATIVE = Path(
    os.environ.get("PERKYBITS_SOURCE", "/Users/jrold/Downloads/perkybits/Source")
)

NATIVE_RUNNER = r'''
#include "NativeV121FoldDrums.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <string>
using N=NativeV121FoldDrums;
template<class T> void load(const std::string& p,T& v){
 std::ifstream f(p,std::ios::binary);
 f.read(reinterpret_cast<char*>(v.data()),v.size());
 if(!f)throw p;
}
static std::uint32_t rd32(const N::Fold2State&s,unsigned o){
 return std::uint32_t(s[o])|(std::uint32_t(s[o+1])<<8)|
        (std::uint32_t(s[o+2])<<16)|(std::uint32_t(s[o+3])<<24);
}
int main(int argc,char**argv){
 if(argc!=4)return 2;std::string d=argv[1];
 N::PitchTable p;N::EnvelopeTable e1,e2;N::WaveTable w[4];
 load(d+"/pitch.bin",p);load(d+"/envelope1.bin",e1);
 load(d+"/envelope2.bin",e2);
 unsigned ids[]={0x080222a0u,0x080224a0u,0x080226a0u,0x080228a0u};
 const char* names[]={"wave_080222a0.bin","wave_080224a0.bin",
                     "wave_080226a0.bin","wave_080228a0.bin"};
 N::Tables t;t.pitch=&p;t.envelope1=&e1;t.envelope2=&e2;
 for(int i=0;i<4;++i){load(d+"/"+names[i],w[i]);t.waves[i]={ids[i],&w[i]};}
 std::ifstream f(argv[2],std::ios::binary);
 std::ofstream g(argv[3],std::ios::binary);
 N::Fold2State s;N::RngState rng;
 while(f.read(reinterpret_cast<char*>(s.data()),s.size())){
  f.read(reinterpret_cast<char*>(&rng),sizeof(rng));if(!f)return 4;
  auto p1=rd32(s,0x128),p2=rd32(s,0x12c);
  auto object=std::min(p1,p2)-0x2cu;
  short pcm[16];
  if(!N::renderFold2(s,object,pcm,16,t,rng))return 3;
  g.write(reinterpret_cast<char*>(pcm),sizeof(pcm));
  g.write(reinterpret_cast<char*>(s.data()),s.size());
  g.write(reinterpret_cast<char*>(&rng),sizeof(rng));
 }
 return 0;
}
'''


def fixture_state(case: Path, name: str) -> bytes:
    blob = (case / name).read_bytes()
    return blob[0xC4:0xC4 + 0x134]


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    simple.envgate.build_host()

    perky = ROOT / "modules/perky"
    parts = [
        """pk_fold2_probe:
 move #>$200,r6
 move #>$3900,r5
 jsr pk_simple_base
 jsr pk_fold2_voice
 move x:>$38e8,a
 move a1,x:>$240
 move x:>$38e9,a
 move a1,x:>$241
 move x:>$38ea,a
 move a1,x:>$242
 move x:>$38eb,a
 move a1,x:>$243
 rts
""",
        (perky / "fold_drum2_voice.asm").read_text(),
    ]

    for name, label in (
        ("envelope", "pk_simple_envelope"),
        ("frequency", "pk_simple_frequency"),
        ("oscillator", "pk_simple_oscillator"),
    ):
        text = (perky / f"simple_drum_{name}.asm").read_text()
        text = text[text.index("\n" + label + ":"):]
        # Four waves occupy $07a5..$0a4f in the shared oscillator's identity
        # order. Keep the envelope after them; the old fixture overlapped its
        # fourth wave and never randomized either oscillator's wave identity.
        text = text.replace("#>$0009a5,r1", "#>$000a50,r1")
        parts.append(text)

    parts += [
        (perky / "simple_drum_delta.asm").read_text(),
        "\npknv_noise:"
        + (perky / "noise_tone_voice_native_xstate.asm")
          .read_text().split("\npknv_noise:", 1)[1],
        (perky / "noise_tone_math.asm").read_text(),
    ]

    source = force_long_local_jsr(
        relativize_local_conditionals("\n".join(parts))
    )
    asm = OUT / "fold2.asm"
    binary = OUT / "fold2.bin"
    sym = OUT / "fold2.sym"
    asm.write_text(source)

    result = subprocess.run(
        [
            str(simple.envgate.ASM), "-in", str(asm), "-org", "2800",
            "-out", str(binary), "-sym", str(sym), "-list",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    dis = subprocess.run(
        [str(simple.envgate.DIS), "-in", str(binary), "-pc", "2800", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed = {
        int(m[1], 16): m[2]
        for m in map(simple.envgate.LINE.match, result.stdout.splitlines())
        if m
    }
    actual = {
        int(m[1], 16): m[2]
        for m in map(simple.envgate.LINE.match, dis.stdout.splitlines())
        if m
    }
    rawbin = binary.read_bytes()
    for at, mnemonic in typed.items():
        if (
            mnemonic == "nop"
            and at not in actual
            and rawbin[(at - 0x2800) * 3:(at - 0x2800) * 3 + 3] == bytes(3)
        ):
            continue
        assert actual.get(at) == mnemonic, (at, mnemonic, actual.get(at))

    labels = {
        row[0]: int(row[1], 16)
        for row in map(str.split, sym.read_text().splitlines())
        if len(row) == 2
    }
    return binary, labels["pk_fold2_probe"]


def table_payload() -> str:
    wave_values = []
    for address in (0x080222A0, 0x080226A0, 0x080228A0, 0x080224A0):
        wave_values.extend(struct.unpack(
            "<256H", (ASSETS / f"wave_{address:08x}.bin").read_bytes()
        ))
    waves = packed.pack_u16(wave_values)
    env = packed.pack_u16(struct.unpack(
        "<2048H", (ASSETS / "envelope1.bin").read_bytes()
    )[:1024])
    pitch = packed.pack_pitch_basis(struct.unpack(
        "<4096H", (ASSETS / "pitch.bin").read_bytes()
    )).words
    return (
        "Y 7a5 " + " ".join(f"{v:06x}" for v in waves) + "\n"
        + "Y a50 " + " ".join(f"{v:06x}" for v in env) + "\n"
        + "Y efb " + " ".join(f"{v:06x}" for v in pitch) + " 000000\n"
        + "X 3964 ffffff\n"
    )


def run_dsp(binary: Path, entry: int, words: list[int],
            rng: bytes, frames: int):
    data = OUT / "case.data"
    pcm = OUT / "case.raw"
    dump = OUT / "case.state"
    meter = OUT / "case.meter"
    script = OUT / "case.script"
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")

    state = list(words) + [0] * (68 - len(words))
    rng16 = struct.unpack("<4H", rng)
    data.write_text(
        "X 200 " + " ".join(f"{x:06x}" for x in state) + "\n"
        + table_payload()
        + "X 38e8 " + " ".join(f"{x:06x}" for x in rng16) + "\n"
    )
    subprocess.run(
        [
            str(simple.envgate.HOST),
            "-code", str(binary), "-org", "2800", "-entry", f"{entry:x}",
            "-data", str(data), "-script", str(script),
            "-out", str(pcm), "-state", str(dump), "-state-words", "68",
            "-frames", str(frames), "-meter", str(meter), "-cycle-meter", "1",
        ],
        check=True,
        capture_output=True,
    )
    raw = list(struct.unpack(
        "<" + "i" * (pcm.stat().st_size // 4), pcm.read_bytes()
    ))
    final = [int(v, 16) & 0xFFFF for v in dump.read_text().split()]
    return raw[::2], final, int(meter.read_text().strip())


def captured_gate(binary: Path, entry: int):
    meters = []
    checked = 0
    for mode in range(1, 4):
        for corner in range(3):
            case = FIX / f"engine-4-mode-{mode}-corner-{corner}"

            if mode in (1, 3):
                before = fixture_state(case, "wrapper-window-before.bin")
                voice = fold2.FoldDrum2.from_arm(before)
                got, final, meter = run_dsp(
                    binary, entry, voice.words, struct.pack("<II", 0, 0), 256
                )
                want = list(struct.unpack(
                    "<256h", (case / "arm-pcm.bin").read_bytes()
                ))
                assert got == want, (mode, corner, "triggered PCM")
                expected = fold2.FoldDrum2.from_arm(
                    fixture_state(case, "wrapper-window-after.bin")
                ).words
                assert final[:fold2.WORDS] == expected, (
                    mode, corner, "triggered state"
                )
                meters.append(meter)
                checked += 1

            before = fixture_state(case, "wrapper-window-after.bin")
            voice = fold2.FoldDrum2.from_arm(before)
            rng = (case / "rng-continuation-before.bin").read_bytes()
            got, final, meter = run_dsp(binary, entry, voice.words, rng, 256)
            want = list(struct.unpack(
                "<256h", (case / "arm-pcm-continuation.bin").read_bytes()
            ))
            assert got == want, (mode, corner, "continuation PCM")
            expected = fold2.FoldDrum2.from_arm(
                fixture_state(case, "wrapper-window-continuation-after.bin")
            ).words
            assert final[:fold2.WORDS] == expected, (
                mode, corner, "continuation state"
            )
            got_rng = tuple(final[64:68])
            want_rng = struct.unpack(
                "<4H", (case / "rng-continuation-after.bin").read_bytes()
            )
            assert got_rng == want_rng, (mode, corner, "continuation RNG")
            meters.append(meter)
            checked += 1
    return checked, meters


def randomized_gate(binary: Path, entry: int):
    if not NATIVE.exists():
        raise FileNotFoundError(
            f"PerkyBits native source not found at {NATIVE}; "
            "set PERKYBITS_SOURCE to Source/"
        )

    runner = OUT / "native.cpp"
    exe = OUT / "native"
    runner.write_text(NATIVE_RUNNER)
    subprocess.run(
        [
            "c++", "-std=c++20", "-O2", "-I" + str(NATIVE), str(runner),
            str(NATIVE / "NativeV121FoldDrums.cpp"), "-o", str(exe),
        ],
        check=True,
        capture_output=True,
    )

    template = fixture_state(
        FIX / "engine-4-mode-2-corner-1", "wrapper-window-before.bin"
    )
    r = random.Random(0xF02D)
    cases = []
    for i in range(400):
        v = fold2.FoldDrum2.from_arm(template)
        v.words[fold2.VELOCITY] = r.choice((0, 1, 63, 127, 255))
        v.words[fold2.MUTE] = int(i % 31 == 0)
        v.words[fold2.MODE] = i % 3
        v.words[fold2.COUNTER] = r.choice(
            (0, 0x8F, 0x90, 0x110, 0x111, 0x210, 0x211, 0xFFFF)
        )
        v.words[fold2.FOLD] = r.randrange(0x10000)
        v.words[fold2.NOISE_COUNT] = r.choice((0, 1, 2, 0xFFFF))
        v.words[fold2.NOISE_RATE] = r.choice((0, 1, 2, 0xFFFF))
        v.words[fold2.NOISE_SAMPLE] = r.randrange(0x10000)
        v.words[fold2.FADE] = r.choice(
            (0, 1, 0x87, 0x88, 0x89, 0x100, 0x7FFF, 0xFFFF)
        )
        v.words[fold2.FADE_SAVED] = r.randrange(0x10000)
        v.words[fold2.PRIMARY] = i & 1
        v.words[fold2.RAW_PITCH] = r.randrange(4096)
        v.words[fold2.PITCH_AMOUNT] = r.randrange(4096)
        ids = (0x080222A0, 0x080224A0, 0x080226A0, 0x080228A0)
        for osc in (fold2.OSC_A, fold2.OSC_B):
            for offset in (4, 6):
                address = r.choice(ids)
                v.words[osc + offset:osc + offset + 2] = [address & 0xFFFF, address >> 16]
            phase = r.choice((0, 0xFFFFF, 0x100000, 0x100001, 0xFFFFFFFF))
            v.words[osc:osc + 2] = [phase & 0xFFFF, phase >> 16]
        rng = struct.pack("<II", r.getrandbits(32), r.getrandbits(32))
        cases.append((v.apply_to_arm(template), rng))

    inp = OUT / "native-input.bin"
    native_out = OUT / "native-output.bin"
    inp.write_bytes(b"".join(raw + rng for raw, rng in cases))
    subprocess.run(
        [str(exe), str(ASSETS), str(inp), str(native_out)],
        check=True,
    )
    blob = native_out.read_bytes()
    stride = 32 + 0x134 + 8
    assert len(blob) == stride * len(cases)

    meters = []
    for i, (raw, rng) in enumerate(cases):
        at = i * stride
        want_pcm = list(struct.unpack("<16h", blob[at:at + 32]))
        want_state = fold2.FoldDrum2.from_arm(
            blob[at + 32:at + 32 + 0x134]
        ).words
        want_rng = struct.unpack(
            "<4H", blob[at + 32 + 0x134:at + stride]
        )
        voice = fold2.FoldDrum2.from_arm(raw)
        got, final, meter = run_dsp(binary, entry, voice.words, rng, 16)
        assert got == want_pcm, (i, "PCM")
        assert final[:fold2.WORDS] == want_state, (i, "state")
        assert tuple(final[64:68]) == want_rng, (i, "RNG")
        meters.append(meter)
    return meters


def main():
    binary, entry = assemble()
    captured, captured_meters = captured_gate(binary, entry)
    random_meters = randomized_gate(binary, entry)
    print(
        "Fold Drum 2 DSP candidate: PASS "
        f"({captured} captured ARM blocks + {len(random_meters)} randomized "
        f"native blocks; exact PCM/state/RNG; {binary.stat().st_size // 3} P "
        f"words; worst captured 256-sample block {max(captured_meters)} modeled "
        f"cycles; worst randomized 16-sample block {max(random_meters)} modeled cycles)"
    )


if __name__ == "__main__":
    main()
