#!/usr/bin/env python3
"""Merged-segment exactness on the actual CF image (PKFM22 and later).

V1-V3 on the target take the production pk_render decision: when the
target's placement_boundary_noop says the event boundary is a rendering
no-op, run the prepare and one 0..16 segment; otherwise render (0, split),
prepare, (split, 16). The independent host oracle always renders two
segments. Every frame compares PCM and the selected engine's raw state.

Controls hold for runs of frames so the merged path is exercised, and
change, trigger and switch algorithm/mode so the fallback path is exercised
too; each layout starts a new Part generation on both sides, as the source
gate does. Both counts must be non-zero.
"""
import argparse, ctypes as C, hashlib, json, os, struct, subprocess
from pathlib import Path
import verify_perky_hybrid_runtime as rt
from unicorn.m68k_const import UC_M68K_REG_D0

ROOT = rt.ROOT
W = Path(os.environ.get('PERKY_FULL_MAP_WORK', str(ROOT / 'out/perky/hybrid/full-map-merge-v1'))).resolve()
U32 = C.c_uint32
FIELDS = {0: 'fold1', 1: 'fold2', 2: 'karplus', 3: 'nt_m1', 4: 'res_snare', 5: 'nh', 6: 'sd', 7: 'cd',
          8: 'slap', 9: 'wt', 11: 'nt_shared', 12: 'res_bass', 13: 'res_nt'}
FAMILY = ((0, 9, 6), (1, 9, 7), (4, 8, 2))


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def physical(algo, mode):
    return 11 if algo == 3 and mode else 12 if algo == 4 and mode == 1 else 13 if algo == 4 and mode == 2 else algo


class Lcg:
    def __init__(self, seed): self.s = seed & 0xffffffff
    def __call__(self, n):
        self.s = (self.s * 1103515245 + 12345) & 0xffffffff
        return (self.s >> 8) % n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--frames', type=int, default=48, help='frames per layout and mode row')
    args = ap.parse_args()
    out = W / 'merged-gate'; out.mkdir(exist_ok=True)
    oracle = out / 'oracle.c'
    oracle.write_text('#include <stddef.h>\n#include <string.h>\n#include "cf_perky4.h"\n'
                      'extern pk4_engine placement_engine;\n'
                      'unsigned fm_raw(unsigned tr,unsigned algo,void*out){pk4_track*t=&placement_engine.tracks[tr];switch(algo){\n'
                      + ''.join(f'case {a}:memcpy(out,t->{f},sizeof(t->{f}));return sizeof(t->{f});\n' for a, f in FIELDS.items())
                      + '}return 0;}\n'
                      'void fm_rng(unsigned tr,unsigned*out){out[0]=placement_engine.tracks[tr].rng_low;out[1]=placement_engine.tracks[tr].rng_high;}\n')
    lib = out / 'oracle.dylib'; native_path = ROOT / 'out/perky/hybrid/cf-placement/native.dylib'
    subprocess.run(['cc', '-O3', '-shared', '-fPIC', '-I' + str(ROOT / 'modules/perky'), str(oracle), str(native_path),
                    '-o', str(lib)], check=True)
    native = C.CDLL(str(native_path)); oracle_lib = C.CDLL(str(lib))
    native.placement_prepare.argtypes = [U32, C.POINTER(U32), C.c_int]
    native.placement_segment.argtypes = [U32, U32, U32, U32]
    native.placement_bind.argtypes = [C.POINTER(C.c_void_p)]
    names = ('pitch', 'chromatic', 'envelope1', 'envelope2', 'w0', 'w1', 'w2', 'w3', 'm1', 'interp_a', 'interp_b',
             'wt_base', 'wt_bank', 'closed', 'open', 'ride')
    buffers = [C.create_string_buffer((ROOT / 'out/perky/hybrid/cf-placement/assets' / f'{n}.bin').read_bytes()) for n in names]
    native.placement_bind((C.c_void_p * 16)(*[C.addressof(b) for b in buffers]))
    output = (C.c_int32 * 64).in_dll(native, 'placement_output')
    version = json.loads((W / 'BUILD.json').read_text())['version']
    image = W / 'probe' / f'mainos_{version}.bin'; elf = image.parent / 'platform/runtime.elf'
    boot = rt.g.emu.boot; rt.g.emu.boot = lambda image: boot(image, count=200000000)
    r, s = rt.machine(image, elf, True); u = r.uc
    assert 'placement_boundary_noop' in s and 'placement_deferred' in s, 'not a merged-segment image'
    layout = out / 'offsets.c'
    layout.write_text('#include <stddef.h>\n#include <stdio.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\n'
                      'int main(void){' + ''.join(f'printf("{a} %zu\\n",offsetof(pk4_track,{f}));' for a, f in FIELDS.items()) + '}\n')
    subprocess.run(['cc', '-I' + str(ROOT / 'modules/perky'), str(layout), '-o', str(out / 'offsets')], check=True)
    offsets = {int(a): int(b) for a, b in (line.split() for line in subprocess.check_output([str(out / 'offsets')], text=True).splitlines())}
    stride = rt.word(u, s['placement_layout']); rng_off = rt.word(u, s['placement_layout'] + 28)
    raw_buffer = C.create_string_buffer(12000); rng_buffer = (U32 * 2)()

    def call(name, values):
        rt.g.emu._call(u, s[name], values)
        return u.reg_read(UC_M68K_REG_D0)

    counts = dict(merged=0, split=0, frames=0)
    rng = Lcg(0x5045524b)
    for layout_index in range(27):
        q = layout_index; algos = []
        for f in FAMILY:
            algos.append(f[q % 3]); q //= 3
        native.placement_init(); rt.w32(u, s['pk_prod_generation'], layout_index + 1)
        controls = [[96, 64, 64, 64] for _ in range(3)]
        for mode_row in range(3):
            modes = [(mode_row + tr) % 3 for tr in range(3)]
            for frame in range(args.frames):
                for tr in range(3):
                    event = rng(16)
                    if event == 0: controls[tr] = [rng(128) for _ in range(4)]
                    if event == 1: modes[tr] = rng(3)
                    if event == 2 and frame: algos[tr] = FAMILY[tr][rng(3)]
                    trig = int(frame == 0 or rng(11) == 0)
                    split = 0 if frame == mode_row == 0 else rng(16)
                    d, t, p1, p2 = controls[tr]
                    p = [algos[tr], modes[tr], d, t, p1, p2, 255, 45, split, trig]
                    vector = (U32 * 10)(*p)
                    u.mem_write(s['placement_inputs'] + 40 * tr, b''.join(v.to_bytes(4, 'big') for v in p))
                    at = s['placement_inputs'] + 40 * tr
                    assert native.placement_segment(tr, 0, split, 0)
                    assert native.placement_prepare(tr, vector, trig)
                    assert native.placement_segment(tr, split, 16, 1)
                    noop = split and call('placement_boundary_noop', (tr, at, trig)) & 0xffffffff
                    if noop:
                        assert call('placement_prepare', (tr, at, trig)) == 1
                        assert call('placement_segment', (tr, 0, 16, 0)) == 1
                        counts['merged'] += 1
                    else:
                        assert call('placement_segment', (tr, 0, split, 0)) == 1
                        assert call('placement_prepare', (tr, at, trig)) == 1
                        assert call('placement_segment', (tr, split, 16, 1)) == 1
                        counts['split'] += 1
                    actual = struct.unpack('>16i', u.mem_read(s['placement_output'] + 64 * tr, 64))
                    where = (layout_index, mode_row, frame, tr, bool(noop))
                    assert list(actual) == list(output[16 * tr:16 * (tr + 1)]), (where, 'PCM')
                    a = physical(algos[tr], modes[tr]); n = oracle_lib.fm_raw(tr, a, raw_buffer); raw = raw_buffer.raw[:n]
                    got = bytes(u.mem_read(s['placement_engine'] + tr * stride + offsets[a], n))
                    assert got == raw, (where, 'raw state', next((i for i, (x, y) in enumerate(zip(got, raw)) if x != y), None))
                    rng_words = struct.unpack('>2I', u.mem_read(s['placement_engine'] + tr * stride + rng_off, 8))
                    oracle_lib.fm_rng(tr, rng_buffer); assert list(rng_words) == list(rng_buffer), (where, 'voice RNG')
                    counts['frames'] += 1
        print('layout', layout_index + 1, '/ 27', counts, flush=True)
    assert counts['merged'] and counts['split'], counts
    result = dict(status='PASS_ACTUAL_IMAGE_MERGED_SEGMENT_PCM_AND_STATE', counts=counts,
                  frames_per_layout_row=args.frames, image_sha256=sha(image), elf_sha256=sha(elf),
                  inputs={str(native_path): sha(native_path), str(lib): sha(lib)},
                  source_sha256={str(Path(__file__).resolve().relative_to(ROOT)): sha(Path(__file__).resolve())},
                  limits=['Direct executed calls of the production predicate, prepare and segment; the integrated pk_render path is covered by sustained workloads.',
                          'V4 keeps two segments and is outside this gate.'])
    (W / 'MERGED_GATE.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], counts)


if __name__ == '__main__':
    main()
