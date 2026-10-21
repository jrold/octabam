#!/usr/bin/env python3
"""Reuse the WT full-state/partial-failure gate against frozen PKFM17 bodies."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky')]
import generate_wt_envelope_blocks as candidate
import verify_wt_block_asm as retained


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    assert not work.exists(), 'Use a fresh experiment directory'
    build = ROOT / 'out/perky/hybrid/full-map-packet-reserve-v2'
    actual = json.loads((build / 'BUILD.json').read_text())
    assert actual['runtime_sha256'] == 'e16f1da5b17b55083ab7fa7f165efd4e6ec262ada259291d4927b2412921d6c9'
    work.mkdir(parents=True)
    baseline_asm = work / 'frozen-baseline.s'
    source = build / 'wavetable-block-asm.c'
    subprocess.run(['m68k-elf-gcc', *actual['compiler_flags'], '-S', str(source),
                    '-o', str(baseline_asm)], cwd=ROOT, check=True)
    assert baseline_asm.read_bytes() == (build / 'probe/cf-generated/pkwavetable.s').read_bytes()
    adapted = inspect.getsource(retained.main)
    old = "source = args.baseline.resolve() / 'wavetable-native20.c'"
    assert adapted.count(old) == 1
    adapted = adapted.replace(old, "source = args.baseline.resolve() / 'wavetable-block-asm.c'", 1)
    old = "flags = [*gcc.FLAGS, '-ffunction-sections', '-fdata-sections', '-I', ROOT / 'modules/perky']"
    assert adapted.count(old) == 1
    adapted = adapted.replace(old, "flags = json.loads((args.baseline / 'BUILD.json').read_text())['compiler_flags']", 1)
    old = "if variant in ('oscillator', 'candidate'): command += [str(work / 'oscillator.o')]"
    assert adapted.count(old) == 1
    adapted = adapted.replace(old, "command += [str(work / 'oscillator.o')]", 1)
    namespace = dict(vars(retained), candidate=candidate, __file__=__file__)
    exec(compile(adapted, __file__, 'exec'), namespace)
    sys.argv = [sys.argv[0], '--work', str(work), '--baseline', str(build),
                '--variants', 'baseline', 'candidate']
    namespace['main']()
    path = work / 'RESULT.json'
    report = json.loads(path.read_text())
    report['PKFM17_runtime_sha256'] = actual['runtime_sha256']
    report['source_sha256'].update({str(path): sha(path) for path in
        (Path(__file__), Path(retained.__file__), build / 'BUILD.json', baseline_asm)})
    report['mean_cycles_saved'] = {key: report['results']['baseline']['groups'][key]['mean'] - value['mean']
        for key, value in report['results']['candidate']['groups'].items()}
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['mean_cycles_saved'], indent=2))


if __name__ == '__main__':
    main()
