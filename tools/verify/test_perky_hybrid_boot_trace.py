#!/usr/bin/env python3
"""Validate loader instrumentation anchors and optional real m68k assembly."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / 'tools/perky/hybrid_boot_trace.py'
LOADER = ROOT / 'tools/remix/loader.S'


def run():
    spec = importlib.util.spec_from_file_location('hybrid_boot_trace', TRACE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = LOADER.read_text()
    out = mod.instrument_loader(src, 0x40c01000)
    expected = (40, 41, 42, 43, 44, 45, 46, 79)
    for stage in expected:
        assert out.count(f'moveq   #{stage},%d0') == 1, stage
    assert out.count('hybrid_boot_trace:') == 1
    assert out.count('hybrid_boot_tx:') == 1
    assert out.count('jsr     (BOOT_CONTINUE).l') == 1
    assert out.count('jsr     (0x40c01000).l') == 1
    assert out.count('hybrid_boot_fatal_stop:') == 1
    assert out.count('bsr.w   hybrid_boot_trace') == 8
    assert out.index('moveq   #45,%d0') < out.index('jsr     (0x40c01000).l')
    assert out.index('jsr     (0x40c01000).l') < out.index('moveq   #46,%d0')
    assert out.index('tst.l   %d0') < out.index('moveq   #46,%d0')
    assert 'move.l  #200000,%d2' in out
    assert 'move.l  #0xb0,%d1' in out and 'moveq   #119,%d1' in out
    assert 'bne.s   1b\n        rts' in out, 'UART timeout must return, not write a byte'
    for missing in ('octabam_bootstrap:', 'pnext:', '        jsr     (BOOT_CONTINUE).l',
                    'done:\n        movem.l (%sp),%d0-%d7/%a0-%a2', 'fatal:\n        bra.w   fatal'):
        try: mod.instrument_loader(src.replace(missing, 'BAD_ANCHOR', 1), 0x40c01000)
        except ValueError: pass
        else: raise AssertionError('missing/changed loader anchor was accepted: ' + missing)
    if shutil.which('m68k-elf-as'):
        with tempfile.TemporaryDirectory(prefix='perky-boottrace-as-') as d:
            work = Path(d)
            (work/'early.inc').write_text('')
            (work/'table.inc').write_text('.long 0\npretable:\n.long 0\n')
            # Builder removes the separate pretable block and locates it in table.inc.
            out = out.replace('.ifdef PREBOOT\n        .align  4\npretable:\n        .include "pretable.inc"\n.endif\n', '')
            srcpath = work/'loader.S'; srcpath.write_text(out)
            subprocess.run(['m68k-elf-as','-mcpu=5475','-I',str(work),
                            '--defsym','PREBOOT=1','-o',str(work/'loader.o'),str(srcpath)], check=True)
            if shutil.which('m68k-elf-ld'):
                subprocess.run(['m68k-elf-ld','-Ttext=0x4010fdf0',
                                '-o',str(work/'loader.elf'),str(work/'loader.o')],check=True)
            print('PASS: real m68k assembler accepted diagnostic loader')
    else:
        print('NOTE: m68k-elf-as unavailable; builder-side syntax requires local cross-assembly')
    print('PASS: 8 bounded MIDI stage markers, boot-init/fatal path, drift rejection')

if __name__ == '__main__':
    run()
