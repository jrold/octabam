#!/usr/bin/env python3
"""Execute stock versus tail-preserving startup; compare every Y word on A/B."""
import os,sys,subprocess,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import ab_records as A, perky_fragmented_image as F, all_fx_layout as L
from verify_perky_shard_emit import shipping_payload

def main():
    asm=shipping_payload()
    image=(ROOT/'out/mainos_bus.bin').read_bytes()
    work=ROOT/'out/perky/fragment-clear';work.mkdir(parents=True,exist_ok=True)
    host=ROOT/'vendor/dsp56300/build/source/dsp_host/dsp_host'
    seed=[(i*65537+0x12345)&0xffffff or 1 for i in range(0x40000)]
    for tag,(va,ln) in zip(('A','B'),(A.PAYLOAD_A,A.PAYLOAD_B)):
        recs,_=A.records(image,va,ln)
        end=0x4a if tag=='A' else 0x4b
        old=[A.rd(image,A.word_at(recs,0,a)) for a in range(0x40,end)]+[0x00000c]
        records,_,_=F.plan(asm,tag);entry,words=records[-1]
        dumps=[]
        for name,origin,code in [('stock',0x40,old),('protected',entry,words)]:
            mem=work/f'{tag}-{name}.mem';dump=work/f'{tag}-{name}.bin'
            def record(space,addr,values):
                return struct.pack('<BII',space,addr,len(values))+struct.pack(f'<{len(values)}I',*values)
            mem.write_bytes(record(0,origin,code)+record(0,0,[0x00000c])+record(0,0x20,[0,0,0x00000c])+record(1,0x20c,[16,16])+record(2,0,seed)+b'\xff')
            cmd=[str(host),'-mem',str(mem),'-init','0','-proc',f'{origin:x}','-blocks','1','-frames','16','-noctl','-ctx','20,21,22','-dumpy',f'0,40000,{dump}']
            result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,check=True)
            (work/f'{tag}-{name}.log').write_text(result.stdout+result.stderr)
            assert 'HUNG' not in result.stdout
            dumps.append(struct.unpack('<262144I',dump.read_bytes()))
        stock,protected=dumps
        local_lo=0x4000 if tag=='A' else 0x3f00
        shared_lo=0x30000 if tag=='A' else 0x37f00
        for i,(before,after) in enumerate(zip(stock,protected)):
            cleared=(local_lo<=i<0xc000 or shared_lo<=i< (0x38000 if tag=='A' else 0x40000))
            assert before==(0 if cleared else seed[i]),(tag,'stock',hex(i))
            tail=any(a<=i<b for a,b in L.SAFE_SHARED_P_SPANS)
            assert after==(seed[i] if cleared and tail else before),(tag,'protected',hex(i),hex(after))
        print(f'[PASS] {tag}: 262144 Y words checked; only reserved tails differ from stock clear')
if __name__=='__main__':main()
