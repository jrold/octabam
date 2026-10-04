#!/usr/bin/env python3
"""Execute PERKY final Noise/Tone mixer and compare exactly to limb oracle."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
V = ROOT / 'vendor/dsp56300'
OUT = ROOT / 'out/perky/mix'
sys.path.insert(0, str(PERKY))
from noise_tone_word_model import (  # noqa:E402
    U32,
    add32,
    arshift32_words,
    mul_low32_words,
    sub32,
)

ASM = V / 'build/source/dsp_host/dsp_asm'
DIS = V / 'build/source/disassemble/dsp56kDisassemble'
HOST = OUT / 'bd909_host'
SRC = ROOT / 'tools/harness/bd909_host/bd909_host.cpp'
ORG = 0x3000
LINE = re.compile(
    r'^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$'
)


def fail(msg: str) -> None:
    raise SystemExit('verify-perky-mix-exec: ' + msg)


def decoded(text: str):
    return {
        int(m.group(1), 16): (m.group(2), (m.group(3) or '').strip())
        for m in map(LINE.match, text.splitlines())
        if m
    }


def build_host() -> None:
    libs = [
        V / 'build/source/dsp56kEmu/libdsp56kEmu.a',
        V / 'build/source/dsp56kBase/libdsp56kBase.a',
        V / 'build/source/asmjit/libasmjit.a',
    ]
    missing = [p for p in [ASM, DIS, *libs] if not p.exists()]
    if missing:
        fail('run `make setup` first; missing ' + ', '.join(map(str, missing)))
    OUT.mkdir(parents=True, exist_ok=True)
    if HOST.exists() and HOST.stat().st_mtime > SRC.stat().st_mtime:
        return
    subprocess.run(
        [
            'c++', '-O3', '-DNDEBUG', '-std=gnu++17', '-DASMJIT_STATIC',
            '-DDSP56300_DEBUGGER=0', f'-I{V}/source', f'-I{V}/source/asmjit/src',
            str(SRC), str(libs[0]), str(libs[1]), str(libs[2]), '-lpthread',
            '-o', str(HOST),
        ],
        check=True,
        capture_output=True,
    )


def assemble():
    binary = OUT / 'mix.bin'
    symbols = OUT / 'mix.sym'
    r = subprocess.run(
        [
            str(ASM), '-in', str(PERKY / 'noise_tone_mix.asm'),
            '-org', f'{ORG:x}', '-out', str(binary), '-list', '-sym', str(symbols),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        fail('assembler failed:\n' + r.stdout[-4000:] + r.stderr[-2000:])
    labels = {
        q[0]: int(q[1], 16)
        for q in (line.split() for line in symbols.read_text().splitlines())
        if len(q) == 2
    }
    if 'pk_mix_probe' not in labels:
        fail('assembler emitted no pk_mix_probe symbol')

    d = subprocess.run(
        [str(DIS), '-in', str(binary), '-pc', f'{ORG:x}', '-le'],
        capture_output=True,
        text=True,
        check=True,
    )
    typed, actual = decoded(r.stdout), decoded(d.stdout)
    if not typed or len(actual) < len(typed) * .9:
        fail('no usable disassembly to compare')
    for addr, (mnemonic, operands) in typed.items():
        dm, dops = actual.get(addr, ('?', ''))
        if dm != mnemonic:
            fail(
                f'P:{addr:06x} typed {mnemonic} {operands} '
                f'but decodes {dm} {dops}'
            )
    return binary, labels['pk_mix_probe']


def s16(raw: int) -> int:
    raw &= 0xFFFF
    return raw - 0x10000 if raw & 0x8000 else raw


def oracle(mix: int, noise: int, osc1: int, osc2: int, amplitude: int, velocity: int):
    mix_u = U32.from_int(mix)
    accumulator = arshift32_words(
        mul_low32_words(mix_u, U32.from_int(s16(noise))), 13
    )
    osc_sum = arshift32_words(
        add32(U32.from_int(s16(osc1)), U32.from_int(s16(osc2))), 4
    )
    factor = sub32(U32.from_int(0x0FFF), mix_u)
    tonal = mul_low32_words(factor, osc_sum)
    accumulator = add32(accumulator, arshift32_words(tonal, 9))
    output = arshift32_words(
        mul_low32_words(accumulator, U32(amplitude & 0xFFFF, 0)), 16
    )
    output = arshift32_words(
        mul_low32_words(output, U32(velocity & 0xFF, 0)), 8
    )
    pre = output
    signed = output.signed()
    if signed < -32768:
        signed = -32768
    elif signed > 32767:
        signed = 32767
    return pre, signed & 0xFFFF


def limbs(value: int) -> tuple[int, int]:
    u = U32.from_int(value)
    return u.lo, u.hi


def run(binary, entry, tag, case):
    mix, noise, osc1, osc2, amplitude, velocity = case
    words = [0] * 64
    words[40], words[41] = limbs(mix)
    words[42] = noise & 0xFFFF
    words[43] = osc1 & 0xFFFF
    words[44] = osc2 & 0xFFFF
    words[45] = amplitude & 0xFFFF
    words[46] = velocity & 0xFF

    data = OUT / f'{tag}.data'
    script = OUT / f'{tag}.script'
    raw = OUT / f'{tag}.raw'
    state_path = OUT / f'{tag}.state'
    data.write_text('X 200 ' + ' '.join(f'{x:06x}' for x in words) + '\n')
    script.write_text(' '.join(['0'] * 12 + ['-1']) + '\n')
    subprocess.run(
        [
            str(HOST), '-code', str(binary), '-org', f'{ORG:x}',
            '-entry', f'{entry:x}', '-data', str(data), '-script', str(script),
            '-out', str(raw), '-state', str(state_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dumped = [int(x, 16) for x in state_path.read_text().split()]
    if len(dumped) < 64:
        fail(f'{tag}: truncated state dump')
    return (
        U32(dumped[48] & 0xFFFF, dumped[49] & 0xFFFF),
        dumped[47] & 0xFFFF,
    )


def main() -> None:
    build_host()
    binary, entry = assemble()

    # mix, noise, osc1, osc2, amplitude, velocity
    cases = [
        (0, 0, 0, 0, 0, 0),
        (0, 0, 0x7FFF, 0x7FFF, 0xFFFF, 0x7F),
        (0, 0, 0x8000, 0x8000, 0xFFFF, 0x7F),
        (0x0FFF, 0x7FFF, 0, 0, 0xFFFF, 0x7F),
        (0x0FFF, 0x8000, 0, 0, 0xFFFF, 0x7F),
        (0x0800, 0x1234, 0x2345, 0x3456, 0x8000, 0x40),
        (0x0800, 0xEDCC, 0xDCBB, 0xCBAA, 0x8000, 0x40),
        (0x1000, 0x7FFF, 0x7FFF, 0x8000, 0xFFFF, 0xFF),
        (0x1FFF, 0x8000, 0x7FFF, 0x7FFF, 0xFFFF, 0xFF),
        (0xFFFFFFFF, 0xFFFF, 0xFFFF, 0x0001, 0xFFFF, 0xFF),
        (0x80000000, 0x4000, 0x4000, 0x4000, 0xFFFF, 0x80),
        (0x7FFFFFFF, 0xC000, 0xC000, 0xC000, 0xFFFF, 0x80),
        (0x00000400, 0x7FFF, 0x7FFF, 0x7FFF, 0xFFFF, 0xFF),
        (0x00000C00, 0x8000, 0x8000, 0x8000, 0xFFFF, 0xFF),
        (0x00000800, 0x7FFF, 0x8000, 0x7FFF, 0xFFFF, 0x00),
    ]

    checked = 0
    for i, case in enumerate(cases):
        want_pre, want_output = oracle(*case)
        got_pre, got_output = run(binary, entry, f'mix-{i}', case)
        if got_pre != want_pre:
            fail(
                f'case {i} pre-clamp: got {got_pre.unsigned():08x} '
                f'({got_pre.signed()}), want {want_pre.unsigned():08x} '
                f'({want_pre.signed()})'
            )
        if got_output != want_output:
            fail(
                f'case {i} output: got {got_output:04x}, want {want_output:04x}'
            )
        checked += 2

    print(
        f'PERKY Noise/Tone mixer executable gate: OK '
        f'({len(cases)} states, {checked} exact outputs)'
    )


if __name__ == '__main__':
    main()
