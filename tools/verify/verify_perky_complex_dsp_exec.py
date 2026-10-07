#!/usr/bin/env python3
"""Execute the Complex Drum DSP candidate against all captured ARM blocks."""
from pathlib import Path
import struct, subprocess, sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
sys.path.insert(0, str(ROOT / 'tools/perky'))
import simple_drum_tables as tables
import complex_drum_compact as compact
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals

OUT = ROOT / 'out/perky/complex-drum-dsp'
FIX = ROOT / 'out/perky/engine-fixtures'
ASSET = ROOT / 'out/perky/simple-drum-assets'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'

def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    source = 'pk_complex_probe:\n move #>$200,r6\n move #>$3900,r5\n jsr pk_complex_voice\n rts\n'
    source += (ROOT / 'modules/perky/complex_drum_voice.asm').read_text()
    for name, label in (('envelope', 'pk_simple_envelope'), ('frequency', 'pk_simple_frequency'), ('oscillator', 'pk_simple_oscillator')):
        text = (ROOT / f'modules/perky/simple_drum_{name}.asm').read_text()
        source += text[text.index('\n' + label + ':'):]
    source += (ROOT / 'modules/perky/simple_drum_delta.asm').read_text()
    asm = OUT / 'candidate.asm'; asm.write_text(force_long_local_jsr(relativize_local_conditionals(source)))
    binary = OUT / 'candidate.bin'; symbols = OUT / 'candidate.sym'
    subprocess.run([str(ASM), '-in', str(asm), '-org', '2800', '-out', str(binary), '-sym', str(symbols)], check=True, capture_output=True)
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
        + 'Y 9a5 ' + ' '.join(f'{x:06x}' for x in env) + '\n'
        + 'Y efb ' + ' '.join(f'{x:06x}' for x in pitch) + '\n'
        + 'X 3964 ffffff\n')

def main():
    binary, entry = assemble(); script = OUT / 'blocks.script'; script.write_text(' '.join(['0'] * 12 + ['-1']) + '\n')
    for mode in range(1, 4):
        for corner in range(3):
            case = FIX / f'engine-6-mode-{mode}-corner-{corner}'
            raw = (case / 'wrapper-window-before.bin').read_bytes()[0x1f8:0x1f8 + 0x140]
            state = compact.CompactComplexDrum.from_arm(raw)
            data = OUT / f'{mode}-{corner}.data'; data_file(data, state.words)
            pcm = OUT / f'{mode}-{corner}.raw'; dump = OUT / f'{mode}-{corner}.state'
            subprocess.run([str(HOST), '-code', str(binary), '-org', '2800', '-entry', f'{entry:x}', '-data', str(data), '-script', str(script), '-out', str(pcm), '-state', str(dump), '-state-words', '42', '-frames', '256'], check=True, capture_output=True)
            got = list(struct.unpack('<512i', pcm.read_bytes()))[::2]
            want = list(struct.unpack('<256h', (case / 'arm-pcm.bin').read_bytes()))
            assert got == want, (mode, corner, 'PCM')
            final = [int(x, 16) & 0xffff for x in dump.read_text().split()[:42]]
            after = (case / 'wrapper-window-after.bin').read_bytes()[0x1f8:0x1f8 + 0x140]
            assert final == compact.CompactComplexDrum.from_arm(after).words, (mode, corner, 'state')
    print('Complex Drum DSP: PASS (9 original ARM blocks, exact PCM and 42-word final state)')

if __name__ == '__main__': main()
