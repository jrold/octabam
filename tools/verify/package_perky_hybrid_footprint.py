#!/usr/bin/env python3
"""Copy locally qualified PERKY upgrade wrappers into a new external bundle.

Never flashes hardware or overwrites a prior bundle. The final aggregation
receipt and its pinned inputs must pass before a destination is created.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'modules/perky/hybrid'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(qualification, destination):
    assert not destination.exists(), 'bundle already exists'
    assert not destination.is_relative_to(ROOT), 'firmware bundle must stay outside repository'
    report = json.loads(qualification.read_text())
    assert report['status'] == 'LOCALLY_QUALIFIED_DIAGNOSTIC_AND_PERFORMANCE; PHYSICAL_MKII_ACCEPTANCE_PENDING'
    assert not report['physical_acceptance'] and not report['hardware_flashed']
    assert report['aggregator_sha256'] == sha(Path(__file__).with_name('qualify_perky_hybrid_footprint.py'))
    for path, digest in report['receipts'].items():
        assert sha(path) == digest, 'qualification receipt changed: ' + path
    for path, digest in report['complete_module_source_hashes'].items():
        assert sha(path) == digest, 'qualified module source changed: ' + path
    for build in report['configurations'].values():
        for artifact in build['artifacts'].values():
            assert sha(artifact['path']) == artifact['sha256'], 'artifact changed'
    baseline_path = ROOT/'out/perky/hybrid/campaign-20261016/final/probe/BUILD.json'
    baseline = json.loads(baseline_path.read_text())
    assert baseline['version'] == 'PKH4O2'
    for key in ('mainos','card','midi'):
        artifact = baseline['artifacts'][key]
        assert sha(artifact['path']) == artifact['sha256'], 'baseline reference changed'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.perky-package-', dir=destination.parent))
    try:
        for kind, build in report['configurations'].items():
            directory = temporary / build['version']
            directory.mkdir()
            for key in ('card','midi','dsp_identity_report','memory_report'):
                source = Path(build['artifacts'][key]['path'])
                shutil.copyfile(source, directory / source.name)
            probe = Path(build['artifacts']['mainos']['path']).parent
            for name in ('BUILD.json','CONFIGURATION.json','VOICE_LAYOUT.json'):
                shutil.copyfile(probe/name, directory/name)
        shutil.copyfile(qualification, temporary/'QUALIFICATION.json')
        (temporary/'PKH4O2_REFERENCE.json').write_text(json.dumps(dict(
            status='PRESERVED_EXISTING_REFERENCE; KNOWN_PHYSICAL_OVERLOAD',
            build_receipt=str(baseline_path), build_sha256=sha(baseline_path),
            artifacts={key:baseline['artifacts'][key] for key in ('mainos','card','midi')},
            firmware_copied_into_this_bundle=False),indent=2)+'\n')
        for name in ('CF_FOOTPRINT_20261016.txt','CF_FOOTPRINT_20261016.json',
                     'CF_FOOTPRINT_20261016_RESOURCES.json',
                     'CF_FOOTPRINT_20261016_FEASIBILITY.csv',
                     'CF_FOOTPRINT_20261016_HARDWARE_AB.txt'):
            shutil.copyfile(DOCS/name, temporary/name)
        readme = ('PERKY PKH5D1 diagnostic / PKH5P1 performance candidates\n\n'
                  'Locally qualified; physical MKII acceptance pending. Both CF voices\n'
                  'remain unrestricted. Read the report, scoped qualification limits\n'
                  'and hardware A/B procedure before selecting an upgrade wrapper.\n'
                  'Use your established card OS UPGRADE or MIDI procedure. No automatic\n'
                  'flashing occurs. Do not install raw MAIN or ELF files. Preserve PKH4O2\n'
                  'and your known-good recovery image; this bundle does not replace them.\n'
                  'BUILD/CONFIGURATION receipts describe build-time status; the separate\n'
                  'QUALIFICATION.json records completed local gates.\n')
        (temporary/'README.txt').write_text(readme)
        files = {str(p.relative_to(temporary)):dict(bytes=p.stat().st_size,sha256=sha(p))
                 for p in sorted(temporary.rglob('*')) if p.is_file()}
        manifest = dict(status=report['status'],firmware_source_commit=report['firmware_source_commit'],
                        hybrid_source_id=report['hybrid_source_id'],physical_acceptance=False,
                        package_tool_sha256=sha(__file__),files=files)
        (temporary/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
        sums = {str(p.relative_to(temporary)):sha(p) for p in sorted(temporary.rglob('*')) if p.is_file()}
        (temporary/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sums.items()))
        assert all(sha(temporary/name)==digest for name,digest in sums.items())
        assert not destination.exists(), 'destination appeared during packaging'
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    print(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args = parser.parse_args()
    package(args.qualification.resolve(),args.destination.resolve())
