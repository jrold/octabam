#!/usr/bin/env python3
"""Verify the hybrid timer's startup order and unsigned read-pair calibration.

The direct-call fixture tests C control flow with explicit timer register
replies. It cannot measure silicon MMIO latency. No timer is reprogrammed by
the runtime; register writes here belong exclusively to the test fixture.
"""
import argparse
import json
from pathlib import Path

from unicorn import UC_HOOK_MEM_READ
import verify_perky_hybrid_runtime as rt


def run(probe, output):
    r, s = rt.machine(probe/'mainos_PKHYB2P.bin', probe/'platform/runtime.elf', True)
    u = r.uc
    assert rt.word(u, 0x400b9654) == 264000000, 'stock stored CPU clock'
    assert rt.word(u, s['pk_hybrid_timer_calibrated']) == 0, 'premature calibration'
    u.mem_unmap(0xfc000000, 0x100000)
    u.mem_map(0xfc000000, 0x100000)
    rt.w32(u, 0xfc07c004, 0xffffffff)
    samples = [0xfffffff0, 0x30]
    reads = []

    def read(mu, access, address, size, value, data):
        assert address == 0xfc07c00c and size == 4
        assert len(reads) < len(samples), 'unbounded/repeated timer calibration'
        rt.w32(mu, address, samples[len(reads)])
        reads.append(samples[len(reads)])

    hook = u.hook_add(UC_HOOK_MEM_READ, read, begin=0xfc07c00c, end=0xfc07c00f)
    rt.g.emu._call(u, s['pk_ui_tick'])  # disabled timer: no measurement
    assert not reads
    u.mem_write(0xfc07c000, b'\x00\x0b')
    rt.w32(u, 0xfc07c004, 127)  # wrong reference modulus: no measurement
    rt.g.emu._call(u, s['pk_ui_tick'])
    assert not reads
    rt.w32(u, 0xfc07c004, 0xffffffff)
    rt.g.emu._call(u, s['pk_ui_tick'])
    assert rt.word(u, s['pk_hybrid_prof']+5*4) == 64
    assert rt.word(u, s['pk_hybrid_timer_calibrated']) == 1
    rt.g.emu._call(u, s['pk_ui_tick'])
    assert reads == samples
    u.hook_del(hook)
    result = {'schema': 'octabam.perky.hybrid.timer-safety.v1', 'status': 'PASS',
              'image_sha256': rt.digest(probe/'mainos_PKHYB2P.bin'),
              'stock_stored_CPU_hz': 264000000, 'configured_bus_hz': 132000000,
              'disabled_timer_not_calibrated': True, 'wrong_modulus_not_calibrated': True,
              'one_pair_only': True, 'unsigned_wrap_delta_ticks': 64,
              'hardware_read_latency': 'UNEXECUTED; fixture does not measure silicon',
              'source': 'NXP MCF54455RM tables 8-3, 29-3, 30-2/5/7'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


def card_export(probe, output):
    # Reuse the existing STOP export fixture, now with explicit current clocks.
    import hashlib
    import verify_perky_hybrid_workload as workload
    import emu_card
    from read_hybrid_profile import read_export
    output.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((rt.ROOT/'modules/perky/hybrid/BASELINE.json').read_text())
    card = output/'export-card.img'
    result = workload.run_integrated_row(
        'automatic_card_export', 'snare', 'snare', image_path=probe/'mainos_PKHYB2P.bin',
        syms=workload.load_elf_symbols(probe/'platform/runtime.elf'),
        project_src=Path(baseline['project']['root']), work_dir=output/'workload',
        tone_path=probe/'workload/HYB_SAMPLER_440.wav', frames=4000, card_out=card,
        extra_steps=['3500:poke:0x800065b8=00000002'])
    exports = {name: data for name, data in emu_card.extract_image(card.read_bytes()).items()
               if name.upper().startswith('PKH2') and name.upper().endswith('.PRF')}
    assert len(exports) == 1, list(exports)
    build = json.loads((probe/'BUILD.json').read_text())
    for name, data in exports.items():
        path = output/name; path.write_bytes(data)
        decoded = read_export(path, build)
        profile = decoded['profile']
        assert profile['frame_count'] > 1000
        assert all(n > 0 for n in profile['dtim3_ticks']['inst_calls'])
        assert profile['extension']['readiness_faults'] == 0
        assert profile['read_calibration_observed']
        result['export'] = {'path': str(path), 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest(), 'decoded': decoded}
    result.update(status='PASS_ACTUAL_FIRMWARE_CARD_EXPORT', image_sha256=rt.digest(probe/'mainos_PKHYB2P.bin'))
    (output/'CARD_EXPORT.json').write_text(json.dumps(result, indent=2)+'\n')
    card.unlink()
    print('Actual STOP-to-card profile export: PASS')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--card-export', action='store_true')
    a = ap.parse_args()
    run(a.probe.resolve(), a.out.resolve())
    if a.card_export:
        card_export(a.probe.resolve(), a.out.resolve().parent/'card-export')
