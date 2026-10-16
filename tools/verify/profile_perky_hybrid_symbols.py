#!/usr/bin/env python3
"""Attribute executed target instructions to symbols without firmware timers.

Links the frozen native oracle objects into the current observer, then checks
the identical canonical stream and target cycle counts with observation off/on.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--reference', type=Path, default=ROOT / 'out/perky/hybrid/optimization/target-before')
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--resources', action='store_true', help='Observe architectural data traffic and executed instruction working sets')
    ap.add_argument('--voices', action='store_true', help='Also attribute nested public render calls to each CF instance')
    args = ap.parse_args()
    if args.voices and not args.resources:
        ap.error('--voices requires --resources')
    reference, candidate, work = (p.resolve() for p in (args.reference, args.candidate, args.work))
    work.mkdir(parents=True, exist_ok=True)
    original = json.loads((reference / 'report.json').read_text())
    current = json.loads((candidate / 'BENCH.json').read_text())
    assert current['status'] == 'PASS_EXACT_FROZEN_REFERENCE'
    command = next(r['argv'][:] for r in original['commands']
                   if any(str(x).endswith('/hybrid_cf_bench_runner.cpp') for x in r['argv']))
    command[command.index('-o') + 1] = str(work / 'runner')
    sources = [Path(p) for p in command if p.endswith(('.cpp', '.o', '.a'))]
    for p in sources:
        if p.name.endswith('-native.o'):
            assert sha(p) == original['artifact_sha256'][p.name], 'frozen oracle object drift'
    for name in ('target.bin', 'target.nm', 'target.elf'):
        assert sha(candidate / name) == current['artifacts'][name]
        shutil.copyfile(candidate / name, work / name)
    if args.resources:
        # GNU objdump's first tab-delimited column after the address contains
        # every instruction word (including extensions). Refuse unknown PCs
        # during execution rather than silently counting first words alone.
        dis = subprocess.check_output(['m68k-elf-objdump', '-d', str(work/'target.elf')], text=True)
        sizes = {}
        previous = None
        for line in dis.splitlines():
            m = re.match(r'^\s*([0-9a-f]+):\s*\t([0-9a-f ]+)\t?(.*)$', line)
            if not m:
                continue
            address, words, mnemonic = int(m[1], 16), m[2].split(), m[3].strip()
            if not words or any(not re.fullmatch('[0-9a-f]{4}', word) for word in words):
                raise ValueError('unrecognized instruction words: '+line)
            size = 2*len(words)
            if mnemonic:
                sizes[address] = size
                previous = address
            elif previous is not None and previous+sizes[previous] == address:
                sizes[previous] += size
            else:
                raise ValueError('orphan instruction extension: '+line)
        (work/'instruction-sizes.txt').write_text(''.join(f'{a:x} {n:x}\n' for a,n in sizes.items()))
    inputs = [*sources, Path(__file__).resolve(), reference / 'report.json', candidate / 'BENCH.json',
              *sorted((ROOT / 'tools/harness/perky_cf').glob('hybrid_cf_*.h*')),
              *sorted((reference / 'assets').glob('*.bin')),
              *[candidate / name for name in ('target.bin', 'target.nm', 'target.elf')]]
    hashes = {str(p): sha(p) for p in inputs}
    report = dict(status='RUNNING', measurement='exclusive emulated target cycles by symbol',
                  inputs=hashes, commands=[command], limits=[
                      'Pair labels describe initial algorithms; canonical frames 40+ exercise mode/family switching.',
                      'No new timer instructions or firmware state; host observation has no modeled target overhead.',
                      'Emulator cycles do not bound silicon cache or bus stalls.'])
    path = work / 'PROFILE.json'

    def save():
        path.write_text(json.dumps(report, indent=2) + '\n')

    save()
    try:
        with (work / 'compile.log').open('w') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        env = dict(os.environ, PK_CF_SYMBOL_PROFILE=str(work / 'symbol-costs.csv'))
        if args.resources:
            env['PK_CF_RESOURCE_PROFILE'] = str(work/'resources.csv')
            if args.voices:
                env['PK_CF_VOICE_PROFILE'] = '1'
        command = [str(work / 'runner'), str(work), str(reference / 'assets')]
        report['commands'].append(command)
        with (work / 'execute.log').open('w') as log:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        exact = json.loads((work / 'shadow-result.json').read_text())
        assert exact == current['exact'], 'observation changed target state/PCM/RNG'
        # Every cost row must also stay identical, including target stack depth.
        assert (work / 'costs.csv').read_bytes() == (candidate / 'costs.csv').read_bytes(), 'observer changed modeled execution'
        symbols = list(csv.DictReader((work / 'symbol-costs.csv').open()))
        grouped = {}
        for row in symbols:
            key = row['symbol']
            grouped[key] = grouped.get(key, 0) + int(row['exclusive_cycles'])
        report.update(status='PASS_EXACT_UNPERTURBED_SYMBOL_PROFILE', exact=exact,
                      top_symbols=sorted(grouped.items(), key=lambda p: p[1], reverse=True)[:30])
        assert hashes == {str(p): sha(p) for p in inputs}, 'input changed during observation'
        report['outputs'] = {p.name: sha(p) for p in work.iterdir() if p.is_file() and p != path}
        print(json.dumps(report['top_symbols'], indent=2))
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
