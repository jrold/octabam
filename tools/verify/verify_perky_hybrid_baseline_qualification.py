#!/usr/bin/env python3
"""Validate the completed local PERKY4S qualification without packaging firmware.

The builder's checkpoint is accepted only with unchanged frozen dependencies,
all 50 command logs, the original image hash, and the untouched input project.
Missing or failed qualification is a failure, never an implicit skip.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'status':'RUNNING'})+'\n')
    build = args.build.resolve()
    baseline = json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())
    frozen = json.loads((ROOT/'modules/perky/hybrid/DSP_DEPENDENCIES.json').read_text())
    for name, row in frozen['sources'].items():
        assert sha(ROOT/name) == row['sha256'], f'frozen dependency drift: {name}'
    checkpoint = build/'qualification-checkpoint.json'
    q = json.loads(checkpoint.read_text())
    assert q['version'] == 'PERKY4S'
    assert q['image_sha256'] == baseline['main_sha256'] == sha(build/'fragmented-mainos.bin')
    assert sha(build/'source-manifest.json') == q['source_manifest_sha256']
    assert len(q['commands']) == 50, 'incomplete qualification'
    assert sum(bool(c['targeted']) for c in q['commands']) == 49
    for c in q['commands']:
        log = Path(c['log'])
        assert c['returncode'] == 0 and sha(log) == c['sha256'], f'failed or changed qualification: {log}'
        contents = log.read_text()
        assert not re.search(r'^\s*\[FAIL\]', contents, re.M), f'failure in {log}'
        if c['targeted']:
            assert not re.search(r'\[SKIP\]|:\s*SKIP\b|^SKIP\b', contents, re.M), f'required skip in {log}'
    # The old odd-access gate silently accepts missing generated assembly.
    # Require the actual production control assembly audited by this run.
    asm = list((build/'odd-audit').glob('*.s'))
    assert asm and all(p.stat().st_size > 0 for p in asm), 'missing generated CF assembly'
    project = Path(baseline['project']['root'])
    current = {str(p.relative_to(project)):sha(p) for p in sorted(project.rglob('*')) if p.is_file()}
    assert current == baseline['project']['files'], 'original project modified'
    # The builder stores the same inventory with size as well as hash.
    before = q['project_input']
    for name, row in before.items():
        expected = row['sha256'] if isinstance(row, dict) else row
        assert current[name] == expected, f'qualification project drift: {name}'
    report = {'status':'PASS_COMPLETED_PERKY4S_QUALIFICATION', 'cached':True,
              'checkpoint':{'path':str(checkpoint),'sha256':sha(checkpoint)},
              'commands':q['commands'], 'main_sha256':q['image_sha256'],
              'frozen_source_count':len(frozen['sources']), 'targeted_commands':49,
              'qualification_commands':50, 'project_files':len(current),
              'scope':'original PERKY4S only; no hybrid firmware or flash wrappers built'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('PERKY4S fresh local qualification: PASS (50 completed commands; validated cached evidence; original MAIN hash)')

if __name__ == '__main__':
    main()
