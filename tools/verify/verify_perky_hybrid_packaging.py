#!/usr/bin/env python3
"""Measure a standalone CF component envelope, never build a hybrid image."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys
from pathlib import Path

def sha(b): return hashlib.sha256(b).hexdigest()
def align(n,a=4): return (n+a-1)&-a

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--target-report',type=Path,required=True)
    ap.add_argument('--firmware',type=Path,required=True)
    ap.add_argument('--baseline',type=Path,default=Path('out/perky/hybrid/baseline/reproduction'))
    args=ap.parse_args(); root=args.root.resolve(); work=args.work.resolve()
    assert work.is_relative_to(root/'out')
    work.mkdir(parents=True,exist_ok=True)
    (work/'report.json').write_text(json.dumps({'status':'RUNNING'})+'\n')
    os.environ['OCTABAM_CACHE']=str(work/'cache');sys.dont_write_bytecode=True
    sys.path[:0]=[str(root/'tools'),str(root/'tools/perky'),str(root/'tools/build')]
    import perky_cf_assets, pcm_rice, bin_decode
    from remix import pack, platform_build, arena
    commands=[];checks=[];inputs={}
    def check(name,ok,detail=None):checks.append(dict(name=name,pass_=bool(ok),detail=detail))
    def pin(path):
        path=path.resolve();b=path.read_bytes();inputs[str(path)]=dict(bytes=len(b),sha256=sha(b));return b
    def run(argv,filename):
        argv=[str(a) for a in argv]; p=subprocess.run(argv,cwd=root,capture_output=True,text=True)
        out=p.stdout+p.stderr;(work/filename).write_text(out);commands.append(dict(argv=argv,exit_status=p.returncode,log=str(work/filename),log_sha256=sha(out.encode())))
        if p.returncode:raise RuntimeError(f'failed {argv}: {out[-2000:]}')
        return out
    report_path=args.target_report.resolve(); target=report_path.parent;tr=json.loads(pin(report_path))
    check('isolated target report passed',tr.get('status')=='PASS_ISOLATED_TARGET_CHECKS')
    compiled_drift=[];all_source_drift=[]
    for p,h in tr['source_sha256'].items():
        q=Path(p);q=q if q.is_absolute() else root/q
        if not q.is_file() or sha(q.read_bytes())!=h:
            all_source_drift.append(str(q))
            if q.suffix in ('.c','.h','.ld','.S','.s'):compiled_drift.append(str(q))
    check('compiled target dependencies still match executed report',not compiled_drift,compiled_drift)
    check('all target report source hashes still match',not all_source_drift,all_source_drift)
    components={}
    for filename in ('target.bin','target.elf','decode.bin','decode.elf'):
        b=pin(target/filename);check(filename+' matches executed target artifact',sha(b)==tr['artifact_sha256'][filename]);components[filename]=b
    secs=run(['m68k-elf-size','-A',target/'target.elf',target/'decode.elf'],'target-size.log')
    check('linked target section sizes agree with report',all(re.search(r'^'+re.escape(k)+r'\s+'+str(n)+r'\s',secs,re.M) for k,n in tr['linked_diagnostic_sections'].items()))
    firmware=pin(args.firmware);blobs=perky_cf_assets.extract(args.firmware);packed=perky_cf_assets.pcm_stream(blobs)
    check('production PKR1 has exactly two assets',struct.unpack_from('<I',packed,4)[0]==2)
    check('production PKR1 round-trips exact asset bytes',pcm_rice.decode_all(packed)==[blobs[n] for n,_,_ in perky_cf_assets.PCM_ASSETS])
    check('production PKR1 matches target decoder input',sha(packed)==tr['memory']['pkr1_sha256'])
    # Assemble the production asset generator alone to measure its real padding.
    (work/'assets.s').write_text('.text\n'+perky_cf_assets.assembly_text(args.firmware))
    run(['m68k-elf-as','-mcpu=54455','-o',work/'assets.o',work/'assets.s'],'assets-assemble.log')
    run(['m68k-elf-objcopy','-O','binary',work/'assets.o',work/'assets.bin'],'assets-binary.log')
    asset_sections=run(['m68k-elf-size','-A',work/'assets.o'],'assets-size.log')
    asset_bytes=(work/'assets.bin').read_bytes();ancillary=sum(len(blobs[n]) for n,_,_,_ in perky_cf_assets.IMAGE_ASSETS)
    check('production asset BSS is exactly 200704 bytes',bool(re.search(r'^\.bss\s+200704\s',asset_sections,re.M)))
    check('asset assembly has bounded documented alignment',len(asset_bytes)==ancillary+len(packed)+4)
    # This concatenation is only a compression/space specimen. No relocations,
    # OS hooks, firmware container, upload patches, or hybrid runtime are built.
    standalone=bytearray()
    component_ranges=[]
    for name,b in [('target.bin',components['target.bin']),('decode.bin',components['decode.bin']),('assets.bin',asset_bytes)]:
        standalone.extend(b'\0'*(align(len(standalone))-len(standalone)));start=len(standalone);standalone.extend(b)
        component_ranges.append(dict(name=name,start=start,bytes=len(b)))
    gka=pack.PACKED_MAGIC+len(standalone).to_bytes(4,'big')+pack.pack(bytes(standalone),4096)
    platform_blob=platform_build.SIGNATURE+gka
    (work/'standalone-components.gka').write_bytes(gka)
    # Read-only decoder validates original PERKY4S wrapper framing/checksum.
    elek=pin(root/'out/elek_PERKY4S.bin');card=pin(root/'out/OCTATRACK_PERKY4S.bin')
    check('original ELEK hash unchanged',sha(elek)=='f639d36154019dee21a1a7ac28d566b611d828abd4532b74d7a2a8e1bc4e7405')
    check('original card hash unchanged',sha(card)=='bc9367ec56b2f310f733d0808a88e74e44da32b63f9483468af09760f7ac8fa9')
    words=struct.unpack('>'+str(len(card)//4)+'I',card); k=words[1];plain=[]
    for c in words[2:-1]:plain.append(bin_decode.decode_word(k,c));k=c
    payload=struct.pack('>'+str(len(plain))+'I',*plain);el_len=struct.unpack_from('>I',payload)[0]
    check('original card decrypts exact ELEK and zero padding',el_len==len(elek) and payload[4:4+el_len]==elek and not any(payload[4+el_len:]))
    check('original card checksum matches',bin_decode.decode_word(k,words[-1])==(sum(plain)&0xffffffff))
    check('ELUP accounting is exact',len(card)==12+align(4+len(elek)) and len(payload)==len(card)-12)
    stock=pin(root/'out/raw/section_3_MAIN_OS.bin');guard_start=0x7f38e;guard_end=0x7f3ae;guard=stock[guard_start:guard_end]
    check('stock MAIN matches frozen input',sha(stock)=='164f31224bf61181e3f50e7dec40df9afcae5b16dbf6e4c0d0cc5e986af0a84e')
    disasm=run(['m68k-elf-objdump','-D','-b','binary','-m','m68k','--adjust-vma=0x40000000','--start-address=0x4007f38e','--stop-address=0x4007f3ae',root/'out/raw/section_3_MAIN_OS.bin'],'stock-card-cap.disasm')
    check('actual stock cap subtracts12 compares1MiB branches over error',all(x in disasm for x in ('4007f390:','addil #-12,%d6','4007f396:','cmpil #1048576,%d6','4007f39c:','bles 0x4007f3ae','moveq #-3,%d4')))
    baseline=args.baseline.resolve();rl=json.loads(pin(baseline/'platform/layout.json'));pl=json.loads(pin(baseline/'platform-loader/layout.json'))
    # Use actual loader table addresses, including uncached aliases.
    txt=pin(baseline/'platform-loader/pretable.inc').decode();entry_rows=[]
    for line in txt.splitlines():
        if '.long preblob' in line:
            f=[x.strip() for x in line.split('.long',1)[1].split(',')]
            entry_rows.append(dict(stage=int(f[3],0),dst=int(f[4],0),rawlen=int(f[5],0),blob_bytes=int(f[1],0)))
    actual=[]
    for i,e in enumerate(entry_rows):
        for role,n in [('dst',e['rawlen']),('stage',e['blob_bytes'])]:
            a=platform_build._cached(e[role]);actual.append(dict(name=f'payload {i} {role}',start=a,end=a+n,uncached_address=e[role]))
    check('actual loader table has both payloads',len(entry_rows)==2)
    check('actual loader ranges equal baseline layout',[(x['start'],x['end']) for x in actual]==[(x['start'],x['end']) for x in pl['preboot']])
    pr=pl['preboot_reserve'];check('preboot reservation immediately precedes runtime reservation',pr['ceiling']==rl['base'] and pr['base']==arena.BASE and pr['size']==242*arena.PAGE)
    check('all preboot extents in reservation',all(pr['base']<=x['start']<x['end']<=pr['ceiling'] for x in actual))
    occupied=actual+[dict(name='frozen runtime loaded',start=rl['base'],end=rl['runtime_end']),dict(name='frozen runtime BSS',start=rl['runtime_end'],end=rl['bss_end']),dict(name='frozen runtime stage',start=rl['stage'],end=rl['stage_end'])]
    check('actual frozen ranges do not overlap after alias normalization',all(not(a['start']<b['end'] and b['start']<a['end']) for i,a in enumerate(occupied) for b in occupied[i+1:]))
    # Explicit design budgets. These are future integration constraints, not a
    # measurement or bound on a firmware file which has not been constructed.
    integration_loaded_allowance=65536;integration_bss_allowance=16384;stack_reserve=4096
    check('observed target stack fits explicit reserve',tr['memory']['observed_max_stack_bytes']<=stack_reserve)
    loaded_budget=len(standalone)+integration_loaded_allowance
    bss_budget=tr['memory']['diagnostic_bss_bytes']+200704+integration_bss_allowance
    # A literal-only representation has 1 tag bit + 8 data bits per byte.
    # Add 16 bytes beyond ceil(9*n/8) for end marker and byte alignment.
    literal_envelope=(9*loaded_budget+7)//8+16
    table_and_blob_framing=4+32+3+12
    additional_elek_budget=align(literal_envelope+table_and_blob_framing)
    proposed_payload=align(4+len(elek)+additional_elek_budget)
    check('explicit packaging feasibility envelope fits cap',proposed_payload<=1048576)
    start=align(max(rl['stage_end'],rl['bss_end']),4096);prospective=[];p=start
    for name,n in [('standalone code/assets plus integration allowance',loaded_budget),('state/decoded PCM plus integration allowance',bss_budget),('stack reserve',stack_reserve),('packed stage envelope',literal_envelope+12)]:
        p=align(p,4096 if name=='packed stage envelope' else 4);prospective.append(dict(name=name,start=p,end=p+n,bytes=n,uncached_start=p+platform_build.UNCACHED));p+=n
    check('prospective component envelope fits existing frozen runtime reservation',p<=rl['ceiling'])
    check('prospective envelope cannot touch frozen preboot/runtime extents',all(not(a['start']<b['end'] and b['start']<a['end']) for a in prospective for b in occupied))
    out=dict(schema='octabam.perky.hybrid.packaging-feasibility.v1',status='PASS_FEASIBILITY_ENVELOPE' if all(c['pass_'] for c in checks) else 'FAIL',hardware_feasibility='UNVERIFIED',hybrid_firmware_built=False,checks=checks,commands=commands,inputs=inputs,source_sha256={str(root/p):sha((root/p).read_bytes()) for p in ['tools/perky/perky_cf_assets.py','tools/perky/pcm_rice.py','tools/remix/pack.py','tools/remix/platform_build.py','tools/remix/arena.py','tools/build/make_bin.py','tools/build/bin_decode.py']},target_report_source_drift=all_source_drift,production_assets=dict(ancillary_bytes=ancillary,alignment_bytes=4,PKR1_bytes=len(packed),PKR1_sha256=sha(packed),decoded_PCM_bytes=200704,asset_loaded_bytes=len(asset_bytes)),standalone_components=dict(ranges=component_ranges,raw_bytes=len(standalone),raw_sha256=sha(standalone),GKA3_bytes=len(gka),GKA3_sha256=sha(gka),platform_blob_bytes=len(platform_blob),note='Compression specimen of independently linked binaries plus production asset object. Not a relocated combined runtime; never wrapped into firmware.'),card=dict(payload_cap=1048576,file_cap=1048588,formula='ELUP bytes = 12 + align4(4 + ELEK bytes)',original_elek_bytes=len(elek),original_ELUP_bytes=len(card),original_payload_bytes=len(payload),original_payload_headroom=1048576-len(payload),stock_guard_range=[hex(0x40000000+guard_start),hex(0x40000000+guard_end)],stock_guard_sha256=sha(guard),documented_old_address='0x4007f748 is not this guard in pinned stock MAIN'),feasibility_envelope=dict(kind='explicit design budget, not an exact future hybrid wrapper measurement',integration_loaded_allowance=integration_loaded_allowance,integration_bss_allowance=integration_bss_allowance,stack_reserve=stack_reserve,literal_encoded_loaded_envelope=literal_envelope,table_and_blob_framing=table_and_blob_framing,additional_elek_budget=additional_elek_budget,projected_payload_with_budget=proposed_payload,margin_under_payload_cap=1048576-proposed_payload,assumptions=['Final combined link/relocation, callback/control integration and differences to baseline outer compression must fit the explicit 65536 loaded-byte allowance.','The final card wrapper must be built and checked in a later goal; no claim of exact combined compressed size is made.']),memory=dict(actual_ranges=occupied,preboot_reservation=pr,runtime_reservation=dict(base=rl['base'],ceiling=rl['ceiling'],bytes=rl['size']),prospective_disjoint_components=prospective,prospective_end=p,remaining_in_existing_reservation=rl['ceiling']-p,note='Cached/uncached views name the same SDRAM. This prospective disjoint placement proves room only, not an implemented loader allocation. Production loader BSS is never implicitly cleared; its temporary stage may overlap BSS until explicit initialization.'))
    out['source_sha256'][str(Path(__file__).resolve())]=sha(Path(__file__).read_bytes())
    (work/'report.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ('status','production_assets','standalone_components','card','feasibility_envelope')},indent=2));return 0 if out['status'].startswith('PASS') else 1
if __name__=='__main__':raise SystemExit(main())
