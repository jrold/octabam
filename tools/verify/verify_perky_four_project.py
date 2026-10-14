#!/usr/bin/env python3
"""PERKY4 long project replay: four-engine locks across all sequencer pages.

The --legacy-page control is the immutable PERKY2V_light_2voice source order.
Completion here is an emulator result, never physical qualification. P-locks
exercise changing controls at non-block-aligned sequencer trigger offsets.
"""
import argparse, hashlib, json, os, re, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/hw'), str(ROOT/'tools/harness'), str(ROOT/'tools')]
import ot_project as otp
import blockdump as bd
import recloop as rl
import verify_perky_synth_port as source_records
from ab_fixture import prepare


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image', type=Path, required=True)
    ap.add_argument('--project', type=Path, default=os.environ.get('OT_PROJECT'))
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--algorithm',type=int,choices=range(4),default=3)
    ap.add_argument('--fixed-algorithm', action='store_true',
                    help='lock every sequencer step to --algorithm, including ALGO p-locks')
    ap.add_argument('--dry', action='store_true', help='disable Dark and all other stock FX')
    ap.add_argument('--stock-only', action='store_true', help='exercise installed firmware with no PERKY assignments')
    ap.add_argument('--legacy-page', action='store_true')
    ap.add_argument('--frames', type=int, default=36000)
    ap.add_argument('--quantum', type=int, default=64)
    solo=ap.add_mutually_exclusive_group()
    solo.add_argument('--t1-only', action='store_true')
    solo.add_argument('--t5-only', action='store_true')
    ap.add_argument('--compare-t1-to',type=Path,
                    help='require T1 post-chain PCM to match a same-image T1-only block dump')
    args = ap.parse_args()
    tracks=() if args.stock_only else (0,) if args.t1_only else (4,) if args.t5_only else (0,4)
    assert args.project and (args.project/'project.work').is_file(), 'real OT_PROJECT required'
    args.work.mkdir(parents=True, exist_ok=True)
    project = prepare(args.project, args.work/'project')
    order = (1,0,3,4,5,2) if args.legacy_page else (0,1,2,3,4,5)
    for bank in project.glob('bank*.work'):
        def mutate(data):
            for part in range(otp.NPARTS_ALL):
                base = otp.PART_BASE + part*otp.PART_STRIDE + 9
                for track in range(8):
                    data[base+60+30*track:base+63+30*track] = bytes(3)
                    data[base+track] = data[base+8+track] = 0
                for track in tracks:
                    data[base+0x22+track] = 1
                    data[base+60+30*track:base+63+30*track] = b'PK\x01'
                    # Logical order TUNE DECAY ALGO PAR1 PAR2 MODE.
                    for slot, value in zip(order, (64,96,args.algorithm,64,64,0)):
                        data[base+0x2a+30*track+6+slot] = value
                    data[base+8+track] = 0x16 if track == 0 and not args.dry else 0  # Dark on T1
            for pattern in range(16):
                for track in range(8):
                    at = otp.trac_off(pattern,track)
                    data[at:at+64] = bytes(64)
                    data[at+0x59:at+0x59+64*32] = bytes([255])*(64*32)
                    # Known stock trig-word layout: clear inherited condition,
                    # microtiming and repeat fields in this private fixture.
                    data[at+0x899:at+0x919] = bytes(128)
                    if track not in tracks and not (args.stock_only and track in (0,4)): continue
                    data[at+0x50:at+0x52]=bytes((64,2))
                    for step in (0,2,5,6,10,13,16,21,25,29,32,37,41,45,48,53,57,61):
                        data[at+7-step//8] |= 1 << (step%8)
                        if step%2:
                            for logical,value in enumerate((8+(step*7)%96,64+step%32,args.algorithm if args.fixed_algorithm else (step//8)%4,(step*11)%128,(step*17)%128,step%3)):
                                data[at+0x59+step*32+order[logical]] = value
        otp._bank_write(project,int(bank.stem[4:]),mutate,guard=False)
    otp.set_tempo(project,120)
    otp.set_pattern_scale(project,1,0,64,'1X',guard=False)
    card = args.work/'card.img'
    subprocess.run([sys.executable,str(ROOT/'tools/emu/ot_emu/stage_card.py'),str(project),'OCTABAM','RIG','--tree',str(args.work/'tree'),'--out',str(card)],check=True,cwd=ROOT)
    dump = args.work/'blocks.bin'
    cmd = [str(ROOT/'out/emu/ot_emu'),'--image',str(args.image.resolve()),'--card',str(card.resolve()),'--set','OCTABAM','--project','RIG','--load-ms','90000','--sequencer','--internal-clock','--bank','0','--frames',str(args.frames),'--dsp','--dsp-dirty','123','--dsp-quantum',str(args.quantum),'--main-level','64','--block-dump',str(dump.resolve())]
    logpath = args.work/'port.log'
    with logpath.open('w') as log:
        log.write(' '.join(cmd)+'\n'); log.flush()
        subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600,check=True)
    log = logpath.read_text()
    assert re.search(r'frames run\s*:\s*'+str(args.frames)+r'.*REACHED',log), 'frame deadline incomplete'
    assert 'FAULT:' not in log and 'ILLEGAL' not in log
    classes = bd.classes(bd.read(dump))
    if args.stock_only:
        assert all(not source_records.signed_records(classes,core) for core in (0,1)), 'stock-only fixture delivered PERKY records'
    results = {}
    for track in tuple(t+1 for t in tracks):
        samples = rl.readback_audio(classes,track)
        assert sum(abs(v)>100 for v in samples)>16, (track,'source silent')
        packets=source_records.signed_records(classes,1 if track==1 else 0)
        hits=[p for p in packets if p[3]==1]
        assert len(hits)>=18,(track,'full 64-step cycle not executed',len(hits))
        steps=(0,2,5,6,10,13,16,21,25,29,32,37,41,45,48,53,57,61)
        expected=[(0,3,2,5)[args.algorithm if args.fixed_algorithm else (step//8)%4 if step%2 else args.algorithm] for step in steps]
        assert [p[19] for p in hits[:18]]==expected,(track,'actual full-page sequencer trig dispatch order',[p[19] for p in hits[:18]],expected)
        required={(0,3,2,5)[args.algorithm]} if args.fixed_algorithm else {0,3,2,5}
        actual_engines={p[19] for p in (packets if args.fixed_algorithm else hits)}
        assert actual_engines==required,(track,'actual algorithms',sorted(actual_engines),required)
        results[str(track)] = dict(triggers=len(hits),engines=sorted({p[19] for p in hits}),samples=len(samples),significant=sum(abs(v)>100 for v in samples),peak=max(map(abs,samples)),
                                  pcm_sha256=hashlib.sha256(struct.pack(f'<{len(samples)}i',*samples)).hexdigest())
    if args.compare_t1_to:
        baseline=rl.readback_audio(bd.classes(bd.read(args.compare_t1_to)),1)
        actual=rl.readback_audio(classes,1)
        assert actual==baseline,('adding T5 changed T1 PCM',len(actual),len(baseline),
                                 next(((i,a,b) for i,(a,b) in enumerate(zip(actual,baseline)) if a!=b),None))
        print('[PASS] T1 post-chain PCM bit-identical with/without T5, including all p-locks and Dark')
    report = dict(status='PASS: PERKY4 emulator project/engine-lock completion; physical qualification pending',frames=args.frames,quantum=args.quantum,legacy_page=args.legacy_page,algorithm=args.algorithm,fixed_algorithm=args.fixed_algorithm,dry=args.dry,stock_only=args.stock_only,image_sha256=hashlib.sha256(args.image.read_bytes()).hexdigest(),t1_only=args.t1_only,tracks=results)
    (args.work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    active='stock machines only' if args.stock_only else ('T1 alone' if args.t1_only else 'T5 alone' if args.t5_only else 'T1 + T5')+(' dry' if args.dry else ', Dark on T1' if not args.t5_only else '')
    print(f'[PASS] PERKY4 base ALGO {args.algorithm+1}, '+('fixed engine' if args.fixed_algorithm else 'all-page engine locks')+', '+active+f': {args.frames} dirty frames, sequencer p-locks, quantum {args.quantum}; no physical qualification implied')


if __name__ == '__main__': main()
