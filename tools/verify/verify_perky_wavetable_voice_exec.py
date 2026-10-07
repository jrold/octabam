#!/usr/bin/env python3
"""Wavetable candidate DSP against original ARM and randomized native C++.

Uses a logical large Y bank in the primitive host. That bank crosses absent
Octatrack address ranges: this gate does NOT qualify a shipping placement.
"""
from pathlib import Path
import importlib.util,random,re,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'modules/perky'),str(ROOT/'tools/perky')]
import wavetable_drum_compact as compact
import simple_drum_tables as packed
from build_noise_tone_synth_source import force_long_local_jsr,relativize_local_conditionals
spec=importlib.util.spec_from_file_location('simplegate',ROOT/'tools/verify/verify_perky_simple_drum_voice_exec.py');simple=importlib.util.module_from_spec(spec);spec.loader.exec_module(simple)
OUT=ROOT/'out/perky/wavetable-voice'
NATIVE=r'''
#include "NativeV121Wavetable.h"
#include <fstream>
#include <string>
#include <vector>
#include <cstdio>
using N=NativeV121WavetableDrum;
template<class T> void load(const std::string& p,T& v){std::ifstream f(p,std::ios::binary);f.read(reinterpret_cast<char*>(v.data()),v.size());if(!f)throw p;}
unsigned ptr(const N::State&s,unsigned off){return unsigned(s[off])|(unsigned(s[off+1])<<8)|(unsigned(s[off+2])<<16)|(unsigned(s[off+3])<<24);}
int main(int argc,char**argv){if(argc!=5)return 2;std::string d=argv[1];N::PitchTable p;N::EnvelopeTable e1,e2;load(d+"/pitch.bin",p);load(d+"/envelope1.bin",e1);load(d+"/envelope2.bin",e2);unsigned ids[]={IDS};std::vector<N::WaveTable>w(sizeof(ids)/sizeof(ids[0]));for(unsigned i=0;i<w.size();++i){char name[64];snprintf(name,sizeof(name),"/asset_%08x.bin",ids[i]);load(std::string(argv[2])+name,w[i]);}std::ifstream f(argv[3],std::ios::binary);std::ofstream g(argv[4],std::ios::binary);N::State s;while(f.read(reinterpret_cast<char*>(s.data()),s.size())){N::Tables t;t.pitch=&p;t.envelope1=&e1;t.envelope2=&e2;for(unsigned j=0;j<4;++j){unsigned address=ptr(s,0x100+j*4);for(unsigned i=0;i<w.size();++i)if(ids[i]==address)t.waves[j]={address,&w[i]};}short pcm[16];if(!N::renderBlock(s,pcm,16,t))return 3;g.write(reinterpret_cast<char*>(pcm),sizeof(pcm));g.write(reinterpret_cast<char*>(s.data()),s.size());}return 0;}
'''

def main():
    OUT.mkdir(parents=True,exist_ok=True);simple.envgate.build_host();perky=ROOT/'modules/perky';assets=ROOT/'out/perky/simple-drum-assets';all_assets=ROOT/'out/perky/all-voice-assets'
    ids=[0x080222a0]+[0x080327cc+i*0x1000 for i in range(48)]
    wrapper='pk_wavetable_probe:\n move #>$200,r6\n move #>$3900,r5\n jsr pk_simple_base\n jsr pk_wavetable_voice\n rts\n'
    parts=[wrapper,(perky/'wavetable_drum_voice.asm').read_text()]
    for name,label in [('envelope','pk_simple_envelope'),('frequency','pk_simple_frequency')]:
        source=(perky/f'simple_drum_{name}.asm').read_text();source=source[source.index('\n'+label+':'):].replace('#>$0009a5,r1','#>$000c50,r1');parts.append(source)
    read=(perky/'simple_drum_oscillator.asm').read_text().split('\npksdo_read_s16:')[1]
    read='\npkwt_packed_s16:'+read.replace('pksdo_read_','pkwtp_').replace('#>$0007a5,r1','#>$001000,r1')
    # This bank reaches index 100351. Keep reciprocal quotient's bit16 until
    # dividing by two; the small Simple Drum helper only needed 16 bits.
    read=re.sub(r'(move\s+x1,b\s*\n\s*and\s+)#>\$00ffff,b',r'\g<1>#>$01ffff,b',read,count=1)
    parts += [read,(perky/'simple_drum_delta.asm').read_text()]
    asm=OUT/'voice.asm';binary=OUT/'voice.bin';sym=OUT/'voice.sym';asm.write_text(force_long_local_jsr(relativize_local_conditionals('\n'.join(parts))))
    r=subprocess.run([str(simple.envgate.ASM),'-in',str(asm),'-org','2800','-out',str(binary),'-sym',str(sym),'-list'],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
    dis=subprocess.run([str(simple.envgate.DIS),'-in',str(binary),'-pc','2800','-le'],capture_output=True,text=True,check=True)
    typed={int(m[1],16):m[2] for m in map(simple.envgate.LINE.match,r.stdout.splitlines()) if m};actual={int(m[1],16):m[2] for m in map(simple.envgate.LINE.match,dis.stdout.splitlines()) if m}
    for at,mn in typed.items():
        if mn=='nop' and at not in actual and binary.read_bytes()[(at-0x2800)*3:(at-0x2800)*3+3]==bytes(3):continue
        assert actual.get(at)==mn,(at,mn,actual.get(at))
    labels={p[0]:int(p[1],16) for p in map(str.split,sym.read_text().splitlines()) if len(p)==2}
    wavewords=packed.pack_u16(v for address in ids for v in struct.unpack('<2048H',(all_assets/f'asset_{address:08x}.bin').read_bytes()))
    envwords=packed.pack_u16(struct.unpack('<2048H',(assets/'envelope1.bin').read_bytes())[:1024]);pitchwords=packed.pack_pitch_basis(struct.unpack('<4096H',(assets/'pitch.bin').read_bytes())).words
    tables='Y 1000 '+' '.join(f'{v:06x}' for v in wavewords)+'\nY c50 '+' '.join(f'{v:06x}' for v in envwords)+'\nY efb '+' '.join(f'{v:06x}' for v in pitchwords)+' 000000\nX 3964 ffffff\n'
    script=OUT/'case.script';script.write_text(' '.join(['0']*12+['-1'])+'\n');data=OUT/'case.data';pcm=OUT/'case.raw';dump=OUT/'case.state';meter=OUT/'case.meter'
    def execute(raw,frames):
        words=compact.WavetableDrum.from_arm(raw).words+[0]*23;data.write_text('X 200 '+' '.join(f'{v:06x}' for v in words)+'\n'+tables)
        subprocess.run([str(simple.envgate.HOST),'-code',str(binary),'-org','2800','-entry',f'{labels["pk_wavetable_probe"]:x}','-data',str(data),'-script',str(script),'-out',str(pcm),'-state',str(dump),'-state-words','64','-frames',str(frames),'-meter',str(meter),'-cycle-meter','1'],check=True,capture_output=True)
        return list(struct.unpack(f'<{frames*2}i',pcm.read_bytes()))[::2],[int(v,16)&65535 for v in dump.read_text().split()][:41],int(meter.read_text().strip())
    for engine,offset in [(2,0x2e8),(5,0x31c)]:
        for mode in range(1,4):
            for corner in range(3):
                case=ROOT/f'out/perky/engine-fixtures/engine-{engine}-mode-{mode}-corner-{corner}'
                raw=(case/'wrapper-window-before.bin').read_bytes()[offset:offset+0x150];after=(case/'wrapper-window-after.bin').read_bytes()[offset:offset+0x150]
                got,state,_=execute(raw,256);want=list(struct.unpack('<256h',(case/'arm-pcm.bin').read_bytes()));assert got==want,(engine,mode,corner,'original PCM',[(i,a,b) for i,(a,b) in enumerate(zip(got,want)) if a!=b][:5]);assert state==compact.WavetableDrum.from_arm(after).words,(engine,mode,corner,'original state')
    native=Path('/Users/jrold/Downloads/perkybits/Source');runner=OUT/'native.cpp';runner.write_text(NATIVE.replace('IDS',','.join(hex(i) for i in ids)));exe=OUT/'native'
    subprocess.run(['c++','-std=c++20','-O2','-I'+str(native),str(runner),str(native/'NativeV121Wavetable.cpp'),'-o',str(exe)],check=True,capture_output=True)
    template=(ROOT/'out/perky/engine-fixtures/engine-2-mode-1-corner-1/wrapper-window-before.bin').read_bytes()[0x2e8:0x2e8+0x150];rng=random.Random(0x5754);cases=[]
    for i in range(240):
        v=compact.WavetableDrum.from_arm(template);v.words[0]=rng.choice([0,1,127,255]);v.words[1]=int(i%19==0)
        phase=rng.choice([0,0xfffff,0x100000,0xfffffff0,rng.getrandbits(32)]);v.words[2:4]=[phase&65535,phase>>16]
        for at in (6,8,34,36):
            address=rng.choice(ids);v.words[at:at+2]=[address&65535,address>>16]
        v.words[38]=rng.choice([0,255,65535,rng.randrange(65536)]);v.words[39]=rng.choice([0,255,65535,rng.randrange(65536)]);v.words[40]=i%3;v.words[32]=rng.randrange(4096);v.words[33]=rng.randrange(4096)
        for at in (10,21):
            v.words[at]=rng.randrange(5);value=rng.choice([0,0xfffff,rng.randrange(0x100000)]);v.words[at+5:at+7]=[value&65535,value>>16];v.words[at+10]=rng.choice([1,6,43,428,65535])
        cases.append(v.apply_to_arm(template))
    (OUT/'native-input.bin').write_bytes(b''.join(cases));subprocess.run([str(exe),str(assets),str(all_assets),str(OUT/'native-input.bin'),str(OUT/'native-output.bin')],check=True)
    output=(OUT/'native-output.bin').read_bytes();meters=[]
    for i,raw in enumerate(cases):
        got,state,cycles=execute(raw,16);at=i*(32+0x150);want=list(struct.unpack('<16h',output[at:at+32]));expected=compact.WavetableDrum.from_arm(output[at+32:at+32+0x150]).words
        assert got==want,(i,'native PCM',[(j,a,b) for j,(a,b) in enumerate(zip(got,want)) if a!=b]);assert state==expected,(i,'native state',[(j,a,b) for j,(a,b) in enumerate(zip(state,expected)) if a!=b]);meters.append(cycles)
    print(f'Wavetable candidate DSP: PASS (18 original ARM blocks + 240 native random blocks, exact PCM/41 live words, all 49 tables; {binary.stat().st_size//3} P words; max 16-sample cost {max(meters)} modeled cycles; logical bank only, shipping memory/controls pending)')
if __name__=='__main__':main()
