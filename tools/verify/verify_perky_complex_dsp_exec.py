#!/usr/bin/env python3
"""Execute the Complex Drum DSP candidate against all captured ARM blocks."""
from pathlib import Path
import json, struct, subprocess, sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
sys.path.insert(0, str(ROOT / 'tools/perky'))
import simple_drum_tables as tables
import complex_drum_compact as compact
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals
from verify_perky_simple_drum_envelope_exec import build_host
from perky_noise_hat_dsp_support import audit_source, audit_binary

OUT = ROOT / 'out/perky/complex-drum-dsp'
FIX = ROOT / 'out/perky/engine-fixtures'
ASSET = ROOT / 'out/perky/simple-drum-assets'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'

def assemble():
    build_host()
    OUT.mkdir(parents=True, exist_ok=True)
    source = 'pk_complex_probe:\n move #>$200,r6\n move #>$3900,r5\n jsr pk_complex_voice\n rts\n'
    source += (ROOT / 'modules/perky/complex_drum_voice.asm').read_text()
    for name, label in (('envelope', 'pk_simple_envelope'), ('frequency', 'pk_simple_frequency'), ('oscillator', 'pk_simple_oscillator')):
        text = (ROOT / f'modules/perky/simple_drum_{name}.asm').read_text()
        text = text[text.index('\n' + label + ':'):]
        if name == 'envelope':
            # Four packed 256-sample Complex waves occupy Y:$07a5..$0a4f.
            # Simple's envelope base at $09a5 would overwrite the fourth wave,
            # exactly where MODE 2 deferred-switch cases diverged. Relocate the
            # Complex candidate's envelope bank to the first free word, $0a50.
            text = text.replace('#>$0009a5,r1', '#>$000a50,r1')
        source += text
    source += (ROOT / 'modules/perky/simple_drum_delta.asm').read_text()
    audit_source(source)
    asm = OUT / 'candidate.asm'; asm.write_text(force_long_local_jsr(relativize_local_conditionals(source)))
    binary = OUT / 'candidate.bin'; symbols = OUT / 'candidate.sym'
    result = subprocess.run([str(ASM), '-in', str(asm), '-org', '2800', '-out', str(binary), '-sym', str(symbols), '-list'], check=True, capture_output=True, text=True)
    audit_binary(result.stdout, binary, 0x2800)
    labels = {p[0]: int(p[1], 16) for p in map(str.split, symbols.read_text().splitlines()) if len(p) == 2}
    return binary, labels['pk_complex_probe']

def data_file(path, state):
    pitch = tables.pack_pitch_basis(struct.unpack('<4096H', (ASSET / 'pitch.bin').read_bytes())).words
    env = tables.pack_u16(struct.unpack('<1024H', (ASSET / 'envelope1.bin').read_bytes()[:2048]))
    waves = []
    # Simple uses ordinals 22a0/26a0/28a0; Complex V2 adds 24a0 as ordinal 3.
    for address in (0x080222a0, 0x080226a0, 0x080228a0, 0x080224a0):
        blob = (ASSET / f'wave_{address:08x}.bin').read_bytes()
        waves.extend(struct.unpack('<256h', blob))
    wave_words = tables.pack_u16(waves)
    path.write_text(
        'X 200 ' + ' '.join(f'{x:06x}' for x in state + [0] * 30) + '\n'
        + 'Y 7a5 ' + ' '.join(f'{x:06x}' for x in wave_words) + '\n'
        + 'Y a50 ' + ' '.join(f'{x:06x}' for x in env) + '\n'
        + 'Y efb ' + ' '.join(f'{x:06x}' for x in pitch) + '\n'
        + 'X 3964 ffffff\n')

def main():
    binary, entry = assemble()
    script = OUT / 'blocks.script'
    script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * 16)
    ids = (0x080222a0, 0x080224a0, 0x080226a0, 0x080228a0)
    waves = {address: (ASSET / f'wave_{address:08x}.bin').read_bytes() for address in ids}
    pitch, e1, e2 = ((ASSET / name).read_bytes() for name in ('pitch.bin', 'envelope1.bin', 'envelope2.bin'))
    meters = []
    checked = 0
    for mode in range(1, 4):
        for corner in range(3):
            case = FIX / f'engine-6-mode-{mode}-corner-{corner}'
            for before, after, audio in (
                ('wrapper-window-before.bin', 'wrapper-window-after.bin', 'arm-pcm.bin'),
                ('wrapper-window-after.bin', 'wrapper-window-continuation-after.bin', 'arm-pcm-continuation.bin'),
            ):
                raw = (case / before).read_bytes()[0x1f8:0x1f8 + 0x140]
                state = compact.CompactComplexDrum.from_arm(raw)
                data = OUT / 'case.data'; data_file(data, state.words)
                pcm, dump, meter = (OUT / f'case.{ext}' for ext in ('raw', 'state', 'meter'))
                subprocess.run([str(HOST), '-code', str(binary), '-org', '2800', '-entry', f'{entry:x}', '-data', str(data), '-script', str(script), '-out', str(pcm), '-state', str(dump), '-state-words', '42', '-meter', str(meter), '-cycle-meter', '1'], check=True, capture_output=True)
                stereo = list(struct.unpack('<512i', pcm.read_bytes()))
                got = stereo[::2]
                assert stereo[1::2] == got, (mode, corner, 'stereo')
                want = list(struct.unpack('<256h', (case / audio).read_bytes()))
                assert got == want, (mode, corner, audio, 'PCM')
                lines = dump.read_text().splitlines()
                assert len(lines) == 16
                for block, line in enumerate(lines):
                    predicted = compact.render_block(state, 16, waves, pitch, e1, e2)
                    assert got[block * 16:(block + 1) * 16] == predicted
                    final = [int(x, 16) & 0xffff for x in line.split()[:42]]
                    assert final == state.words, (mode, corner, audio, block, 'state')
                raw_after = (case / after).read_bytes()[0x1f8:0x1f8 + 0x140]
                assert state.words == compact.CompactComplexDrum.from_arm(raw_after).words
                assert compact.CompactComplexDrum.from_arm(state.apply_to_arm(raw_after)).words == state.words
                meters.extend(map(int, meter.read_text().split()))
                checked += 16
    report = {'schema': 'perky-complex-dsp-v1', 'blocks': checked,
              'p_words': binary.stat().st_size // 3, 'x_words': 42, 'worst_cycles': max(meters)}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"Complex Drum DSP: PASS ({checked} consecutive blocks / 18 original ARM captures; exact stereo PCM and 42-word state every block; {report['p_words']} P words; worst {max(meters)} modeled cycles/16)")

if __name__ == '__main__': main()
