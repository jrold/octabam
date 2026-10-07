#!/usr/bin/env python3
"""CI-safe Fold Drum 2 DSP execution gate.

Uses deterministic synthetic wave/state fixtures so public CI can assemble and
execute the candidate without firmware-derived assets. The local full oracle
gate remains verify_perky_fold2_dsp_exec.py.
"""
from pathlib import Path
import random, struct, subprocess, sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import fold_drum2_compact as fold2
import simple_drum_compact as simple
import simple_drum_tables as packed
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals

OUT = ROOT / 'out/perky/fold-drum2-synthetic'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'
WAVE_IDS = (0x080222A0, 0x080224A0, 0x080226A0, 0x080228A0)


def make_waves():
    waves = {}
    for ordinal, address in enumerate(WAVE_IDS):
        values = []
        for i in range(256):
            if ordinal == 0:
                v = ((i - 128) * 257) // 2
            elif ordinal == 1:
                v = 24000 if i < 128 else -24000
            elif ordinal == 2:
                v = (127 - i) * 193
            else:
                v = ((i * 977 + 12345) & 0xffff) - 0x8000
            values.append(max(-32768, min(32767, v)))
        waves[address] = b''.join(struct.pack('<h', v) for v in values)
    return waves


def u32_words(value):
    return [value & 0xffff, (value >> 16) & 0xffff]


def set_u32(words, off, value):
    words[off:off + 2] = u32_words(value & 0xffffffff)


def state_case(seed, mode, primary, fade, counter, noise_count, muted=False):
    rng = random.Random(seed)
    w = [0] * fold2.WORDS
    w[fold2.VELOCITY] = rng.choice((1, 63, 127, 255))
    w[fold2.MUTE] = int(muted)
    for base, cur, nxt in (
        (fold2.OSC_A, WAVE_IDS[(seed + 0) & 3], WAVE_IDS[(seed + 1) & 3]),
        (fold2.OSC_B, WAVE_IDS[(seed + 2) & 3], WAVE_IDS[(seed + 3) & 3]),
    ):
        set_u32(w, base + 0, rng.choice((0, 0x000ff000, 0x000ffff0, 0x00100000)))
        set_u32(w, base + 2, rng.choice((0x00008000, 0x00018000, 0x00028000)))
        set_u32(w, base + 4, cur)
        set_u32(w, base + 6, nxt)
    for base in (fold2.AMP_ENV, fold2.PITCH_ENV):
        w[base + simple.ENV_STATE] = rng.choice((1, 3, 4))
        w[base + simple.ENV_SHAPE] = 0
        w[base + simple.ENV_FLAG4] = rng.choice((0, 1))
        w[base + simple.ENV_FLAG6] = rng.choice((0, 1))
        w[base + simple.ENV_TRIGGER] = rng.choice((0, 1))
        set_u32(w, base + simple.ENV_VALUE, rng.choice((0x20000, 0x80000, 0x0fffff)))
        set_u32(w, base + simple.ENV_HOLD, rng.choice((0, 1, 0x100)))
        w[base + simple.ENV_ATTACK] = rng.choice((1, 0x80, 0x1000))
        w[base + simple.ENV_DECAY] = rng.choice((1, 0x40, 0x800))
    w[fold2.RAW_PITCH] = rng.randrange(0x1000)
    w[fold2.PITCH_AMOUNT] = rng.randrange(0x1000)
    w[fold2.MODE] = mode
    w[fold2.COUNTER] = counter
    w[fold2.FOLD] = rng.choice((0, 0x80, 0x100, 0x300, 0xffff))
    w[fold2.NOISE_COUNT] = noise_count
    w[fold2.NOISE_RATE] = rng.choice((0, 1, 2, 7))
    w[fold2.NOISE_SAMPLE] = rng.randrange(0x10000)
    w[fold2.FADE_SAVED] = rng.randrange(0x10000)
    w[fold2.FADE] = fade
    w[fold2.PRIMARY] = primary
    return fold2.FoldDrum2(w)


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    perky = ROOT / 'modules/perky'
    source = '''pk_fold2_probe:\n move #>$200,r6\n move #>$3900,r5\n jsr pk_fold2_voice\n move x:>$38e8,a\n move a1,x:>$240\n move x:>$38e9,a\n move a1,x:>$241\n move x:>$38ea,a\n move a1,x:>$242\n move x:>$38eb,a\n move a1,x:>$243\n rts\n'''
    source += (perky / 'fold_drum2_voice.asm').read_text()
    for name, label in (
        ('envelope', 'pk_simple_envelope'),
        ('frequency', 'pk_simple_frequency'),
        ('oscillator', 'pk_simple_oscillator'),
    ):
        text = (perky / f'simple_drum_{name}.asm').read_text()
        source += text[text.index('\n' + label + ':'):]
    noise = (perky / 'noise_tone_voice_native_xstate.asm').read_text()
    source += '\npknv_noise:' + noise.split('\npknv_noise:', 1)[1]
    source += (perky / 'noise_tone_math.asm').read_text()
    asm = OUT / 'candidate.asm'
    binary = OUT / 'candidate.bin'
    symbols = OUT / 'candidate.sym'
    asm.write_text(force_long_local_jsr(relativize_local_conditionals(source)))
    result = subprocess.run(
        [str(ASM), '-in', str(asm), '-org', '2800', '-out', str(binary), '-sym', str(symbols)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    labels = {p[0]: int(p[1], 16) for p in map(str.split, symbols.read_text().splitlines()) if len(p) == 2}
    return binary, labels['pk_fold2_probe']


def main():
    binary, entry = assemble()
    waves = make_waves()
    packed_waves = packed.pack_u16(
        v for address in WAVE_IDS for v in struct.unpack('<256H', waves[address])
    )
    wave_line = 'Y 7a5 ' + ' '.join(f'{v:06x}' for v in packed_waves) + '\n'
    script = OUT / 'case.script'
    script.write_text(' '.join(['0'] * 12 + ['-1']) + '\n')

    cases = []
    seed = 1
    for mode in (0, 1, 2):
        for primary in (0, 1):
            for fade, counter, noise_count in (
                (0, 0, 0), (0x40, 0x8f, 1), (0x88, 0x90, 0),
                (0x200, 0x110, 0), (0xffff, 0x210, 2), (0x10, 0x211, 0),
            ):
                cases.append(state_case(seed, mode, primary, fade, counter, noise_count, seed % 17 == 0))
                seed += 1

    meters = []
    for index, voice in enumerate(cases):
        prepared_base = (0x120 + index * 37) & 0xffffffff
        rng32 = [0x12345678 ^ (index * 0x10203), 0x9abcdef0 ^ (index * 0x30405)]
        model_rng = list(rng32)
        expected = fold2.FoldDrum2(list(voice.words))
        want = expected.render(
            16, waves, b'', None, None, model_rng,
            prepared_base_frequency=prepared_base,
        )
        state = list(voice.words) + [0] + u32_words(prepared_base)
        state += [0] * (68 - len(state))
        rng16 = struct.unpack('<4H', struct.pack('<II', *rng32))
        data = OUT / 'case.data'
        data.write_text(
            'X 200 ' + ' '.join(f'{x & 0xffff:06x}' for x in state) + '\n'
            + wave_line
            + 'X 38e8 ' + ' '.join(f'{x:06x}' for x in rng16) + '\n'
        )
        pcm = OUT / 'case.raw'
        dump = OUT / 'case.state'
        meter = OUT / 'case.meter'
        subprocess.run([
            str(HOST), '-code', str(binary), '-org', '2800', '-entry', f'{entry:x}',
            '-data', str(data), '-script', str(script), '-out', str(pcm),
            '-state', str(dump), '-state-words', '68', '-frames', '256',
            '-meter', str(meter), '-cycle-meter', '1'
        ], check=True, capture_output=True)
        got = list(struct.unpack('<32i', pcm.read_bytes()))[::2]
        assert got == want, (
            index, 'PCM', [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:8]
        )
        actual = [int(v, 16) & 0xffff for v in dump.read_text().split()]
        assert actual[:fold2.WORDS] == expected.words, (
            index, 'state', [(i, a, b) for i, (a, b) in enumerate(zip(actual, expected.words)) if a != b][:8]
        )
        got_rng = struct.pack('<4H', *actual[64:68])
        assert got_rng == struct.pack('<II', *model_rng), (index, 'RNG')
        meters.append(int(meter.read_text().strip()))

    print(
        f'Fold Drum 2 synthetic DSP: PASS ({len(cases)} cases; all modes, '
        f'primary orders, crossfade/transient/RNG; {binary.stat().st_size // 3} P words; '
        f'worst {max(meters)} modeled cycles)'
    )


if __name__ == '__main__':
    main()
