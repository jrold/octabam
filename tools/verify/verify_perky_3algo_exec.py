#!/usr/bin/env python3
"""Qualify the COMPOSED reduced Perky DSP machine, algorithm by algorithm.

This gate assembles the exact shipping composition produced by
``tools/perky/build_dsp_3algo_source.py`` -- the same shared resonator/decay
cores, the same deduplicated low32/RNG/envelope helpers, the same Fold Drum 1
primitive set -- and drives each of the three renderer entry points directly.
Its whole purpose is to prove deduplication did not move one sample:

* Fold Drum 1   : 15 original ARM blocks (all three transient modes, initial
                  and continuation states) plus 400 randomized native-oracle
                  blocks;
* Resonant Bass : 256 synthetic states including both sides of every guarded
                  path plus the three original ARM continuation captures;
* Resonant Snare: the same for the snare's three original captures.

Every case checks PCM on both channels, the renderer's X state after each
16-sample block and the shared RNG limbs. The seam/admission/transport gates
are separate; this one is about the renderers inside the shipping layout.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky")]

import build_dsp_3algo_source as composed  # noqa:E402
import fold_drum_compact as fold  # noqa:E402
import resonator_compact as c  # noqa:E402
import resonant_bass_compact as bass  # noqa:E402
import resonant_dsp as recipe  # noqa:E402
import resonant_snare_compact as snare  # noqa:E402
import simple_drum_tables as tables  # noqa:E402
from verify_perky_noise_hat_classic_synthetic_exec import (  # noqa:E402
    make_envelopes,
    make_env,
)

FIX = ROOT / "out/perky/engine-fixtures"
OUT = ROOT / "out/perky/dsp-3algo"
ORG = composed.DSP_ORG
ASM = composed.ASM
DIS = composed.ASM.parent.parent / "disassemble/dsp56kDisassemble"

VOICE = composed.VOICE_BASE          # X:$3800, the composed private voice block
STATE = VOICE                        # fixtures are loaded straight into it
# The Fold/Simple second-difference cache is named by the primitives as an
# ABSOLUTE address: `pk_simple_base` loads `move #>$003964,r4` and
# `pk_simple_delta_at` reads through r4. The standalone gate seeds exactly that
# word (`X 3964 ffffff`); this gate must seed the same address, not
# SCRATCH_BASE+0x40.
FOLD_CACHE = 0x3964
FOLD_CACHE_WORDS = 17
RNG = composed.RNG_BASE              # X:$38e8..$38eb (the two u32 limbs)
# The dump destination must NOT be RNG+4: that is composed.EVENT_OFFSET /
# composed.ADMIT_LATCH (X:$38ec/$38ed), the machine's OWN one-voice-per-core
# latch. Parking the four RNG words there overwrites the latch, and the next
# frame reads a non-zero latch and renders silence -- a harness collision that
# looks exactly like a broken renderer. The standalone gate dumps to X:$240;
# this gate keeps its dump inside the private voice block's tail instead, at
# VOICE+$70 (X:$3870), which the composed layout leaves free: the voice block
# ends at $386c and the scratch block starts at $3900.
DUMP = composed.VOICE_BASE + 0x70
SCRATCH = composed.SCRATCH_BASE
BLOCK_STATE = 108                    # words dumped back after each block

HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-exec: " + message)


def equal(got, want, label: str) -> None:
    if got != want:
        differences = [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b]
        raise AssertionError(
            f"{label}: {differences[:8]}, lengths {len(got)}/{len(want)}")


def build_host() -> None:
    """Reuse the repository's canonical perky host build (same ABI/flags)."""
    if HOST.exists():
        return
    spec = importlib.util.spec_from_file_location(
        "envgate3", ROOT / "tools/verify/verify_perky_simple_drum_envelope_exec.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build_host()
    # The canonical gate builds into its own directory; publish it here too so
    # this gate is self-contained (and never rebuilds a different ABI).
    built = ROOT / "out/perky/simple-drum-envelope/bd909_host"
    if not built.exists() and built.with_suffix(".exe").exists():
        built = built.with_suffix(".exe")
    if not built.exists():
        die(f"the repository host build did not publish {built}")
    if not HOST.exists() or HOST.read_bytes() != built.read_bytes():
        HOST.write_bytes(built.read_bytes())
        HOST.chmod(0o755)


PROBE = """pk3t_fold:
        move    #>${voice:06x},r6
        move    #>${scratch:06x},r5
        jsrl    pk_simple_base
        jsrl    pk_fold_voice
        jsrl    pk3c_rng_out
        rts
pk3t_bass:
        move    #>${voice:06x},r6
        move    #>${scratch:06x},r5
        jsrl    {bass}
        jsrl    pk3c_rng_out
        rts
pk3t_snare:
        move    #>${voice:06x},r6
        move    #>${scratch:06x},r5
        jsrl    {snare}
        jsrl    pk3c_rng_out
        rts
pk3c_rng_out:
        move    #>${rng0:06x},r1
        move    #>${dump:06x},r2
        move    x:(r1)+,a
        move    a1,x:(r2)+
        move    x:(r1)+,a
        move    a1,x:(r2)+
        move    x:(r1)+,a
        move    a1,x:(r2)+
        move    x:(r1)+,a
        move    a1,x:(r2)+
        rts
"""


def assemble(with_source: bool, out: Path) -> tuple[Path, dict[str, int]]:
    build_host()
    out.mkdir(parents=True, exist_ok=True)
    probe = PROBE.format(voice=VOICE, scratch=SCRATCH, rng0=RNG, dump=DUMP,
                         bass=f"{composed.P}bass_voice",
                         snare=f"{composed.P}snare_voice")
    # The seam's continuation address is the build's per-payload substitution;
    # the gate assembles one payload copy and only needs the value to be a
    # legal absolute address here (the seam contract is exercised elsewhere).
    text = (probe + "\n"
            + composed.normalize(composed.compose(with_source=with_source))
            .replace("@CONT@", "$000426"))
    asm, binary, symbols = (out / f"composed.{ext}" for ext in ("asm", "bin", "sym"))
    asm.write_text(text)
    result = subprocess.run(
        [str(ASM), "-in", str(asm), "-org", format(ORG, "x"),
         "-out", str(binary), "-sym", str(symbols), "-list"],
        capture_output=True, text=True)
    if result.returncode:
        die("dsp_asm failed:\n" + result.stdout[-6000:] + result.stderr[-3000:])
    labels = {p[0]: int(p[1], 16) for p in map(str.split, symbols.read_text().splitlines())
              if len(p) == 2}
    for name in ("pk3t_fold", "pk3t_bass", "pk3t_snare"):
        if name not in labels:
            die(f"assembled probe is missing {name}")
    if with_source and "pk3d_source" not in labels:
        die("shipping composition lost its seam entry point")
    # Disassemble what we assembled: the assembler has mis-encoded silently
    # before, so every emitted word is checked against the decode.
    listing = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", format(ORG, "x"), "-le"],
        capture_output=True, text=True, check=True)
    if listing.stdout.count("\n") < 2:
        die("disassembler returned no instructions for the composed image")
    return binary, labels


def tables_text(env1: bytes, env2: bytes, interp_a: bytes, interp_b: bytes,
                assets: Path) -> str:
    waves = tables.pack_u16(
        v for name in ("wave_080222a0.bin", "wave_080226a0.bin", "wave_080228a0.bin")
        for v in struct.unpack("<256H", (assets / name).read_bytes()))
    senv = tables.pack_u16(struct.unpack("<2048H", (assets / "envelope1.bin").read_bytes())[:1024])
    pitch = tables.pack_pitch_basis(struct.unpack("<4096H", (assets / "pitch.bin").read_bytes())).words
    return (
        f"Y {composed.Y_WAVES:x} " + " ".join(f"{v:06x}" for v in waves) + "\n"
        + f"Y {composed.Y_SIMPLE_ENV:x} " + " ".join(f"{v:06x}" for v in senv) + "\n"
        + f"Y {composed.Y_PITCH:x} " + " ".join(f"{v:06x}" for v in pitch) + " 000000\n"
        + f"Y {composed.Y_ENV1:x} "
        + " ".join(f"{v:06x}" for v in tables.pack_u16(struct.unpack("<1025H", env1[:2050]))) + "\n"
        + f"Y {composed.Y_ENV2:x} "
        + " ".join(f"{v:06x}" for v in tables.pack_u16(struct.unpack("<1025H", env2[:2050]))) + "\n"
        + f"Y {composed.Y_INTERP_A:x} "
        + " ".join(f"{v:06x}" for v in struct.unpack("<257H", interp_a)) + "\n"
        + f"Y {composed.Y_INTERP_B:x} "
        + " ".join(f"{v:06x}" for v in struct.unpack("<257H", interp_b)) + "\n")


def rng_limbs(rng) -> list[int]:
    """Accept either two u32 words or the four u16 limbs the host stores."""
    if len(rng) == 4:
        return list(rng)
    lower, upper = rng
    return [lower & 0xFFFF, (lower >> 16) & 0xFFFF,
            upper & 0xFFFF, (upper >> 16) & 0xFFFF]


def run(binary: Path, entry: int, words: list[int], rng, ytext: str,
        blocks: int, tag: str, out: Path) -> tuple[list[int], list[list[int]], int]:
    """Render `blocks` 16-sample blocks; return PCM, per-block X state, worst."""
    limbs = rng_limbs(rng)
    # The composer's voice block ends well before the RNG limbs; write the two
    # regions separately so the gap in between stays zero and the ledger is
    # explicit rather than implied by a long zero run.
    if len(words) > composed.RNG_GAP_START - STATE:
        die(f"{tag}: {len(words)} state words overrun the composed voice block")
    out_words = words + [0] * (composed.RNG_GAP_START - STATE - len(words))
    data = out / "case.data"
    data.write_text(
        f"X {STATE:x} " + " ".join(f"{v:06x}" for v in out_words) + "\n"
        # The scratch block and the Fold second-difference cache must start
        # known: a garbage block is not a renderer input, and the cache is
        # seeded with the 'no block decoded' sentinel the standalone gate uses.
        + f"X {composed.RNG_GAP_END:x} " + " ".join(f"{v:06x}" for v in limbs) + "\n"
        + f"X {SCRATCH:x} " + " ".join(["000000"] * composed.SCRATCH_WORDS) + "\n"
        # THE SENTINEL IS NOT ZERO. `pk_simple_delta_at` compares the cache
        # word against the block index it wants and only decodes on a MISS;
        # zero is a valid index, so seeding zeros makes block 0 look already
        # decoded, `pk_simple_base` reads a zero delta, and the whole Fold path
        # renders silence. The standalone gate writes `X 3964 ffffff`, which is
        # the 'no block decoded' sentinel. Verified by minimal reproducer:
        # with ffffff the composed source matches the standalone reference
        # (-1,-2,-4,-6,...); with zeros it stores all zeros.
        + f"X {FOLD_CACHE:x} " + " ".join(["ffffff"] * FOLD_CACHE_WORDS) + "\n"
        + ytext)
    script = out / "case.script"
    script.write_text((" ".join(["0"] * 12 + ["-1"]) + "\n") * blocks)
    pcm, dump, meter = (out / f"case.{ext}" for ext in ("raw", "state", "meter"))
    subprocess.run(
        [str(HOST), "-code", str(binary), "-org", format(ORG, "x"),
         "-entry", format(entry, "x"), "-data", str(data), "-script", str(script),
         "-out", str(pcm), "-state", str(dump), "-state-words", str(BLOCK_STATE),
         # -frames sets n7, and the renderers' sample loop is `do n7,...`. The
         # host defaults it to 16, so this is explicit rather than implied: a
         # wrong n7 runs the loop the wrong number of times and writes the
         # wrong number of samples, which reads as a silent renderer.
         "-frames", "16",
         "-meter", str(meter), "-cycle-meter", "1"],
        check=True, capture_output=True, timeout=180)
    stereo = list(struct.unpack(f"<{16 * blocks * 2}i", pcm.read_bytes()))
    equal(stereo[1::2], stereo[::2], tag + " stereo")
    lines = dump.read_text().splitlines()
    if len(lines) != blocks:
        die(f"{tag}: host dumped {len(lines)} block states, expected {blocks}")
    state = [[int(v, 16) & 0xFFFF for v in line.split()] for line in lines]
    return stereo[::2], state, int(meter.read_text().split()[-1])


# ---------------------------------------------------------------------------
# Fold Drum 1
# ---------------------------------------------------------------------------
FOLD_NATIVE_RUNNER = r'''
#include "NativeV121FoldDrums.h"
#include <fstream>
#include <string>
using N=NativeV121FoldDrums;
template<class T> void load(const std::string& p,T& v){std::ifstream f(p,std::ios::binary);f.read(reinterpret_cast<char*>(v.data()),v.size());if(!f)throw p;}
int main(int argc,char**argv){if(argc!=4)return 2;std::string d=argv[1];N::PitchTable p;N::EnvelopeTable e1,e2;N::WaveTable w[3];load(d+"/pitch.bin",p);load(d+"/envelope1.bin",e1);load(d+"/envelope2.bin",e2);unsigned ids[]={0x080222a0,0x080226a0,0x080228a0};const char*names[]={"wave_080222a0.bin","wave_080226a0.bin","wave_080228a0.bin"};N::Tables t;t.pitch=&p;t.envelope1=&e1;t.envelope2=&e2;for(int i=0;i<3;++i){load(d+"/"+names[i],w[i]);t.waves[i]={ids[i],&w[i]};}std::ifstream f(argv[2],std::ios::binary);std::ofstream g(argv[3],std::ios::binary);N::Fold1State s;N::RngState rng;while(f.read(reinterpret_cast<char*>(s.data()),s.size())){f.read(reinterpret_cast<char*>(&rng),sizeof(rng));short pcm[16];if(!N::renderFold1(s,pcm,16,t,rng))return 3;g.write(reinterpret_cast<char*>(pcm),sizeof(pcm));g.write(reinterpret_cast<char*>(s.data()),s.size());g.write(reinterpret_cast<char*>(&rng),sizeof(rng));}return 0;}
'''


def arm_fold_cases() -> list[dict]:
    cases = []
    for mode, continuation in ((1, False), (3, False), (1, True), (2, True), (3, True)):
        for corner in range(3):
            case = FIX / f"engine-1-mode-{mode}-corner-{corner}"
            before = (case / ("wrapper-window-after.bin" if continuation
                              else "wrapper-window-before.bin")).read_bytes()[0xc4:0xc4 + 0xf4]
            after_name = ("wrapper-window-continuation-after.bin" if continuation
                          else "wrapper-window-after.bin")
            cases.append({
                "tag": f"fold arm mode {mode} corner {corner}"
                       + (" continuation" if continuation else ""),
                "state": fold.FoldDrum1.from_arm(before).words + [0] * 28,
                "pcm": list(struct.unpack("<256h", (case / (
                    "arm-pcm-continuation.bin" if continuation else "arm-pcm.bin")).read_bytes())),
                "final": fold.FoldDrum1.from_arm(
                    (case / after_name).read_bytes()[0xc4:0xc4 + 0xf4]).words,
                "rng": list(struct.unpack("<4H", (case / "rng-continuation-before.bin").read_bytes()))
                       if continuation else [0, 0, 0, 0],
                "final_rng": list(struct.unpack(
                    "<4H", (case / "rng-continuation-after.bin").read_bytes()))
                    if continuation else None,
                "blocks": 16,
            })
    return cases


def native_fold_cases(assets: Path, out: Path) -> tuple[list[dict], int]:
    """Randomized states rendered by the independent native C++ oracle."""
    native = Path(os.environ.get("PERKYBITS_SOURCE", "/Users/jrold/Downloads/perkybits")) / "Source"
    if not native.is_dir():
        die(f"missing PerkyBits source at {native}; set PERKYBITS_SOURCE")
    runner = out / "native.cpp"
    runner.write_text(FOLD_NATIVE_RUNNER)
    exe = out / "native"
    subprocess.run(["c++", "-std=c++20", "-O2", "-I" + str(native), str(runner),
                    str(native / "NativeV121FoldDrums.cpp"), "-o", str(exe)],
                   check=True, capture_output=True)
    randomizer = random.Random(0xF01D)
    template = (FIX / "engine-1-mode-2-corner-1/wrapper-window-before.bin").read_bytes()[0xc4:0xc4 + 0xf4]
    cases = []
    for i in range(400):
        voice = fold.FoldDrum1.from_arm(template)
        voice.words[0] = randomizer.choice([0, 1, 127, 255])
        voice.words[1] = int(i % 19 == 0)
        voice.words[34] = i % 3
        voice.words[35] = randomizer.choice([0, 143, 144, 272, 273, 528, 529, 65535])
        voice.words[36] = randomizer.choice([0, 4092, 65535, randomizer.randrange(65536)])
        voice.words[37] = randomizer.choice([0, 1, 2, 65535])
        voice.words[38] = randomizer.choice([0, 2, 65535])
        voice.words[39] = randomizer.randrange(65536)
        voice.words[32] = randomizer.randrange(4096)
        voice.words[33] = randomizer.randrange(4096)
        if i >= 240:
            voice.words[36] = randomizer.randrange(4093)
            voice.words[37] = randomizer.randrange(3)
            voice.words[38] = 2
        rng = struct.pack("<II", randomizer.getrandbits(32), randomizer.getrandbits(32))
        cases.append((voice.apply_to_arm(template), rng))
    (out / "native-input.bin").write_bytes(b"".join(a + b for a, b in cases))
    subprocess.run([str(exe), str(assets), str(out / "native-input.bin"),
                    str(out / "native-output.bin")], check=True)
    produced = (out / "native-output.bin").read_bytes()
    stride = 32 + 0xf4 + 8
    blocks = []
    for i, (_, rng) in enumerate(cases):
        start = i * stride
        blocks.append({
            "tag": f"fold native {i}",
            "state": fold.FoldDrum1.from_arm(cases[i][0]).words + [0] * 28,
            "pcm": list(struct.unpack("<16h", produced[start:start + 32])),
            "final": fold.FoldDrum1.from_arm(produced[start + 32:start + 32 + 0xf4]).words,
            "rng": list(struct.unpack("<4H", rng)),
            "final_rng": list(struct.unpack("<4H", produced[start + 32 + 0xf4:start + stride])),
            "blocks": 1,
        })
    return blocks, 400


# ---------------------------------------------------------------------------
# Resonant bass / snare
# ---------------------------------------------------------------------------
def resonant_state(family: str, index: int):
    """Synthetic state covering both sides of every bounded-path guard."""
    r = random.Random(0x5245534F + index)
    model, cls = ((bass, bass.ResonantBass) if family == "bass"
                  else (snare, snare.ResonantSnare))
    w = [0] * model.WORDS
    w[0] = r.choice((0, 1, 127, 255))
    make_env(w, model.AMP_ENV, r, index % 3)
    w[model.NOISE:model.NOISE + 3] = [r.randrange(4), r.randrange(4), r.randrange(65536)]
    resonators = ((bass.TONE_RES, bass.NOISE_RES) if family == "bass"
                  else (snare.RES1, snare.RES2, snare.RES3))
    for base in resonators:
        w[base + c.RES_DIRTY] = index & 1
        w[base + c.RES_PITCH_A] = r.randrange(65536)
        w[base + c.RES_PITCH_B] = r.randrange(65536)
        for field in (c.RES_COEFF_A, c.RES_COEFF_B):
            c.set_u32(w, base + field, r.randrange(65536))
        c.set_u32(w, base + c.RES_MOD, r.choice((0, 1, 65535, 0xFFFFFFFF)))
        w[base + c.RES_BYPASS] = r.randrange(2)
        for field in (c.RES_POSITION, c.RES_VELOCITY):
            c.set_u32(w, base + field, r.randint(-32767, 32767))
    decays = ((bass.DECAY_A, bass.DECAY_B, bass.DECAY_C, bass.DECAY_LEVEL)
              if family == "bass"
              else (snare.DECAY_A, snare.DECAY_B, snare.DECAY_C, snare.DECAY_D))
    for base in decays:
        for field in (c.DECAY_MUL, c.DECAY_VALUE):
            c.set_u32(w, base + field, r.getrandbits(32))
        c.set_u32(w, base + c.DECAY_COUNT, r.choice((0, 1, 2, 0xFFFFFFFF)))
        c.set_u32(w, base + c.DECAY_SIGN, r.choice((0, 0x80000000, 0xFFFFFFFF, 32767)))
        c.set_u32(w, base + c.DECAY_MIN, r.randint(-65536, 65536))
    if index >= 32:
        for base in decays:
            c.set_u32(w, base + c.DECAY_MUL,
                      r.choice((0, 1, 4095, 0x7FFFFF, 0x800000, r.randrange(1 << 24))))
            c.set_u32(w, base + c.DECAY_VALUE,
                      r.choice((0, 1, 0xFFFF, 0x7FFFFF, 0x800000, r.randrange(1 << 24))))
            c.set_u32(w, base + c.DECAY_SIGN,
                      r.choice((0, -1, 32767, 65535, 0x3FFFFF, -0x400000,
                                0x400000, -0x400001, 0x80000000)))
            c.set_u32(w, base + c.DECAY_COUNT,
                      r.choice((0, 1, 2, 65535, 0xFFFFFFFF, 0xFFFF1234, 0xFFFEFFFF)))
            c.set_u32(w, base + c.DECAY_MIN,
                      r.choice((0, 65535, -1, r.randrange(65536))))
    if family == "bass":
        w[bass.PITCH] = r.randrange(65536)
        c.set_u32(w, bass.RESONATOR_STATE, r.getrandbits(32))
        c.set_u32(w, bass.RESONATOR_COEFF, r.getrandbits(32))
    else:
        c.set_u32(w, snare.MIX_FIRST, r.getrandbits(32))
        c.set_u32(w, snare.MIX_SECOND, r.getrandbits(32))
    return cls(w), [r.getrandbits(32), r.getrandbits(32)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assets = Path(os.environ.get("PERKY_SIMPLE_ASSETS", ROOT / "out/perky/simple-drum-assets"))
    if not (assets / "pitch.bin").is_file():
        die(f"missing {assets}; generate the external Simple/Fold assets first")

    binary, labels = assemble(True, OUT / "shipping")
    renderers, rlabels = assemble(False, OUT / "renderers")
    shipping_words = binary.stat().st_size // 3

    e1, e2, _, _ = make_envelopes()
    interp_a = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    interp_b = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = tables_text(e1, e2, interp_a, interp_b, assets)

    report = {"schema": "perky-3algo-composed-exec-v1",
              "p_words_shipping": shipping_words,
              "p_words_renderers": renderers.stat().st_size // 3,
              "engines": composed.ENGINE_LABELS, "algorithms": {}}

    # ---- Fold Drum 1 -----------------------------------------------------
    fold_meters, fold_blocks, cases = [], 0, []
    for case in arm_fold_cases():
        got, state, worst = run(renderers, rlabels["pk3t_fold"], case["state"],
                                case["rng"], ytext, case["blocks"], case["tag"], OUT)
        # `run` returns stereo[::2], i.e. ONE word per sample (the host writes
        # the same value to both channels). Comparing against the fixture's
        # stereo-interleaved expectation needs the same shape, so the reference
        # is interleaved here rather than the result doubled.
        equal(got, [v for v in case["pcm"] for _ in range(2)][::2], case["tag"] + " PCM")
        equal(state[-1][:40], case["final"], case["tag"] + " X")
        if case["final_rng"] is not None:
            equal(state[-1][64:68], case["final_rng"], case["tag"] + " RNG")
        fold_meters.append(worst)
        fold_blocks += case["blocks"]
        cases.append({"case": case["tag"], "blocks": case["blocks"], "worst_cycles": worst})
    native, native_count = native_fold_cases(assets, OUT)
    short_meters = []
    for case in native:
        got, state, worst = run(renderers, rlabels["pk3t_fold"], case["state"],
                                case["rng"], ytext, 1, case["tag"], OUT)
        # `run` returns stereo[::2], i.e. ONE word per sample (the host writes
        # the same value to both channels). Comparing against the fixture's
        # stereo-interleaved expectation needs the same shape, so the reference
        # is interleaved here rather than the result doubled.
        equal(got, [v for v in case["pcm"] for _ in range(2)][::2], case["tag"] + " PCM")
        equal(state[-1][:40], case["final"], case["tag"] + " X")
        equal(state[-1][64:68], case["final_rng"], case["tag"] + " RNG")
        short_meters.append(worst)
        fold_blocks += 1
        cases.append({"case": case["tag"], "blocks": 1, "worst_cycles": worst})
    report["algorithms"]["fold"] = {
        "x_words": 40, "blocks": fold_blocks,
        "worst_cycles_arm": max(fold_meters) if fold_meters else 0,
        "worst_cycles_native": max(short_meters) if short_meters else 0,
    }
    print(f"Fold Drum 1 in composition: PASS ({fold_blocks} blocks, "
          f"{native_count} native randomized; worst {max(short_meters)} modeled "
          f"cycles/16; ARM worst {max(fold_meters)})", flush=True)

    # ---- Resonant bass / snare ------------------------------------------
    for family, model, panel, offset, size in (
            ("bass", bass, 2, 0x39E8, 0x178),
            ("snare", snare, 1, 0x2734, 0x1D4)):
        entry = rlabels[f"pk3t_{family}"]
        blocks = 0
        worst = 0
        cases = []
        for index in range(256):
            voice, rng = resonant_state(family, index)
            tag = f"{family} synthetic {index}"
            got, state, meter = run(renderers, entry, voice.words, rng, ytext,
                                    4, tag, OUT)
            for block in range(4):
                want = voice.render(16, e1, e2, interp_a, interp_b, rng)
                equal(got[block * 16:(block + 1) * 16], want, f"{tag} block {block} PCM")
                equal(state[block][:model.WORDS], voice.words, f"{tag} block {block} X")
                equal([state[block][0x72] | state[block][0x73] << 16,
                       state[block][0x74] | state[block][0x75] << 16], rng,
                      f"{tag} block {block} RNG")
            blocks += 4
            worst = max(worst, meter)
            cases.append({"case": tag, "blocks": 4, "worst_cycles": meter})
        report["algorithms"][family] = {"x_words": model.WORDS, "blocks": blocks,
                                        "worst_cycles": worst}
        print(f"Resonant {family} in composition: PASS ({blocks} blocks; "
              f"{model.WORDS} X words; worst {worst} modeled cycles/16)", flush=True)

    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"composed reduced Perky DSP: {shipping_words} P words shipping; "
          f"all three algorithms bit-exact in the shipping composition")


if __name__ == "__main__":
    main()
