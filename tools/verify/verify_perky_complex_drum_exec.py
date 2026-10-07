#!/usr/bin/env python3
"""Exact Complex Drum host/native gate for the V2 common-oscillator cluster."""
from pathlib import Path
import struct, subprocess, sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
import complex_drum_compact as compact

FIX = ROOT / 'out/perky/engine-fixtures'
ASSET = ROOT / 'out/perky/simple-drum-assets'
OUT = ROOT / 'out/perky/complex-drum'
NATIVE = Path('/Users/jrold/Downloads/perkybits/Source')

RUNNER = r'''
#include "NativeV121ComplexDrum.h"
#include <fstream>
#include <string>
using N=NativeV121ComplexDrum;
template<class T> void load(std::string p,T& v){std::ifstream f(p,std::ios::binary);f.read((char*)v.data(),v.size());if(!f)throw p;}
unsigned u32(const N::State&s,unsigned o){return s[o]|s[o+1]<<8|s[o+2]<<16|s[o+3]<<24;}
int main(int argc,char**a){if(argc!=5)return 2;N::PitchTable p;N::EnvelopeTable e1,e2;load(std::string(a[1])+"/pitch.bin",p);load(std::string(a[1])+"/envelope1.bin",e1);load(std::string(a[1])+"/envelope2.bin",e2);unsigned ids[]={0x080222a0,0x080224a0,0x080226a0,0x080228a0};N::WaveTable w[4];for(int i=0;i<4;i++){char n[32];snprintf(n,sizeof(n),"/wave_%08x.bin",ids[i]);load(std::string(a[1])+n,w[i]);}std::ifstream f(a[3],std::ios::binary);std::ofstream g(a[4],std::ios::binary);N::State s;while(f.read((char*)s.data(),s.size())){N::Tables t{&p,&e1,&e2,{}};for(int i=0;i<4;i++)t.waves[i]={ids[i],&w[i]};short pcm[256];if(!N::renderBlock(s,pcm,256,t))return 3;g.write((char*)pcm,sizeof(pcm));g.write((char*)s.data(),s.size());}return 0;}
'''

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runner = OUT / 'native.cpp'; exe = OUT / 'native'; runner.write_text(RUNNER)
    subprocess.run(['c++','-std=c++20','-O2','-I'+str(NATIVE),str(runner),str(NATIVE/'NativeV121ComplexDrum.cpp'),'-o',str(exe)], check=True)
    cases=[]; expected=[]
    for mode in range(1,4):
        for corner in range(3):
            case=FIX/f'engine-6-mode-{mode}-corner-{corner}'
            raw=(case/'wrapper-window-before.bin').read_bytes()[0x1f8:0x1f8+0x140]
            cases.append(raw); expected.append(case)
    inp=OUT/'input.bin'; out=OUT/'native-output.bin'; inp.write_bytes(b''.join(cases))
    subprocess.run([str(exe),str(ASSET),str(ASSET),str(inp),str(out)], check=True)
    blob=out.read_bytes(); stride=512+0x140
    for i,(case,raw) in enumerate(zip(expected,cases)):
        pcm=list(struct.unpack('<256h',blob[i*stride:i*stride+512]))
        want=list(struct.unpack('<256h',(case/'arm-pcm.bin').read_bytes()))
        assert pcm == want, (i, 'native/arm PCM')
        native=blob[i*stride+512:i*stride+512+0x140]
        got=compact.CompactComplexDrum.from_arm(native).words
        after=(case/'wrapper-window-after.bin').read_bytes()[0x1f8:0x1f8+0x140]
        want_state=compact.CompactComplexDrum.from_arm(after).words
        assert got == want_state, (i, 'native/arm state')
    for mode in range(1,4):
        for corner in range(3):
            case=FIX/f'engine-6-mode-{mode}-corner-{corner}'
            raw=(case/'wrapper-window-before.bin').read_bytes()[0x1f8:0x1f8+0x140]
            v=compact.CompactComplexDrum.from_arm(raw)
            waves={a:(ASSET/f'wave_{a:08x}.bin').read_bytes() for a in (v.u32(6),v.u32(8),v.u32(14),v.u32(16))}
            got=compact.render_block(v,256,waves,(ASSET/'pitch.bin').read_bytes(),(ASSET/'envelope1.bin').read_bytes(),(ASSET/'envelope2.bin').read_bytes())
            want=list(struct.unpack('<256h',(case/'arm-pcm.bin').read_bytes()))
            assert got == want, (mode,corner,'model/arm PCM')
    print('Complex Drum exact gate: PASS (9 original ARM blocks, native and compact PCM/state)')

if __name__ == '__main__': main()
