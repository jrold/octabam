#!/usr/bin/env python3
"""Prove the mixed injector leaves the existing Noise/Tone upload path identical."""
from pathlib import Path
import subprocess,sys,tempfile,types
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky')]
import perky_image as current
import fabricate_noise_tone_fixtures as fab
import build_noise_tone_payload as payload

def main():
    old=types.ModuleType('legacy_perky_image');old.__file__=str(ROOT/'tools/build/perky_image.py')
    baseline=subprocess.check_output(['git','show','9b12c0eb:tools/build/perky_image.py'],cwd=ROOT,text=True)
    exec(compile(baseline,old.__file__,'exec'),old.__dict__)
    with tempfile.TemporaryDirectory(prefix='perky-legacy.') as td:
        root=Path(td);fab.emit_tables(root/'source');payload.build(root/'source',root/'packed')
        for image in (ROOT/'out/raw/section_3_MAIN_OS.bin',ROOT/'out/mainos_bus.bin'):
            raw=image.read_bytes()
            assert old.integrate(raw,root/'packed')==current.integrate(raw,root/'packed'),image
    print('PERKY legacy upload identity: PASS (stock and finalized image; byte-identical A/B uploads, packing, pointers, logs and layout)')
if __name__=='__main__':main()
