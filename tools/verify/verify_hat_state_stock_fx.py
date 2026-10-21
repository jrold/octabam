#!/usr/bin/env python3
"""All fourteen stock FX, stock DSP-B source and bounded Hat low-Y reclaim.

The original full-map stock gate remains unchanged. This candidate replaces
custom shared P and reclaims A-only PERKY waveform Y; neither is stock FX data.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ('tools/verify', 'tools/perky', 'tools/build', 'tools')]
import ab_records as A
import perky_image as P
import generate_hat_state_dsp as snapshot
from remix import registry, stock

W = Path(os.environ.get('PERKY_FULL_MAP_WORK', str(ROOT / 'out/perky/hybrid/full-map-state-v1'))).resolve()
BASELINE = ROOT / 'out/perky/hybrid/full-map-budget-v5'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(blob, span):
    rows, _ = A.records(blob, *span)
    return {(space, at + i): A.rd(blob, off + 3 * i)
            for space, at, n, off in rows for i in range(n)}


def main():
    stock_image = ROOT / 'out/raw/section_3_MAIN_OS.bin'
    pristine = stock_image.read_bytes()
    build = json.loads((W / 'BUILD.json').read_text())
    memory = build['memory']
    assert memory['shared_words'] <= memory['shared_capacity']
    assert memory['private_P_used'] == {'A': 0, 'B': 0}
    cases = {}
    inputs = [stock_image, W / 'BUILD.json']
    for tag in ('A', 'B'):
        old = words(pristine, P.PAY[tag]['payload'])
        path = W / f'dsp-{tag}.upload.bin'
        blob = path.read_bytes()
        new = words(blob, (A.BASE, len(blob)))
        reference_path = BASELINE / path.name
        reference_blob = reference_path.read_bytes()
        reference = words(reference_blob, (A.BASE, len(reference_blob)))
        allowed = set(range(0x40, 0x4A if tag == 'A' else 0x4B))
        if tag == 'A':
            allowed |= {0x39C, 0x39D, 0x53E, 0x53F}
        assert {at for space, at in new if space == 0 and at < 0x2000} == {
            at for space, at in old if space == 0 and at < 0x2000}, 'private program tail appended'
        for (space, at), value in old.items():
            if space == 0 and at in allowed:
                continue
            assert new[space, at] == value, (tag, 'stock word changed', space, hex(at))
        effects = {}
        for name, (start, count) in stock.p_spans(tag).items():
            effect_id = registry.modules()[name].menu.fx2_id
            assert all(new[0, at] == old[0, at] for at in range(start, start + count)), (tag, name, 'code')
            assert all(new[1, base + effect_id] == old[1, base + effect_id]
                       for base in (0x215, 0x235)), (tag, name, 'dispatch')
            effects[name] = dict(start=start, words=count, FX1_and_FX2_dispatch_exact=True)
        effect_id = registry.modules()['DELAY'].menu.fx2_id
        assert all(new[1, base + effect_id] == old[1, base + effect_id] for base in (0x215, 0x235))
        effects['DELAY'] = dict(code_identity='complete stock program comparison', FX1_and_FX2_dispatch_exact=True)
        assert len(effects) == 14
        shared = {at for space, at in new if space == 0 and at >= 0x30000}
        inherited = {at for space, at in old if space == 0 and at >= 0x30000}
        assert len(shared - inherited) == memory['shared_words']
        # All private program/data words remain identical to PKFM11 except
        # A's relocated source/embed calls and the explicitly reclaimed Y.
        changes = []
        assert {key for key in new if key[1] < 0x30000} == {
            key for key in reference if key[1] < 0x30000}
        for (space, at), value in reference.items():
            if at >= 0x30000:
                continue
            if new[space, at] == value:
                continue
            if tag == 'A' and ((space == 0 and at in {0x39D, 0x53F})
                               or (space == 2 and snapshot.BASE <= at < snapshot.BUFFER_END)):
                changes.append([space, at])
                continue
            raise AssertionError((tag, 'unexpected PKFM11 private change', space, hex(at)))
        if tag == 'B':
            assert not changes
            assert all(new[0, at] == old[0, at] for at in (0x1A2, 0x1A3))
        else:
            assert new[2, snapshot.CURSOR] == snapshot.STREAM_WORDS
            assert all(new[2, at] == 0 for at in range(snapshot.BASE, snapshot.CURSOR))
        cases[tag] = dict(effects=effects, stock_existing_X_Y_exact=True,
                          private_program_tail_added=False, stock_source_exact=(tag == 'B'),
                          private_changes_from_PKFM11=changes,
                          added_shared_words=len(shared - inherited),
                          upload_sha256=sha(path), PKFM11_reference_sha256=sha(reference_path))
        inputs += [path, reference_path]
    result = dict(status='PASS_STATE_HANDOFF_ALL_FOURTEEN_FX_STOCK_DATA_AND_B_SOURCE',
                  cases=cases, shared_P=dict(used=memory['shared_words'], capacity=memory['shared_capacity'],
                                            free=memory['shared_capacity'] - memory['shared_words']),
                  reclaimed_A_Y=dict(start=snapshot.BASE, end=snapshot.BUFFER_END,
                                     within_retired_wave=[0x7A5, 0x9A5],
                                     curves_and_clock_unchanged=True),
                  inputs={str(path): sha(path) for path in inputs},
                  source_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                                 (Path(__file__).resolve(), ROOT / 'tools/perky/generate_hat_state_dsp.py')},
                  limits=['Upload-byte and declared-memory proof; actual DSP low-Y poison/read-watch gate is separate.',
                          'All FX execution, exact live audio, scheduling and physical timing require their own gates.'])
    (W / 'STATE_STOCK_FX_GATE.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
