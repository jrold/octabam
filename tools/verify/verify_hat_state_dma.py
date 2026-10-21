#!/usr/bin/env python3
"""Execute the candidate's real scheduled-DMA carrier extractor.

This untimed helper gate covers startup, both DMA banks, and the full 32-bit
sequence wrap. Whole-machine audio, lifecycle and timing have separate gates.
No replacement function, instruction hook, or repaired target bytes are used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

import verify_perky_hybrid_runtime as rt

ROOT = rt.ROOT
BASE = 0x80003390
SELECTOR = 0x800000e0
GUARD_BASE = BASE - 16
GUARD_BYTES = 0x800 + 32
MAIL_BYTES = 48
STATUS = 'PASS_ACTUAL_CF_DMA_STARTUP_FULL_WRAP_AND_CARRIER_CLEAR'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    work = args.build.resolve()
    build = json.loads((work / 'BUILD.json').read_text())
    image = work / 'probe' / ('mainos_' + build['version'] + '.bin')
    elf = image.parent / 'platform/runtime.elf'
    assert sha(image) == build['main_sha256']
    assert sha(elf) == build['runtime_sha256']
    source = work / 'cf-noise-hat-state-transport.c'
    source_key = str(source.relative_to(ROOT))
    assert sha(source) == build['source_sha256'][source_key]
    text = source.read_text()
    assert text.count('if(!nhs_transport_started)return 0;') == 1
    assert 'if(!pk_nhr_sequence)return 0;' not in text
    evidence = work / 'dma-gate'
    evidence.mkdir(exist_ok=True)
    disassembly = subprocess.check_output(
        ['m68k-elf-objdump', '-d', '--disassemble=pk_nhr_dma_step', str(elf)], text=True)
    assert '<pk_nhr_dma_step>:' in disassembly
    (evidence / 'pk_nhr_dma_step.dis').write_text(disassembly)

    original_boot = rt.g.emu.boot
    rt.g.emu.boot = lambda path: original_boot(path, count=200000000)
    try:
        machine, symbols = rt.machine(image, elf, True)
    finally:
        rt.g.emu.boot = original_boot
    u = machine.uc
    required = ('pk_nhr_dma_step', 'nhs_transport_started', 'pk_nhr_sequence',
                'pk_nhr_enabled', 'pk_nhr_mail', 'pk_nhr_dma_reads',
                'pk_nhr_dma_done', 'pk_nhb_reset')
    assert all(name in symbols for name in required)

    # The same actual reset used at boot must initialize even poisoned BSS.
    rt.w32(u, symbols['nhs_transport_started'], 0xffffffff)
    rt.g.emu._call(u, symbols['pk_nhb_reset'])
    assert rt.word(u, symbols['nhs_transport_started']) == 0
    rows = []
    cases = [(0, 0, bank, 1) for bank in (0, 1)]
    # A nonzero diagnostic sequence with a cold latch distinguishes the new
    # explicit startup guard from the historical sequence-only sentinel.
    cases += [(0, 7, bank, 1) for bank in (0, 1)]
    cases += [(1, 7, bank, 1) for bank in (0, 1)]
    # Keep extraction active during CF ownership, including valid full wrap.
    cases += [(1, 0, bank, 0) for bank in (0, 1)]
    cases += [(1, 0xffffffff, bank, 0) for bank in (0, 1)]
    for index, (started, sequence, bank, enabled) in enumerate(cases):
        initial = bytearray(((i * 37 + index * 19 + 11) & 255)
                            for i in range(GUARD_BYTES))
        at = BASE + bank * 0x400
        # Include ordinary ring feedback plus nonzero snapshot metadata/data.
        words = [0x4e52, sequence & 65535, 17, 0x8000 | (index * 3)]
        words += [((i * 0x3091 + index * 0x101 + 0x8123) & 65535)
                  for i in range(20)]
        for i, value in enumerate(words):
            offset = at - GUARD_BASE + 8 * i
            initial[offset + 3] = value >> 8
            initial[offset + 7] = value & 255
        u.mem_write(GUARD_BASE, bytes(initial))
        rt.w32(u, SELECTOR, bank)
        rt.w32(u, symbols['nhs_transport_started'], started)
        rt.w32(u, symbols['pk_nhr_sequence'], sequence)
        rt.w32(u, symbols['pk_nhr_enabled'], enabled)
        old_mail = bytes(((i * 13 + index + 0x55) & 255) for i in range(MAIL_BYTES))
        u.mem_write(symbols['pk_nhr_mail'], old_mail)
        before_reads, before_done = 0x12345678 + index, 0x87654321 + index
        rt.w32(u, symbols['pk_nhr_dma_reads'], before_reads)
        rt.w32(u, symbols['pk_nhr_dma_done'], before_done)
        rt.g.emu._call(u, symbols['pk_nhr_dma_step'])
        assert u.reg_read(rt.g.emu.UC_M68K_REG_D0) == 0
        expected = bytearray(initial)
        if started:
            for i in range(24):
                offset = at - GUARD_BASE + 8 * i
                expected[offset + 3] = expected[offset + 7] = 0
            want_mail = struct.pack('>24H', *words)
        else:
            want_mail = old_mail
        # Complete surrounding memory equality proves all non-carrier bytes,
        # the other ping bank, and both guards remain unchanged.
        assert bytes(u.mem_read(GUARD_BASE, GUARD_BYTES)) == bytes(expected), (index, 'carrier/stock byte mismatch')
        assert bytes(u.mem_read(symbols['pk_nhr_mail'], MAIL_BYTES)) == want_mail, (index, 'mail mismatch')
        assert rt.word(u, symbols['pk_nhr_dma_reads']) == before_reads + started
        assert rt.word(u, symbols['pk_nhr_dma_done']) == before_done + started
        assert rt.word(u, symbols['nhs_transport_started']) == started
        assert rt.word(u, symbols['pk_nhr_sequence']) == sequence
        assert rt.word(u, SELECTOR) == bank
        rows.append(dict(started=bool(started), sequence=sequence, bank=bank,
                         enabled=bool(enabled), extracted=bool(started),
                         exact_mail=True, carrier_cleared=bool(started),
                         stock_bytes_unchanged=True,
                         mail_sha256=hashlib.sha256(want_mail).hexdigest()))

    sources = [Path(__file__).resolve(), source,
               ROOT / 'tools/perky/build_perky_state_handoff.py',
               ROOT / 'tools/perky/generate_hat_state_handoff.py',
               ROOT / 'tools/harness/perky_cf/hat_state_handoff.h',
               ROOT / 'modules/perky/cf_noise_hat_handoff.c']
    for path in sources[1:]:
        key = str(path.relative_to(ROOT))
        assert key in build['source_sha256'], ('unbound compiled source', key)
        assert sha(path) == build['source_sha256'][key], ('source drift', key)
    result = dict(status=STATUS, image_sha256=sha(image), elf_sha256=sha(elf),
                  startup_no_extract=True, zero_sequence_extract=True,
                  exact_mail=True, carrier_cleared=True,
                  poisoned_startup_latch_reset=True,
                  actual_function='pk_nhr_dma_step', actual_function_address=symbols['pk_nhr_dma_step'],
                  instruction_hooks=False, target_code_repaired=False,
                  both_ping_banks=True, cf_owner_extraction=True,
                  cases=rows, source_sha256={str(path.relative_to(ROOT)): sha(path) for path in sources},
                  input_sha256={str(image): sha(image), str(elf): sha(elf)},
                  disassembly_sha256=sha(evidence / 'pk_nhr_dma_step.dis'),
                  limits=['Untimed actual-helper proof; whole-machine audio and timing are separate gates.'])
    (work / 'DMA_GATE.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
