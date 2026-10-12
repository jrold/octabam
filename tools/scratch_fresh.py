import sys, struct, importlib.util
from pathlib import Path
sys.path[:0]=['modules/perky','tools/perky','tools/verify']
def load(n,rel):
    s=importlib.util.spec_from_file_location(n, rel); m=importlib.util.module_from_spec(s)
    sys.modules[n]=m; s.loader.exec_module(m); return m
join=load('join','tools/verify/verify_perky_3algo_engine_join.py')
g=load('g','tools/verify/verify_perky_3algo_exec.py')
composer=join.load_composer()
import resonant_control_update as rcu, resonant_bass_compact as ba, resonant_snare_compact as sn
A=Path('out/perky/res-assets')
pitch=A.joinpath('pitch.bin').read_bytes(); chrom=A.joinpath('chromatic.bin').read_bytes()
def fresh_words(fam, targets=(2048,2048,2048,2048), vel=255, note=45):
    if fam=='bass':
        b=rcu.trigger_bass(rcu.update_bass(rcu.fresh_bass(vel,note), targets, pitch, chrom), vel, note)
        return list(ba.ResonantBass.from_arm(bytes(b[:0x178])).words)
    b=rcu.trigger_snare(rcu.update_snare(rcu.fresh_snare(vel,note), targets, pitch, chrom), vel, note)
    return list(sn.ResonantSnare.from_arm(bytes(b)).words)
OUT=Path('out/perky/dsp-3algo/fresh'); OUT.mkdir(parents=True,exist_ok=True)
e1,e2,_,_=g.make_envelopes()
ia=struct.pack('<257H',*[(i*257+i*i)&0xFFFF for i in range(257)])
ib=struct.pack('<257H',*[(65535-i*251)&0xFFFF for i in range(257)])
ytext=g.tables_text(e1,e2,ia,ib, Path('out/perky/simple-drum-assets'))
V=composer.VOICE_BASE
probe=('meas_one:\n        move    #$000300,r4\n        jsrl    pk3d_source\n        rts\n')
src=composer.normalize(composer.compose()).replace('@CONT@','$000400')
b,lab=join.assemble(composer, probe+"\n"+src, 'fresh')
print(f"{'engine':8s} {'words':>6s} {'DSP peak':>10s} {'DSP meter':>10s}")
for fam,eng in (('bass',10),('snare',11)):
    w=fresh_words(fam)
    st=w+[0]*(composer.RNG_GAP_START-V-len(w))
    rec=[0]*20; rec[0]=0x504b; rec[2]=0x5931; rec[3]=1
    rec[composer.ENGINE_ID_OFFSET]=eng; rec[16]=1
    rec[8],rec[10],rec[12],rec[14]=0x0100,0x0200,0x0300,0x0400
    (OUT/f'{fam}.data').write_text(
        f"X {V:x} "+" ".join(f"{v:06x}" for v in st)+"\n"
        +f"X {composer.SCRATCH_BASE:x} "+" ".join(["000000"]*composer.SCRATCH_WORDS)+"\n"
        +"X 3964 "+" ".join(["ffffff"]*17)+"\n"
        +f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\nP 400 00000c\n"+ytext
        +f"X {composer.ENGINE_LEDGER:x} {0x8000|eng:06x}\n"
        +f"X 300 "+" ".join(f"{x:06x}" for x in rec)+"\n"
        +f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\nX 20e 000000\n"
        +"X 0 "+" ".join(["000000"]*32)+"\n")
    (OUT/f'{fam}.script').write_text(" ".join(["0"]*12+["-1"])+"\n")
    import subprocess
    subprocess.run([str(join.OUT/'bd909_host'),'-code',str(b),'-org',format(composer.DSP_ORG,'x'),
      '-entry',format(lab['meas_one'],'x'),'-data',str(OUT/f'{fam}.data'),
      '-script',str(OUT/f'{fam}.script'),'-out',str(OUT/f'{fam}.raw'),
      '-state',str(OUT/f'{fam}.state'),'-state-words','64','-statebase',format(V,'x'),
      '-frames','16','-meter',str(OUT/f'{fam}.meter'),'-cycle-meter','1'],
      check=True,capture_output=True)
    pcm=struct.unpack('<32i',(OUT/f'{fam}.raw').read_bytes())[::2]
    print(f'{fam:8s} {len(w):6d} {max(abs(v) for v in pcm):10d} {int((OUT/f"{fam}.meter").read_text().split()[-1]):10d}')
