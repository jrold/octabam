#!/usr/bin/env python3
"""Bounded hybrid cold-init test with stale native BSS, before any callback.

Poison is injected at the actual loader-to-initializer call, after depacking.
The stale Bank/Part tuple models RAM retained from the same previous project.
No stock input or generated firmware bytes are saved in the source tree.
"""
import argparse
import json
from pathlib import Path

from unicorn import UC_HOOK_CODE
import verify_perky_hybrid_runtime as rt


def run(probe, output):
    version=json.loads((probe/'BUILD.json').read_text())['version']
    image, elf = probe/f'mainos_{version}.bin', probe/'platform/runtime.elf'
    r, syms = rt.machine(image, elf, True)
    bank = rt.word(r.uc, rt.g.emu.PART_PTR)

    def first_native(machine, symbols):
        part = rt.word(machine.uc, rt.g.emu.PART_PTR)+0x8ed80
        for track in (0, 4):
            machine.uc.mem_write(part+0x22+track, b'\x01')
            machine.uc.mem_write(part+60+30*track, b'PK\x01')
        return b''.join(rt.args_for(machine.uc, t, 0, 7, symbols) for t in (0, 4))

    clean = first_native(r, syms)
    sizes = rt.sizes(elf)
    initialized = ('pk_hybrid_voices', 'pk_hybrid_pristine',
                   'pk_hybrid_karplus', 'pk_hybrid_karplus_pristine',
                   'pk_hybrid_generation', 'pk_hybrid_voice_generation',
                   'pk_hybrid_trigger_latch', 'pk_hybrid_frame_started',
                   'pk_hybrid_frame_pcm', 'simple_controls', 'pk_prefix_valid')
    expected_state = {name: bytes(r.uc.mem_read(syms[name], sizes[name]))
                      for name in initialized}
    expected_pcm = bytes(r.uc.mem_read(syms['pk_pcm_wt_base'], 4096)) + bytes(
        r.uc.mem_read(syms['pk_pcm_wt_bank'], 196608))
    bss_lo, bss_hi = syms['__bss_start'], syms['_end']
    expected_bss = bytes(r.uc.mem_read(bss_lo, bss_hi - bss_lo))
    original = rt.g.emu.Uc
    calls = []

    class PoisonedUc(original):
        def __new__(cls, *args, **kwargs):
            return object.__new__(cls)

        def ctl_set_cpu_model(self, model):
            super().ctl_set_cpu_model(model)

            def poison(mu, pc, size, data):
                lo, hi = syms['__bss_start'], syms['_end']
                mu.mem_write(lo, b'\xa5'*(hi-lo))
                rt.w32(mu, syms['simple_bank'], bank)
                rt.w32(mu, syms['simple_part'], 0)
                # A previously active same-family native smoother is valid.
                # PKSimpleControl: 8 longs, last[4], mode, valid, family, pad.
                for track, family in ((0, 0), (4, 3)):
                    mu.mem_write(syms['simple_controls']+40*track+37, bytes((1, family)))
                calls.append(pc)

            self.hook_add(UC_HOOK_CODE, poison,
                          begin=syms['pk_hybrid_boot_init'], end=syms['pk_hybrid_boot_init'])

    rt.g.emu.Uc = PoisonedUc
    try:
        dirty, symbols = rt.machine(image, elf, True)
        actual = first_native(dirty, symbols)
        state_equal = all(bytes(dirty.uc.mem_read(symbols[name], sizes[name])) == value
                          for name, value in expected_state.items())
        pcm_equal = expected_pcm == bytes(dirty.uc.mem_read(symbols['pk_pcm_wt_base'], 4096)) + bytes(
            dirty.uc.mem_read(symbols['pk_pcm_wt_bank'], 196608))
        full_bss_equal = expected_bss == bytes(dirty.uc.mem_read(
            symbols['__bss_start'], symbols['_end'] - symbols['__bss_start']))
    finally:
        rt.g.emu.Uc = original
    assert len(calls) == 1, 'poison not injected exactly at loader initialization'
    result = {
        'schema': 'octabam.perky.hybrid.cold-safety.v1',
        'status': 'PASS' if clean == actual and state_equal and pcm_equal and full_bss_equal else 'FAIL_INITIALIZATION',
        'image_sha256': rt.digest(image), 'elf_sha256': rt.digest(elf),
        'poison_bytes': syms['_end']-syms['__bss_start'],
        'stale_bank': hex(bank), 'first_native_record_equal': clean == actual,
        'initialized_state_equal': state_equal, 'decoded_PCM_equal': pcm_equal,
        'whole_BSS_equal_after_poison': full_bss_equal,
        'initialized_symbols': list(initialized),
        'differing_record_offsets': [i for i, (a, b) in enumerate(zip(clean, actual)) if a != b],
        'scope': 'First T1/T5 native producer after poisoned loader init; no physical timing claim',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return clean == actual and state_equal and pcm_equal and full_bss_equal


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.probe.resolve(), args.out.resolve()) else 1)
