#!/usr/bin/env python3
"""Run every retained stock FX init/proc with PERKY and read back all P shards."""
import os,sys,subprocess,re,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky'),str(ROOT/'tools/hw'),str(ROOT/'tools/harness')]
os.environ.setdefault('REMIX','perky-machine')
import verify_perky_synth_port as port
import perky_fragmented_image as F
import ot_project as otp
from remix import registry

def main():
    project=os.environ.get('OT_PROJECT')
    if not project:
        print('[SKIP] fragmented FX runtime: needs OT_PROJECT');return
    work=ROOT/'out/perky/fragmented-fx';work.mkdir(parents=True,exist_ok=True)
    build=ROOT/'out/perky/fragmented'
    plans={tag:F.plan(build/'multi.asm',tag) for tag in ('A','B')}
    watch=next(r['start'] for r in plans['A'][1] if r['name']=='fold_drum_voice.asm')
    peek=';'.join(f'{core}:P:{addr:x},{len(words)}' for tag,core in [('A',0),('B',1)] for addr,words in plans[tag][0])
    configs=[('FILTER','EQUALIZER','DJ EQ','PHASER'),('SPATIALIZER','FLANGER','CHORUS','COMB FILTER')]
    for index in range(4):
        fx1=configs[index%2]
        port.OUT=work/f'config{index}';port.OUT.mkdir(parents=True,exist_ok=True)
        fixture=port.configure_fixture(project,engine=0)
        for bank in fixture.glob('bank*.work'):
            def ordinary(data):
                for part in range(8):
                    base=otp.PART_BASE+part*otp.PART_STRIDE+9
                    for t in (1,2,3,5,6,7):data[base+60+30*t:base+63+30*t]=bytes(3)
            otp._bank_write(fixture,int(bank.stem[4:]),ordinary,guard=False)
        for track in range(1,9):
            for slot,effect in [('fx1',fx1[(track-1)%4]),('fx2',('LO-FI','SPRING REV','DARK REV','DELAY')[(track-1+index)%4])]:
                values=otp.module_defaults(registry.modules()[effect])
                otp.set_fx(fixture,slot,track,effect,page=values[:6],page2=values[6:12],guard=False)
        card=port.OUT/'card.img'
        subprocess.run([sys.executable,str(ROOT/'tools/emu/ot_emu/stage_card.py'),str(fixture),'OCTABAM','RIG','--tree',str(port.OUT/'tree'),'--out',str(card)],cwd=ROOT,check=True)
        cmd=[str(ROOT/'out/emu/ot_emu'),'--image',str(build/'fragmented-mainos.bin'),'--card',str(card),'--set','OCTABAM','--project','RIG','--load-ms','90000','--sequencer','--internal-clock','--bank','0','--frames','2600','--dsp','--dsp-dirty','123','--main-level','64','--dsp-peek',peek,'--dsp-pcwatch',f'0:{watch:x}']
        with (port.OUT/'port.log').open('w') as out:
            out.write(' '.join(cmd)+'\n');out.flush()
            subprocess.run(cmd,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True,timeout=600)
        log=(port.OUT/'port.log').read_text()
        assert 'FAULT:' not in log and 'ILLEGAL' not in log
        assert re.search(r'frames run\s*:\s*2600 .*REACHED',log)
        assert int(re.search(r'dsp pcwatch:.*last (\d+) arrival',log)[1])>0
        readback={(int(c),int(a,16)):[int(w,16) for w in words.split()] for c,a,words in re.findall(r'core (\d+) P:0x([0-9a-f]+): ([0-9a-f ]+)',log)}
        for tag,core in [('A',0),('B',1)]:
            for addr,words in plans[tag][0]:assert readback[core,addr]==words,(index,tag,hex(addr))
        print(f'[PASS] FX configuration {index}: 2600 dirty frames, shared code executed, every P shard survives all FX init/proc')
if __name__=='__main__':main()
