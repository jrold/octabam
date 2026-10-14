#!/usr/bin/env python3
"""Build narrow PERKY4R hardware diagnostics from frozen local images.

These are not authenticity releases. Use Fold1 or Simple only. NDISP removes
the new dispatch block with no placement change; OLDDSP replaces the DSP
component with frozen PERKY4 while retaining PERKY4R's ColdFire runtime.
PLACE retains complete PERKY4R code, constraining common controls to bank 7.
Proprietary inputs and generated outputs remain outside Git.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'tools/build'), str(ROOT/'tools/perky'), str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX', 'perky-machine')
import ab_records as A
import perky_emit_shards as E
import repack_machine_loader as R
import perky_fragmented_image as F
import perky_four_placement as placement
from remix import pack, platform_build

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--frozen', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args=ap.parse_args(); frozen=args.frozen.resolve(); out=args.out.resolve()
    old=frozen/'PERKY4'; new=frozen/'PERKY4R'
    expected={'PERKY4':'b412c1a1cfc8f738fcccddb78b1f85f028d7d27aff8eafbc7d05e701940710f2', 'PERKY4R':'6499de13d66ab4099ad87521e93e3f362c4fa80259deb95b6e86190f20ecd495'}
    for version in expected:
        assert sha(frozen/version/'fragmented-mainos.bin')==expected[version], version+' input drift'
    snapshots={v:{f:sha(frozen/v/f) for f in ('fragmented-mainos.bin','fragmented-normal.bin','p-records.json','platform/runtime.raw')} for v in ('PERKY4','PERKY4R')}
    out.mkdir(parents=True,exist_ok=True)
    platform=out/'platform-input'; platform.mkdir(exist_ok=True)
    for f in ('layout.json','runtime.raw'): shutil.copy2(new/'platform'/f,platform/f)
    (platform/'table.inc').write_text(' .long 1\n')
    raw=(platform/'runtime.raw').read_bytes()
    (platform/'blob0.bin').write_bytes(platform_build.SIGNATURE+pack.PACKED_MAGIC+len(raw).to_bytes(4,'big')+pack.pack(raw,platform_build.MAX_CANDIDATES))
    # Repacking the reference without a logical change must reproduce it.
    identity=out/'identity'; identity.mkdir(exist_ok=True)
    R.build(new/'fragmented-normal.bin',new,identity/'mainos.bin',platform_dir=platform,work=identity/'loader',p_records=json.loads((new/'p-records.json').read_text()))
    assert sha(identity/'mainos.bin')==snapshots['PERKY4R']['fragmented-mainos.bin'], 'identity rebuild mismatch'
    for name in ('P4RNDISP','P4ROLDDSP','P4RPLACE'):
        dst=out/name;dst.mkdir(exist_ok=True)
        normal=bytearray((new/'fragmented-normal.bin').read_bytes())
        records=json.loads((new/'p-records.json').read_text()); changes=[]
        if name=='P4RNDISP':
            for tag in ('A','B'):
                from functools import partial
                original=placement.place
                placement.place=partial(original,guard_words=0)
                try: _,_,_,final,syms=E.emit(new/'multi.asm',tag)
                finally: placement.place=original
                lo,hi=final(syms['p3sg_base']),final(syms['p4mod_base'])
                assert hi-lo==8
                for upload in ('A','B'):
                    match=[(addr,words) for addr,words in records[upload] if addr<=lo<hi<=addr+len(words)]
                    assert len(match)==1
                    addr,words=match[0]; before=words[lo-addr:hi-addr]
                    assert before[0:6]==[0x56f000,0x39bf,0x0140c5,5,0x0d1042,4],before
                    words[lo-addr:hi-addr]=[0]*8
                changes.append(dict(core=tag,start=lo,before=before,after=[0]*8))
            assert records['A']==records['B'], 'union drift'
        elif name=='P4ROLDDSP':
            # The normal prefix's DSP sections are fixed-size stock records.
            # No ColdFire code, descriptor, hook or runtime byte is replaced.
            before=bytes(normal); old_normal=(old/'fragmented-normal.bin').read_bytes()
            spans=[]
            for va,length in (A.PAYLOAD_A,A.PAYLOAD_B):
                start=va-A.BASE; normal[start:start+length]=old_normal[start:start+length];spans.append((start,start+length))
            assert all(x==y or any(lo<=i<hi for lo,hi in spans) for i,(x,y) in enumerate(zip(before,normal)))
            records=json.loads((old/'p-records.json').read_text())
            changes=[dict(component='DSP P/X/Y uploads',source='PERKY4',ColdFire_runtime='PERKY4R unchanged')]
        else:
            # One placement constraint; the frozen PERKY4R source is unchanged.
            # Assemble every reference at its final address with round-trip
            # checking. Do not splice machine-code addresses heuristically.
            source=(ROOT/'tools/perky/perky_four_placement.py').read_text().replace('guard_words=PREFETCH_GUARD_WORDS','guard_words=0')
            needle="and (core is None or (a<0x38000)==(core=='A'))]"
            assert source.count(needle)==1
            constrained=source.replace(needle,"and (core is None or (a<0x38000)==(core=='A'))\n                   and (name != 'pk_three_common_controls' or i == 4)]")
            namespace={'L':placement.L};exec(compile(constrained,'bank1-placement','exec'),namespace)
            original=placement.place;placement.place=namespace['place']
            try: plans={tag:F.plan(new/'multi.asm',tag,pad_guard=False) for tag in ('A','B')}
            finally: placement.place=original
            union={}; ledgers={}
            for tag,(va,length) in zip(('A','B'),(A.PAYLOAD_A,A.PAYLOAD_B)):
                upload,_=A.records(normal,va,length)
                ledgers[tag]=plans[tag][1]
                for address,words in plans[tag][0]:
                    if address<0x30000:
                        for i,word in enumerate(words):A.wr(normal,A.word_at(upload,0,address+i),word)
                    else:
                        if address in union:assert union[address]==words
                        union[address]=words
            ordered=sorted(union.items())
            for (address,words),(next_addr,_) in zip(ordered,ordered[1:]):assert address+len(words)<=next_addr
            records={tag:ordered for tag in ('A','B')}
            changes=[dict(component='DSP placement only',constraint='pk_three_common_controls in original bank 7 (0x3e000..0x3ffff)',DSP_source_sha256=sha(new/'multi.asm'),AU_fixes='all retained')]
        (dst/'fragmented-normal.bin').write_bytes(normal)
        (dst/'p-records.json').write_text(json.dumps(records)+'\n')
        for f in ('tables.words','tables.bin','state_init.words','state_init.bin','layout.json'):
            shutil.copy2(new/f,dst/f)
        for f in ('multi.asm','memory.json'): shutil.copy2((old if name=='P4ROLDDSP' else new)/f,dst/f)
        if name=='P4RPLACE':
            ledger=json.loads((new/'memory.json').read_text())
            for tag in ('A','B'):ledger['cores'][tag]['p_shards']=ledgers[tag]
            physical={row['start']:row for rows in ledgers.values() for row in rows if row['start']>=0x30000}
            ledger['physical_shared_p']['extents']=list(physical.values())
            from perky_four_memory import gaps
            import all_fx_layout as L
            ledger['physical_shared_p']['free_extents']=gaps(L.SAFE_SHARED_P_SPANS,[(a,a+len(words)) for a,words in ordered])
            (dst/'memory.json').write_text(json.dumps(ledger,indent=2)+'\n')
        image=dst/'fragmented-mainos.bin'
        R.build(dst/'fragmented-normal.bin',dst,image,platform_dir=platform,work=dst/'platform-loader',p_records=records)
        boot=[sys.executable,str(ROOT/'tools/verify/verify_perky_machine_boot.py'),'--image',str(image),'--packed',str(dst),'--platform',str(platform),'--platform-work',str(dst/'platform-loader'),'--normal-image',str(dst/'fragmented-normal.bin'),'--p-records',str(dst/'p-records.json')]
        with (dst/'boot.log').open('w') as log: subprocess.run(boot,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        (dst/'diagnostic.json').write_text(json.dumps(dict(name=name,status='diagnostic; physical stability unresolved; Fold1/Simple only',source_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),inputs=snapshots,changes=changes,mainos_sha256=sha(image),ColdFire_runtime_sha256=sha(platform/'runtime.raw'),boot_command=boot),indent=2)+'\n')
        print(name,sha(image),flush=True)
    assert snapshots=={v:{f:sha(frozen/v/f) for f in snapshots[v]} for v in snapshots},'frozen inputs modified'

if __name__=='__main__':main()
