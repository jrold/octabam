#!/usr/bin/env python3
"""Static release contract for the final four-voice Perky CF packager."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / "tools/perky/build_cf_final.py").read_text()

required = (
    'PERKY MACHINES FINAL COLDFIRE BUILD',
    'tracks=T1,T2,T3,T4 independent',
    'src=A:Tune,B:Decay,C:Algo,D:Prm1,E:Prm2,F:Mode; all six p-lockable',
    'algos=Fold1,Fold2,Karplus,NoiseTone(M1/M2/M3),ResonantDrums(M1/M2/M3),NoiseHat(M1/M2/M3)',
    'production_pcm=196608 exact samples per Algo; 786432 total',
    'production_pk_render=1024 simultaneous four-voice frames / 4096 voice events / 65536 exact samples',
    'verify_perky_cf_final.py',
    'generate_cf_final.generate(generated)',
    'verify_perky_cf_codegen.py',
    'perky-cf-final',
    'verify_perky_stock_dsp_identity.py',
    'wrap_flashable(FINAL_MAIN, args.version)',
    'm68k-elf-gcc',
    '-mcpu=54455',
    '-msoft-float',
)
for needle in required:
    if needle not in s:
        raise AssertionError(f"missing release-builder contract: {needle}")

# The forbidden list guards against "reduced" release behaviour leaking back
# in. Three entries that used to be forbidden are legitimate now and are
# deliberately not listed:
#   * OT_PROJECT -- the final builder REQUIRES a real card/project path for the
#     whole-machine emulator gate (die() when it is unset); it is no longer a
#     way to point the build at a toy fixture.
#   * SimpleDrum / SIMPLE DRUM -- Simple Drum is a real PĒRKONS v1.2.1 voice
#     (family V1 algorithm 3) that the shipped per-track algorithm list has to
#     be able to name.  It is a milestone, not a reduction.
for bad in (
    'probe_glue.asm',
    'synthetic_control_map',
    'PERKY HW4',
    'retire',
    'reduced-FX',
):
    if bad in s:
        raise AssertionError(f"nonfinal/reduced release behavior leaked into builder: {bad}")

# The target-code audit must happen after generation and before the remix/link.
gen = s.index('generate_cf_final.generate(generated)')
audit = s.index('verify_perky_cf_codegen.py')
remix = s.index('build all-stock-FX remix')
if not gen < audit < remix:
    raise AssertionError('ColdFire codegen audit is not ordered before final remix/link')

# DSP identity must be proven before any flashable wrapper is emitted.
identity = s.index('verify_perky_stock_dsp_identity.py')
wrap = s.index('wrap_flashable(FINAL_MAIN, args.version)')
if not identity < wrap:
    raise AssertionError('flashable image can be wrapped before stock DSP identity proof')

print(
    'PERKY CF release builder: PASS '
    '(four-Algo release frozen; qualification -> codegen audit -> all-FX remix -> '
    'stock-DSP identity -> card/MIDI wrapper)'
)
