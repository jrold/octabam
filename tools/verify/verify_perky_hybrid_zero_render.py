#!/usr/bin/env python3
"""Prove prepared empty renders are no-ops and compare callback boundaries.

Reference is the archived pre-iteration image, not a host approximation.
With no --candidate, perform only the reference no-op proof before editing.
"""
import argparse
import hashlib
import json
from pathlib import Path

import verify_perky_hybrid_runtime as runtime

ROOT = Path(__file__).resolve().parents[2]


def start(probe):
    r, syms = runtime.machine(probe/'mainos_PKHYB2P.bin', probe/'platform/runtime.elf', True)
    return r.uc, syms, runtime.sizes(probe/'platform/runtime.elf')


def state(u, syms, sizes):
    return bytes(u.mem_read(syms['pk_hybrid_voices'], sizes['pk_hybrid_voices']))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--candidate', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=1024)
    args = ap.parse_args()
    u, syms, sz = start(args.reference)
    call = runtime.g.emu._call
    noops = 0
    for frame in range(256):
        for inst in (0, 1):
            algo, mode = (frame // 3) % 3, frame % 3
            values = (inst, frame % 128, frame*13 % 128, frame*19 % 128,
                      frame*29 % 128, mode, algo, 255, 45, frame % 2)
            call(u, syms['pk_hybrid_cf_prepare_event'], values)
            # Both freshly prepared state and state after rendered samples.
            for count in (0, frame % 17):
                if count:
                    call(u, syms['pk_hybrid_cf_render_segment'], (inst, 0x80011000, count))
                before = state(u, syms, sz)
                u.mem_write(0x80011000, b'\xa5'*32)
                call(u, syms['pk_hybrid_cf_render_segment'], (inst, 0x80011000, 0))
                assert u.reg_read(runtime.g.emu.UC_M68K_REG_D0) == 1
                assert state(u, syms, sz) == before, ('empty render mutates state', frame, inst, algo, mode)
                assert bytes(u.mem_read(0x80011000, 32)) == b'\xa5'*32
                noops += 1
    result = {'status': 'PASS', 'prepared_reference_noop_cases': noops,
              'reference_image_sha256': runtime.digest(args.reference/'mainos_PKHYB2P.bin')}
    if args.candidate:
        u, syms, sz = start(args.reference)
        new, ns, nz = start(args.candidate)
        h = hashlib.sha256()
        callbacks = zero_callbacks = 0
        for frame in range(args.frames):
            split = frame % 17
            for track in (1, 5):
                vals = (24+frame % 80, 80+frame % 48,
                        (frame // 17+track) % 3, frame*13 % 128,
                        frame*19 % 128, frame // 11 % 3)
                for mu, symbols in ((u, syms), (new, ns)):
                    for k, v in enumerate(vals):
                        mu.mem_write(0x80008000+2*k, (v << 8).to_bytes(2, 'big'))
                    mu.mem_write(0x80001c90+0xa80+336*track, b'\x5a'*336)
                    runtime.w32(mu, 0x80001c80, 0x80010000)
                for ping, (start_at, end_at, trigger) in enumerate(
                        ((0, split, frame % 3 == 0), (split, 16, False))):
                    for mu, symbols in ((u, syms), (new, ns)):
                        mu.mem_write(0x46104d0c+track, bytes([16 if trigger else 0]))
                        call(mu, symbols['pk_render'], (track, ping, start_at, end_at))
                    assert state(u, syms, sz) == state(new, ns, nz), ('state/RNG', frame, track, start_at, end_at)
                    slot = 0x80001c90+0xa80+336*track
                    record = bytes(u.mem_read(slot, 336))
                    assert record == bytes(new.mem_read(slot, 336)), ('slot/prefix/tail', frame, track, start_at, end_at)
                    assert runtime.word(u, 0x80001c80) == runtime.word(new, 0x80001c80)
                    for name in ('pk_render_calls', 'pk_hits'):
                        assert runtime.word(u, syms[name]) == runtime.word(new, ns[name])
                    h.update(record); h.update(state(new, ns, nz))
                    callbacks += 1
                    zero_callbacks += start_at == end_at
        result.update(callbacks_compared=callbacks, zero_callbacks_compared=zero_callbacks,
                      split_offsets=17, frames=args.frames,
                      records_state_RNG_sha256=h.hexdigest(),
                      candidate_image_sha256=runtime.digest(args.candidate/'mainos_PKHYB2P.bin'))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
