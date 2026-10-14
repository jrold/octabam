#!/usr/bin/env python3
"""Compare completed actual-image replays without hiding gain/time differences.

The project runner asserts every record contains the requested fixed engine.
This verifier checks complete post-chain PCM and producer packets against the
frozen PERKY4 image, including tail samples, and inventories the exact images.
Emulator equality is explicitly not physical stability qualification.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/harness'),str(ROOT/'tools/verify')]
import blockdump as bd
import recloop as rl
import verify_perky_synth_port as records

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--baseline-version',default='PERKY4')
    ap.add_argument('--versions',nargs='+',default=['PERKY4R','P4RNDISP','P4ROLDDSP','P4RPLACE'])
    ap.add_argument('--cases',nargs='+',default=['fold1-q16','simple-q16'])
    ap.add_argument('--report',type=Path,help='unique report path when running multiple comparison subsets')
    args=ap.parse_args(); results=[]
    for case in args.cases:
        base=args.work/(args.baseline_version+'-'+case)
        baseline=json.loads((base/'result.json').read_text())
        baseline_classes=bd.classes(bd.read(base/'blocks.bin'))
        assert baseline['fixed_algorithm']
        for version in args.versions:
            current=args.work/(version+'-'+case)
            result=json.loads((current/'result.json').read_text())
            assert result['fixed_algorithm'] and result['frames']==baseline['frames']
            assert result['algorithm']==baseline['algorithm']
            classes=bd.classes(bd.read(current/'blocks.bin'))
            for track,core in ((1,1),(5,0)):
                expected=rl.readback_audio(baseline_classes,track);actual=rl.readback_audio(classes,track)
                assert actual==expected,(version,case,track,'complete post-chain PCM mismatch',next(((i,a,b) for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),None))
                old_records=records.signed_records(baseline_classes,core);new_records=records.signed_records(classes,core)
                assert old_records==new_records,(version,case,track,'producer records differ')
            results.append(dict(version=version,case=case,baseline_image_sha256=baseline['image_sha256'],image_sha256=result['image_sha256'],frames=result['frames'],tracks=result['tracks'],PCM='bit-exact',producer_packets='bit-exact'))
            print(f'[PASS] {version} vs {args.baseline_version}, {case}: complete T1/T5 PCM and producer packets exact; engine {baseline["algorithm"]+1} fixed')
    report=dict(status='LOCAL DIFFERENTIAL PASS; physical regression NOT resolved',comparisons=results,failed=0,skipped=0)
    report_path=args.report or args.work/('differential-'+args.baseline_version+'.json')
    report_path.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
