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


def probe_evidence_errors(probe_dir: Path) -> list[str]:
    """Refuse qualification based on report existence or a partial smoke run.

    These checks supplement executable gates; they cannot manufacture missing
    lifecycle, hardware-profiler, or sustained workload evidence.
    """
    errors = []
    reports = {}
    for name in ('BUILD', 'TIMING', 'PROBE_GATES'):
        try:
            reports[name] = json.loads((probe_dir / f'{name}.json').read_text())
        except (OSError, ValueError) as exc:
            errors.append(f'{name}: missing or invalid evidence: {exc}')
            reports[name] = {}
    build, timing, gates = (reports[n] for n in ('BUILD', 'TIMING', 'PROBE_GATES'))
    for rel, expected in build.get('sources', {}).items():
        path = ROOT / rel
        if not path.is_file() or sha(path) != expected:
            errors.append(f'probe source drift: {rel}')
        try:
            recorded = subprocess.check_output(
                ['git', 'show', f'{build["git_commit"]}:{rel}'], cwd=ROOT,
                stderr=subprocess.DEVNULL)
            if hashlib.sha256(recorded).hexdigest() != expected:
                errors.append(f'probe source differs from recorded commit: {rel}')
        except (KeyError, subprocess.CalledProcessError):
            errors.append(f'probe source absent from recorded commit: {rel}')
    if not build.get('sources'):
        errors.append('probe build lacks source hashes')
    for label, meta in build.get('artifacts', {}).items():
        try:
            path = Path(meta['path'])
            if not path.is_file() or path.stat().st_size != meta['bytes'] or sha(path) != meta['sha256']:
                errors.append(f'probe artifact drift: {label}')
        except (KeyError, TypeError):
            errors.append(f'invalid probe artifact metadata: {label}')
    for name in ('TIMING', 'PROBE_GATES'):
        evidence = reports[name].get('evidence', {})
        for label in ('mainos', 'runtime_elf'):
            expected = build.get('artifacts', {}).get(label, {}).get('sha256')
            if not expected or evidence.get(label + '_sha256') != expected:
                errors.append(f'{name} is not bound to the actual hybrid {label}')
        emu = ROOT / 'out/emu/ot_emu'
        if not emu.is_file() or evidence.get('emulator_sha256') != sha(emu):
            errors.append(f'{name} emulator identity missing or stale')
    if timing.get('status') != 'LOCAL_MODEL_WITHIN_BUDGET_HARDWARE_PENDING':
        errors.append('required sustained timing qualification is incomplete or requires review')
    summary = timing.get('summary', {})
    if summary.get('global_deadline_misses') != 0 or summary.get('global_within_80pct_margin') is not True:
        errors.append('full-frame timing has not passed the deadline and 80% margin gates')
    # The old callback-sum profiler is not a full-frame hardware measurement.
    if timing.get('hardware_profiler_qualification', {}).get('status') != 'PASS':
        errors.append('hardware full-frame profiler frequency/wrap/overhead/export path unqualified')
    if timing.get('clocks', {}).get('dtim3_bus_hz') != 132_000_000:
        errors.append('DTIM3 frequency must agree with the qualified 132 MHz stock timer')
    mandatory = {('V1', 'V1'), ('V1', 'V2'), ('V2', 'snare'), ('V1', 'bass'),
                 ('snare', 'snare'), ('bass', 'snare'), ('third', 'third')}
    extra = {('V2', 'V2'), ('V2', 'V1'), ('snare', 'V2'), ('bass', 'V1'), ('snare', 'bass')}
    for key, expected in (('mandatory_rows_60s', mandatory), ('extra_rows_60s', extra)):
        rows = timing.get(key, [])
        if not isinstance(rows, list):
            errors.append(f'invalid workload rows: {key}')
            continue
        qualified = set()
        for row in rows:
            if row.get('frames', 0) < 165375:
                errors.append(f'workload row shorter than 60 simulated seconds: {row.get("row")}')
                continue
            audio = row.get('audio_verification') or {}
            if any(audio.get(f'T{t}', {}).get('chain_significant', 0) <= 64 for t in range(1, 9)):
                errors.append(f'workload lacks all-eight-track active audio proof: {row.get("row")}')
            qualified.add((row.get('t2'), row.get('t6')))
        if not expected <= qualified:
            errors.append(f'missing sustained workload combinations: {key}')
    if timing.get('worst_row_10min', {}).get('frames', 0) < 1653750:
        errors.append('worst-row ten-minute workload incomplete')
    if not timing.get('profiler_and_arm_comparisons'):
        errors.append('profiler-on/off and CF armed/disarmed comparisons missing')
    if gates.get('dsp_readback_and_12_fx', {}).get('status') != 'PASS':
        errors.append('both-core DSP readback and retained FX gate missing or skipped')
    if gates.get('lifecycle_and_reference', {}).get('status') != 'PASS':
        errors.append('hybrid cold-start/Bank/Part generation and original-reference gate unqualified')
    return errors


def run_probe_stage(work: Path, b: dict, frozen_val: dict) -> int:
    probe_dir = work / 'probe'
    result = {
        'schema': 'octabam.perky.hybrid.phase2.v1',
        'stage': 'probe',
        'status': 'BLOCKED',
        'hardware_feasibility': 'UNVERIFIED',
        'source_commit': git('rev-parse', 'HEAD'),
        'frozen_validation': {'status': 'PASS', **frozen_val},
        'commands': [],
        'unresolved_requirements': [],
    }
    py = str(ROOT / '.venv/bin/python3')
    env = os.environ.copy()
    env.update(b['environment'])
    env.pop('PERKYBITS_SOURCE', None)
    execution_environment = {k: env[k] for k in b['environment'] if k in env}

    mainos = probe_dir / 'mainos_PKHYB2P.bin'
    elek = probe_dir / 'elek_PKHYB2P.bin'
    card = probe_dir / 'OCTATRACK_PKHYB2P.bin'
    midi = probe_dir / 'OCTATRACK_OS1.40C_PKHYB2P.syx'

    def gate(name, *extra):
        return [py, str(ROOT / 'tools/verify' / name), *map(str, extra)]

    plans = [
        ('probe', 'ctest', ['ctest', '--test-dir', str(ROOT / 'out/emu'), '--output-on-failure']),
        ('probe', 'machine-boot', gate(
            'verify_perky_machine_boot.py',
            '--image', mainos,
            '--packed', probe_dir,
            '--platform-work', probe_dir / 'platform-loader',
            '--platform', probe_dir / 'platform',
            '--normal-image', probe_dir / 'fragmented-normal.bin',
            '--p-records', probe_dir / 'p-records.json',
        )),
        ('probe', 'prefetch-guard', gate('verify_perky_prefetch_guard.py', '--build', probe_dir)),
        ('probe', 'odd-access', gate('verify_perky_cf_odd_access.py', '--generated', probe_dir / 'odd-audit')),
        ('probe', 'startup-diff', gate('verify_perky_four_startup.py', '--build', probe_dir)),
        ('probe', 'dsp-memory', gate('verify_perky_three_memory.py', '--build', probe_dir)),
        ('probe', 'wrappers', gate(
            'verify_perky_final_wrappers.py',
            '--mainos', mainos,
            '--elek', elek,
            '--card', card,
            '--midi', midi,
            '--eft', env['PERKY_EFT'],
            '--version', 'PKHYB2P',
            '--work', probe_dir / 'wrapper-verify',
        )),
        ('probe', 'hybrid-gates', gate('verify_perky_hybrid_probe_gates.py', '--work', work)),
    ]

    log_dir = probe_dir / 'verify-logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    for _cat, name, argv in plans:
        log = log_dir / f'{name}.log'
        with log.open('w') as out:
            rc = subprocess.run(argv, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=900).returncode
        text = log.read_text(errors='replace')
        skipped = bool(re.search(r'\[SKIP\]|:\s*SKIP\b|^SKIP\b', text, re.M))
        status = 'PASS' if rc == 0 and not skipped else 'FAIL'
        result['commands'].append({
            'name': name,
            'argv': argv,
            'environment': execution_environment,
            'exit_status': rc,
            'status': status,
            'log': item(log),
        })
        print(f'{status}: {name} (exit {rc}); {log}', flush=True)

    # Validate required generated hybrid artifacts and JSON reports (must NOT be historical PERKY4S or CF-only images)
    required_files = ('BUILD.json', 'MEMORY.json', 'DSP_IDENTITY.json', 'TIMING.json')
    artifacts = {}
    for fname in required_files:
        fpath = probe_dir / fname
        if not fpath.is_file():
            result['unresolved_requirements'].append(f'missing probe report: {fpath}')
        else:
            artifacts[fname] = item(fpath)

    for label, fpath in (('mainos', mainos), ('elek', elek), ('card', card), ('midi', midi)):
        if not fpath.is_file():
            result['unresolved_requirements'].append(f'missing probe binary: {fpath}')
        else:
            artifacts[label] = item(fpath)

    if mainos.is_file():
        m_sha = sha(mainos)
        if m_sha == b['main_sha256']:
            result['unresolved_requirements'].append('probe mainos matches historical PERKY4S image (not hybrid)')

    if (probe_dir / 'DSP_IDENTITY.json').is_file():
        dsp_id = json.loads((probe_dir / 'DSP_IDENTITY.json').read_text())
        if dsp_id.get('status') != 'PASS':
            result['unresolved_requirements'].append('DSP_IDENTITY.json status is not PASS')
        if dsp_id.get('frozen_perky4s_main_sha256') != b['main_sha256']:
            result['unresolved_requirements'].append('DSP_IDENTITY.json baseline MAIN hash mismatch')

    if (probe_dir / 'MEMORY.json').is_file():
        mem_rep = json.loads((probe_dir / 'MEMORY.json').read_text())
        if mem_rep.get('status') != 'PASS':
            result['unresolved_requirements'].append('MEMORY.json status is not PASS')
        if mem_rep.get('coldfire_dram', {}).get('decoded_waveform_bss_bytes') != 200704:
            result['unresolved_requirements'].append('MEMORY.json decoded_waveform_bss_bytes != 200704')
        if mem_rep.get('coldfire_dram', {}).get('physical_overlaps'):
            result['unresolved_requirements'].append('MEMORY.json physical DRAM overlaps detected')

    result['artifacts'] = artifacts
    result['unresolved_requirements'].extend(probe_evidence_errors(probe_dir))
    result['failed_commands'] = [c['name'] for c in result['commands'] if c['status'] != 'PASS']
    for name in result['failed_commands']:
        result['unresolved_requirements'].append(f'required probe check failed: {name}')

    if not result['unresolved_requirements']:
        result['status'] = 'LOCAL_PROBE_QUALIFIED_HARDWARE_PENDING'
    (probe_dir / 'VERIFY_PROBE.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'{result["status"]}; hardware feasibility UNVERIFIED; {probe_dir / "VERIFY_PROBE.json"}', flush=True)
    return 0 if result['status'] == 'LOCAL_PROBE_QUALIFIED_HARDWARE_PENDING' else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['baseline','probe'],required=True)
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
        frozen_val = validate_frozen(b)
        result['frozen_validation'] = {'status':'PASS',**frozen_val}
    except (AssertionError,OSError,KeyError,ValueError,subprocess.CalledProcessError) as exc:
        result['frozen_validation'] = {'status':'FAIL','error':str(exc)}
        (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(f'BLOCKED: frozen evidence invalid: {exc}',flush=True)
        return 1
    if args.stage == 'probe':
        return run_probe_stage(work, b, frozen_val)
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
