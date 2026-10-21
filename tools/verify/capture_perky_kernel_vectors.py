#!/usr/bin/env python3
"""Capture real kernel test vectors from an actual CF image under Unicorn.

Drives the production pk_render for T1, T2, T5 and T6 in stock loop order
(chunk 1, chunk 2) with scripted controls, triggers, algorithm and mode
changes, and hooks one renderer's entry and return. Each vector records the
renderer's arguments, the bytes of its object and RNG before the call, and
the PCM and object/RNG bytes after it. A replacement kernel must reproduce
every vector exactly.

Kernels and the object bytes they own:
  wt    pk_cf_wt_render(uint8_t*s, int16_t*d, uint32_t n, const tables*)
  slap  pk_cf_slap_render(uint8_t*s, int16_t*d, uint32_t n, tables*, rng*)
  nt    pk_cf_nt_shared_render(uint8_t*s, int16_t*d, uint32_t n, tables*, rng*)
"""
import argparse, json, struct
from pathlib import Path
import verify_perky_hybrid_runtime as rt
from unicorn import UC_HOOK_CODE

ROOT = rt.ROOT
KERNELS = {
    'wt': dict(symbol='pk_cf_wt_render', state=0x150, rng=None,
               voices={0: (1,), 1: (1,)}),                  # local ALGO 1 = Wavetable on T1/T2
    'slap': dict(symbol='pk_cf_slap_render', state=0x2670, rng=4,
                 voices={2: (1,)}),                          # local ALGO 1 = Slap on T5
    'nt': dict(symbol='pk_cf_nt_shared_render', state=0x100, rng=4,
               voices={3: (1,)}),                            # local ALGO 1 = Noise/Tone on T6
}
TRACKS = (0, 1, 4, 5)
SLOTS = dict(tune=0, decay=1, algo=2, p1=3, p2=4, mode=5)


class Lcg:
    def __init__(self, seed): self.s = seed & 0xffffffff
    def __call__(self, n):
        self.s = (self.s * 1103515245 + 12345) & 0xffffffff
        return (self.s >> 8) % n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build', type=Path, default=ROOT / 'out/perky/hybrid/full-map-merge-v1')
    ap.add_argument('--kernel', choices=sorted(KERNELS), required=True)
    ap.add_argument('--frames', type=int, default=600)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    k = KERNELS[args.kernel]
    build = args.build.resolve()
    version = json.loads((build / 'BUILD.json').read_text())['version']
    image = build / 'probe' / f'mainos_{version}.bin'; elf = image.parent / 'platform/runtime.elf'
    boot_fn = rt.g.emu.boot; rt.g.emu.boot = lambda i: boot_fn(i, count=200000000)
    r, s = rt.machine(image, elf, True); u = r.uc
    part0 = rt.word(u, 0x46c82456) + 0x8ed80
    for part in range(4):
        for track in TRACKS:
            u.mem_write(part0 + part * 0x18b2 + 0x22 + track, b'\x01')
            u.mem_write(part0 + part * 0x18b2 + 60 + 30 * track, b'PK\x02')
    vectors, pending, table_words = [], [], []
    entry = s[k['symbol']]

    from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0
    import re, subprocess
    dis = subprocess.check_output(['m68k-elf-objdump', '-d', str(elf)], text=True)
    returns = [int(m.group(1), 16) + 6 for m in re.finditer(r'^([0-9a-f]+):\s+4eb9 [0-9a-f]{4} [0-9a-f]{4} \s+jsr [0-9a-f]+ <' + k['symbol'] + r'>', dis, re.M)]
    assert returns, ('no call sites', k['symbol'])

    def hook_entry(uc, address, size, data):
        sp = uc.reg_read(UC_M68K_REG_A7)
        ret = rt.word(uc, sp)
        a = [rt.word(uc, sp + 4 + 4 * i) for i in range(5)]
        st, dst, n = a[0], a[1], a[2]
        rec = dict(args=a, n=n, state_in=bytes(uc.mem_read(st, k['state'])).hex(), ret=ret, sp=sp)
        if k['rng']:
            rec['rng_in'] = bytes(uc.mem_read(a[k['rng']], 8)).hex()
        count = dict(wt=5, slap=11, nt=10)[args.kernel]
        words = [rt.word(uc, a[3] + 4 * i) for i in range(count)]
        if not table_words: table_words.extend(words)
        assert words == table_words, ('table struct changed', words, table_words)
        pending.append(rec)

    def hook_return(uc, address, size, data):
        sp = uc.reg_read(UC_M68K_REG_A7)
        if pending and address == pending[-1]['ret'] and sp == pending[-1]['sp'] + 4:
            rec = pending.pop()
            st, dst, n = rec['args'][0], rec['args'][1], rec['n']
            rec['pcm_out'] = bytes(uc.mem_read(dst, 2 * n)).hex()
            rec['state_out'] = bytes(uc.mem_read(st, k['state'])).hex()
            rec['result'] = uc.reg_read(UC_M68K_REG_D0)
            if k['rng']:
                rec['rng_out'] = bytes(uc.mem_read(rec['args'][k['rng']], 8)).hex()
            vectors.append(rec)

    u.hook_add(UC_HOOK_CODE, hook_entry, begin=entry, end=entry)
    for at in returns:
        u.hook_add(UC_HOOK_CODE, hook_return, begin=at, end=at)
    rng = Lcg(args.seed * 7919 + len(args.kernel))
    local = {t: 0 for t in TRACKS}; modes = {t: 0 for t in TRACKS}; controls = {t: [96, 64, 64, 64] for t in TRACKS}
    voice_of = {0: 0, 1: 1, 4: 2, 5: 3}
    for t in TRACKS:
        v = voice_of[t]
        if v in k['voices']: local[t] = k['voices'][v][0]
    for frame in range(args.frames):
        plan = []
        for t in TRACKS:
            v = voice_of[t]
            event = rng(18)
            if event == 0: controls[t] = [rng(128) for _ in range(4)]
            if event == 1: modes[t] = rng(3)
            if event == 2 and v not in k['voices']: local[t] = rng(2 if t == 5 else 3)
            if event == 3 and v in k['voices'] and frame % 97 == 0: local[t] = rng(3) if t != 5 else rng(2)
            if v in k['voices'] and frame % 97 == 5: local[t] = k['voices'][v][0]
            trig = frame % 48 == t or rng(17) == 0
            plan.append((t, trig, rng(16)))
        for t, trig, split in plan:
            d, tu, p1, p2 = controls[t]
            values = {SLOTS['tune']: tu, SLOTS['decay']: d, SLOTS['algo']: local[t], SLOTS['p1']: p1, SLOTS['p2']: p2, SLOTS['mode']: modes[t]}
            for idx, val in values.items(): u.mem_write(0x80008000 + 2 * idx, (val << 8).to_bytes(2, 'big'))
            rt.w32(u, 0x800062a8, 0x80008000)
            u.mem_write(0x46104d0c + t, bytes([16 if trig else 0]))
            rt.w32(u, 0x80001c80, 0x80010000)
            rt.g.emu._call(u, s['pk_render'], (t, frame & 1, 0, split))
            u.mem_write(0x46104d0c + t, b'\0')
            rt.w32(u, 0x80001c80, 0x80010000)
            rt.g.emu._call(u, s['pk_render'], (t, (frame + 1) & 1, split, 16))
    tables = {}
    if vectors:
        # The table struct the kernel reads and every region it points at,
        # dumped beside the vectors (BSS assets are decoded at boot).
        tp = vectors[0]['args'][3]
        words = table_words
        tables = dict(struct_at=tp, words=words, regions={})
        for w in sorted(set(words)):
            if 0x40c00000 <= w < 0x42000000:
                size = 0x30000 if args.kernel == 'wt' and w == words[4] else 0x2000
                path = args.out.with_suffix(f'.{w:08x}.bin')
                path.write_bytes(bytes(u.mem_read(w, size)))
                tables['regions'][f'{w:#x}'] = str(path)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dict(kernel=args.kernel, image=str(image), elf=str(elf), tables=tables,
                                        vectors=vectors), indent=0) + '\n')
    print(args.kernel, 'vectors', len(vectors), 'n values', sorted({v['n'] for v in vectors}))


if __name__ == '__main__':
    main()
