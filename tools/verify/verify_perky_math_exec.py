#!/usr/bin/env python3
"""Assemble/execute PERKY u32 math in dsp56kEmu and compare exactly."""
from __future__ import annotations
import pathlib,re,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]; PERKY=ROOT/'modules/perky'; V=ROOT/'vendor/dsp56300'; OUT=ROOT/'out/perky/math'
sys.path.insert(0,str(PERKY))
from noise_tone_word_model import U32,add32,sub32,arshift32_words,mul_low32_words,mul_full64_words  # noqa:E402
ASM=V/'build/source/dsp_host/dsp_asm'; DIS=V/'build/source/disassemble/dsp56kDisassemble'; HOST=OUT/'bd909_host'; SRC=ROOT/'tools/harness/bd909_host/bd909_host.cpp'; ORG=0x2000
LINE=re.compile(r'^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$')
def fail(s): raise SystemExit('verify-perky-math-exec: '+s)
def decoded(t): return {int(m.group(1),16):(m.group(2),(m.group(3) or '').strip()) for m in map(LINE.match,t.splitlines()) if m}
def host():
    libs=[V/'build/source/dsp56kEmu/libdsp56kEmu.a',V/'build/source/dsp56kBase/libdsp56kBase.a',V/'build/source/asmjit/libasmjit.a']; miss=[p for p in [ASM,DIS,*libs] if not p.exists()]
    if miss: fail('run `make setup` first; missing '+', '.join(map(str,miss)))
    OUT.mkdir(parents=True,exist_ok=True)
    if HOST.exists() and HOST.stat().st_mtime>SRC.stat().st_mtime:return
    subprocess.run(['c++','-O3','-DNDEBUG','-std=gnu++17','-DASMJIT_STATIC','-DDSP56300_DEBUGGER=0',f'-I{V}/source',f'-I{V}/source/asmjit/src',str(SRC),str(libs[0]),str(libs[1]),str(libs[2]),'-lpthread','-o',str(HOST)],check=True,capture_output=True)
def build():
    b=OUT/'math.bin'; s=OUT/'math.sym'; r=subprocess.run([str(ASM),'-in',str(PERKY/'noise_tone_math.asm'),'-org',f'{ORG:x}','-out',str(b),'-list','-sym',str(s)],capture_output=True,text=True)
    if r.returncode: fail('assembler failed:\n'+r.stdout[-3000:]+r.stderr[-2000:])
    labels={q[0]:int(q[1],16) for q in (line.split() for line in s.read_text().splitlines()) if len(q)==2}
    if 'pk_math_probe' not in labels: fail('assembler emitted no pk_math_probe symbol')
    d=subprocess.run([str(DIS),'-in',str(b),'-pc',f'{ORG:x}','-le'],capture_output=True,text=True,check=True); typed,actual=decoded(r.stdout),decoded(d.stdout)
    if not typed or len(actual)<len(typed)*.9: fail('no usable disassembly to compare')
    for addr,(mn,ops) in typed.items():
        dm,dops=actual.get(addr,('?',''))
        if dm!=mn: fail(f'P:{addr:06x} typed {mn} {ops} but decodes {dm} {dops}')
    return b,labels['pk_math_probe']
def run(binary,entry,tag,op,a,b=0,shift=0):
    w=[0]*64; aa=U32.from_int(a); bb=U32.from_int(b); w[:5]=[aa.lo,aa.hi,bb.lo,bb.hi,shift]
    data=OUT/(tag+'.data'); script=OUT/(tag+'.script'); raw=OUT/(tag+'.raw'); state=OUT/(tag+'.state')
    data.write_text('X 200 '+' '.join(f'{x:06x}' for x in w)+'\n'); script.write_text(' '.join(map(str,[op]+[0]*11))+' -1\n')
    subprocess.run([str(HOST),'-code',str(binary),'-org',f'{ORG:x}','-entry',f'{entry:x}','-data',str(data),'-script',str(script),'-out',str(raw),'-state',str(state)],check=True,capture_output=True,text=True)
    d=[int(x,16) for x in state.read_text().split()]
    if len(d)<64: fail(tag+': truncated state dump')
    return U32(d[8]&0xffff,d[9]&0xffff),U32(d[10]&0xffff,d[11]&0xffff)
def ck(tag,got,want):
    if got!=want: fail(f'{tag}: got {got.unsigned():08x}, want {want.unsigned():08x}')
def main():
    host(); binary,entry=build(); n=0
    pairs=[(0,0),(1,2),(0xffff,1),(0xffffffff,1),(0x1234ffff,0x43210001),(0x80000000,0x80000000),(0x89abcdef,0x76543210),(0x5851f42d,0x4c957f2d)]
    for i,(a,b) in enumerate(pairs):
        for op,name,fn in ((1,'add',add32),(2,'sub',sub32),(4,'mul',mul_low32_words)):
            tag=f'{name}-{i}'; ck(tag,run(binary,entry,tag,op,a,b)[0],fn(U32.from_int(a),U32.from_int(b))); n+=1
        lo,hi=run(binary,entry,f'mul64-{i}',5,a,b); wlo,whi=mul_full64_words(U32.from_int(a),U32.from_int(b)); ck(f'mul64-low-{i}',lo,wlo); ck(f'mul64-high-{i}',hi,whi); n+=2
    vals=[0,1,0x7fffffff,0x80000000,0xffffffff,0x89abcdef,0x01234567]
    for vi,a in enumerate(vals):
        for sh in (0,1,4,8,9,10,12,13,16,17,31):
            tag=f'asr-{vi}-{sh}'; ck(tag,run(binary,entry,tag,3,a,shift=sh)[0],arshift32_words(U32.from_int(a),sh)); n+=1
    print(f'PERKY DSP math executable gate: OK ({n} exact result words)')
if __name__=='__main__': main()
