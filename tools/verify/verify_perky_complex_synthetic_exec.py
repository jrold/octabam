#!/usr/bin/env python3
"""CI-safe executable gate for the Complex Drum DSP candidate.

Synthetic tables/states avoid firmware-derived assets while exercising both
oscillators, deferred fourth-wave switching, shaped pitch envelope, pitch-basis
decode and exact 42-word state continuation.
"""
from pathlib import Path
import random, struct, subprocess, sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import complex_drum_compact as compact
import simple_drum_compact as simple
import simple_drum_tables as tables
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals

OUT = ROOT / 'out/perky/complex-drum-synthetic'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'
WAVE_IDS = (0x080222A0, 0x080226A0, 0x080228A0, 0x080224A0)


def set_u32(words, off, value):
    words[off] = value & 0xffff
    words[off + 1] = (value >> 16) & 0xffff


def make_pitch():
    basis = [30000 + i for i in range(512)]
    full = [basis[i & 0x1ff] >> (7 - (i >> 9)) for i in range(4096)]
    packed = tables.pack_pitch_basis(full).words
    blob = b''.join(struct.pack('<H', v) for v in full)
    return blob, packed


def make_envelope():
    values = [min(65535, i * 63) for i in range(1024)]
    full = values + [values[-1]] * 1024
    return b''.join(struct.pack('<H', v) for v in full), tables.pack_u16(values)


def make_waves():
    waves = {}
    for ordinal, address in enumerate(WAVE_IDS):
        vals = []
        for i in range(256):
            if ordinal == 0:
                v = (i - 128) * 180
            elif ordinal == 1:
                v = 26000 if i < 96 else (-18000 if i < 192 else 7000)
            elif ordinal == 2:
                v = (127 - i) * 211
            else:
                v = ((i * 1543 + 0x2345) & 0xffff) - 0x8000
            vals.append(max(-32768, min(32767, v)))
        waves[address] = b''.join(struct.pack('<h', v) for v in vals)
    return waves


def make_voice(seed):
    r = random.Random(seed)
    w = [0] * compact.WORDS
    w[compact.VELOCITY] = r.choice((31, 63, 127, 255))
    w[compact.MUTE] = int(seed % 19 == 0)

    # Main and modulation oscillators. Cases deliberately choose 24a0 as both
    # current and deferred-next identities so the fourth packed bank is read.
    osc_sets = (
        (compact.MAIN_PHASE, WAVE_IDS[seed & 3], WAVE_IDS[(seed + 3) & 3]),
        (compact.MOD_PHASE, WAVE_IDS[(seed + 1) & 3], WAVE_IDS[(seed + 2) & 3]),
    )
    for base, current, nxt in osc_sets:
        set_u32(w, base + 0, r.choice((0, 0x000fe000, 0x000ffff0, 0x00100000)))
        set_u32(w, base + 2, r.choice((0x00008000, 0x00018000, 0x00030000)))
        set_u32(w, base + 4, current)
        set_u32(w, base + 6, nxt)

    # Amp uses analytic shape 0; pitch uses relocated shape-1 table at Y:$0a50.
    for base, shape in ((compact.AMP_ENV, 0), (compact.PITCH_ENV, 1)):
        w[base + simple.ENV_STATE] = r.choice((1, 3, 4))
        w[base + simple.ENV_SHAPE] = shape
        w[base + simple.ENV_FLAG4] = r.choice((0, 1))
        w[base + simple.ENV_FLAG6] = r.choice((0, 1))
        w[base + simple.ENV_TRIGGER] = r.choice((0, 1))
        set_u32(w, base + simple.ENV_VALUE, r.choice((0x18000, 0x70000, 0x0ff000)))
        set_u32(w, base + simple.ENV_HOLD, r.choice((0, 1, 0x100)))
        w[base + simple.ENV_ATTACK] = r.choice((1, 0x40, 0x800))
        w[base + simple.ENV_DECAY] = r.choice((1, 0x20, 0x400))

    w[compact.RAW_PITCH] = r.randrange(4096)
    w[compact.PITCH_AMOUNT] = r.randrange(4096)
    return compact.CompactComplexDrum(w)


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    source = 'pk_complex_probe:\n move #>$200,r6\n move #>$3900,r5\n jsr pk_complex_voice\n rts\n'
    source += (ROOT / 'modules/perky/complex_drum_voice.asm').read_text()
    for name, label in (
        ('envelope', 'pk_simple_envelope'),
        ('frequency', 'pk_simple_frequency'),
        ('oscillator', 'pk_simple_oscillator'),
    ):
        text = (ROOT / f'modules/perky/simple_drum_{name}.asm').read_text()
        text = text[text.index('\n' + label + ':'):]
        if name == 'envelope':
            text = text.replace('#>$0009a5,r1', '#>$000a50,r1')
        source += text
    source += (ROOT / 'modules/perky/simple_drum_delta.asm').read_text()
    asm = OUT / 'candidate.asm'
    binary = OUT / 'candidate.bin'
    symbols = OUT / 'candidate.sym'
    asm.write_text(force_long_local_jsr(relativize_local_conditionals(source)))
    result = subprocess.run(
        [str(ASM), '-in', str(asm), '-org', '2800', '-out', str(binary), '-sym', str(symbols)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    labels = {p[0]: int(p[1], 16) for p in map(str.split, symbols.read_text().splitlines()) if len(p) == 2}
    return binary, labels['pk_complex_probe']


def main():
    binary, entry = assemble()
    pitch_blob, pitch_words = make_pitch()
    env_blob, env_words = make_envelope()
    waves = make_waves()
    wave_words = tables.pack_u16(
        v for address in WAVE_IDS for v in struct.unpack('<256H', waves[address])
    )
    script = OUT / 'case.script'
    script.write_text(' '.join(['0'] * 12 + ['-1']) + '\n')

    meters = []
    for index in range(72):
        voice = make_voice(index + 1)
        expected = compact.CompactComplexDrum(list(voice.words))
        want = compact.render_block(expected, 16, waves, pitch_blob, env_blob, env_blob)
        state = list(voice.words) + [0] * 30
        data = OUT / 'case.data'
        data.write_text(
            'X 200 ' + ' '.join(f'{x:06x}' for x in state) + '\n'
            + 'Y 7a5 ' + ' '.join(f'{x:06x}' for x in wave_words) + '\n'
            + 'Y a50 ' + ' '.join(f'{x:06x}' for x in env_words) + '\n'
            + 'Y efb ' + ' '.join(f'{x:06x}' for x in pitch_words) + '\n'
            + 'X 3964 ffffff\n'
        )
        pcm = OUT / 'case.raw'
        dump = OUT / 'case.state'
        meter = OUT / 'case.meter'
        subprocess.run([
            str(HOST), '-code', str(binary), '-org', '2800', '-entry', f'{entry:x}',
            '-data', str(data), '-script', str(script), '-out', str(pcm),
            '-state', str(dump), '-state-words', '42',
            '-meter', str(meter), '-cycle-meter', '1',
        ], check=True, capture_output=True)
        got = list(struct.unpack('<32i', pcm.read_bytes()))[::2]
        assert got == want, (
            index, 'PCM', [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:8]
        )
        final = [int(x, 16) & 0xffff for x in dump.read_text().split()[:42]]
        assert final == expected.words, (
            index, 'state', [(i, a, b) for i, (a, b) in enumerate(zip(final, expected.words)) if a != b][:8]
        )
        meters.append(int(meter.read_text().strip()))

    print(
        f'Complex Drum synthetic DSP: PASS (72 cases; fourth-wave switch + shaped envelope; '
        f'{binary.stat().st_size // 3} P words; worst {max(meters)} modeled cycles)'
    )


if __name__ == '__main__':
    main()
