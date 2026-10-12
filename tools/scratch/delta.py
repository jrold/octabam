"""One harness, one seeded state, one assembly -- only the entry differs.

Three entries over the SAME composed source and the SAME data:
  m_render   : base + voice            (the renderer alone)
  m_quoted   : base + voice + the gate's 12-instruction RNG dump
                                        (what verify_perky_3algo_timing quotes)
  m_dispatch : pk3d_source, @CONT@ -> a `rts` trampoline at P:0x400
                                        (the production path)
"""
import sys, importlib.util, struct, subprocess
from pathlib import Path
sys.path[:0]=['modules/perky','tools/perky','tools/verify']
def load(n,rel):
    s=importlib.util.spec_from_file_location(n, rel); m=importlib.util.module_from_spec(s)
    sys.modules[n]=m; s.loader.exec_module(m); return m
join=load('join','tools/verify/verify_perky_3algo_engine_join.py')
g=load('g','tools/verify/verify_perky_3algo_exec.py')
composer=join.load_composer()
import fold_drum_compact as fold
OUT=Path('out/perky/dsp-3algo/delta'); OUT.mkdir(parents=True,exist_ok=True)
e1,e2,_,_=g.make_envelopes()
ia=struct.pack('<257H',*[(i*257+i*i)&0xFFFF for i in range(257)])
ib=struct.pack('<257H',*[(65535-i*251)&0xFFFF for i in range(257)])
ytext=g.tables_text(e1,e2,ia,ib, Path('out/perky/simple-drum-assets'))
case=Path('out/perky/engine-fixtures/engine-1-mode-1-corner-0')
state=fold.FoldDrum1.from_arm((case/'wrapper-window-before.bin').read_bytes()[0xc4:0xc4+0xf4]).words
state=state+[0]*(composer.RNG_GAP_START-composer.VOICE_BASE-len(state))

src=composer.normalize(composer.compose()).replace('@CONT@','$000400')
probe=(
 'm_render:\n'
 f'        move    #${composer.VOICE_BASE:06x},r6\n'
 f'        move    #${composer.SCRATCH_BASE:06x},r5\n'
 '        jsrl    pk_simple_base\n        jsrl    pk_fold_voice\n        rts\n'
 'm_quoted:\n'
 f'        move    #${composer.VOICE_BASE:06x},r6\n'
 f'        move    #${composer.SCRATCH_BASE:06x},r5\n'
 '        jsrl    pk_simple_base\n        jsrl    pk_fold_voice\n'
 '        jsrl    m_rng_out\n        rts\n'
 'm_rng_out:\n'
 f'        move    #${composer.RNG_BASE:06x},r1\n        move    #$000300,r2\n'
 '        move    x:(r1)+,a\n        move    a1,x:(r2)+\n'
 '        move    x:(r1)+,a\n        move    a1,x:(r2)+\n'
 '        move    x:(r1)+,a\n        move    a1,x:(r2)+\n'
 '        move    x:(r1)+,a\n        move    a1,x:(r2)+\n        rts\n'
 'm_dispatch:\n'
 '        move    #$000300,r4\n        jsrl    pk3d_source\n'
 '        move    #$000000,r0\n        rts\n')
binary,labels=join.assemble(composer, probe+"\n"+src, 'delta')

rec=[0]*20; rec[0]=0x504b; rec[2]=0x5931; rec[3]=1
rec[composer.ENGINE_ID_OFFSET]=composer.ENGINE_FOLD; rec[0x10]=1
data=(f"X {composer.VOICE_BASE:x} "+" ".join(f"{v:06x}" for v in state)+"\n"
      +f"X {composer.SCRATCH_BASE:x} "+" ".join(["000000"]*composer.SCRATCH_WORDS)+"\n"
      +"X 3964 "+" ".join(["ffffff"]*17)+"\n"
      +f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\n"
      +"P 400 00000c\n"                      # the `rts` trampoline @CONT@ lands on
      +ytext
      +f"X 300 "+" ".join(f"{w:06x}" for w in rec)+"\n"
      +f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\nX 20e 000000\n")
res={}
for entry in ('m_render','m_quoted','m_dispatch'):
    join.drive(composer, binary, labels, entry, data, entry)
    res[entry]=int((join.OUT/f"join_{entry}.meter").read_text().split()[-1])
    print(f'{entry:12s}: {res[entry]:6d} modeled cycles/block')
print()
print(f'the gate-only dump adds      : {res["m_quoted"]-res["m_render"]:+6d}')
print(f'the production path adds     : {res["m_dispatch"]-res["m_quoted"]:+6d}  over the quoted basis')
print(f'production / renderer-alone  : {res["m_dispatch"]/res["m_render"]:.3f}x')
