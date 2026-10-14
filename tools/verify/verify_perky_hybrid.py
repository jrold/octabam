#!/usr/bin/env python3
"""Fail-closed baseline/CF foundation evidence gate; emits a bounded JSON report.

No production hybrid is built. Known failed original-reference checks are run
without repinning, bypassing or normalizing them. A BLOCKED result is exit 1.
The remaining acceptance requirements are explicit; they cannot be satisfied by
editing a report's status string. Extend executable checks before enabling PASS.
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

# Deliberately required, not "skipped" or priced from the old four-voice run.
UNRESOLVED = (
    'Complete original V1/V2 initialization, control-cadence and boundary differential proof',
    'Exact Resonant snare/bass/third-mode PCM/state/RNG success',
    'Simultaneous two-instance differential coverage, releases, long tails and family changes',
    'Audited actual DSP source dependency closure (qualified inventory is conservative)',
    'Corrected-model target-code costs for all required/reversed profile-mode pairings',
    'Actual proposed linked two-instance allocation, stack and deterministic readiness proof',
    'Separate ELUP container/header accounting and validated card payload limit',
    'Completed fresh production qualification (the initial attempt was interrupted on CF failures)',
)


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
    for rel,want in b['source_inventory'].items():
        p = ROOT/rel
        if not p.is_file() or sha(p) != want:
            errors.append(f'frozen source drift: {rel}')
    for v in b['inputs']+b['packaging_inputs']+b['perkybits']['native_sources']:
        verify(v)
    for v in b['toolchain'].values():
        verify(v)
    verify(b['release_receipt'])
    r = json.loads(Path(b['release_receipt']['path']).read_text())
    assert r['source_commit'] == b['baseline_commit'], 'receipt baseline mismatch'
    for v in r['artifacts'].values():
        verify(v)
    for v in r['component_reports'].values():
        verify(v['artifact'])
        assert json.loads(Path(v['artifact']['path']).read_text()) == v['results'], 'component evidence mismatch'
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
    return {'sources':len(b['source_inventory']),'inputs':len(b['inputs']),
            'historical_commands':len(r['commands']),'main_sha256':b['main_sha256']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['baseline'],required=True)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid')
    args = ap.parse_args()
    work = args.work.resolve()
    # Results may never enter a tracked source/input tree.
    assert work.is_relative_to(ROOT/'out'), '--work must be under ignored out/'
    work.mkdir(parents=True,exist_ok=True)
    result = {'schema':'octabam.perky.hybrid.phase1.v1','stage':args.stage,'status':'BLOCKED',
              'hardware_feasibility':'UNVERIFIED','source_commit':git('rev-parse','HEAD'),
              'commands':[],'unresolved_requirements':list(UNRESOLVED)}
    try:
        b = json.loads(BASELINE.read_text())
        assert b['schema'] == 'octabam.perky.hybrid.baseline.v1', 'baseline schema'
        result['baseline_manifest'] = item(BASELINE)
        result['frozen_validation'] = {'status':'PASS',**validate_frozen(b)}
    except (AssertionError,OSError,KeyError,ValueError,subprocess.CalledProcessError) as exc:
        result['frozen_validation'] = {'status':'FAIL','error':str(exc)}
        (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(f'BLOCKED: frozen evidence invalid: {exc}',flush=True)
        return 1
    env = os.environ.copy()
    env.update(b['environment'])
    py = str(ROOT/'.venv/bin/python3')
    fw, pb = env['PERKONS_FIRMWARE'],env['PERKYBITS_ROOT']
    def gate(name,*extra):
        return [py,str(ROOT/'tools/verify'/name),*map(str,extra)]
    plans = [
        ('baseline','ctest',['ctest','--test-dir',str(ROOT/'out/emu'),'--output-on-failure']),
        ('baseline','release-guards',gate('verify_perky_release_guards_selftest.py')),
        ('baseline','prefetch-guard',gate('verify_perky_prefetch_guard.py','--build',Path(b['memory_ledger_file']['path']).parent)),
        ('cf-contract','legacy',gate('verify_perky_cf_final.py','--firmware',fw,'--perkybits',pb,'--work',work/'cf-contract/legacy')),
        ('cf-contract','wavetable',gate('verify_perky_cf_wavetable_dsp.py','--firmware',fw,'--work',work/'cf-contract/wavetable')),
        ('cf-contract','resonant',gate('verify_perky_cf_resonant_dsp.py','--firmware',fw,'--work',work/'cf-contract/resonant')),
        ('cf-contract','noise-tone',gate('verify_perky_cf_noise_tone.py','--firmware',fw,'--source',pb)),
        ('cf-contract','noise-tone-controls',gate('verify_perky_noise_tone_control_evidence.py')),
        ('cf-contract','freestanding',gate('verify_perky_cf_freestanding.py')),
        ('cf-contract','hotloops',gate('verify_perky_cf_hotloops.py')),
        ('cf-contract','stock-record',gate('verify_perky_cf_stock_record_abi.py')),
        ('cf-contract','runtime-memory',gate('verify_perky_cf_runtime_memory_final.py')),
        ('cf-contract','wt-profiles',gate('verify_perky_hybrid_wt_profiles.py','--firmware',fw,'--work',work/'cf-contract/wt-profiles')),
    ]
    for category,name,argv in plans:
        log = work/category/f'{name}-gate.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        sources = {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'modules/perky').glob('*') if p.is_file()}
        for arg in argv:
            p = Path(arg)
            if p.is_file() and p.is_relative_to(ROOT) and p.suffix in ('.py','.c','.cpp'):
                sources[str(p.relative_to(ROOT))] = sha(p)
        tool = shutil.which(argv[0])
        with log.open('w') as out:
            try:
                rc = subprocess.run(argv,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=300).returncode
            except (OSError,subprocess.TimeoutExpired) as exc:
                out.write(str(exc)+'\n')
                rc = 124 if isinstance(exc,subprocess.TimeoutExpired) else 127
        text = log.read_text()
        skipped = bool(re.search(r'\[SKIP\]|:\s*SKIP\b',text))
        record = {'name':name,'argv':argv,'environment':b['environment'],'exit_status':rc,
                  'status':'PASS' if rc==0 and not skipped else 'FAIL','skipped_required_test':skipped,
                  'log':item(log),'tool':item(tool) if tool else None,'source_hashes':sources}
        result['commands'].append(record)
        (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(f'{record["status"]}: {name} (exit {rc}); {log}',flush=True)
    # Unimplemented/failed requirements are a hard refusal, never a green banner.
    result['failed_commands'] = [c['name'] for c in result['commands'] if c['status']!='PASS']
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'BLOCKED; hardware feasibility UNVERIFIED; {work/"results.json"}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
