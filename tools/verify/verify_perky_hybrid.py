#!/usr/bin/env python3
"""Fail-closed baseline/CF foundation evidence gate; emits a bounded JSON report.

No production hybrid is built. Historical reference pins remain authoritative;
changed CF sources are freshly qualified against them. PASS_FOR_PROBE_BUILD
authorizes a later probe stage only; hardware feasibility remains UNVERIFIED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT/'modules/perky/hybrid/BASELINE.json'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def item(path):
    p = Path(path).resolve()
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def validate_frozen(b):
    errors = []
    def verify(v):
        p = Path(v['path'])
        if not p.is_file():
            errors.append(f'missing: {p}')
        elif sha(p) != v['sha256'] or p.stat().st_size != v['bytes']:
            errors.append(f'identity drift: {p}')
    assert git('branch','--show-current') == 'perky-cf-dsp-hybrid', 'wrong development branch'
    assert git('rev-parse','perky-machines') == b['baseline_commit'], 'preserved branch moved'
    subprocess.run(['git','merge-base','--is-ancestor',b['baseline_commit'],'HEAD'],cwd=ROOT,check=True)
    for commit in (b['integration_commit'],b['timing_repair_commit'],b['original_dsp_commit']):
        subprocess.run(['git','merge-base','--is-ancestor',commit,b['baseline_commit']],cwd=ROOT,check=True)
    # The old broad inventory is immutable historical evidence, not the DSP
    # dependency graph: it included independent CF development files while
    # omitting imported DSP build dependencies. Audit historical deltas and
    # freeze the executed dependency closure separately.
    independent_deltas = {}
    for rel,want in b['source_inventory'].items():
        p = ROOT/rel
        if not p.is_file() or sha(p) != want:
            old = subprocess.check_output(['git','show',f'{b["baseline_commit"]}:{rel}'],cwd=ROOT)
            assert hashlib.sha256(old).hexdigest() == want, f'historical inventory drift: {rel}'
            independent_deltas[rel] = {'historical':want,'current':sha(p) if p.is_file() else None}
    frozen = json.loads((ROOT/'modules/perky/hybrid/DSP_DEPENDENCIES.json').read_text())
    assert frozen['baseline_commit'] == b['baseline_commit']
    for rel,row in frozen['sources'].items():
        if not (ROOT/rel).is_file() or sha(ROOT/rel) != row['sha256']:
            errors.append(f'frozen DSP dependency drift: {rel}')
        obj = row['historical_object']
        data = subprocess.check_output(['git','-C',str(ROOT/obj['repository']),
                                        'show',f'{obj["commit"]}:{obj["path"]}'])
        assert hashlib.sha256(data).hexdigest() == row['sha256'], f'baseline object mismatch: {rel}'
    for v in b['inputs']+b['packaging_inputs']+b['perkybits']['native_sources']:
        verify(v)
    for v in b['toolchain'].values():
        verify(v)
    verify(b['release_receipt'])
    r = json.loads(Path(b['release_receipt']['path']).read_text())
    assert r['source_commit'] == b['baseline_commit'], 'receipt baseline mismatch'
    for v in r['artifacts'].values():
        verify(v)
    # Canonical generated report paths are mutable across qualifications.
    # Preserve the original receipt's exact bytes/hashes in a separate archive.
    # These reports are reconstructible from that receipt's embedded results;
    # the reference hashes themselves are never changed.
    archive = json.loads((ROOT/'modules/perky/hybrid/BASELINE_REPORT_ARCHIVE.json').read_text())['reports']
    assert set(archive) == {v['artifact']['path'] for v in r['component_reports'].values()}
    for v in r['component_reports'].values():
        saved = archive[v['artifact']['path']]
        assert (saved['sha256'],saved['bytes']) == (v['artifact']['sha256'],v['artifact']['bytes'])
        verify(saved)
        assert json.loads(Path(saved['path']).read_text()) == v['results'], 'component evidence mismatch'
    for c in r['commands']:
        assert c['returncode'] == 0 and not (c['targeted'] and c['skip_lines']), 'release qualification missing/failed'
        if not Path(c['log']).is_file() or sha(c['log']) != c['sha256']:
            errors.append(f'release command log drift: {c["log"]}')
    project = Path(b['project']['root'])
    inventory = {str(p.relative_to(project)):sha(p) for p in sorted(project.rglob('*')) if p.is_file()}
    assert inventory == b['project']['files'], 'read-only project changed'
    for v in b['frozen_uploads'].values():
        verify(v['readback'])
    verify(b['local_reproduction']['artifact'])
    assert b['local_reproduction']['artifact']['sha256'] == b['main_sha256'] == 'be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0'
    verify(b['memory_ledger_file'])
    ledger = json.loads(Path(b['memory_ledger_file']['path']).read_text())
    assert ledger == b['memory_ledger'], 'ledger differs'
    for c in ledger['cores'].values():
        assert (c['private_p']['words'],c['private_p']['capacity']) == (770,774)
    # Parse the ACTUAL boot readbacks again, preserving order and all records.
    sys.path[:0] = [str(ROOT/'tools/verify'),str(ROOT/'tools/build'),str(ROOT/'tools')]
    from verify_perky_table_image import parse_upload
    for tag,v in b['frozen_uploads'].items():
        records = []
        for i,(sp,addr,words) in enumerate(parse_upload(Path(v['readback']['path']).read_bytes())):
            raw = b''.join(x.to_bytes(3,'little') for x in words)
            records.append({'ordinal':i,'space':'PXY'[sp],'destination_word':addr,'words':len(words),
                            'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        assert records == v['ordered_records'], f'{tag} ordered upload drift'
    if errors:
        raise AssertionError(json.dumps({'count':len(errors),'bounded_errors':errors[:20]}))
    return {'historical_sources':len(b['source_inventory']),'frozen_dsp_sources':len(frozen['sources']),
            'independent_source_deltas':independent_deltas,'inputs':len(b['inputs']),
            'historical_commands':len(r['commands']),'main_sha256':b['main_sha256']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['baseline'],required=True)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid')
    ap.add_argument('--baseline-build',type=Path,default=ROOT/'out/perky/hybrid/resume/baseline/build',
                    help='completed build_four_machine.py --qualify-only work directory')
    args = ap.parse_args()
    work = args.work.resolve()
    # Results may never enter a tracked source/input tree.
    assert work.is_relative_to(ROOT/'out'), '--work must be under ignored out/'
    work.mkdir(parents=True,exist_ok=True)
    result = {'schema':'octabam.perky.hybrid.phase1.v1','stage':args.stage,'status':'BLOCKED',
              'hardware_feasibility':'UNVERIFIED','source_commit':git('rev-parse','HEAD'),
              'commands':[],'unresolved_requirements':[]}
    try:
        b = json.loads(BASELINE.read_text())
        assert b['schema'] == 'octabam.perky.hybrid.baseline.v1', 'baseline schema'
        result['baseline_manifest'] = item(BASELINE)
        result['dependency_manifest'] = item(ROOT/'modules/perky/hybrid/DSP_DEPENDENCIES.json')
        result['report_archive_manifest'] = item(ROOT/'modules/perky/hybrid/BASELINE_REPORT_ARCHIVE.json')
        result['frozen_validation'] = {'status':'PASS',**validate_frozen(b)}
    except (AssertionError,OSError,KeyError,ValueError,subprocess.CalledProcessError) as exc:
        result['frozen_validation'] = {'status':'FAIL','error':str(exc)}
        (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(f'BLOCKED: frozen evidence invalid: {exc}',flush=True)
        return 1
    env = os.environ.copy()
    env.update(b['environment'])
    # Legacy gates disagree on whether SOURCE means checkout or Source/.
    # Their repository-local defaults resolve both correctly; ROOT is explicit.
    env.pop('PERKYBITS_SOURCE',None)
    execution_environment={k:env[k] for k in b['environment'] if k in env}
    py = str(ROOT/'.venv/bin/python3')
    fw, pb = env['PERKONS_FIRMWARE'],env['PERKYBITS_ROOT']
    # Preserve the initial blocked-run evidence in its existing directories.
    runwork = work/'qualification'
    def gate(name,*extra):
        return [py,str(ROOT/'tools/verify'/name),*map(str,extra)]
    plans = [
        ('baseline','ctest',['ctest','--test-dir',str(ROOT/'out/emu'),'--output-on-failure']),
        ('baseline','release-guards',gate('verify_perky_release_guards_selftest.py')),
        ('baseline','prefetch-guard',gate('verify_perky_prefetch_guard.py','--build',Path(b['memory_ledger_file']['path']).parent)),
        ('baseline','dsp-dependencies',gate('verify_perky_hybrid_dsp_dependencies.py','--work',runwork/'dsp-dependencies')),
        ('baseline','completed-qualification',gate('verify_perky_hybrid_baseline_qualification.py','--build',args.baseline_build,'--report',runwork/'baseline-qualification.json')),
        ('cf-contract','legacy',gate('verify_perky_cf_final.py','--requalify','--firmware',fw,'--perkybits',pb,'--work',runwork/'legacy')),
        ('cf-contract','wavetable',gate('verify_perky_cf_wavetable_dsp.py','--firmware',fw,'--work',runwork/'wavetable')),
        ('cf-contract','resonant',gate('verify_perky_cf_resonant_dsp.py','--firmware',fw,'--work',runwork/'resonant')),
        ('cf-contract','noise-tone',gate('verify_perky_cf_noise_tone.py','--firmware',fw,'--source',pb)),
        ('cf-contract','noise-tone-controls',gate('verify_perky_hybrid_noise_evidence.py','--firmware',fw,'--source',pb,'--work',runwork/'noise-tone-controls')),
        ('cf-contract','freestanding',gate('verify_perky_cf_freestanding.py')),
        ('cf-contract','hotloops',gate('verify_perky_cf_hotloops.py')),
        ('cf-contract','stock-record',gate('verify_perky_cf_stock_record_abi.py')),
        ('cf-contract','runtime-memory',gate('verify_perky_cf_runtime_memory_final.py')),
        ('cf-contract','wt-profiles',gate('verify_perky_hybrid_wt_profiles.py','--firmware',fw,'--work',runwork/'wt-profiles')),
        ('cf-contract','original-profiles',gate('verify_perky_hybrid_original_profiles.py','--firmware',fw,'--perkybits',pb,
                                             '--unicorn-build',Path(pb)/'build-local/_deps/unicorn-build','--work',runwork/'original-profiles')),
        ('feasibility','target',gate('verify_perky_hybrid_target.py','--firmware',fw,'--work',runwork/'target')),
        ('feasibility','packaging',gate('verify_perky_hybrid_packaging.py','--firmware',fw,
                                      '--target-report',runwork/'target/report.json','--work',runwork/'packaging')),
    ]
    # Bind every gate to one source tree, including imported helpers and harness
    # dependencies. A change between gates invalidates earlier correctness proof.
    source_paths=[p for parent in ('modules/perky','tools','remixes/test/perky-cf-final')
                  for p in (ROOT/parent).rglob('*') if p.is_file() and p.suffix in ('.c','.h','.hpp','.cpp','.py','.s','.S','.ld')]
    qualification_sources={str(p.relative_to(ROOT)):sha(p) for p in source_paths}
    result['qualification_source_hashes']=qualification_sources
    for category,name,argv in plans:
        log = runwork/category/f'{name}-gate.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        sources = {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'modules/perky').glob('*') if p.is_file()}
        for arg in argv:
            p = Path(arg)
            if p.is_file() and p.is_relative_to(ROOT) and p.suffix in ('.py','.c','.cpp'):
                sources[str(p.relative_to(ROOT))] = sha(p)
        tool = shutil.which(argv[0])
        with log.open('w') as out:
            try:
                rc = subprocess.run(argv,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=1800).returncode
            except (OSError,subprocess.TimeoutExpired) as exc:
                out.write(str(exc)+'\n')
                rc = 124 if isinstance(exc,subprocess.TimeoutExpired) else 127
        text = log.read_text()
        skipped = bool(re.search(r'\[SKIP\]|:\s*SKIP\b|^SKIP\b',text,re.M))
        drift = [p for p,h in sources.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
        record = {'name':name,'argv':argv,'environment':execution_environment,'exit_status':rc,
                  'status':'PASS' if rc==0 and not skipped and not drift else 'FAIL','skipped_required_test':skipped,
                  'source_drift_during_execution':drift,
                  'log':item(log),'tool':item(tool) if tool else None,'source_hashes':sources}
        result['commands'].append(record)
        (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(f'{record["status"]}: {name} (exit {rc}); {log}',flush=True)
    # Unimplemented/failed requirements are a hard refusal, never a green banner.
    result['failed_commands'] = [c['name'] for c in result['commands'] if c['status']!='PASS']
    result['unresolved_requirements'] = [f'required executable check failed: {name}' for name in result['failed_commands']]
    # Revalidate after execution as well: no gate may mutate frozen inputs.
    try:
        validate_frozen(b)
    except (AssertionError,OSError,KeyError,ValueError,subprocess.CalledProcessError) as exc:
        result['unresolved_requirements'].append(f'frozen evidence changed during execution: {exc}')
    final_drift=[p for p,h in qualification_sources.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    result['source_drift_across_qualification']=final_drift
    if final_drift:
        result['unresolved_requirements'].append('source changed across qualification: '+', '.join(final_drift))
    # Recheck external native references, emulator libraries and child inputs
    # after every gate, not just at the time that child finished. This binds
    # correctness and feasibility evidence to the same complete input epoch.
    receipts=[('legacy/qualification.json',('current_sources',)),
              ('noise-tone-controls/capture-manifest.json',('input_hashes',)),
              ('original-profiles/receipt.json',('inputs',)),
              ('target/report.json',('source_sha256','linked_library_sha256')),
              ('packaging/report.json',('source_sha256','inputs'))]
    evidence_drift=[];checked_inputs=0
    for relative,fields in receipts:
        path=runwork/relative
        try:
            evidence=json.loads(path.read_text())
            for field in fields:
                for name,value in evidence[field].items():
                    expected=value['sha256'] if isinstance(value,dict) else value
                    source=Path(name);source=source if source.is_absolute() else ROOT/source
                    checked_inputs+=1
                    if not source.is_file() or sha(source)!=expected:evidence_drift.append(str(source))
        except (OSError,ValueError,KeyError) as exc:
            evidence_drift.append(f'{path}: {exc}')
    result['child_evidence_revalidation']={'input_checks':checked_inputs,'drift':sorted(set(evidence_drift))}
    if evidence_drift:
        result['unresolved_requirements'].append('child evidence inputs changed or unavailable: '+', '.join(sorted(set(evidence_drift))))
    if not result['unresolved_requirements']:
        result['status'] = 'PASS_FOR_PROBE_BUILD'
    result['limits'] = ['No hybrid firmware built.', 'Hardware feasibility UNVERIFIED.',
                        'Target costs are isolated model observations, not full-machine timing bounds.',
                        'Packaging is a measured component budget with explicit integration allowances; the later hybrid container must be checked.']
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'{result["status"]}; hardware feasibility UNVERIFIED; {work/"results.json"}')
    return 0 if result['status']=='PASS_FOR_PROBE_BUILD' else 1


if __name__ == '__main__':
    raise SystemExit(main())
