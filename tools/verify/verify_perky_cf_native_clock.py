#!/usr/bin/env python3
"""Exhaust the CF adapter's phase/segment space against the rational oracle."""
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/perky'))
from source_clock import Clock


class State(ctypes.Structure):
    _fields_ = [('phase', ctypes.c_uint32), ('have', ctypes.c_uint32),
                ('carry', ctypes.c_int32)]


def main():
    work = ROOT / 'out/perky/hybrid/cf-placement/clock'
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'adapter.c'
    source.write_text('''#include "cf_native_clock.h"
unsigned needed(pk_cf_native_clock *c,unsigned n){return pk_cf_native_needed(c,n);}
void convert(pk_cf_native_clock *c,const int16_t *p,unsigned n,int32_t *o){pk_cf_native_convert(c,p,n,o);}
void reset(pk_cf_native_clock *c){pk_cf_native_reset(c);}
''')
    library = work / 'adapter.dylib'
    subprocess.run(['cc', '-std=c11', '-O3', '-shared', '-fPIC', '-Wall', '-Wextra',
                    '-Werror', '-I', str(ROOT / 'modules/perky'), str(source),
                    '-o', str(library)], check=True)
    dll = ctypes.CDLL(str(library))
    dll.needed.argtypes = [ctypes.POINTER(State), ctypes.c_uint]
    dll.needed.restype = ctypes.c_uint
    dll.convert.argtypes = [ctypes.POINTER(State), ctypes.POINTER(ctypes.c_int16),
                            ctypes.c_uint, ctypes.POINTER(ctypes.c_int32)]
    dll.reset.argtypes = [ctypes.POINTER(State)]
    count = 0
    # Include fresh post-reset phases as well as steady-state carried phases.
    for phase in range(147):
        for have in sorted({0, int(phase >= 13)}):
            for n in range(17):
                for pattern in range(4):
                    oracle = Clock()
                    oracle.phase = phase
                    oracle.tail = [-32768] if have else []
                    state = State(phase, have, -32768 if have else 0)
                    needed = oracle.needed(n)
                    assert dll.needed(ctypes.byref(state), n) == needed
                    pcm = [((i * 7919 + phase * 31) % 65536) - 32768
                           if pattern == 0 else (-32768 if pattern == 1 else
                                                32767 if pattern == 2 else
                                                (-32768 if i % 2 else 32767))
                           for i in range(needed)]
                    data = oracle.tail + pcm
                    native = (ctypes.c_int16 * max(1, len(data)))(*data)
                    output = (ctypes.c_int32 * max(1, n))()
                    expected = oracle.render(pcm, n)
                    dll.convert(ctypes.byref(state), native, n, output)
                    assert list(output)[:n] == expected, (phase, have, n, pattern)
                    assert state.phase == oracle.phase
                    assert state.have == len(oracle.tail)
                    assert state.carry == (oracle.tail[0] if oracle.tail else 0)
                    dll.reset(ctypes.byref(state))
                    assert (state.phase, state.have, state.carry) == (0, 0, 0)
                    count += 1
    result = dict(status='PASS', cases=count,
                  header_sha256=hashlib.sha256((ROOT / 'modules/perky/cf_native_clock.h').read_bytes()).hexdigest(),
                  scope='Host C arithmetic, all 147 phases and segment lengths 0..16; target execution is covered separately by the placement matrix.')
    (work / 'CLOCK.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
