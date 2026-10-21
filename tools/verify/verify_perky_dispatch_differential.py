#!/usr/bin/env python3
"""Differential pk_render gate: a candidate image against a reference image.

Both images run under the same Unicorn harness with identical scripted stock
inputs: per-track source slots, trigger bytes, event splits, the stock packet
cursor and occasional Part changes. Each frame calls pk_render for T1, T2, T5
and T6 exactly as the stock loop does: (0, split), then (split, 16).

After every frame the gate compares every placement_*, pk_prod_*, pk_nh* and
fm_* data object of the reference (except the candidate-only deferral
marker), the source output, both packet pings and the cleared cursor block.
Any byte difference fails with its object and offset.
"""
import argparse, hashlib, json, subprocess
from pathlib import Path
import verify_perky_hybrid_runtime as rt

ROOT = rt.ROOT
PERKY_TRACKS = (0, 1, 4, 5)
SLOTS = dict(tune=0, decay=1, algo=2, p1=3, p2=4, mode=5)
BANK, PART_IDX, PART_OFF, PART_STRIDE = 0x46c82456, 0x100b14cf, 0x8ed80, 0x18b2
SLOT_BASE, PING_BYTES = 0x80001c90, 0xa80
CURSOR = 0x80010000
EXCLUDE = {'placement_deferred', 'placement_trace', 'placement_trace_enabled'}


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Lcg:
    def __init__(self, seed): self.s = seed & 0xffffffff
    def __call__(self, n):
        self.s = (self.s * 1103515245 + 12345) & 0xffffffff
        return (self.s >> 8) % n


def data_objects(elf):
    rows = subprocess.check_output(['m68k-elf-nm', '-S', str(elf)], text=True)
    out = {}
    for line in rows.splitlines():
        f = line.split()
        if len(f) == 4 and f[2] in 'bBdD' and f[3].startswith(('placement_', 'pk_prod_', 'pk_nh', 'fm_')):
            if f[3] not in EXCLUDE:
                out[f[3]] = int(f[1], 16)
    return out


def symbol_map(elf):
    """Sorted runtime symbol starts, so a pointer compares as (symbol, offset)."""
    rows = subprocess.check_output(['m68k-elf-nm', '-n', str(elf)], text=True)
    starts = [(int(f[0], 16), f[2]) for line in rows.splitlines() if len(f := line.split()) == 3
              and f[1] in 'tTbBdDrR' and int(f[0], 16) >= 0x40c00000]
    return [a for a, _ in starts], [n for _, n in starts]


def pointer(word, table):
    import bisect
    starts, names = table
    if not starts or word < starts[0] or word >= 0x41000000:
        return None
    i = bisect.bisect_right(starts, word) - 1
    return names[i], word - starts[i]


def same_after_pointers(x, y, tables):
    """True when every differing byte lies in a word that is the same symbol+offset in both."""
    i = 0
    while i < len(x):
        if x[i] == y[i]:
            i += 1; continue
        ok = False
        for start in range(max(0, i - 3), i + 1):
            if start + 4 > len(x): continue
            p = pointer(int.from_bytes(x[start:start + 4], 'big'), tables[0])
            q = pointer(int.from_bytes(y[start:start + 4], 'big'), tables[1])
            if p and p == q:
                i = start + 4; ok = True; break
        if not ok:
            return i
    return None


def boot(build):
    version = json.loads((build / 'BUILD.json').read_text())['version']
    image = build / 'probe' / f'mainos_{version}.bin'; elf = image.parent / 'platform/runtime.elf'
    r, s = rt.machine(image, elf, True); u = r.uc
    part0 = rt.word(u, BANK) + PART_OFF
    for part in range(4):
        base = part0 + part * PART_STRIDE
        for track in PERKY_TRACKS:
            u.mem_write(base + 0x22 + track, b'\x01')
            u.mem_write(base + 60 + 30 * track, b'PK\x02')
    return u, s, image, elf


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference', type=Path, default=ROOT / 'out/perky/hybrid/full-map-stock-cf-v1')
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=1500)
    args = ap.parse_args()
    boot_fn = rt.g.emu.boot; rt.g.emu.boot = lambda image: boot_fn(image, count=200000000)
    machines = [boot(args.reference.resolve()), boot(args.candidate.resolve())]
    objects = data_objects(machines[0][3])
    tables = [symbol_map(m[3]) for m in machines]
    hits = {}
    cu, cs = machines[1][0], machines[1][1]
    for name in ('placement_merge_apply', 'placement_segment', 'pk_hybrid_render_general', 'placement_v4_merge_eligible'):
        if name in cs:
            hits[name] = 0
            def hook(uc, address, size, data, name=name): hits[name] += 1
            cu.hook_add(rt.UC_HOOK_CODE, hook, begin=cs[name], end=cs[name])
    if 'placement_segment' in cs:
        from unicorn.m68k_const import UC_M68K_REG_A7
        hits['whole_frame_segments'] = {}
        def whole(uc, address, size, data):
            sp = uc.reg_read(UC_M68K_REG_A7)
            tr, start, end = (rt.word(uc, sp + 4 + 4 * i) for i in range(3))
            if (start, end) == (0, 16): hits['whole_frame_segments'][str(tr)] = hits['whole_frame_segments'].get(str(tr), 0) + 1
        cu.hook_add(rt.UC_HOOK_CODE, whole, begin=cs['placement_segment'], end=cs['placement_segment'])
    missing = [n for n in objects if n not in machines[1][1]]
    assert not missing, ('candidate lacks reference objects', missing)
    rng = Lcg(0x44495350)
    local_algo = {t: 0 for t in PERKY_TRACKS}; modes = {t: 0 for t in PERKY_TRACKS}
    controls = {t: [96, 64, 64, 64] for t in PERKY_TRACKS}
    counts = dict(frames=0, trigs=0, part_changes=0, zero_splits=0)
    part = 0
    for frame in range(args.frames):
        if frame and rng(240) == 0:
            part = (part + 1 + rng(3)) & 3; counts['part_changes'] += 1
        plan = []
        for track in PERKY_TRACKS:
            event = rng(14)
            if event == 0: controls[track] = [rng(128) for _ in range(4)]
            if event == 1: modes[track] = rng(3)
            if event == 2: local_algo[track] = rng(2 if track == 5 else 3)
            trig = frame % 64 == track or rng(13) == 0
            split = rng(16)
            counts['trigs'] += trig; counts['zero_splits'] += split == 0
            plan.append((track, trig, split))
        for u, s, _, _ in machines:
            u.mem_write(PART_IDX, bytes([part]))
            for track, trig, split in plan:
                d, t, p1, p2 = controls[track]
                values = {SLOTS['tune']: t, SLOTS['decay']: d, SLOTS['algo']: local_algo[track],
                          SLOTS['p1']: p1, SLOTS['p2']: p2, SLOTS['mode']: modes[track]}
                for k, v in values.items(): u.mem_write(0x80008000 + 2 * k, (v << 8).to_bytes(2, 'big'))
                rt.w32(u, 0x800062a8, 0x80008000)
                u.mem_write(0x46104d0c + track, bytes([16 if trig else 0]))
                rt.w32(u, 0x80001c80, CURSOR)
                rt.g.emu._call(u, s['pk_render'], (track, frame & 1, 0, split))
                u.mem_write(0x46104d0c + track, b'\0')
                rt.w32(u, 0x80001c80, CURSOR)
                rt.g.emu._call(u, s['pk_render'], (track, (frame + 1) & 1, split, 16))
        (ua, sa, _, _), (ub, sb, _, _) = machines
        regions = [(name, sa[name], sb[name], size) for name, size in objects.items()]
        regions += [('packet slots', SLOT_BASE, SLOT_BASE, 2 * PING_BYTES), ('cleared cursor block', CURSOR, CURSOR, 0x200)]
        for name, a, b, size in regions:
            x, y = bytes(ua.mem_read(a, size)), bytes(ub.mem_read(b, size))
            if x != y:
                at = same_after_pointers(x, y, tables)
                if at is not None:
                    raise AssertionError((frame, name, 'offset', at, x[at:at + 8].hex(), y[at:at + 8].hex()))
                counts['pointer_normalized'] = counts.get('pointer_normalized', 0) + 1
        counts['frames'] += 1
        if frame % 250 == 249: print('frames', frame + 1, counts, hits, flush=True)
    result = dict(status='PASS_DISPATCH_DIFFERENTIAL_ALL_PLACEMENT_PRODUCTION_HAT_STATE_PACKETS',
                  counts=counts, candidate_entries=hits, compared_objects=sorted(objects),
                  reference=dict(image_sha256=sha(machines[0][2]), elf_sha256=sha(machines[0][3])),
                  candidate=dict(image_sha256=sha(machines[1][2]), elf_sha256=sha(machines[1][3])),
                  source_sha256={str(Path(__file__).resolve().relative_to(ROOT)): sha(Path(__file__).resolve())},
                  limits=['Unicorn harness with the dispatcher profiler off (rt.machine); V4 Hat transport runs without DSP mail.',
                          'Stock tracks are not called; the stock loop order is reproduced for the four PERKY tracks only.'])
    out = args.candidate.resolve() / 'DISPATCH_DIFFERENTIAL.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], counts, hits)


if __name__ == '__main__':
    main()
