#!/usr/bin/env python3
"""Host-test the exact production BSS scrub helper, without firmware/CI.

Extract the two C helpers directly from the hybrid source, not copies of their
algorithms, so changed code is what GCC/Clang actually execute. Also verify
that boot_init clears BSS *before* reading its PCM readiness cookie.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'modules/perky/control_cf_dsp_hybrid.c'


def extract(src: str, signature: str) -> str:
    p = src.find(signature)
    if p < 0 or src.find(signature, p + 1) >= 0:
        raise AssertionError(f'expected exactly one function {signature}')
    start = src.index('{', p)
    level = 1
    for i in range(start + 1, len(src)):
        if src[i] == '{': level += 1
        if src[i] == '}': level -= 1
        if level == 0: return src[p:i + 1]
    raise AssertionError(f'unterminated function {signature}')


def run() -> None:
    src = SOURCE.read_text()
    init = extract(src, 'int pk_hybrid_boot_init(void)')
    assert init.index('pk_hybrid_pcm_cookie = PK_HYB_PCM_COLD') < init.index('pk_hybrid_clear_boot_bss_range(__bss_start, _end)'), 'BSS scrub must invalidate the loaded PCM readiness cookie'
    assert init.index('pk_hybrid_rt_cookie = PK_HYB_RT_COLD') < init.index('pk_hybrid_clear_boot_bss_range(__bss_start, _end)'), 'BSS scrub must invalidate runtime readiness'
    assert init.index('pk_hybrid_clear_boot_bss_range(__bss_start, _end)') < init.index('pk_hybrid_ensure_pcm()'), 'BSS scrub must precede any BSS reads/decode'
    assert 'extern uint8_t __bss_start[];' in src
    assert 'extern uint8_t _end[];' in src
    helpers = [
        extract(src, 'static void pk_hybrid_zero_u32(void *dst, uint32_t bytes)'),
        extract(src, 'static int pk_hybrid_clear_boot_bss_range(uint8_t *start, uint8_t *end)'),
    ]
    c = '\n'.join([
        '#include <stdint.h>', '#include <stddef.h>', '#include <stdlib.h>',
        '#include <stdio.h>', '#include <string.h>',
        *helpers,
        '''int main(void) {
        enum { N = 218560, GUARD = 32, ALLOC = 0x40000 + 1024 };
        uint32_t *raw = malloc(ALLOC + 2 * GUARD);
        if (!raw) return 2;
        uint8_t *bytes = (uint8_t *)raw;
        memset(bytes, 0xa5, ALLOC + 2 * GUARD);
        uint8_t *b = bytes + GUARD;
        if (!pk_hybrid_clear_boot_bss_range(b, b + N)) return 3;
        for (unsigned i = 0; i < N; ++i) if (b[i]) return 4;
        for (unsigned i = 0; i < GUARD; ++i)
            if (bytes[i] != 0xa5 || bytes[GUARD + N + i] != 0xa5) return 5;
        b[0] = 0x7a;
        if (pk_hybrid_clear_boot_bss_range(b + N, b)) return 6;
        if (pk_hybrid_clear_boot_bss_range(b + 1, b + N)) return 7;
        if (pk_hybrid_clear_boot_bss_range(b, b + 0x40000 + 1)) return 8;
        if (b[0] != 0x7a) return 9;
        memset(b, 0x66, 0x40000);
        if (!pk_hybrid_clear_boot_bss_range(b, b + 0x40000)) return 10;
        for (unsigned i = 0; i < 0x40000; ++i) if (b[i]) return 11;
        if (b[0x40000] != 0xa5) return 12;
        free(raw);
        puts("PASS: production BSS scrub 218560 bytes, guard preservation, invalid bounds rejected");
        return 0;
        }'''
    ])
    tools = [t for t in ('gcc', 'clang') if shutil.which(t)]
    if not tools:
        raise SystemExit('no C compiler available')
    with tempfile.TemporaryDirectory(prefix='perky-coldboot-bss-') as d:
        path = Path(d) / 'test.c'; path.write_text(c)
        for compiler in tools:
            exe = Path(d) / ('bss-' + compiler)
            subprocess.run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
            if compiler == 'clang':
                san = Path(d) / 'bss-sanitized'
                subprocess.run([compiler, '-std=c99', '-O1', '-Wall', '-Wextra', '-Werror',
                                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                                str(path), '-o', str(san)], check=True)
                subprocess.run([str(san)], check=True)
    print('PASS: production boot init order and GCC/Clang scrub tests')

if __name__ == '__main__':
    run()
