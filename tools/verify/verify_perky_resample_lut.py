#!/usr/bin/env python3
"""Prove rational LUT interpolation and the actual ColdFire helper/ABI.

Before integration, load a separately linked helper once at a fresh address.
With --linked, execute the exact function in the candidate runtime instead.
Neither path rewrites translated instructions or installs code hooks.
"""
import argparse
import ctypes as C
import hashlib
import json
import random
import struct
import subprocess
import sys
from pathlib import Path

import verify_perky_hybrid_runtime as rt
import unicorn.m68k_const as reg

ROOT = rt.ROOT
sys.path.insert(0, str(ROOT / 'tools/perky'))
import generate_cf_resample_lut as generator


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Clock(C.Structure):
    _fields_ = [('phase', C.c_uint32), ('have', C.c_uint32), ('carry', C.c_int32)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build', type=Path, default=ROOT / 'out/perky/hybrid/full-map-state-v4')
    ap.add_argument('--work', type=Path, default=ROOT / 'out/perky/hybrid/resample-lut-v1')
    ap.add_argument('--linked', action='store_true')
    args = ap.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = generator.generate(work)
    reference = work / 'reference.c'
    reference.write_text('''#include "cf_native_clock.h"
void reference(pk_cf_native_clock*c,const int16_t*d,unsigned n,int32_t*out){pk_cf_native_convert(c,d,n,out);}
int proof(void){
 for(int32_t d=-65535;d<=65535;d++)for(int64_t p=0;p<147;p++){
  int64_t sign=d<0?-1:0, a=d<0?-(int64_t)d:d;
  int64_t c=(p*32*(1LL<<26)+146)/147+sign;
  int64_t product=(a<<5)*c;
  int64_t q=product>=0?product/(1LL<<31):-((-product+(1LL<<31)-1)/(1LL<<31));
  q^=sign;
  int64_t n=(int64_t)d*32*p;
  int64_t expected=n>=0?n/147:-((-n+146)/147);
  if(q!=expected)return 1;
 }return 0;
}
''')
    lib = work / 'reference.dylib'
    subprocess.run(['cc', '-O3', '-shared', '-fPIC', '-I' + str(ROOT / 'modules/perky'),
                    str(reference), '-o', str(lib)], check=True)
    native = C.CDLL(str(lib))
    assert native.proof() == 0, 'exhaustive rational quotient'
    build = args.build.resolve()
    receipt = json.loads((build / 'BUILD.json').read_text())
    image = build / 'probe' / ('mainos_' + receipt['version'] + '.bin')
    elf = build / 'probe/platform/runtime.elf'
    boot = rt.g.emu.boot
    rt.g.emu.boot = lambda image: boot(image, count=200000000)
    r, symbols = rt.machine(image, elf, True)
    u = r.uc
    if not any(lo <= 0x48000000 and hi >= 0x480fffff for lo, hi, _ in u.mem_regions()):
        u.mem_map(0x48000000, 0x100000)
    if args.linked:
        entry = symbols['pk_nhb_native_convert_fast']
        assert receipt['source_sha256'][str(build.relative_to(ROOT) / source.name)] == sha(source)
        helper_elf = elf
    else:
        helper_elf = work / 'helper.elf'
        subprocess.run(['m68k-elf-gcc', '-mcpu=54455', '-nostdlib', '-Wl,-Ttext=0x480c0000',
                        '-Wl,--entry=pk_nhb_native_convert_fast', str(source), '-o', str(helper_elf)], check=True)
        binary = work / 'helper.bin'
        subprocess.run(['m68k-elf-objcopy', '-O', 'binary', str(helper_elf), str(binary)], check=True)
        u.mem_write(0x480c0000, binary.read_bytes())
        entry = 0x480c0000
    disassembly = subprocess.check_output(['m68k-elf-objdump', '-d', str(helper_elf)], text=True)
    (work / 'helper-disassembly.txt').write_text(disassembly)
    canary = work / 'canary.s'
    canary.write_text('''.text
.globl seed
seed:
 move.l #0,%macsr
 move.l 8(%sp),%d0
 move.l %d0,%acc0
 move.l 12(%sp),%d0
 move.l %d0,%accext01
 move.l 4(%sp),%d0
 move.l %d0,%macsr
 rts
.globl readback
readback:
 move.l 4(%sp),%a0
 move.l %macsr,%d0
 move.l %d0,(%a0)+
 move.l #0,%macsr
 move.l %acc0,%d1
 move.l %d1,(%a0)+
 move.l %accext01,%d1
 move.l %d1,(%a0)+
 move.l %d0,%macsr
 rts
''')
    subprocess.run(['m68k-elf-gcc', '-mcpu=54455', '-nostdlib', '-Wl,-Ttext=0x480e0000',
                    '-Wl,--entry=seed', str(canary), '-o', str(work / 'canary.elf')], check=True)
    subprocess.run(['m68k-elf-objcopy', '-O', 'binary', str(work / 'canary.elf'),
                    str(work / 'canary.bin')], check=True)
    u.mem_write(0x480e0000, (work / 'canary.bin').read_bytes())
    symbols_canary = {x[2]: int(x[0], 16) for line in subprocess.check_output(
        ['m68k-elf-nm', str(work / 'canary.elf')], text=True).splitlines() if len(x := line.split()) == 3}
    rng = random.Random(0x52534c54)
    canaries = {getattr(reg, f'UC_M68K_REG_{p}{k}'): 0x12340000 + 16 * k
                for p, ks in (('D', range(2, 8)), ('A', range(2, 7))) for k in ks}
    count = 0
    audio_hash = hashlib.sha256()
    for phase in range(147):
        for n in range(17):
            for kind in range(4):
                data = [-32768 if kind == 0 else 32767 if kind == 1 else
                        (-32768 if i % 2 else 32767) if kind == 2 else rng.randrange(-32768, 32768)
                        for i in range(20)]
                clock = Clock(phase, kind & 1, rng.randrange(-32768, 32768))
                initial = (clock.phase, clock.have, clock.carry)
                expected = (C.c_int32 * 16)()
                native.reference(C.byref(clock), (C.c_int16 * 20)(*data), n, expected)
                c, d, o = 0x48000020, 0x48001020, 0x48002020
                u.mem_write(c, struct.pack('>IIi', *initial))
                u.mem_write(d, struct.pack('>20h', *data))
                u.mem_write(o - 16, b'\xa5' * (4 * n + 32))
                rt.g.emu._call(u, symbols_canary['seed'],
                               ((0, 0x20, 0x40, 0x60, 0x80, 0xf0)[count % 6],
                                rng.randrange(1 << 32), rng.randrange(1 << 32)))
                rt.g.emu._call(u, symbols_canary['readback'], (0x48003000,))
                emac = bytes(u.mem_read(0x48003000, 12))
                for k, v in canaries.items():
                    u.reg_write(k, v)
                rt.g.emu._call(u, entry, (c, d, n, o))
                assert all(u.reg_read(k) == v for k, v in canaries.items()), (phase, n, kind, 'ABI')
                rt.g.emu._call(u, symbols_canary['readback'], (0x48003000,))
                assert bytes(u.mem_read(0x48003000, 12)) == emac, (phase, n, kind, 'EMAC')
                assert bytes(u.mem_read(c, 12)) == struct.pack('>IIi', clock.phase, clock.have, clock.carry), (phase, n, kind, 'clock')
                wanted = b'\xa5' * 16 + b''.join((x & 0xffffffff).to_bytes(4, 'big') for x in expected[:n]) + b'\xa5' * 16
                actual = bytes(u.mem_read(o - 16, 4 * n + 32))
                assert actual == wanted, (phase, n, kind, 'PCM/guard')
                audio_hash.update(actual)
                count += 1
    result = dict(status='PASS_EXACT_RATIONAL_LUT_SOURCE_PCM_CLOCK_EMAC_ABI',
                  exhaustive_difference_phase_cases=131071 * 147, actual_CF_cases=count,
                  linked_candidate=args.linked, image_sha256=sha(image), elf_sha256=sha(elf),
                  helper_elf_sha256=sha(helper_elf), PCM_sha256=audio_hash.hexdigest(),
                  source_sha256={str(p.relative_to(ROOT)): sha(p) for p in
                                 (Path(__file__).resolve(), Path(generator.__file__),
                                  ROOT / 'modules/perky/production_resample.s',
                                  ROOT / 'modules/perky/cf_native_clock.h', reference, canary, source)})
    (work / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], count, result['exhaustive_difference_phase_cases'])


if __name__ == '__main__':
    main()
