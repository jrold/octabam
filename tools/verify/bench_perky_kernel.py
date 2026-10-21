#!/usr/bin/env python3
"""Replay captured kernel vectors through cf_cycle_bench: exactness and cycles.

The reference is the captured image's own function (its ELF loaded at link
addresses); a candidate is an assembled blob entered at its own address with
the same arguments. Every vector's PCM, object bytes and RNG must match the
capture exactly. Cycles come from the frozen observer's core model with a
warm predictor (two runs per vector, the second counted); use them to compare
candidates, never as admission evidence.

  bench_perky_kernel.py VECTORS.json [--blob CODE.bin --blob-elf CODE.elf]
"""
import argparse, json, os, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / 'out/perky/hybrid/cf-cycle-bench/cf_cycle_bench'  # tools/harness/perky_cf/build_cf_cycle_bench.sh
OBJECT, PCM, TABLES, RNG = 0x400000, 0x500000, 0x600000, 0x610000
BLOB_AT = 0x700000


def symbols(elf):
    rows = subprocess.check_output(['m68k-elf-nm', str(elf)], text=True)
    return {f[2]: int(f[0], 16) for line in rows.splitlines() if len(f := line.split()) == 3}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('vectors', type=Path)
    ap.add_argument('--candidate-elf', type=Path, help='linked candidate (code placed at its link address)')
    ap.add_argument('--candidate-symbol', help='entry symbol in the candidate ELF')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--stride', type=int, default=1)
    ap.add_argument('--profile', type=Path, help='write per-PC cycles (second, warm run) here')
    args = ap.parse_args()
    data = json.loads(args.vectors.read_text())
    kernel = data['kernel']
    state_bytes = dict(wt=0x150, slap=0x2670, nt=0x100)[kernel]
    rng_arg = dict(wt=None, slap=4, nt=4)[kernel]
    ref_elf = Path(data['elf'])
    ref_entry = symbols(ref_elf)[dict(wt='pk_cf_wt_render', slap='pk_cf_slap_render', nt='pk_cf_nt_shared_render')[kernel]]
    cand = None
    if args.candidate_elf:
        cand = (args.candidate_elf, symbols(args.candidate_elf)[args.candidate_symbol])
    vectors = data['vectors'][::args.stride]
    if args.limit: vectors = vectors[:args.limit]
    totals = {'reference': 0, 'candidate': 0}; samples = 0; mismatches = []; profile = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        words = data['tables']['words']
        for index, v in enumerate(vectors):
            n = v['n']; samples += n
            (tmp / 'state.bin').write_bytes(bytes.fromhex(v['state_in']))
            setup = [f'mem {OBJECT:#x} {tmp / "state.bin"}']
            for i, w in enumerate(words): setup.append(f'long {TABLES + 4 * i:#x} {w:#x}')
            for at, path in data['tables']['regions'].items(): setup.append(f'mem {at} {ROOT / path}')
            argv = [OBJECT, PCM, n, TABLES]
            if rng_arg:
                (tmp / 'rng.bin').write_bytes(bytes.fromhex(v['rng_in']))
                setup.append(f'mem {RNG:#x} {tmp / "rng.bin"}'); argv.append(RNG)
            setup += [f'push {a:#x}' for a in argv]
            setup += ['repeat 2', f'dump {OBJECT:#x} {state_bytes}', f'dump {PCM:#x} {2 * n}']
            if rng_arg: setup.append(f'dump {RNG:#x} 8')
            runs = [('reference', ref_elf, ref_entry)] + ([('candidate', *cand)] if cand else [])
            for label, elf, entry in runs:
                # A candidate may resolve helpers in the reference image (ld -R).
                images = [f'elf {elf}'] if label == 'reference' else [f'elf {ref_elf}', f'elf {elf}']
                (tmp / 'setup.txt').write_text('\n'.join(images + [f'entry {entry:#x}'] + setup) + '\n')
                out = subprocess.run([str(BENCH), '/dev/null', str(tmp / 'setup.txt')], capture_output=True, text=True)
                line = out.stdout.strip().splitlines()[-1]
                result = json.loads(line)
                totals[label] += result['cycles']
                for off, c in result['pc'].items():
                    at = (entry + int(off, 16)) & 0xffffffff
                    profile.setdefault(label, {})
                    profile[label][at] = profile[label].get(at, 0) + c
                dumps = result['dumps']
                got = dict(state=dumps[0], pcm=dumps[1], rng=dumps[2] if rng_arg else None)
                want = dict(state=v['state_out'], pcm=v['pcm_out'], rng=v.get('rng_out'))
                bad = [k for k in got if got[k] != want[k]] + (['result'] if (result['d0'] & 0xffffffff) != (v['result'] & 0xffffffff) else [])
                if bad: mismatches.append((label, index, bad))
            if len(mismatches) > 8: break
    report = dict(kernel=kernel, vectors=len(vectors), native_samples=samples,
                  reference_cycles=totals['reference'], candidate_cycles=totals['candidate'] if cand else None,
                  reference_cycles_per_sample=totals['reference'] / max(samples, 1),
                  candidate_cycles_per_sample=(totals['candidate'] / max(samples, 1)) if cand else None,
                  mismatches=mismatches[:8])
    print(json.dumps(report, indent=1))
    if args.profile:
        args.profile.write_text(json.dumps({k: {f'{a:x}': c for a, c in v.items()} for k, v in profile.items()}))
    raise SystemExit(1 if mismatches else 0)


if __name__ == '__main__':
    main()
