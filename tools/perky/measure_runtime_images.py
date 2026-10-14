#!/usr/bin/env python3
"""Meter and trace source routines read from generated firmware upload records.

These are isolated source calls, not hardware timing or complete FX deadlines.
Bank fetch counts describe exposure; no invented wait-state factor is a gate.
"""
import argparse, collections, hashlib, json, os, struct, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'tools/verify'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import ab_records as A
import build_bus as B
import verify_perky_controlled_voice_exec as host
import verify_perky_synth_seam_exec as seam

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference',type=Path,required=True)
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    host.OUT=args.out;host.HOST=args.out/'bd909_host';host.build_host()
    reports=[]; outputs={}
    for version,build in (('PERKY4R',args.reference),(args.candidate.name,args.candidate)):
        normal=(build/'fragmented-normal.bin').read_bytes();shared=json.loads((build/'p-records.json').read_text())
        ledger=json.loads((build/'memory.json').read_text())
        for tag,(va,length) in zip(('A','B'),(A.PAYLOAD_A,A.PAYLOAD_B)):
            upload,_=A.records(normal,va,length)
            rows=ledger['cores'][tag]['p_shards']
            entry=next(r['start'] for r in rows if r['name']=='synth_seam_glue.asm')
            wrapper=seam.WRAPPER
            start=wrapper.index('        move #>$000100,r1');end=wrapper.index('        move r4,x:>$209',start)
            wrapper=wrapper[:start]+wrapper[end:]
            wrapper=wrapper.replace('jsrl pk_probe_source',f'jsrl ${entry:06x}')
            wrapper=wrapper.replace('        move r4,x:>$209','        move #>$4080,a\n        move a1,x:>$20b\n        move r4,x:>$209',1)
            wrapper=wrapper.replace('        move b1,x:(r4+$3)','        or #>$030000,b\n        move b1,x:(r4+$3)')
            words,labels=B.assemble_syms(wrapper,0x5000,'runtime_wrapper',strict_layout=True)
            stub=args.out/'wrapper.bin';stub.write_bytes(b''.join(w.to_bytes(3,'little') for w in words))
            initial=host.words(build/'state_init.words');table=host.words(build/'tables.words')
            for engine in (0,2,5):
                run=args.out/f'{version}-{tag}-{engine}';run.mkdir(exist_ok=True)
                # The same prepared controls feed both placements. Complex uses
                # its real AU-repaired ABI; Fold/Simple retain their own ABI.
                values=(2046,29,180,2046) if engine==5 else (2048,428,1040,1024) if engine==2 else (2046,29,2046,2046)
                record=[v for value in values for v in (value>>8,value&255)]+[0,31 if engine==5 else 0,0,engine]
                text=''
                for sp,address,count,offset in upload:
                    if sp==0:
                        chunk=[A.rd(normal,offset+3*i) for i in range(count)]
                        text+=f'P {address:x} '+' '.join(f'{w:06x}' for w in chunk)+'\n'
                for address,chunk in shared[tag]:text+=f'P {address:x} '+' '.join(f'{w:06x}' for w in chunk)+'\n'
                cont=0x426 if tag=='A' else 0x221
                text+=f'P {cont:x} 0bf080 {labels["pkse_finish"]:06x} 00000c\n'
                text+='X 3800 '+' '.join(f'{w:06x}' for w in initial)+'\nY 7a5 '+' '.join(f'{w:06x}' for w in table)+'\n'
                text+='X 3900 '+' '.join(['000000']*118)+'\nX 3964 00ffff '+' '.join(['000000']*16)+'\nX 39b0 '+' '.join(['000000']*17)+'\n'
                text+='X 500 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{w|0x030000:06x}' for w in record)+'\nX 418 000000\nX 20b 004080\n'
                (run/'data.txt').write_text(text)
                (run/'script.txt').write_text('\n'.join(' '.join(map(str,[0]*12+[event])) for event in (0,-1,15,-1))+'\n')
                command=[str(host.HOST),'-code',str(stub),'-org','5000','-entry',f'{labels["pk_controlled_voice_exec"]:x}','-data',str(run/'data.txt'),'-script',str(run/'script.txt'),'-out',str(run/'audio.raw'),'-meter',str(run/'meter.txt'),'-fetch-trace',str(run/'trace.txt'),'-registers',str(run/'registers.txt'),'-frames','16']
                subprocess.run(command,cwd=ROOT,capture_output=True,check=True)
                trace=[(int(pc,16),int(cycles)) for pc,cycles in map(str.split,(run/'trace.txt').read_text().splitlines())]
                spans=[(r['start'],r['start']+r['length']) for r in rows]
                source=[(pc,cycles) for pc,cycles in trace if any(lo<=pc<hi for lo,hi in spans)]
                banks=collections.Counter((pc-0x30000)//0x2000 for pc,_ in source if 0x30000<=pc<0x40000)
                cycles=list(map(int,(run/'meter.txt').read_text().split()))
                assert max(cycles)<=23040,(version,tag,engine,cycles)
                outputs[version,tag,engine]=(run/'audio.raw').read_bytes()
                assert any(struct.unpack(f'<{len(outputs[version,tag,engine])//4}i',outputs[version,tag,engine])),(version,tag,engine,'silent source measurement')
                registers=[list(map(lambda value:int(value,16),line.split())) for line in (run/'registers.txt').read_text().splitlines()]
                assert all(row[8]==0 for row in registers),(version,tag,engine,'unbalanced return stack')
                reports.append(dict(version=version,core=tag,engine=engine,cycles=cycles,source_trace_cycles=sum(c for _,c in source),shared_opcode_fetches=dict(sorted(banks.items())),image_sha256=hashlib.sha256((build/'fragmented-mainos.bin').read_bytes()).hexdigest()))
                print('[PASS]',version,tag,engine,'modeled cycles',cycles,'shared opcode fetches',dict(sorted(banks.items())),flush=True)
    for tag in ('A','B'):
        for engine in (0,2,5):assert outputs['PERKY4R',tag,engine]==outputs[args.candidate.name,tag,engine],(tag,engine,'placement changed source PCM')
    (args.out/'report.json').write_text(json.dumps(dict(status='source model only; hardware arbitration not modeled',records=reports,PCM_comparisons=6,failed=0,skipped=0),indent=2)+'\n')

if __name__=='__main__':main()
