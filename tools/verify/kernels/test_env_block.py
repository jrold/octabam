#!/usr/bin/env python3
"""Exhaustive-style random test of modules/perky/cf_env_block.s on cf_cycle_bench.

An independent Python model of the shared C envelope step (wt_env_step /
nt_lin_step / slap_env) is the oracle. Covers every state byte class, all
flag combinations, rates that wrap, v at and around every threshold, both
output modes, the curve's last-interval wrap and n = 0..20.
"""
import random, struct, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / 'out/perky/hybrid/cf-cycle-bench/cf_cycle_bench'  # tools/harness/perky_cf/build_cf_cycle_bench.sh
M = 0xffffffff


def s32(x): x &= M; return x - (1 << 32) if x & 0x80000000 else x


def model(v, st, up, dn, curve, flags, n):
    f4, f6, f7, f10 = flags & 1, flags & 2, flags & 4, flags & 8
    out = []
    for _ in range(n):
        if st == 0:
            if f7 or f4: st = 1
        elif st == 1:
            v = s32(v + up)
            if v > 0xffffe:
                st = 4 if (f4 or f6) else 3
                if v >= 0x100000: v = 0xfffff
        elif st == 3:
            if not f7 and (f4 or not f10): st = 4
        elif st == 4:
            if f7: st = 1
            else:
                v = s32(v - dn)
                if v <= 0: v = 0; st = 1 if f4 else 0
        u = v & M
        if curve is None:
            out.append((u >> 4) & 0xffff)
        else:
            i = (u >> 10) & 0x7ff; j = (i + 1) & 0x7ff; f = u & 0x3ff
            a, z = curve[i], curve[j]
            p = s32((z - a) * f)
            out.append((a + (p >> 10)) & 0xffff)
    return v, st, out


def main():
    rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    curve = [rng.randrange(65536) for _ in range(2048)]
    curve[2047] = 0x1234; curve[0] = 0xfedc
    special = [0, 1, 0xffffe, 0xfffff, 0x100000, 0x100001, 0x7fffffff, 0x80000000, 0xffffffff, 0x3ff, 0x400, 0x1ffc00, 0x1ffbff]
    cases = []
    for k in range(count):
        st = rng.choice([0, 1, 2, 3, 4, 4, 4, 1, 1, 5, 255])
        v = rng.choice(special) if rng.random() < 0.3 else rng.choice([rng.randrange(0x100000), rng.randrange(1 << 32)])
        up = rng.choice([0, 1, 0x3ff, 0x400, 0x7fff, 0xffff, rng.randrange(1 << 16), rng.randrange(1 << 32)])
        dn = rng.choice([0, 1, 0x3ff, 0x400, 0x7fff, 0xffff, rng.randrange(1 << 16), rng.randrange(1 << 32)])
        flags = rng.randrange(16)
        lin = rng.random() < 0.35
        n = rng.choice([0, 1, 2, 16, 17, 18, 20, rng.randrange(21)])
        cases.append((v & M, st, up, dn, lin, flags, n))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        table = b''.join(struct.pack('<H', c) for c in curve)
        (tmp / 'curve.bin').write_bytes(table)
        blob = b''.join(struct.pack('>7I', v, st, up, dn, 0 if lin else 0x500000, flags, n) for v, st, up, dn, lin, flags, n in cases)
        (tmp / 'cases.bin').write_bytes(blob)
        src = ROOT / 'tools/verify/kernels/env_block_driver.s'
        env = ROOT / 'modules/perky/cf_env_block.s'
        for s, o in ((src, 'd.o'), (env, 'e.o')):
            subprocess.run(['m68k-elf-as', '-mcpu=54455', str(s), '-o', str(tmp / o)], check=True)
        subprocess.run(['m68k-elf-ld', '-Ttext=0x10000', '-e', '_start', str(tmp / 'd.o'), str(tmp / 'e.o'), '-o', str(tmp / 'a.elf')], check=True)
        subprocess.run(['m68k-elf-objcopy', '-O', 'binary', str(tmp / 'a.elf'), str(tmp / 'a.bin')], check=True)
        setup = [f'long 0x2ffffc {len(cases)}', f'mem 0x300000 {tmp / "cases.bin"}', f'mem 0x500000 {tmp / "curve.bin"}',
                 f'dump 0x300000 {28 * len(cases)}', f'dump 0x400000 {40 * len(cases)}']
        (tmp / 'setup.txt').write_text('\n'.join(setup) + '\n')
        out = subprocess.run([str(BENCH), str(tmp / 'a.bin'), str(tmp / 'setup.txt')], capture_output=True, text=True)
        import json
        res = json.loads(out.stdout.strip().splitlines()[-1])
        assert res['unhandled'] == 0, res
        ctx = bytes.fromhex(res['dumps'][0]); outs = bytes.fromhex(res['dumps'][1])
    bad = 0; samples = 0
    for k, (v, st, up, dn, lin, flags, n) in enumerate(cases):
        wv, wst, wout = model(s32(v), st, up, dn, None if lin else curve, flags, n)
        gv, gst = struct.unpack('>2I', ctx[28 * k:28 * k + 8])
        gout = list(struct.unpack(f'>{n}H', outs[40 * k:40 * k + 2 * n]))
        samples += n
        if (gv, gst, gout) != (wv & M, wst, wout):
            bad += 1
            if bad <= 5: print('MISMATCH', k, dict(v=hex(v), st=st, up=hex(up), dn=hex(dn), lin=lin, flags=flags, n=n), 'got', hex(gv), gst, gout[:6], 'want', hex(wv & M), wst, wout[:6])
    print(f'cases {len(cases)} samples {samples} mismatches {bad} cycles {res["cycles"]} instructions {res["instructions"]} mispredicts {res["mispredicts"]}')
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
