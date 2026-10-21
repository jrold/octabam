#!/usr/bin/env python3
"""Opt-in resident Hat state snapshot, retaining the PKFM11 CF improvements.

The normal DSP-owned path performs no CF Hat synthesis. State snapshots use
existing scheduled feedback padding; only a requested takeover runs catch-up.
"""
import json
import os
import subprocess
from pathlib import Path

import build_perky_budget_optimized as budget
import generate_hat_state_dsp as dsp
import generate_hat_state_handoff as cfstate

ROOT = budget.ROOT
WORK = Path(os.environ.get('PERKY_STATE_WORK', str(ROOT / 'out/perky/hybrid/full-map-state-v4'))).resolve()
VERSION = os.environ.get('PERKY_STATE_VERSION', 'PKFM15')


def dma_transport_source():
    """Replace the historical sequence-zero startup sentinel only here.

    Sequence zero is a valid full-wrap packet. The explicit boot-reset latch
    becomes sticky when the first real NHT packet is emitted, so scheduled
    DMA must keep extracting its feedback throughout every later wrap.
    """
    source = ROOT / 'modules/perky/cf_noise_hat_handoff.c'
    text = source.read_text()
    old = '    if(!pk_nhr_sequence)return 0;'
    assert text.count(old) == 1
    text = text.replace(old, '    if(!nhs_transport_started)return 0;', 1)
    anchor = '#include "cf_noise_hat_offload.c"'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '\nextern uint32_t nhs_transport_started;', 1)
    target = WORK / 'cf-noise-hat-state-transport.c'
    target.write_text(text)
    return target


def direct_dsp_fixture():
    """Decode this actual upload for direct gates; never reuse old P bytes."""
    import ab_records as records
    out = WORK / 'import-gate'
    out.mkdir(exist_ok=True)
    upload = WORK / 'dsp-A.upload.bin'
    blob = upload.read_bytes()
    rows, _ = records.records(blob, records.BASE, len(blob))
    program = [0] * 0x40000
    data = []
    for space, at, length, offset in rows:
        values = [records.rd(blob, offset + 3 * i) for i in range(length)]
        if space == 0:
            assert at + length <= len(program)
            program[at:at + length] = values
        else:
            data.append(('X' if space == 1 else 'Y') + f' {at:x} ' +
                        ' '.join(f'{v:x}' for v in values) + '\n')
    (out / 'code.bin').write_bytes(b''.join(v.to_bytes(3, 'little') for v in program))
    (out / 'initial.data').write_text(''.join(data))
    (out / 'UPLOAD_BINDING.json').write_text(json.dumps(
        {str(p): budget.card.a.b.sha(p) for p in (upload, out / 'code.bin', out / 'initial.data')}, indent=2) + '\n')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    budget.WORK = WORK
    budget.VERSION = VERSION
    for key in ('PERKY_BUDGET_SLAP', 'PERKY_BUDGET_CONTROLS'):
        assert os.environ.get(key, '1') == '1', 'State handoff retains both admitted CF optimizations'
        os.environ[key] = '1'
    assert not os.environ.get('PERKY_BUDGET_CODEGEN'), 'Rejected codegen experiment is excluded'
    platform = budget.card.a.b.G.h.CF
    program = budget.card.a.b.F
    image = budget.card.a.b.G.h.P
    original_build = platform.build
    original_service = program.service
    original_upload = image.extend_upload
    original_run = subprocess.run

    def service():
        return dsp.transform(original_service())

    def upload(img, tag, y, x=None, extra=None, extra_y=None, p_records=None):
        if tag == 'A' and budget.card.a.fx.READY:
            y = dsp.snapshot_initial_y(y)
        return original_upload(img, tag, y, x, extra, extra_y, p_records)

    def build(work, **kwargs):
        path = WORK / 'full-map-transport.h'
        path.write_text(cfstate.transform(WORK, path.read_text()))
        units = list(kwargs['additional_units'])
        matches = [i for i, (name, _) in enumerate(units) if name == 'pkhatrpc']
        assert len(matches) == 1
        at = matches[0]
        assert Path(units[at][1]).name == 'cf_noise_hat_handoff.c'
        units[at] = ('pkhatrpc', str(dma_transport_source()))
        kwargs['additional_units'] = tuple(units)
        return original_build(work, **kwargs)

    def run(command, *args, **kwargs):
        if (isinstance(command, (list, tuple)) and len(command) > 1
                and str(command[1]) == str(ROOT / 'tools/verify/verify_perky_noise_hat_resident_boot.py')):
            command = list(command)
            command[1] = str(ROOT / 'tools/verify/verify_hat_state_boot.py')
        return original_run(command, *args, **kwargs)

    platform.build = build
    program.service = service
    image.extend_upload = upload
    subprocess.run = run
    try:
        budget.main()
    finally:
        platform.build = original_build
        program.service = original_service
        image.extend_upload = original_upload
        subprocess.run = original_run
    dsp.write_contract(WORK)
    direct_dsp_fixture()
    path = WORK / 'BUILD.json'
    result = json.loads(path.read_text())
    result.update(status='BUILT_ON_DEMAND_HAT_STATE_HANDOFF_NOT_QUALIFIED',
                  integration_scope='Resident DSP Hat with scheduled snapshot feedback and on-demand CF catch-up; no continuous CF Hat shadow')
    sources = [Path(__file__).resolve(), ROOT / 'tools/perky/generate_hat_state_dsp.py',
               ROOT / 'tools/perky/generate_hat_state_handoff.py',
               ROOT / 'tools/harness/perky_cf/hat_state_handoff.h',
               ROOT / 'tools/verify/verify_hat_state_boot.py',
               WORK / 'full-map-state-handoff.h', WORK / 'full-map-transport.h',
               ROOT / 'modules/perky/cf_noise_hat_handoff.c',
               WORK / 'cf-noise-hat-state-transport.c']
    result['source_sha256'].update({str(p.relative_to(ROOT)): budget.card.a.b.sha(p) for p in sources})
    result['state_handoff_contract'] = json.loads((WORK / 'STATE_HANDOFF_CONTRACT.json').read_text())
    result['memory']['notes'].append('The snapshot reuses retired A-only oscillator-wave storage inside the existing PERKY low-Y allocation; no envelope/clock table or stock FX storage is replaced.')
    result['memory']['state_snapshot'] = result['state_handoff_contract']
    path.write_text(json.dumps(result, indent=2) + '\n')
    (WORK / 'MEMORY.json').write_text(json.dumps(result['memory'], indent=2) + '\n')
    print(result['status'], VERSION)


if __name__ == '__main__':
    main()
