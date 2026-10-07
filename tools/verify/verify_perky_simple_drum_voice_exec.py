#!/usr/bin/env python3
"""Execute the complete composed Simple Drum renderer against native C++.

Requires local PerkyBits sources and authentic extraction; never embeds assets.
Exercises renderer-owned state across modes, retriggers, wraps and envelopes.
This gate does not imply integration/transport/memory qualification.
"""
from pathlib import Path
import hashlib, importlib.util, os, random, re, struct, subprocess, sys
ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT/'modules/perky'
sys.path.insert(0,str(PERKY));sys.path.insert(0,str(ROOT/'tools/perky'))
import simple_drum_compact as compact
import simple_drum_live as live
import simple_drum_ref as ref
import simple_drum_tables as packed
from build_noise_tone_synth_source import force_long_local_jsr, relativize_local_conditionals
OUT=ROOT/'out/perky/simple-drum-voice';ORG=0x2800
spec=importlib.util.spec_from_file_location('envgate',ROOT/'tools/verify/verify_perky_simple_drum_envelope_exec.py')
envgate=importlib.util.module_from_spec(spec);spec.loader.exec_module(envgate)

NATIVE_RUNNER=r'''
#include "NativeV121SimpleDrum.h"
#include <fstream>
#include <vector>
#include <string>
using N=NativeV121SimpleDrum;
template<class T> void load(const std::string& p,T& v){std::ifstream f(p,std::ios::binary);f.read(reinterpret_cast<char*>(v.data()),v.size());if(!f)throw p;}
unsigned ptr(const N::State& s,unsigned i){return unsigned(s[i])|(unsigned(s[i+1])<<8)|(unsigned(s[i+2])<<16)|(unsigned(s[i+3])<<24);}
int main(int argc,char**argv){if(argc!=4)return 2;std::string d=argv[1],in=argv[2],out=argv[3];N::PitchTable pitch;N::EnvelopeTable e1,e2;N::WaveTable waves[3];load(d+"/pitch.bin",pitch);load(d+"/envelope1.bin",e1);load(d+"/envelope2.bin",e2);unsigned ids[]={0x080222a0,0x080226a0,0x080228a0};const char*names[]={"wave_080222a0.bin","wave_080226a0.bin","wave_080228a0.bin"};for(int i=0;i<3;++i)load(d+"/"+names[i],waves[i]);std::ifstream f(in,std::ios::binary);std::ofstream g(out,std::ios::binary);N::State s;while(f.read(reinterpret_cast<char*>(s.data()),s.size())){N::Tables t;t.pitch=&pitch;t.envelope1=&e1;t.envelope2=&e2;unsigned cur=ptr(s,0x38),next=ptr(s,0x3c);for(int v=0;v<2;++v){unsigned id=v?next:cur;for(int j=0;j<3;++j)if(ids[j]==id)t.waves[v]={id,&waves[j]};}short pcm[16];if(!N::renderBlock(s,pcm,16,t))return 3;g.write(reinterpret_cast<char*>(pcm),sizeof(pcm));g.write(reinterpret_cast<char*>(s.data()),s.size());}return 0;}
'''

def fail(s):raise SystemExit('simple-drum-voice: '+s)

def assemble():
    wrapper='pk_simple_voice_probe:\n        move #>$200,r6\n        move #>$3900,r5\n        jsr pk_simple_base\n        jsr pk_simple_voice\n        rts\n'
    parts=[wrapper,(PERKY/'simple_drum_voice.asm').read_text()]
    for name,label in [('envelope','pk_simple_envelope'),('frequency','pk_simple_frequency'),('oscillator','pk_simple_oscillator')]:
        text=(PERKY/f'simple_drum_{name}.asm').read_text();text=text[text.index('\n'+label+':'):]
        if name=='envelope': text=text.replace('#>$0009a5,r1','#>$000c50,r1')
        if name=='oscillator': text=text.replace('#>$0007a5,r1','#>$000a50,r1')
        parts.append(text)
    parts.append((PERKY/'simple_drum_delta.asm').read_text())
    source=OUT/'voice.asm';binary=OUT/'voice.bin';symbols=OUT/'voice.sym'
    source.write_text(force_long_local_jsr(relativize_local_conditionals('\n'.join(parts))))
    r=subprocess.run([str(envgate.ASM),'-in',str(source),'-org',f'{ORG:x}','-out',str(binary),'-sym',str(symbols),'-list'],capture_output=True,text=True)
    if r.returncode:fail(r.stdout[-6000:]+r.stderr)
    d=subprocess.run([str(envgate.DIS),'-in',str(binary),'-pc',f'{ORG:x}','-le'],check=True,capture_output=True,text=True)
    typed={int(m[1],16):m[2] for m in map(envgate.LINE.match,r.stdout.splitlines()) if m}
    actual={int(m[1],16):m[2] for m in map(envgate.LINE.match,d.stdout.splitlines()) if m}
    for at,mn in typed.items():
        if mn=='nop' and at not in actual and binary.read_bytes()[(at-ORG)*3:(at-ORG)*3+3]==bytes(3):continue
        if actual.get(at)!=mn:fail(f'disassembly mismatch {at:x}: {mn} vs {actual.get(at)}')
    labels={p[0]:int(p[1],16) for p in (line.split() for line in symbols.read_text().splitlines()) if len(p)==2}
    return binary,labels['pk_simple_voice_probe']

def main():
    OUT.mkdir(parents=True,exist_ok=True);envgate.build_host()
    assets=Path(os.environ.get('PERKY_SIMPLE_ASSETS',str(ROOT/'out/perky/simple-drum-assets')))
    native=Path(os.environ.get('PERKYBITS_SOURCE','/Users/jrold/Downloads/perkybits'))/'Source'
    runner=OUT/'native.cpp';runner.write_text(NATIVE_RUNNER);exe=OUT/'native'
    subprocess.run(['c++','-std=c++20','-O2','-I'+str(native),str(runner),str(native/'NativeV121SimpleDrum.cpp'),'-o',str(exe)],check=True,capture_output=True)
    ids=[0x080222a0,0x080226a0,0x080228a0]
    waves={i:(assets/f'wave_{i:08x}.bin').read_bytes() for i in ids}
    pitch=(assets/'pitch.bin').read_bytes();e1=(assets/'envelope1.bin').read_bytes();e2=(assets/'envelope2.bin').read_bytes()
    wavewords=packed.pack_u16(v for i in ids for v in struct.unpack('<256H',waves[i]))
    envwords=packed.pack_u16(struct.unpack('<2048H',e1)[:1024])
    pitchwords=packed.pack_pitch_basis(struct.unpack('<4096H',pitch)).words
    data_tables='Y a50 '+' '.join(f'{v:06x}' for v in wavewords)+'\nY c50 '+' '.join(f'{v:06x}' for v in envwords)+'\nY efb '+' '.join(f'{v:06x}' for v in pitchwords)+' 000000\nX 3964 ffffff\n'
    rng=random.Random(0x503003);cases=[]
    for i in range(240):
        l=live.LiveSimpleDrum.fresh();v=l.voice
        v.words[0]=rng.choice([0,1,127,255]);v.words[1]=int(i%19==0)
        v.set_u32(2,rng.choice([0,0xfffff,0x100000,rng.randrange(0x100001),0xfffffff0]))
        v.set_u32(6,ids[i%3]);v.set_u32(8,ids[(i//3)%3])
        v.words[32]=rng.choice([0,4095,rng.randrange(4096)]);v.words[33]=rng.choice([0,2047,rng.randrange(2048)])
        for base in [10,21]:
            v.words[base]=rng.randrange(5);v.set_u32(base+5,rng.choice([0,0xfffff,rng.randrange(0x100000)]))
            v.words[base+10]=rng.choice([1,8,428,1040,rng.randrange(1,65536)])
        v.words[14]=int(i%23==0)
        if i%4==0:l.trigger()
        cases.append(v.apply_to_arm(bytes(ref.STATE_BYTES)))
    (OUT/'native-input.bin').write_bytes(b''.join(cases))
    subprocess.run([str(exe),str(assets),str(OUT/'native-input.bin'),str(OUT/'native-output.bin')],check=True)
    native_out=(OUT/'native-output.bin').read_bytes();binary,entry=assemble();meters=[]
    for i,raw in enumerate(cases):
        v=compact.CompactSimpleDrum.from_arm(raw);base=ref.base_frequency(v.words[32],pitch)
        state=v.words+[0xffff]+[0]*17+[base&0xffff,base>>16]+[0]*4
        data=OUT/'case.data';data.write_text('X 200 '+' '.join(f'{x:06x}' for x in state)+'\n'+data_tables)
        script=OUT/'case.script';script.write_text(' '.join(['0']*12+['-1'])+'\n')
        pcm=OUT/'case.raw';dump=OUT/'case.state';meter=OUT/'case.meter'
        subprocess.run([str(envgate.HOST),'-code',str(binary),'-org',f'{ORG:x}','-entry',f'{entry:x}','-data',str(data),'-script',str(script),'-out',str(pcm),'-state',str(dump),'-state-words','64','-meter',str(meter),'-cycle-meter','1'],check=True,capture_output=True)
        got=list(struct.unpack('<32i',pcm.read_bytes()))
        start=i*(32+ref.STATE_BYTES);want_pcm=list(struct.unpack('<16h',native_out[start:start+32]));want_state=compact.CompactSimpleDrum.from_arm(native_out[start+32:start+32+ref.STATE_BYTES]).words
        if got!=[p for p in want_pcm for _ in range(2)]:fail(f'case {i} PCM {got[:8]} vs {want_pcm[:4]}')
        got_state=[int(x,16)&0xffff for x in dump.read_text().split()][:34]
        if got_state!=want_state:fail(f'case {i} state '+str([(j,a,b) for j,(a,b) in enumerate(zip(got_state,want_state)) if a!=b]))
        meters.append(int(meter.read_text().strip()))
    print(f'Simple Drum complete native parity: PASS ({len(cases)} blocks, PCM + 34 state words, all waves, retriggers, wraps; {binary.stat().st_size//3} P words; max {max(meters)} modeled cycles)')
if __name__=='__main__':main()
