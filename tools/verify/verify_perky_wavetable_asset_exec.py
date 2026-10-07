#!/usr/bin/env python3
"""Execute lossless Wavetable block decoder across every original asset sample.

Logical single-bank storage only. Measures sequential misses and hit cost;
whole-renderer cache misses and physical memory remain separate gates.
"""
from pathlib import Path
import importlib.util,struct,subprocess,sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')]
import build_wavetable_asset_bank as bank
from build_noise_tone_synth_source import force_long_local_jsr,relativize_local_conditionals
spec=importlib.util.spec_from_file_location('envgate',ROOT/'tools/verify/verify_perky_simple_drum_envelope_exec.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
OUT=ROOT/'out/perky/wavetable-decoder'

def main():
    OUT.mkdir(parents=True,exist_ok=True);gate.build_host()
    report=bank.build(ROOT/'out/perky/all-voice-assets',ROOT/'out/perky/wavetable-bank')
    words=[int.from_bytes((ROOT/'out/perky/wavetable-bank/bank.bin').read_bytes()[i:i+3],'little') for i in range(0,report['bank_words']*3,3)]
    wrapper='''pk_wave_asset_probe:
 move #>$3900,r5
 move #>$3975,r4
 move x:(r6),a
 move a1,x:(r5+$60)
 do n7,pkwdap_done
 move x:(r5+$60),r6
 move x:(r6),x0
 move x:(r6+$1),r1
 move x:(r6+$2),n4
 jsr pk_wavetable_asset_at
 move a1,x:(r0)+
 move a1,x:(r0)+
 move x:(r5+$60),r6
 move x:(r6),a
 add #>$1,a
 move a1,x:(r6)
pkwdap_done:
 nop
 rts
'''.replace(' move x:(r6),a\n move a1,x:(r5+$60)\n do',' move #>$200,r6\n move r6,a\n move a1,x:(r5+$60)\n do',1)
    source=force_long_local_jsr(relativize_local_conditionals(wrapper+(ROOT/'modules/perky/wavetable_asset_decode.asm').read_text()))
    asm=OUT/'decoder.asm';binary=OUT/'decoder.bin';sym=OUT/'decoder.sym';asm.write_text(source)
    r=subprocess.run([str(gate.ASM),'-in',str(asm),'-org','100','-out',str(binary),'-sym',str(sym),'-list'],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
    dis=subprocess.run([str(gate.DIS),'-in',str(binary),'-pc','100','-le'],capture_output=True,text=True,check=True)
    typed={int(m[1],16):m[2] for m in map(gate.LINE.match,r.stdout.splitlines()) if m};actual={int(m[1],16):m[2] for m in map(gate.LINE.match,dis.stdout.splitlines()) if m}
    for at,mn in typed.items():
        if mn=='nop' and at not in actual and binary.read_bytes()[(at-0x100)*3:(at-0x100)*3+3]==bytes(3):continue
        assert actual.get(at)==mn,(at,mn,actual.get(at))
    labels={p[0]:int(p[1],16) for p in map(str.split,sym.read_text().splitlines()) if len(p)==2}
    script=OUT/'case.script';script.write_text((' '.join(['0']*12+['-1'])+'\n')*128)
    data=OUT/'case.data';pcm=OUT/'case.raw';meter=OUT/'case.meter';tables='Y 1000 '+' '.join(f'{v:06x}' for v in words)+'\n'
    costs=[]
    for asset in report['assets']:
        header=0x1000+asset['descriptor_start']-1;packed=0x1000+asset['data_start']
        data.write_text(f'X 200 000000 {header:06x} {packed:06x}\nX 3975 ffffff\n'+tables)
        subprocess.run([str(gate.HOST),'-code',str(binary),'-org','100','-entry',f'{labels["pk_wave_asset_probe"]:x}','-data',str(data),'-script',str(script),'-out',str(pcm),'-frames','16','-meter',str(meter),'-cycle-meter','1'],capture_output=True,check=True)
        got=list(struct.unpack('<4096i',pcm.read_bytes()))[::2]
        expected=list(struct.unpack('<2048h',(ROOT/'out/perky/all-voice-assets'/f'asset_{int(asset["address"],16):08x}.bin').read_bytes()))
        assert got==expected,(asset['address'],[(i,a,b) for i,(a,b) in enumerate(zip(got,expected)) if a!=b][:5])
        costs += [int(v) for v in meter.read_text().split()]
    print(f'Wavetable asset DSP: PASS ({len(report["assets"])} assets / {len(report["assets"])*2048} exact samples; decoder {binary.stat().st_size//3} P words; 33 cache words; sequential 16-sample max {max(costs)} modeled cycles; full renderer random misses/physical placement pending)')
if __name__=='__main__':main()
