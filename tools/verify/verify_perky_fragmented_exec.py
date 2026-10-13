#!/usr/bin/env python3
"""Run the existing exact PCM/state/RNG seam corpus at production shard addresses.

The harness wrapper is private at P:0x5000; every renderer shard uses the
production placement. Its synthetic stock continuation is P:0x400, as in the
original reference gates. This is a DSP execution differential, not a project
or hardware timing model; the separate port gates cover the real dispatcher.
"""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import build_bus as B, perky_emit_shards as E
import verify_perky_controlled_voice_exec as c
import verify_perky_fold_seam_exec as fold_gate
import verify_perky_multi_seam_exec as mixed_gate
import build_fold_candidate as candidate

original_assemble=c.assemble

def assemble(source):
    if 'BEGIN fold_drum2_voice.asm' not in source:
        return original_assemble(source)
    cut=source.index('; ===== BEGIN')
    asm=c.OUT/'fragmented-source.asm';asm.write_text(source[cut:])
    pieces,whole,dest,final,syms=E.emit(asm)
    wrapper,labels=B.assemble_syms(E.rewrite(source[:cut],syms,final),0x5000,'fragment_test_wrapper',strict_layout=True)
    spans=[(0x5000,wrapper)]
    for name,a,b,text,_ in pieces:
        words,_=B.assemble_syms(E.rewrite(text,syms,final),dest[name],name,strict_layout=True)
        assert len(words)==b-a
        spans.append((dest[name],words))
    flat=[0]*(max(a+len(w) for a,w in spans)-c.ORG)
    for addr,words in spans:flat[addr-c.ORG:addr-c.ORG+len(words)]=words
    binary=c.OUT/'fragmented-test.bin';binary.write_bytes(b''.join(w.to_bytes(3,'little') for w in flat))
    labels.update({label:final(addr) for label,addr in syms.items()})
    binary.with_suffix('.sym').write_text('\n'.join(f'{label} {addr:06x}' for label,addr in labels.items())+'\n')
    return binary,labels['pk_controlled_voice_exec']

def main():
    c.ORG=0x1000;c.assemble=assemble
    fold_gate.OUT=ROOT/'out/perky/fragmented-exec-fold';fold_gate.main()
    def build(assets,out):
        source,_=candidate.build(out);(out/'multi.asm').write_text(source)
    mixed_gate.payload.build=build
    mixed_gate.OUT=ROOT/'out/perky/fragmented-exec-simple-noise';mixed_gate.main()
    print('[PASS] production fragment addresses: unchanged exact Fold1/Simple/Noise PCM, state, RNG, retriggers, controls, modes and long release tails')
if __name__=='__main__':main()
