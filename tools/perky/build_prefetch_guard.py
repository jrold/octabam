#!/usr/bin/env python3
"""Place frozen PERKY4R code below a six-word shared-P boundary guard.

This is a hardware discrimination build, not proof of a silicon prefetch fault.
Every AU fix and synthesis instruction is retained. Only placement changes;
six previously-free shared words become explicit NOP padding.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import ab_records as A
import perky_fragmented_image as F
import perky_four_placement as placement
import repack_machine_loader as R
from perky_four_memory import gaps
from remix import pack,platform_build
GUARD=6
VERSION='P4RPG6'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def guard_placer():
    # Explicit policy keeps the hardware-tested diagnostic reproducible.
    from functools import partial
    return partial(placement.place, guard_words=GUARD)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();reference=args.reference.resolve();work=args.out.resolve();work.mkdir(parents=True,exist_ok=True)
    assert sha(reference/'fragmented-mainos.bin')=='6499de13d66ab4099ad87521e93e3f362c4fa80259deb95b6e86190f20ecd495'
    normal=bytearray((reference/'fragmented-normal.bin').read_bytes())
    before=bytes(normal);prior=placement.place;placement.place=guard_placer()
    try:plans={tag:F.plan(reference/'multi.asm',tag,pad_guard=False) for tag in ('A','B')}
    finally:placement.place=prior
    union={};ledgers={};changed_offsets=set()
    for tag,(va,length) in zip(('A','B'),(A.PAYLOAD_A,A.PAYLOAD_B)):
        records,_=A.records(normal,va,length);ledgers[tag]=plans[tag][1]
        assert sum(row['length'] for row in ledgers[tag] if row['start']<0x30000)==770
        for address,words in plans[tag][0]:
            if address<0x30000:
                for i,word in enumerate(words):
                    offset=A.word_at(records,0,address+i)
                    if address==ledgers[tag][-1]['start']:
                        assert A.rd(normal,offset)==word,'startup clear changed'
                    changed_offsets.update((offset,offset+1,offset+2));A.wr(normal,offset,word)
            else:
                assert address+len(words)<=0x40000-GUARD,'program enters guard'
                if address in union:assert union[address]==words
                union[address]=words
    assert len(before)==len(normal)
    assert all(a==b or i in changed_offsets for i,(a,b) in enumerate(zip(before,normal))),'non-private-P prefix changed'
    assert sum(map(len,union.values()))==2398
    union[0x40000-GUARD]=[0]*GUARD
    ordered=sorted(union.items())
    for (address,words),(next_address,_) in zip(ordered,ordered[1:]):assert address+len(words)<=next_address
    assert sum(len(words) for _,words in ordered)==2404
    uploaded={tag:ordered for tag in ('A','B')}
    (work/'fragmented-normal.bin').write_bytes(normal)
    (work/'p-records.json').write_text(json.dumps(uploaded)+'\n')
    for name in ('multi.asm','tables.words','tables.bin','state_init.words','state_init.bin','layout.json'):
        shutil.copy2(reference/name,work/name)
    ledger=json.loads((reference/'memory.json').read_text())
    for tag in ('A','B'):ledger['cores'][tag]['p_shards']=ledgers[tag]
    physical={row['start']:row for rows in ledgers.values() for row in rows if row['start']>=0x30000}
    padding=dict(name='mapped prefetch guard NOPs',start=0x40000-GUARD,length=GUARD)
    physical[padding['start']]=padding
    ledger['physical_shared_p'].update(words=2404,free=0,extents=list(physical.values()),free_extents=gaps(placement.L.SAFE_SHARED_P_SPANS,[(a,a+len(words)) for a,words in ordered]),executable_words=2398,prefetch_padding_words=GUARD)
    assert not ledger['physical_shared_p']['free_extents']
    for tag in ('A','B'):
        ledger['cores'][tag]['p_shards'].append(padding.copy())
        ledger['cores'][tag]['p_free']=4
        ledger['cores'][tag]['p_words']=sum(row['length'] for row in ledger['cores'][tag]['p_shards'])
        ranges=[row for row in ledger['cores'][tag]['ranges'] if not row['what'].startswith('PERKY shared P/X/Y code:')]
        ranges.extend(dict(space='x',start=row['start'],length=row['length'],what='PERKY shared P/X/Y code: '+row['name'],half_relative=False) for row in physical.values())
        ledger['cores'][tag]['ranges']=ranges
    (work/'memory.json').write_text(json.dumps(ledger,indent=2)+'\n')
    platform=work/'platform';platform.mkdir(exist_ok=True)
    for name in ('layout.json','runtime.raw'):shutil.copy2(reference/'platform'/name,platform/name)
    (platform/'table.inc').write_text(' .long 1\n')
    raw=(platform/'runtime.raw').read_bytes()
    (platform/'blob0.bin').write_bytes(platform_build.SIGNATURE+pack.PACKED_MAGIC+len(raw).to_bytes(4,'big')+pack.pack(raw,platform_build.MAX_CANDIDATES))
    image=work/'fragmented-mainos.bin'
    R.build(work/'fragmented-normal.bin',work,image,platform_dir=platform,work=work/'platform-loader',p_records=uploaded)
    command=[sys.executable,str(ROOT/'tools/verify/verify_perky_machine_boot.py'),'--image',str(image),'--packed',str(work),'--platform',str(platform),'--platform-work',str(work/'platform-loader'),'--normal-image',str(work/'fragmented-normal.bin'),'--p-records',str(work/'p-records.json')]
    with (work/'boot.log').open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    diagnostic=dict(name=VERSION,status='hardware discrimination: prefetch boundary hypothesis unproven',source_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),mainos_sha256=sha(image),DSP_source_sha256=sha(work/'multi.asm'),ColdFire_runtime_sha256=sha(platform/'runtime.raw'),reference_mainos_sha256=sha(reference/'fragmented-mainos.bin'),guard_words=GUARD,changes='placement policy plus explicit guard padding only; complete R source/AU fixes retained',boot_command=command)
    assert diagnostic['DSP_source_sha256']==sha(reference/'multi.asm')
    (work/'diagnostic.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
    print('[PASS]',VERSION,sha(image),'; 770 private words/core, 2398 shared code + 6 guard, startup unchanged',flush=True)

if __name__=='__main__':main()
