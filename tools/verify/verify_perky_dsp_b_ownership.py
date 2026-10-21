#!/usr/bin/env python3
"""Exercise B-tail kernels with retained FX and audit loaded P after PLAY.

This is a scoped port ownership check with one admitted source on B. It
does not qualify two-voice production dispatch, physical RAM or DSP timing.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/p) for p in ('tools', 'tools/build', 'tools/perky', 'modules/perky', 'tools/verify', 'tools/hw', 'tools/harness')]
os.environ.setdefault('REMIX','perky-machine')
import ab_records as A
import perky_dsp_b_specialization as S
import verify_perky_synth_port as port
import ot_project as otp
from remix import registry


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/dsp-b-feasibility')
    p.add_argument('--project',type=Path,required=True)
    args = p.parse_args()
    work = args.work.resolve()
    image_sha256 = hashlib.sha256((work/'fragmented-mainos.bin').read_bytes()).hexdigest()
    assert (args.project/'project.work').is_file(), 'real project fixture required'
    output = work/'ownership'
    output.mkdir(exist_ok=True)
    plans = {tag:S.plan(work/'multi.asm',tag) for tag in ('A','B')}
    uploads = json.loads((work/'p-records.json').read_text())
    expected = {}
    for tag in ('A','B'):
        raw = (work/f'dsp-{tag}.upload.bin').read_bytes()
        records,_ = A.records(raw,A.BASE,len(raw))
        expected[tag] = {addr+i:A.rd(raw,off+3*i) for sp,addr,n,off in records if sp == 0 and addr < 0x2000 for i in range(n)}
    peeks = ['0:P:0,8192','1:P:0,8192']
    peeks += [f'{core}:P:{addr:x},{len(words)}' for core,tag in enumerate(('A','B')) for addr,words in uploads[tag] if addr >= 0x30000]
    configs = [('FILTER','EQUALIZER','DJ EQ','PHASER'),('SPATIALIZER','FLANGER','CHORUS','COMB FILTER')]
    watched = {0:'fold_drum_voice.asm',3:'fold_drum2_voice.asm',2:'simple_drum_voice.asm',5:'complex_drum_production_voice'}
    rows = []
    for index,engine in enumerate((0,3,2,5)):
        port.OUT = output/'scratch'
        port.OUT.mkdir(exist_ok=True)
        fixture = port.configure_fixture(str(args.project),engine=engine)
        for bank in fixture.glob('bank*.work'):
            def ordinary(data):
                for part in range(8):
                    base = otp.PART_BASE+part*otp.PART_STRIDE+9
                    for track in range(1,8):
                        data[base+60+30*track:base+63+30*track] = bytes(3)
            otp._bank_write(fixture,int(bank.stem[4:]),ordinary,guard=False)
        for track in range(1,9):
            for slot,effect in (('fx1',configs[index%2][(track-1)%4]),
                                ('fx2',('LO-FI','SPRING REV','DARK REV','DELAY')[(track-1+index)%4])):
                values = otp.module_defaults(registry.modules()[effect])
                otp.set_fx(fixture,slot,track,effect,page=values[:6],page2=values[6:12],guard=False)
        card = port.OUT/'card.img'
        staged = subprocess.run([sys.executable,str(ROOT/'tools/emu/ot_emu/stage_card.py'),str(fixture),
                                 'OCTABAM','RIG','--tree',str(port.OUT/'tree'),'--out',str(card)],
                                cwd=ROOT,check=True,capture_output=True,text=True)
        watch = next(r['start'] for r in plans['B'][1] if r['name'] == watched[engine])
        cmd = [str(ROOT/'out/emu/ot_emu'),'--image',str(work/'fragmented-mainos.bin'),
               '--card',str(card),'--set','OCTABAM','--project','RIG','--load-ms','90000',
               '--sequencer','--internal-clock','--bank','0','--frames','2600','--dsp',
               '--dsp-dirty','123','--main-level','64','--dsp-peek',';'.join(peeks),
               '--dsp-pcwatch',f'1:{watch:x}']
        log_path = output/f'engine-{engine}.log'
        with log_path.open('w') as out:
            out.write(' '.join(cmd)+'\n'+staged.stdout+staged.stderr)
            out.flush()
            result = subprocess.run(cmd,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=600)
        assert result.returncode == 0, log_path
        log = log_path.read_text()
        assert 'FAULT:' not in log and 'ILLEGAL' not in log
        assert re.search(r'frames run\s*:\s*2600 .*REACHED',log), log_path
        hits = int(re.search(r'dsp pcwatch:.*last (\d+) arrival',log)[1])
        assert hits > 0, (engine,'kernel never executed')
        readback = {(int(c),int(a,16)):[int(w,16) for w in words.split()] for c,a,words in re.findall(r'core (\d+) P:(?:0x)?([0-9a-f]+): ([0-9a-f ]+)',log)}
        for core,tag in enumerate(('A','B')):
            for addr,value in expected[tag].items():
                # Stock frame setup patches these AND-mask literals. See
                # docs/firmware/DSP.md, non-effect modules and bank take.
                if addr in {'A':(0x58c,0x59b),'B':(0x371,0x380)}[tag]:
                    assert value == 0xffff and readback[core,0][addr] in (0x3fff,0x5fff), (tag,'stock packer mask')
                    continue
                assert readback[core,0][addr] == value, (engine,tag,hex(addr),'private P changed')
            for addr,words in uploads[tag]:
                if addr >= 0x30000:
                    assert readback[core,addr] == words, (engine,tag,hex(addr),'shared P changed')
        rows.append(dict(engine=engine,frames=2600,kernel_pc=watch,kernel_arrivals=hits,
                         log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest()))
        print(f'[PASS] B engine {engine}: executed at {watch:#x}, all uploaded private/shared P survives dirty startup and retained FX',flush=True)
    assert hashlib.sha256((work/'fragmented-mainos.bin').read_bytes()).hexdigest() == image_sha256, 'image changed during ownership gate'
    report = dict(schema='perky-dsp-b-ownership-v1',hardware_validated=False,rows=rows,
                  image_sha256=image_sha256,
                  project_sha256=hashlib.sha256((args.project/'project.work').read_bytes()).hexdigest(),
                  scope='One B source and retained FX in the port; no simultaneous CF or paired B production qualification.')
    (work/'ownership.json').write_text(json.dumps(report,indent=2)+'\n')
    shutil.rmtree(output/'scratch')


if __name__ == '__main__':
    main()
