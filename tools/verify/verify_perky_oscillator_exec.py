#!/usr/bin/env python3
"""Execute PERKY oscillator interpolation against synthetic-table oracle cases."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
V = ROOT / 'vendor/dsp56300'
OUT = ROOT / 'out/perky/oscillator'
sys.path.insert(0, str(PERKY))
from noise_tone_word_model import U32, WordState, render_oscillator  # noqa:E402

ASM = V / 'build/source/dsp_host/dsp_asm'
DIS = V / 'build/source/disassemble/dsp56kDisassemble'
HOST = OUT / 'bd909_host'
SRC = ROOT / 'tools/harness/bd909_host/bd909_host.cpp'
ORG = 0x0100  # isolated kernels fit the short-call region; shipping gate tests high P
ID0 = 0x11112222
ID1 = 0x33334444
TABLE0 = 0x3000
TABLE1 = 0x3100
BASE = 0x2C
LINE = re.compile(
    r'^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$'
)


def fail(msg: str) -> None:
    raise SystemExit('verify-perky-oscillator-exec: ' + msg)


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
    binary = OUT / 'oscillator.bin'
    symbols = OUT / 'oscillator.sym'
    r = subprocess.run(
        [
            str(ASM), '-in', str(PERKY / 'noise_tone_oscillator.asm'),
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
    if 'pk_osc_probe' not in labels:
        fail('assembler emitted no pk_osc_probe symbol')

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
    return binary, labels['pk_osc_probe']


def wave0_raw(index: int) -> int:
    return (index * 257 + 0x1357) & 0xFFFF


def wave1_raw(index: int) -> int:
    return ((index * 911) ^ 0xA5A5) & 0xFFFF


def wave_bytes(fn) -> bytes:
    out = bytearray()
    for i in range(256):
        value = fn(i)
        out += bytes((value & 0xFF, value >> 8))
    return bytes(out)


WAVE0 = wave_bytes(wave0_raw)
WAVE1 = wave_bytes(wave1_raw)
WAVES = {ID0: WAVE0, ID1: WAVE1}


def limbs(value: int) -> tuple[int, int]:
    u = U32.from_int(value)
    return u.lo, u.hi


def oracle(phase: int, inc: int, current: int, nxt: int):
    state = WordState(bytearray(0x120))
    state.set_u32(BASE + 4, U32.from_int(phase))
    state.set_u32(BASE + 8, U32.from_int(inc))
    state.set_u32(BASE + 0x0C, U32.from_int(current))
    state.set_u32(BASE + 0x10, U32.from_int(nxt))
    sample = render_oscillator(state, BASE, WAVES)
    return (
        state.u32(BASE + 4),
        state.u32(BASE + 0x0C),
        sample & 0xFFFF,
    )


def run(binary, entry, tag, phase, inc, current, nxt):
    words = [0] * 100
    words[0x40], words[0x41] = limbs(phase)
    words[0x42], words[0x43] = limbs(inc)
    words[0x44], words[0x45] = limbs(current)
    words[0x46], words[0x47] = limbs(nxt)

    data = OUT / f'{tag}.data'
    script = OUT / f'{tag}.script'
    raw = OUT / f'{tag}.raw'
    state_path = OUT / f'{tag}.state'
    data.write_text(
        'X 200 ' + ' '.join(f'{x:06x}' for x in words) + '\n'
        + f'X {TABLE0:x} ' + ' '.join(f'{wave0_raw(i):06x}' for i in range(256)) + '\n'
        + f'X {TABLE1:x} ' + ' '.join(f'{wave1_raw(i):06x}' for i in range(256)) + '\n'
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
        U32(dumped[0x40] & 0xFFFF, dumped[0x41] & 0xFFFF),
        U32(dumped[0x44] & 0xFFFF, dumped[0x45] & 0xFFFF),
        dumped[0x48] & 0xFFFF,
    )


def check_u32(tag: str, got: U32, want: U32) -> None:
    if got != want:
        fail(
            f'{tag}: got {got.unsigned():08x}, want {want.unsigned():08x}'
        )


def main() -> None:
    build_host()
    binary, entry = assemble()

    # Boundary cases deliberately exercise the strict > $00100000 test,
    # table switching, 32-bit phase wrap, index 255 -> 0 interpolation and
    # negative signed phases which must NOT take the waveform-wrap path.
    cases = [
        (0x00000000, 0x00000000, ID0, ID0),
        (0x00000000, 0x00000FFF, ID0, ID0),
        (0x000FE000, 0x00000ABC, ID0, ID0),
        (0x000FF000, 0x00001000, ID0, ID1),   # exactly threshold: no switch
        (0x000FF001, 0x00001000, ID0, ID1),   # threshold+1: switch
        (0x000FFFFF, 0x00000002, ID0, ID1),   # tiny wrapped phase
        (0x000FEABC, 0x00000000, ID0, ID0),   # index 254/255 interpolation
        (0x000FFABC, 0x00000000, ID0, ID0),   # index 255/0 interpolation
        (0x00100000, 0x00000001, ID1, ID0),   # switch back to table 0
        (0x7FFFFFFF, 0x00000001, ID0, ID1),   # add wraps signed-negative
        (0xFFFFFFFF, 0x00000000, ID1, ID0),   # negative phase, no switch
        (0xFFFFFFFE, 0x00000003, ID1, ID1),   # modulo add -> +1
        (0x000FFFF0, 0x00000020, ID1, ID1),   # wrap but same table
    ]

    checked = 0
    for i, case in enumerate(cases):
        want_phase, want_current, want_sample = oracle(*case)
        got_phase, got_current, got_sample = run(
            binary, entry, f'osc-{i}', *case
        )
        check_u32(f'case {i} phase', got_phase, want_phase)
        check_u32(f'case {i} current', got_current, want_current)
        if got_sample != want_sample:
            fail(
                f'case {i} sample: got {got_sample:04x}, '
                f'want {want_sample:04x}'
            )
        checked += 3

    print(
        f'PERKY Noise/Tone oscillator executable gate: OK '
        f'({len(cases)} states, {checked} exact outputs)'
    )


if __name__ == '__main__':
    main()
