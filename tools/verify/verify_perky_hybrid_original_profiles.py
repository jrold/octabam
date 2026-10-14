#!/usr/bin/env python3
"""Execute hybrid CF profile differentials against original v1.2.1 ARM code.

No firmware image is built. All binaries, extracted tables, and reports stay in
--work. Original fixture and firmware identities remain mandatory and unchanged.
The optional legacy scope reports the unrelated WT/Fold target-sharing mismatch.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'modules/perky/cf_perky4.c').is_file())
sys.path[:0] = [str(ROOT/'tools/verify'), str(ROOT/'tools/perky')]
import verify_perky_cf_wavetable_dsp as reference
import verify_perky_cf_resonant_dsp as resonant_reference
import generate_cf_final_fixtures as fixtures

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path, required=True)
    ap.add_argument('--perkybits', type=Path, required=True)
    ap.add_argument('--unicorn-build', type=Path)
    ap.add_argument('--fixtures', type=Path, default=ROOT/'out/perky/engine-fixtures')
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--diagnostic-scope', choices=['corpus','grid','trajectory','profile','resonant','res-transitions','wt-boundary','long-tail','legacy'], help='Reduced diagnostic only; never returns an acceptance PASS')
    args = ap.parse_args()
    scope=args.diagnostic_scope or 'all'
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    (work/'receipt.json').write_text(json.dumps({'status':'RUNNING'})+'\n')
    source=args.perkybits.resolve()/'Source';u=(args.unicorn_build or args.perkybits/'build-local/_deps/unicorn-build').resolve()
    harness=ROOT/'tools/harness/perky_cf/perky_hybrid_wt_original.cpp'
    if not harness.is_file():
        harness=Path(__file__).resolve().with_name('perky_hybrid_wt_original.cpp')
    if sha(args.firmware)!=reference.FIRMWARE_SHA256:
        raise SystemExit('authoritative firmware hash mismatch')
    capture_digest,capture_count=reference.capture_digest(args.fixtures)
    if capture_digest!=reference.CAPTURE_SET_SHA256:
        raise SystemExit('authoritative Wavetable capture-set hash mismatch')
    fixture_manifest=json.loads((args.fixtures/'manifest.json').read_text())
    if fixture_manifest['firmware_sha256']!=reference.FIRMWARE_SHA256:
        raise SystemExit('historical fixture manifest firmware pin drift')
    captured={}
    stages=['pre-trigger','before','after','continuation-after','retrigger-before','retrigger-after']
    names=[f'wrapper-window-{stage}.bin' for stage in stages]+['arm-pcm.bin','arm-pcm-continuation.bin','arm-pcm-retrigger.bin']
    for family in (2,5,7):
        for mode in (1,2,3):
            for corner in (0,1,2):
                for name in names:
                    relative=f'engine-{family}-mode-{mode}-corner-{corner}/{name}'
                    digest=sha(args.fixtures/relative)
                    if fixture_manifest['files'].get(relative)!=digest:
                        raise SystemExit(f'historical original capture drift: {relative}')
                    captured[relative]=digest
    for relative,digest in resonant_reference.CAPTURE_SHA256.items():
        if sha(args.fixtures/relative)!=digest:
            raise SystemExit(f'authoritative Resonant capture drift: {relative}')
    historical=fixture_manifest['source_sha256']
    native=[source/'FirmwareImage.cpp',source/'PerkonsM7.cpp',source/'PerkonsVoices.cpp',*sorted(source.glob('NativeV121*.cpp'))]
    for path in native:
        key='Source/'+path.name
        if historical.get(key)!=sha(path):
            raise SystemExit(f'original runtime source drift: {path}; preserve the original fixture source pin')
    names=['cf_fold','cf_karplus','cf_noise_tone','cf_perky4','cf_resonant','cf_noise_hat','cf_simple_drum','cf_complex_drum','cf_slap','cf_wavetable']
    inputs=[harness,Path(__file__).resolve(),args.firmware.resolve(),args.fixtures/'manifest.json',*native,*sorted(source.glob('*.h'))]
    inputs += [ROOT/'modules/perky'/f'{n}.c' for n in names]
    inputs += sorted((ROOT/'modules/perky').glob('*.h'))
    inputs += [u/name for name in ['libunicorn.a','libarm-softmmu.a','libunicorn-common.a']]
    # Include the actual imported repository helper closure, including firmware
    # extraction and the historical reference pin modules used above.
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            path=Path(name).resolve()
            if ROOT in path.parents and path.suffix=='.py' and path.is_file():
                inputs.append(path)
    inputs=sorted(set(p.resolve() for p in inputs))
    receipt={'status':'RUNNING','scope':scope,'firmware_sha256':sha(args.firmware),'capture_set_sha256':capture_digest,'capture_files':capture_count,'all_read_capture_files':captured,'inputs':{str(p.resolve()):sha(p) for p in inputs},'commands':[],'limits':['Host execution establishes correctness, not ColdFire timing.','The host-only narrow profile adapter gives V1/V2 independent state; it is not the production firmware adapter.','The optional legacy WT/Fold roundtrip is outside the two-family hybrid contract.']}
    receipt_path=work/'receipt.json'
    def save():receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    def run(argv,label):
        log=work/(label+'.log');start=time.monotonic()
        with log.open('w') as out:r=subprocess.run([str(x) for x in argv],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
        item={'argv':[str(x) for x in argv],'exit_code':r.returncode,'elapsed_seconds':time.monotonic()-start,'log':str(log),'log_sha256':sha(log)};receipt['commands'].append(item);save()
        print(f'{label}: exit {r.returncode}, {item["elapsed_seconds"]:.2f}s; {log}',flush=True)
        if r.returncode:raise subprocess.CalledProcessError(r.returncode,argv)
    try:
        cc=shutil.which('cc');cxx=shutil.which('c++')
        if not cc or not cxx:raise RuntimeError('existing C/C++ compiler unavailable')
        receipt['tools']={}
        for compiler in (cc,cxx):
            path=Path(compiler).resolve()
            receipt['tools'][compiler]={'resolved_path':str(path),'sha256':sha(path),'version':subprocess.check_output([compiler,'--version'],text=True)}
            if platform.system()=='Darwin':
                delegated=Path(subprocess.check_output([compiler,'-print-prog-name=clang'],text=True).strip()).resolve()
                receipt['tools'][compiler]['delegated_clang']={'path':str(delegated),'sha256':sha(delegated)}
        python=Path(sys.executable).resolve()
        receipt['tools'][sys.executable]={'resolved_path':str(python),'sha256':sha(python),'version':sys.version}
        assets=fixtures.write_assets(args.firmware.resolve(),work/'fixtures')
        receipt['assets']={str(p):sha(p) for p in sorted(assets.glob('*.bin'))}
        objects=[]
        for name in names:
            obj=work/(name+'.o');run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I',ROOT/'modules/perky','-c',ROOT/'modules/perky'/f'{name}.c','-o',obj],'compile-'+name);objects.append(obj)
        extra=[]
        if platform.system()=='Darwin' and platform.machine()=='arm64':
            us=u.parent/'unicorn-src';cache=us/'qemu/util/cacheinfo.c';text=cache.read_text();old='    arch_cache_info(&isize, &dsize);'
            if text.count(old)!=1:raise RuntimeError('existing Unicorn cacheinfo source changed')
            patched=work/'cacheinfo.c';patched.write_text(text.replace(old,'    /* Darwin fallback avoids protected CTR_EL0. */'))
            obj=work/'cacheinfo.o';includes=[u.parent.parent,us/'glib_compat',us/'qemu',us/'qemu/include',us/'include',us/'qemu/tcg',us/'qemu/tcg/aarch64']
            run([cc,'-O2','-DNDEBUG','-std=gnu11','-D_GNU_SOURCE','-DUNICORN_HAS_ARM',*[f'-I{x}' for x in includes],'-c',patched,'-o',obj],'compile-cacheinfo');extra=[obj];receipt['cacheinfo_source_sha256']=sha(cache);receipt['inputs'][str(cache.resolve())]=sha(cache);receipt['cacheinfo_generated_sha256']=sha(patched)
        exe=work/'perky_hybrid_wt_original'
        run([cxx,'-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(source),'-I'+str(u.parent/'unicorn-src/include'),'-I',ROOT/'modules/perky',harness,*native,*objects,*extra,u/'libunicorn.a',u/'libarm-softmmu.a',u/'libunicorn-common.a','-lpthread','-lm','-o',exe],'link-original-gate')
        receipt['executable']={'path':str(exe),'sha256':sha(exe)}
        run([exe,args.firmware.resolve(),args.fixtures.resolve(),assets,work/'report.json',scope],'run-original-gate')
        report=json.loads((work/'report.json').read_text())
        expected_status='DIAGNOSTIC_PASS' if args.diagnostic_scope else 'PASS'
        if report['status']!=expected_status or report['scope']!=scope:
            raise RuntimeError('differential report failed or reduced coverage was misrepresented')
        if not args.diagnostic_scope:
            if len(report.get('wavetable_selection_coverage',[]))!=6:
                raise RuntimeError('original selectable-table coverage missing')
            expected={
                'isolated_constructor':(18,216,13824),'isolated_boundary':(1536,82944,393216),
                'pinned_corpus':(36,432,55296),'boundary_grid':(12288,43008,393216),
                'paired_trajectories':(384,11310,162048),'hybrid_resonant_roundtrip':(24,144,1536),
                'hybrid_profile_retention':(288,2199,100352),'resonant_mode_transitions':(192,4208,32128),
                'wavetable_long_tail_release':(12,49368,789504),'resonant_long_tail_release':(6,49362,394752),
            }
            for mode in (1,2,3):
                for name,bounds in [('corpus',(6,108,9216)),('grid',(2048,11264,65536)),('trajectories',(384,15990,162048))]:
                    expected[f'resonant_mode_{mode}_{name}']=bounds
            if set(report['sections'])!=set(expected) or report['release_calls']!=138:
                raise RuntimeError('required original-reference coverage missing')
            for name,bounds in expected.items():
                section=report['sections'][name]
                if tuple(section[k] for k in ('cases','state_checks','pcm_samples'))!=bounds or section['failures']:
                    raise RuntimeError(f'required coverage mismatch: {name}')
        drift=[path for path,digest in receipt['inputs'].items() if sha(path)!=digest]
        if drift:
            raise RuntimeError(f'input changed during original qualification: {drift}')
        receipt['input_hashes_rechecked_after_run']=True
        receipt['report']=report;receipt['report_path']=str(work/'report.json');receipt['report_sha256']=sha(work/'report.json');receipt['status']=expected_status
        print(json.dumps(report,indent=2),flush=True)
    except Exception as exc:
        receipt['status']='FAIL';receipt['error']=str(exc);save();raise
    save()
    return 0
if __name__=='__main__':raise SystemExit(main())
