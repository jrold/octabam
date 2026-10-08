#!/usr/bin/env python3
"""Static release contract for the final four-voice Perky CF packager."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / "tools/perky/build_cf_final.py").read_text()

required = (
    'PERKY MACHINES FINAL FOUR-ALGORITHM COLDFIRE BUILD',
    'tracks=T1,T2,T5,T6 independent',
    'src=A:Decay,B:Tune,C:Param1,D:Param2,E:Mode,F:Algo; all six p-lockable',
    'algos=Fold1,Fold2,Karplus,NoiseTone(M1/M2/M3)',
    'production_pcm=196608 exact samples per Algo; 786432 total',
    'production_pk_render=1024 simultaneous four-voice frames / 4096 voice events / 65536 samples',
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

for bad in (
    'OT_PROJECT',
    'SimpleDrum',
    'SIMPLE DRUM',
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
