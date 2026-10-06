#!/usr/bin/env python3
"""Execute PERKY's DSP filter probe and compare state exactly with the oracle."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
V = ROOT / 'vendor/dsp56300'
OUT = ROOT / 'out/perky/filter'
sys.path.insert(0, str(PERKY))
from noise_tone_word_model import U32, WordState, advance_filter  # noqa:E402

ASM = V / 'build/source/dsp_host/dsp_asm'
DIS = V / 'build/source/disassemble/dsp56kDisassemble'
HOST = OUT / 'bd909_host'
SRC = ROOT / 'tools/harness/bd909_host/bd909_host.cpp'
ORG = 0x0100  # isolated kernels fit the short-call region; shipping gate tests high P
LINE = re.compile(
    r'^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$'
)
BASE = 0x9C


def fail(msg: str) -> None:
    raise SystemExit('verify-perky-filter-exec: ' + msg)


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
    binary = OUT / 'filter.bin'
    symbols = OUT / 'filter.sym'
    r = subprocess.run(
        [
            str(ASM), '-in', str(PERKY / 'noise_tone_filter.asm'),
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
    if 'pk_filter_probe' not in labels:
        fail('assembler emitted no pk_filter_probe symbol')

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
    return binary, labels['pk_filter_probe']


def limbs(value: int) -> tuple[int, int]:
    u = U32.from_int(value)
    return u.lo, u.hi


def oracle(coeff: int, damping: int, first: int, velocity: int, sample: int):
    state = WordState(bytearray(0x120))
    state.set_u16(BASE + 0x0E, coeff)
    state.set_u16(BASE + 0x0C, damping)
    state.set_u32(BASE + 0x10, U32.from_int(first))
    state.set_u32(BASE + 0x18, U32.from_int(velocity))
    signed_sample = sample if sample < 0x8000 else sample - 0x10000
    advance_filter(state, BASE, signed_sample)
    return (
        state.u32(BASE + 0x10),
        state.u32(BASE + 0x14),
        state.u32(BASE + 0x18),
    )


def run(binary, entry, tag, coeff, damping, first, velocity, sample):
    words = [0] * 100
    words[0x44] = coeff & 0xffff
    words[0x45] = damping & 0xffff
    words[0x46], words[0x47] = limbs(first)
    words[0x50], words[0x51] = limbs(velocity)
    words[0x52] = sample & 0xffff

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
            '-out', str(raw), '-state', str(state_path), '-state-words', '100',
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dumped = [int(x, 16) for x in state_path.read_text().split()]
    if len(dumped) < 64:
        fail(f'{tag}: truncated state dump')
    first_got = U32(dumped[0x46] & 0xffff, dumped[0x47] & 0xffff)
    second_got = U32(dumped[0x48] & 0xffff, dumped[0x49] & 0xffff)
    velocity_got = U32(dumped[0x50] & 0xffff, dumped[0x51] & 0xffff)
    return first_got, second_got, velocity_got


def check(tag: str, got: U32, want: U32) -> None:
    if got != want:
        fail(
            f'{tag}: got {got.unsigned():08x} ({got.signed()}), '
            f'want {want.unsigned():08x} ({want.signed()})'
        )


def main() -> None:
    build_host()
    binary, entry = assemble()

    # These deliberately include states around every signed clamp and around
    # the firmware's negative-product +0xffff rounding quirk.
    cases = [
        # coeff, damping, first, velocity, input-u16
        (0x0000, 0x0000, 0, 0, 0x0000),
        (0x0000, 0x0000, 12345, -23456, 0x7fff),
        (0x0000, 0xffff, -12345, 23456, 0x8000),
        (0x0001, 0x0001, 32767, 32767, 0x7fff),
        (0x0001, 0x0001, -32767, -32767, 0x8001),
        (0x7fff, 0x0000, 0, 32767, 0x7fff),
        (0x7fff, 0x7fff, 0, -32767, 0x8000),
        (0xffff, 0xffff, 30000, 30000, 0x7fff),
        (0xffff, 0xffff, -30000, -30000, 0x8000),
        (0x4000, 0x2000, 32760, 32760, 0x7fff),
        (0x4000, 0x2000, -32760, -32760, 0x8000),
        (0x1234, 0xabcd, 0x1234, -0x2345, 0x8ace),
        (0xabcd, 0x1234, -0x1234, 0x2345, 0x7531),
        (0xfffe, 0x8001, 1, -1, 0xffff),
        (0x8001, 0xfffe, -1, 1, 0x0001),
    ]

    checked = 0
    for i, case in enumerate(cases):
        want = oracle(*case)
        got = run(binary, entry, f'filter-{i}', *case)
        for field, actual, expected in zip(
            ('first', 'second', 'velocity'), got, want
        ):
            check(f'case {i} {field}', actual, expected)
            checked += 1

    print(
        f'PERKY Noise/Tone filter executable gate: OK '
        f'({len(cases)} states, {checked} exact u32 outputs)'
    )


if __name__ == '__main__':
    main()
