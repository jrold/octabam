#!/usr/bin/env python3
"""Qualify candidate Fold Drum DSP against original ARM, without dispatching it.

Covers all transient modes including original RNG continuation. Production
controls and shipping integration remain separate requirements.
"""
from pathlib import Path
import importlib.util, os, random, struct, subprocess, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')]
import fold_drum_compact as fold
import simple_drum_tables as packed
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals
spec=importlib.util.spec_from_file_location('simplegate',ROOT/'tools/verify/verify_perky_simple_drum_voice_exec.py')
simple=importlib.util.module_from_spec(spec);spec.loader.exec_module(simple)
OUT=ROOT/'out/perky/fold-drum-voice'
NATIVE_RUNNER=r'''
#include "NativeV121FoldDrums.h"
#include <fstream>
#include <string>
using N=NativeV121FoldDrums;
template<class T> void load(const std::string& p,T& v){std::ifstream f(p,std::ios::binary);f.read(reinterpret_cast<char*>(v.data()),v.size());if(!f)throw p;}
int main(int argc,char**argv){if(argc!=4)return 2;std::string d=argv[1];N::PitchTable p;N::EnvelopeTable e1,e2;N::WaveTable w[3];load(d+"/pitch.bin",p);load(d+"/envelope1.bin",e1);load(d+"/envelope2.bin",e2);unsigned ids[]={0x080222a0,0x080226a0,0x080228a0};const char*names[]={"wave_080222a0.bin","wave_080226a0.bin","wave_080228a0.bin"};N::Tables t;t.pitch=&p;t.envelope1=&e1;t.envelope2=&e2;for(int i=0;i<3;++i){load(d+"/"+names[i],w[i]);t.waves[i]={ids[i],&w[i]};}std::ifstream f(argv[2],std::ios::binary);std::ofstream g(argv[3],std::ios::binary);N::Fold1State s;N::RngState rng;while(f.read(reinterpret_cast<char*>(s.data()),s.size())){f.read(reinterpret_cast<char*>(&rng),sizeof(rng));short pcm[16];if(!N::renderFold1(s,pcm,16,t,rng))return 3;g.write(reinterpret_cast<char*>(pcm),sizeof(pcm));g.write(reinterpret_cast<char*>(s.data()),s.size());g.write(reinterpret_cast<char*>(&rng),sizeof(rng));}return 0;}
'''

def main():
    OUT.mkdir(parents=True,exist_ok=True);simple.envgate.build_host()
    perky=ROOT/'modules/perky';assets=ROOT/'out/perky/simple-drum-assets'
    parts=['pk_fold_probe:\n move #>$200,r6\n move #>$3900,r5\n jsr pk_simple_base\n jsr pk_fold_voice\n move x:>$38e8,a\n move a1,x:>$240\n move x:>$38e9,a\n move a1,x:>$241\n move x:>$38ea,a\n move a1,x:>$242\n move x:>$38eb,a\n move a1,x:>$243\n rts\n', (perky/'fold_drum_voice.asm').read_text()]
    for name,label in [('envelope','pk_simple_envelope'),('frequency','pk_simple_frequency'),('oscillator','pk_simple_oscillator')]:
        source=(perky/f'simple_drum_{name}.asm').read_text();source=source[source.index('\n'+label+':'):]
        source=source.replace('#>$0009a5,r1','#>$000c50,r1').replace('#>$0007a5,r1','#>$000a50,r1');parts.append(source)
    parts += [(perky/'simple_drum_delta.asm').read_text(),'\npknv_noise:'+ (perky/'noise_tone_voice_native_xstate.asm').read_text().split('\npknv_noise:')[1], (perky/'noise_tone_math.asm').read_text()]
    asm=OUT/'fold.asm';binary=OUT/'fold.bin';sym=OUT/'fold.sym'
    asm.write_text(force_long_local_jsr(relativize_local_conditionals('\n'.join(parts))))
    result=subprocess.run([str(simple.envgate.ASM),'-in',str(asm),'-org','2800','-out',str(binary),'-sym',str(sym),'-list'],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    dis=subprocess.run([str(simple.envgate.DIS),'-in',str(binary),'-pc','2800','-le'],capture_output=True,text=True,check=True)
    typed={int(m[1],16):m[2] for m in map(simple.envgate.LINE.match,result.stdout.splitlines()) if m}
    actual={int(m[1],16):m[2] for m in map(simple.envgate.LINE.match,dis.stdout.splitlines()) if m}
    for at,mn in typed.items():
        if mn=='nop' and at not in actual and binary.read_bytes()[(at-0x2800)*3:(at-0x2800)*3+3]==bytes(3):continue
        assert actual.get(at)==mn,(at,mn,actual.get(at))
    labels={p[0]:int(p[1],16) for p in (line.split() for line in sym.read_text().splitlines()) if len(p)==2}
    waves=packed.pack_u16(v for name in ['wave_080222a0.bin','wave_080226a0.bin','wave_080228a0.bin'] for v in struct.unpack('<256H',(assets/name).read_bytes()))
    env=packed.pack_u16(struct.unpack('<2048H',(assets/'envelope1.bin').read_bytes())[:1024])
    pitch=packed.pack_pitch_basis(struct.unpack('<4096H',(assets/'pitch.bin').read_bytes())).words
    tables='Y a50 '+' '.join(f'{v:06x}' for v in waves)+'\nY c50 '+' '.join(f'{v:06x}' for v in env)+'\nY efb '+' '.join(f'{v:06x}' for v in pitch)+' 000000\nX 3964 ffffff\n'
    script=OUT/'case.script';script.write_text(' '.join(['0']*12+['-1'])+'\n')
    meters=[]
    for mode,continuation in [(1,False),(3,False),(1,True),(2,True),(3,True)]:
        for corner in range(3):
            case=ROOT/f'out/perky/engine-fixtures/engine-1-mode-{mode}-corner-{corner}'
            before=(case/('wrapper-window-after.bin' if continuation else 'wrapper-window-before.bin')).read_bytes()[0xc4:0xc4+0xf4]
            expected=fold.FoldDrum1.from_arm((case/('wrapper-window-continuation-after.bin' if continuation else 'wrapper-window-after.bin')).read_bytes()[0xc4:0xc4+0xf4]).words
            state=fold.FoldDrum1.from_arm(before).words+[0]*24
            rng=struct.unpack('<4H',(case/'rng-continuation-before.bin').read_bytes()) if continuation else (0,0,0,0)
            rng_line='X 38e8 '+' '.join(f'{v:06x}' for v in rng)+'\n'
            data=OUT/'case.data';data.write_text('X 200 '+' '.join(f'{v:06x}' for v in state)+'\n'+tables+rng_line)
            pcm=OUT/'case.raw';dump=OUT/'case.state';meter=OUT/'case.meter'
            subprocess.run([str(simple.envgate.HOST),'-code',str(binary),'-org','2800','-entry',f'{labels["pk_fold_probe"]:x}','-data',str(data),'-script',str(script),'-out',str(pcm),'-state',str(dump),'-state-words','68','-frames','256','-meter',str(meter),'-cycle-meter','1'],check=True,capture_output=True)
            want=list(struct.unpack('<256h',(case/('arm-pcm-continuation.bin' if continuation else 'arm-pcm.bin')).read_bytes()));got=list(struct.unpack('<512i',pcm.read_bytes()))
            assert got==[v for v in want for _ in range(2)],f'PCM mode {mode} corner {corner}: '+str([(i,a,b) for i,(a,b) in enumerate(zip(got[::2],want)) if a!=b][:8])
            actual=[int(v,16)&0xffff for v in dump.read_text().split()][:40]
            assert actual==expected,f'state mode {mode} corner {corner}: '+str([(i,a,b) for i,(a,b) in enumerate(zip(actual,expected)) if a!=b])
            if continuation:
                got_rng=tuple(int(v,16)&0xffff for v in dump.read_text().split()[64:68])
                assert got_rng==struct.unpack('<4H',(case/'rng-continuation-after.bin').read_bytes()),(mode,corner,got_rng)
            meters.append(int(meter.read_text().strip()))
    native=(Path(os.environ.get('PERKYBITS_SOURCE','/Users/jrold/Downloads/perkybits'))/'Source');runner=OUT/'native.cpp';runner.write_text(NATIVE_RUNNER);exe=OUT/'native'
    subprocess.run(['c++','-std=c++20','-O2','-I'+str(native),str(runner),str(native/'NativeV121FoldDrums.cpp'),'-o',str(exe)],check=True,capture_output=True)
    randomizer=random.Random(0xf01d);cases=[]
    template=(ROOT/'out/perky/engine-fixtures/engine-1-mode-2-corner-1/wrapper-window-before.bin').read_bytes()[0xc4:0xc4+0xf4]
    for i in range(400):
        v=fold.FoldDrum1.from_arm(template)
        v.words[0]=randomizer.choice([0,1,127,255]);v.words[1]=int(i%19==0)
        v.words[34]=i%3;v.words[35]=randomizer.choice([0,143,144,272,273,528,529,65535])
        v.words[36]=randomizer.choice([0,4092,65535,randomizer.randrange(65536)])
        v.words[37]=randomizer.choice([0,1,2,65535]);v.words[38]=randomizer.choice([0,2,65535]);v.words[39]=randomizer.randrange(65536)
        v.words[32]=randomizer.randrange(4096);v.words[33]=randomizer.randrange(4096)
        if i>=240:
            v.words[36]=randomizer.randrange(4093);v.words[37]=randomizer.randrange(3);v.words[38]=2
        rng=struct.pack('<II',randomizer.getrandbits(32),randomizer.getrandbits(32))
        cases.append((v.apply_to_arm(template),rng))
    (OUT/'native-input.bin').write_bytes(b''.join(a+b for a,b in cases))
    subprocess.run([str(exe),str(assets),str(OUT/'native-input.bin'),str(OUT/'native-output.bin')],check=True)
    native_out=(OUT/'native-output.bin').read_bytes();short_meters=[]
    for i,(raw,rng) in enumerate(cases):
        v=fold.FoldDrum1.from_arm(raw);data.write_text('X 200 '+' '.join(f'{x:06x}' for x in v.words+[0]*28)+'\n'+tables+'X 38e8 '+' '.join(f'{x:06x}' for x in struct.unpack('<4H',rng))+'\n')
        subprocess.run([str(simple.envgate.HOST),'-code',str(binary),'-org','2800','-entry',f'{labels["pk_fold_probe"]:x}','-data',str(data),'-script',str(script),'-out',str(pcm),'-state',str(dump),'-state-words','68','-meter',str(meter),'-cycle-meter','1'],check=True,capture_output=True)
        start=i*(32+0xf4+8);want=list(struct.unpack('<16h',native_out[start:start+32]));got=list(struct.unpack('<32i',pcm.read_bytes()))
        assert got==[x for x in want for _ in range(2)],f'random PCM case {i}: '+str([(j,a,b) for j,(a,b) in enumerate(zip(got[::2],want)) if a!=b])
        actual=[int(v,16)&0xffff for v in dump.read_text().split()];expected=fold.FoldDrum1.from_arm(native_out[start+32:start+32+0xf4]).words
        assert actual[:40]==expected,f'random state case {i}: '+str([(j,a,b) for j,(a,b) in enumerate(zip(actual,expected)) if a!=b])
        assert tuple(actual[64:68])==struct.unpack('<4H',native_out[start+32+0xf4:start+32+0xf4+8]),f'RNG case {i}'
        short_meters.append(int(meter.read_text().strip()))
    print(f'Fold Drum candidate: PASS (15 original ARM blocks + 400 randomized native blocks, PCM/state/RNG, all modes; {binary.stat().st_size//3} P words, worst random 16-sample block {max(short_meters)} modeled cycles, physical noise-hold subset {max(short_meters[240:])})')
if __name__=='__main__':main()
