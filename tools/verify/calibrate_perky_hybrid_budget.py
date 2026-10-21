#!/usr/bin/env python3
"""Replay hardware-labeled configurations without changing firmware or clocks.

Hardware labels describe reported configurations, not a recovered performance
trace: the original card, complete control history and algorithm pair are not
available. A separating model budget is therefore an empirical screening gate,
not a silicon conversion factor or a proof of physical reliability.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ('tools/verify', 'tools/harness', 'tools/hw')]
import measure_perky_cf_placement_integrated as integrated
import measure_perky_full_map as full

HISTORICAL = ROOT / 'out/perky/hybrid/campaign-20261016/final'
CURRENT = ROOT / 'out/perky/hybrid/full-map-release'
DEFAULT_WORK = ROOT / 'out/perky/hybrid/budget-calibration'
PERIOD = 16e6 / 44100
PINNED = {
    'PKH4O2': 'f7f04e26969522d2024b1bba5be85f620857d636dbe0b284aa38c0fb087a21db',
    'PKFM6': 'c062f9232949f0073198b5e073c2948558275ff1d02f716054d82b9a314bfa77',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def build_observer(work):
    """Extend the existing read-only observer with exact cycle distributions."""
    base = CURRENT / 'observer'
    out = work / 'observer'
    out.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((base / 'OBSERVER_BUILD.json').read_text())
    assert sha(base / 'ot_emu_safety') == receipt['binary_sha256']
    old_header = ROOT / 'out/perky/hybrid/cf-placement-integrated/observer/observer.h'
    header = old_header.read_text()
    marker = 'uint64_t isr_sum_cycles=0, timer_samples=0, timer_invalid=0, timer_sum=0;'
    assert header.count(marker) == 1
    header = header.replace(marker, marker + '''
    std::map<uint64_t,uint64_t> budget_all_cycles, budget_steady_cycles;
    uint64_t budget_steady_sum=0, budget_steady_frames=0;
''')
    marker = 'isr_sum_cycles+=cost;'
    assert header.count(marker) == 1
    header = header.replace(marker, marker + '''
                ++budget_all_cycles[cost];
                if(returns>512) {++budget_steady_cycles[cost];
                    budget_steady_sum+=cost;++budget_steady_frames;}
''')
    marker = 'f<<"],\\\"render_calls\\\":[";'
    assert header.count(marker) == 1
    header = header.replace(marker, '''
        f<<"],\\\"budget_cycles\\\":{\\\"steady_after_completed_ISR\\\":512,\\\"steady_sum\\\":"
         <<budget_steady_sum<<",\\\"steady_frames\\\":"<<budget_steady_frames;
        for(unsigned which=0;which<2;++which) {
            f<<(which ? ",\\\"steady_histogram\\\":[" : ",\\\"all_histogram\\\":[");
            bool sep=false;
            for(const auto& pair:which ? budget_steady_cycles:budget_all_cycles) {
                if(sep)f<<',';sep=true;f<<'['<<pair.first<<','<<pair.second<<']';
            }
            f<<']';
        }
        f<<"},\\\"render_calls\\\":[";
''')
    staged_header = out / 'observer.h'
    staged_header.write_text(header)
    # Both objects must see the same extended class layout.
    machine = (base / 'machine.cpp').read_text()
    assert machine.count(str(old_header)) == 1
    machine = machine.replace(str(old_header), str(staged_header))
    periph = (old_header.parent / 'periph.cpp').read_text()
    assert periph.count(str(old_header)) == 1
    periph = periph.replace(str(old_header), str(staged_header))
    flags = (ROOT / 'out/emu/CMakeFiles/ot_machine.dir/flags.make').read_text()
    import shlex
    options = []
    for key in ('CXX_DEFINES', 'CXX_INCLUDES', 'CXX_FLAGS'):
        options += shlex.split(next(line.split(' = ', 1)[1] for line in flags.splitlines()
                                   if line.startswith(key + ' = ')))
    commands = []
    for name, text in (('machine', machine), ('periph', periph)):
        path = out / (name + '.cpp')
        path.write_text(text)
        cmd = ['/usr/bin/c++', *options, '-I' + str(ROOT / 'tools/emu/ot_emu'),
               '-c', str(path), '-o', str(out / (name + '.o'))]
        subprocess.run(cmd, check=True)
        commands.append(cmd)
    link = list(receipt['commands'][-1])
    assert '-o' in link and str(base / 'ot_emu_safety') in link
    link[link.index('-o') + 1] = str(out / 'ot_emu_safety')
    link[link.index(str(base / 'machine.o'))] = str(out / 'machine.o')
    old_periph = str(old_header.parent / 'periph.o')
    link[link.index(old_periph)] = str(out / 'periph.o')
    subprocess.run(link, check=True)
    commands.append(link)
    save(out / 'BUILD.json', dict(binary_sha256=sha(out / 'ot_emu_safety'),
         parent_observer_sha256=sha(base / 'ot_emu_safety'), commands=commands,
         inputs={str(p): sha(p) for p in (Path(__file__), old_header,
                 base / 'machine.cpp', old_header.parent / 'periph.cpp',
                 base / 'dsp.o', base / 'rtos.o')},
         scope='Read-only full ISR executed-cycle histograms; steady excludes first 512 completed interrupts.'))


def cases():
    rows = {}
    for pair in (('V1', 'V1'), ('snare', 'snare'), ('snare', 'bass'), ('third', 'third')):
        for role, cf, stock in (
                ('working-shape', (1,), (2, 3, 5, 6, 7)),
                ('matched-one', (1,), (2, 3, 6)),
                ('failing-shape', (1, 5), (2, 3, 6))):
            name = '-'.join(('H4', role, *pair))
            rows[name] = dict(version='PKH4O2', role=role, pair=pair,
                              cf_tracks=cf, stock_tracks=stock)
    for v4, mode in ((5, 0), (5, 1), (5, 2), (3, 1), (10, 1)):
        for fx in ('shared12', 'all14'):
            rows[f'F6-WTWT-Slap-{v4}-M{mode}-{fx}'] = dict(
                version='PKFM6', role='candidate', algos=[9, 9, 8, v4],
                modes=[1, 2, 0, mode], FX=fx)
    return rows


def current_card(directory, row, project):
    """Use the same stock fixture; publish the production PK/2 selectors."""
    full.W = CURRENT
    if row['FX'] == 'all14':
        return full.stage(project, directory, 'static', row['algos'], row['modes'], 15)
    otp = integrated.workload.otp
    previous = otp._bank_write

    def write(pdir, banknum, mutate, guard=True):
        def bound(data):
            mutate(data)
            for part in range(otp.NPARTS_ALL):
                live = otp.PART_BASE + part * otp.PART_STRIDE + 9
                for voice, track in enumerate((0, 1, 4, 5)):
                    at = live + 48 + 30 * track
                    data[at + 2] = full.FAMILY[voice].index(row['algos'][voice])
                    data[at + 5] = row['modes'][voice]
                    data[live + 60 + 30 * track:live + 63 + 30 * track] = b'PK\x02'
            for pattern in range(4):
                for track in (0, 1, 4, 5):
                    at = otp.trac_off(pattern, track) + 0x59
                    for step in range(64):
                        data[at + 32 * step + 2] = data[at + 32 * step + 5] = 255
        return previous(pdir, banknum, bound, guard=guard)

    otp._bank_write = write
    try:
        card = integrated.stage_fixture(project, directory, 'static', row['algos'], row['modes'], 15)
    finally:
        otp._bank_write = previous
    # Same verified PCM asset as the final image's normal fixture.
    import emu_card
    tree = directory / 'asset-tree'
    tree.mkdir()
    for name, data in emu_card.extract_image(card.read_bytes()).items():
        p = tree / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (tree / 'PERKYAH.DAT').write_bytes((CURRENT / 'PERKYAH.DAT').read_bytes())
    card.write_bytes(emu_card.build_image(tree))
    shutil.rmtree(tree)
    return card


def histogram_stats(hist):
    count = sum(n for _, n in hist)
    assert count
    def quantile(q):
        threshold = math.ceil(q * count)
        total = 0
        for value, n in hist:
            total += n
            if total >= threshold:
                return value / 264
    return dict(frames=count, mean_us=sum(v*n for v, n in hist)/count/264,
                p50_us=quantile(.5), p95_us=quantile(.95), p99_us=quantile(.99),
                p99_9_us=quantile(.999), max_us=hist[-1][0]/264)


def run(work, name, frames, parent=False):
    row = cases()[name]
    directory = work / (name + ('-parent' if parent else ''))
    assert not directory.exists(), 'Use a new output directory; never overwrite a receipt'
    directory.mkdir(parents=True)
    version = row['version']
    source = HISTORICAL if version == 'PKH4O2' else CURRENT
    image = source / f'probe/mainos_{version}.bin'
    elf = source / 'probe/platform/runtime.elf'
    assert sha(image) == PINNED[version], 'historical/final image drift'
    syms = integrated.private.symbols(elf)
    project = Path(json.loads((ROOT / 'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
    env = integrated.private.environment(source, name)
    env.update(HYBRID_SAFETY_REPORT=str(directory / 'stack.json'),
               HYBRID_PRIVATE_REPORT=str(directory / 'private.json'))
    for key in list(env):
        if key.startswith(('FM_', 'NHB_', 'NHT_', 'NHL_')):
            del env[key]
    pokes = []
    def poke(symbol, value):
        pokes.extend(f'{syms[symbol]+i:#x}={b:#x}' for i, b in enumerate(value.to_bytes(4, 'big')))
    dumps = []
    if version == 'PKH4O2':
        card = integrated.workload.stage_integrated_fixture(project, directory, *row['pair'],
            tone_path=directory / 'tone.wav', sampler_kind='static',
            cf_tracks=row['cf_tracks'], sampler_tracks=row['stock_tracks'])
        poke('pk_hybrid_profiler_enable', 1)
        poke('pk_hybrid_cf_arm', 1)
        sizes = subprocess.check_output(['m68k-elf-nm', '-S', str(elf)], text=True)
        size = next(int(line.split()[1], 16) for line in sizes.splitlines()
                    if len(line.split()) == 4 and line.split()[-1] == 'pk_hybrid_prof')
        dumps.append(('prof', syms['pk_hybrid_prof'], size))
        active = {0, 4, *row['cf_tracks'], *row['stock_tracks']}
        cf_tracks = set(row['cf_tracks'])
    else:
        card = current_card(directory, row, project)
        full.W = CURRENT
        env.update(full.environment(directory, syms))
        poke('placement_mask', 15)
        for voice in range(4):
            for offset, value in ((0, row['algos'][voice]), (4, row['modes'][voice])):
                pokes.extend(f'{syms["placement_inputs"]+40*voice+offset+i:#x}={b:#x}'
                             for i, b in enumerate(value.to_bytes(4, 'big')))
        for symbol in ('pk_nhr_failures', 'pk_nhb_overflows', 'pk_nhb_clock_errors',
                       'pk_nhb_produced', 'pk_nhb_completed', 'fma_ready', 'fma_status'):
            dumps.append((symbol, syms[symbol], 4))
        active = set(range(8))
        cf_tracks = {0, 1, 4, 5}
    observer = (CURRENT / 'observer' if parent else work / 'observer') / 'ot_emu_safety'
    binding = {str(p): sha(p) for p in (image, elf, card, observer, Path(__file__),
               Path(integrated.workload.__file__), Path(full.__file__))}
    command = [str(observer), '--image', str(image), '--card', str(card), '--set', 'OCTABAM',
        '--project', 'RIG', '--load-ms', '90000', '--sequencer', '--internal-clock', '--bank', '0',
        '--frames', str(frames), '--dsp', '--dsp-dirty', '123', '--main-level', '64',
        '--pit-clock-hz', '132000000', '--cf-cycles-clock', '1.0', '--cf-cycles-clock-before-transport',
        '--cf-frame-hist', '--block-dump', str(directory / 'blocks.bin'),
        '--cmd-log', str(directory / 'card-load.log'), '--cmd-log-end', str(directory / 'card-end.log'),
        '--poke-before-play', ';'.join(pokes), '--mem-dump',
        ';'.join(f'{at:#x},{size}={directory/(n+".bin")}' for n, at, size in dumps)]
    save(directory / 'INPUTS.json', dict(command=command, inputs=binding, case=row,
         environment={k:v for k,v in env.items() if k.startswith(('HYBRID_', 'FM_', 'NHB_'))}))
    with (directory / 'port.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    assert result.returncode == 0, (directory, result.returncode)
    assert binding == {p: sha(p) for p in binding}, 'input drift during run'
    log = (directory / 'port.log').read_text()
    assert 'cycle clock: startup/pre-roll/transport use' in log
    assert re.search(rf'frames run\s*:\s*{frames}\s+since transport start.*REACHED', log)
    assert 'FAULT:' not in log and 'ILLEGAL' not in log
    stack = json.loads((directory / 'stack.json').read_text())
    own = json.loads((directory / 'private.json').read_text())
    assert stack['frames'] == stack['frame_returns'] == own['switched'] == own['restored']
    assert not any(stack[k] for k in ('DMA_read_write_overlaps', 'guard_writes_after_dispatch'))
    assert not own['ownership_register_frame_or_mask_violations'] and not own['fence_writes']
    classes = integrated.blockdump.classes(integrated.blockdump.read(directory / 'blocks.bin'))
    audio = {}
    for track in sorted(active):
        source_pcm = integrated.recloop.track_audio(classes, track + 1)
        post = integrated.recloop.readback_audio(classes, track + 1)
        counts = dict(source_significant=sum(abs(v)>64 for v in source_pcm),
                      post_FX_significant=sum(abs(v)>64 for v in post))
        assert counts['post_FX_significant'] > 64, (name, track, counts)
        if track in cf_tracks or track not in (0, 4):
            assert counts['source_significant'] > 64, (name, track, counts)
        audio[str(track + 1)] = counts
    load = (directory / 'card-load.log').read_text().splitlines()
    end = (directory / 'card-end.log').read_text().splitlines()
    assert end[:len(load)] == load
    reads = sum(line.startswith('READ ') for line in end[len(load):])
    assert reads > 0
    summary = dict(case=name, configuration=row, frames=stack['frame_returns'],
        image_sha256=sha(image), observer_sha256=sha(observer), clocks=dict(CF=264000000, PIT=132000000),
        full_ISR=dict(mean_us=stack['full_ISR_sum_cycles']/stack['frame_returns']/264,
                      max_us=stack['full_ISR_max_cycles']/264, modeled_misses=stack['ISR_duration_misses']),
        stock_audio=audio, playback_card_read_commands=reads,
        whole_CPU=integrated.workload.parse_ot_emu_log(log), inputs=binding,
        comparison_dumps={p.name:sha(p) for p in directory.glob('*.bin')})
    if not parent:
        summary['steady_ISR'] = histogram_stats(stack['budget_cycles']['steady_histogram'])
        summary['all_ISR'] = histogram_stats(stack['budget_cycles']['all_histogram'])
        assert summary['all_ISR']['frames'] == stack['frame_returns']
        assert summary['all_ISR']['max_us'] == summary['full_ISR']['max_us']
    if version == 'PKH4O2':
        prof = integrated.workload.decode_profiler_dump((directory / 'prof.bin').read_bytes())
        assert prof['active_cf_voices'] == len(cf_tracks)
        summary['target_profile'] = {k:prof[k] for k in ('active_cf_voices','active_dsp_voices','active_voice_mask','dtim3_us')}
    else:
        exact = json.loads((directory / 'full-map-exact.json').read_text())
        assert full.exact(exact), exact
        transport = {n:int.from_bytes((directory/(n+'.bin')).read_bytes(),'big') for n,_,_ in dumps}
        assert not any(transport[k] for k in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors'))
        assert transport['pk_nhb_completed'] > 0
        assert transport['fma_ready'] == 0x41484f4b and transport['fma_status'] == 2
        summary.update(exact_source=exact, transport=transport)
    save(directory / 'ROW.json', summary)
    # Preserve hashes, histograms and small target dumps; discard reproducible bulk.
    for p in (card, directory/'blocks.bin'):
        p.unlink()
    for p in (directory/'project', directory/'tree'):
        if p.exists():
            shutil.rmtree(p)
    print(json.dumps(dict(case=name, full_ISR=summary['full_ISR'], steady_ISR=summary.get('steady_ISR'))), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    parser.add_argument('--build-observer', action='store_true')
    parser.add_argument('--case', choices=cases())
    parser.add_argument('--frames', type=int, default=16384)
    parser.add_argument('--parent-observer', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if args.build_observer:
        build_observer(work)
    if args.case:
        run(work, args.case, args.frames, args.parent_observer)


if __name__ == '__main__':
    main()
