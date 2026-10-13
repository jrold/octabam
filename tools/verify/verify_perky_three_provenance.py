#!/usr/bin/env python3
"""Verify a PERKY3R release report against committed sources and local artifacts.

This gate checks provenance, not physical hardware qualification. Firmware and
reference assets stay outside Git; the report records their full hashes.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    commit = report['source_commit']
    subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'], cwd=ROOT, check=True)
    assert report['version'] == 'PERKY3R'
    assert report['hardware_qualified'] is False
    assert report['algorithms'] == ['Fold Drum 1', 'Fold Drum 2', 'Simple Drum']
    assert report['controls'] == ['TUNE', 'DECAY', 'ALGO', 'PAR1', 'PAR2', 'MODE']
    assert report['voices'] == ['T1', 'T5']
    artifacts = report['artifacts']
    for name in ('mainos', 'elek', 'card', 'midi', 'source_manifest', 'memory_ledger'):
        item = artifacts[name]
        assert digest(item['path']) == item['sha256'], name
        assert Path(item['path']).stat().st_size == item['bytes'], name
    sources = json.loads(Path(artifacts['source_manifest']['path']).read_text())
    for relative, expected in sources.items():
        assert digest(ROOT / relative) == expected, relative + ': working source drift'
        blob = subprocess.check_output(['git', 'show', commit + ':' + relative], cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest() == expected, relative + ': commit drift'
    for item in report['inputs'] + report['logs']:
        assert digest(item['path']) == item['sha256'], item['path']
    final = json.loads(Path(report['final_image_commands']).read_text())
    assert len(final) == 8
    for item in final:
        assert item['returncode'] == 0, item['command']
        assert item['image_sha256'] == artifacts['mainos']['sha256']
        assert digest(item['log']) == item['sha256']
    assert report['committed_rebuild_sha256'] == artifacts['mainos']['sha256']
    counts = report['qualification']
    assert counts['repository_assertions'] == {'pass': 349, 'fail': 0, 'skip': 2}
    assert counts['repository_gate_commands'] == {'pass': 88, 'fail': 0}
    assert counts['refhash_configurations'] == {'pass': 24, 'fail': 0}
    assert counts['targeted_commands'] == {'pass': 22, 'fail': 0, 'skip': 0}
    print(f'[PASS] PERKY3R provenance: {len(sources)} committed sources, '
          f'{len(report["inputs"])} inputs, {len(report["logs"])} logs, '
          'six artifacts; final-image commands and committed rebuild agree')


if __name__ == '__main__':
    main()
