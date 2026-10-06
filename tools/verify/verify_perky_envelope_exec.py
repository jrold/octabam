#!/usr/bin/env python3
"""Execute PERKY envelope state/interpolation and compare exactly to word model."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
V = ROOT / 'vendor/dsp56300'
OUT = ROOT / 'out/perky/envelope'
sys.path.insert(0, str(PERKY))
from noise_tone_word_model import U32, WordState, render_envelope  # noqa:E402

ASM = V / 'build/source/dsp_host/dsp_asm'
DIS = V / 'build/source/disassemble/dsp56kDisassemble'
HOST = OUT / 'bd909_host'
SRC = ROOT / 'tools/harness/bd909_host/bd909_host.cpp'
ORG = 0x0100  # isolated kernels fit the short-call region; shipping gate tests high P
TABLE1 = 0x3200
TABLE2 = 0x3A00
BASE = 0x74
LINE = re.compile(
    r'^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$'
)


def fail(msg: str) -> None:
    raise SystemExit('verify-perky-envelope-exec: ' + msg)


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
    binary = OUT / 'envelope.bin'
    symbols = OUT / 'envelope.sym'
    r = subprocess.run(
        [
            str(ASM), '-in', str(PERKY / 'noise_tone_envelope.asm'),
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
    if 'pk_envelope_probe' not in labels:
        fail('assembler emitted no pk_envelope_probe symbol')

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
    return binary, labels['pk_envelope_probe']


def curve1_raw(index: int) -> int:
    return (index * 31 + 0x1234) & 0xFFFF


def curve2_raw(index: int) -> int:
    return ((index * 97) ^ 0xBEEF) & 0xFFFF


def curve_bytes(fn) -> bytes:
    out = bytearray()
    for i in range(2048):
        value = fn(i)
        out += bytes((value & 0xFF, value >> 8))
    return bytes(out)


CURVE1 = curve_bytes(curve1_raw)
CURVE2 = curve_bytes(curve2_raw)


def limbs(value: int) -> tuple[int, int]:
    u = U32.from_int(value)
    return u.lo, u.hi


def oracle(case):
    env_state, shape, flag4, flag6, flag7, value, hold, attack, decay = case
    state = WordState(bytearray(0x120))
    state.set_byte(BASE, env_state)
    state.set_byte(BASE + 1, shape)
    state.set_byte(BASE + 4, flag4)
    state.set_byte(BASE + 6, flag6)
    state.set_byte(BASE + 7, flag7)
    state.set_u32(BASE + 0x0C, U32.from_int(value))
    state.set_u32(BASE + 0x10, U32.from_int(hold))
    state.set_u16(BASE + 0x20, attack)
    state.set_u16(BASE + 0x22, decay)
    output = render_envelope(state, BASE, CURVE1, CURVE2)
    return state.byte(BASE), state.u32(BASE + 0x0C), output


def run(binary, entry, tag, case):
    env_state, shape, flag4, flag6, flag7, value, hold, attack, decay = case
    words = [0] * 100
    words[0x40] = env_state & 0xFF
    words[0x41] = shape & 0xFF
    words[0x42] = flag4 & 0xFF
    words[0x43] = flag6 & 0xFF
    words[0x44] = flag7 & 0xFF
    words[0x45], words[0x46] = limbs(value)
    words[0x47], words[0x48] = limbs(hold)
    words[0x49] = attack & 0xFFFF
    words[0x50] = decay & 0xFFFF

    data = OUT / f'{tag}.data'
    script = OUT / f'{tag}.script'
    raw = OUT / f'{tag}.raw'
    state_path = OUT / f'{tag}.state'
    data.write_text(
        'X 200 ' + ' '.join(f'{x:06x}' for x in words) + '\n'
        + f'X {TABLE1:x} ' + ' '.join(f'{curve1_raw(i):06x}' for i in range(2048)) + '\n'
        + f'X {TABLE2:x} ' + ' '.join(f'{curve2_raw(i):06x}' for i in range(2048)) + '\n'
    )
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
    return (
        dumped[0x40] & 0xFF,
        U32(dumped[0x45] & 0xFFFF, dumped[0x46] & 0xFFFF),
        dumped[0x51] & 0xFFFF,
    )


def check_u32(tag: str, got: U32, want: U32) -> None:
    if got != want:
        fail(
            f'{tag}: got {got.unsigned():08x} ({got.signed()}), '
            f'want {want.unsigned():08x} ({want.signed()})'
        )


def main() -> None:
    build_host()
    binary, entry = assemble()

    # env, shape, flag4, flag6, flag7, value, hold, attack, decay
    cases = [
        (0, 0, 0, 0, 0, 0x00012345, 0, 0, 0),
        (0, 0, 0, 0, 1, 0x00012345, 0, 0, 0),
        (0, 0, 1, 0, 0, 0x00012345, 0, 0, 0),
        (1, 0, 0, 0, 0, 0x00010000, 0, 0x1234, 0),
        (1, 0, 0, 0, 0, 0x000FF000, 0, 0x0FFF, 0),  # -> fffff, state 3
        (1, 0, 0, 1, 0, 0x000FF000, 0, 0x1000, 0),  # -> 100000 then clamp/state4
        (1, 0, 1, 0, 0, 0x000FF000, 0, 0x1000, 0),
        (1, 0, 0, 0, 0, 0x000FFFFE, 0, 1, 0),       # exact fffff, no clamp
        (1, 0, 0, 0, 0, 0x000FFFFF, 0, 1, 0),       # 100000 -> clamp
        (2, 0, 1, 1, 1, 0x00123456, 0, 0xFFFF, 0xFFFF),
        (3, 0, 0, 0, 1, 0x000F0000, 0, 0, 0),
        (3, 0, 0, 0, 0, 0x000F0000, 1, 0, 0),
        (3, 0, 1, 0, 0, 0x000F0000, 1, 0, 0),
        (3, 0, 0, 0, 0, 0x000F0000, 0, 0, 0),
        (4, 0, 0, 0, 1, 0x00010000, 0, 0, 0x0100),
        (4, 0, 0, 0, 0, 0x00010000, 0, 0, 0x0100),
        (4, 0, 0, 0, 0, 0x00000010, 0, 0, 0x0020),
        (4, 0, 1, 0, 0, 0x00000010, 0, 0, 0x0020),
        # Curve interpolation without state mutation (state 2).
        (2, 1, 0, 0, 0, 0x00000000, 0, 0, 0),
        (2, 1, 0, 0, 0, 0x000003FF, 0, 0, 0),
        (2, 1, 0, 0, 0, 0x001FFFFF, 0, 0, 0),  # index 2047 -> 0
        (2, 2, 0, 0, 0, 0x000ABCDE, 0, 0, 0),
        (2, 2, 0, 0, 0, 0x00123456, 0, 0, 0),
        (2, 7, 0, 0, 0, 0x89ABCDEF, 0, 0, 0),  # unknown shape = linear
    ]

    checked = 0
    for i, case in enumerate(cases):
        want_state, want_value, want_output = oracle(case)
        got_state, got_value, got_output = run(binary, entry, f'env-{i}', case)
        if got_state != want_state:
            fail(f'case {i} state: got {got_state}, want {want_state}')
        check_u32(f'case {i} value', got_value, want_value)
        if got_output != want_output:
            fail(
                f'case {i} output: got {got_output:04x}, want {want_output:04x}'
            )
        checked += 3

    print(
        f'PERKY Noise/Tone envelope executable gate: OK '
        f'({len(cases)} states, {checked} exact outputs)'
    )


if __name__ == '__main__':
    main()
