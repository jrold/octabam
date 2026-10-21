#!/usr/bin/env python3
"""Bind the exact zero-ramp DELAY proof to final packaged and booted code.

Reuse the frozen stock-mixer binding mechanics with explicit checked markers;
only the new generator/proof/name/site width and report schema change.
"""
import inspect
import json
from pathlib import Path
import sys

import verify_stock_source_mix_binding as template


def main():
    source=inspect.getsource(template.main)
    replacements={
        "ROOT/'out/perky/hybrid/stock-source-block-v2/RESULT.json'":"ROOT/'out/perky/hybrid/stock-isr-next-delay-v1/RESULT.json'",
        "build/'stock-mixer-binding-v2'":"build/'stock-delay-binding-v1'",
        "ROOT/'tools/perky/generate_stock_source_mix_block.py'":"ROOT/'tools/perky/generate_stock_delay_steady_mix.py'",
        "'PASS_ACTUAL_COMPLETE_STOCK_MIX_BLOCK_REGS_CCR_EMAC_ALL_MEMORY'":"'PASS_ACTUAL_STOCK_DELAY_ZERO_RAMP_REGS_CCR_EMAC_ALL_MEMORY'",
        "name='pk_stock_source_mix_block'":"name='pk_stock_delay_steady_mix'",
        "detour=b'\\x4e\\xf9'+actual_address.to_bytes(4,'big')+b'\\x4e\\x71'":"detour=b'\\x4e\\xf9'+actual_address.to_bytes(4,'big')+b'\\x4e\\x71'*3",
        "assert execution['mean_saved_cycles']==proof['mean_saved_cycles']":"assert execution['mean_saved_cycles_fast']==proof['mean_saved_cycles_fast']\n    assert execution['mean_saved_cycles_fallback']==proof['mean_saved_cycles_fallback']",
        "status='PASS_FINAL_IMAGE_STOCK_MIXER_PROOF_AND_BOOT_BINDING'":"status='PASS_FINAL_IMAGE_STOCK_DELAY_MIX_PROOF_AND_BOOT_BINDING'",
        "padding='one NOP'":"padding='three NOPs'",
        "standalone_mean_saved_cycles=proof['mean_saved_cycles']":"standalone_mean_saved_cycles=proof['mean_saved_cycles_fast']",
        "standalone_mean_saved_us=proof['mean_saved_us_per_block']":"standalone_mean_saved_us=proof['mean_saved_us_fast']",
        "'Binds the exact complete-block register/CCR/EMAC/aliased-memory proof to final packaged and booted code.'":"'Binds exact zero/nonzero-ramp register/CCR/EMAC/aliased-memory proof to final packaged and booted DELAY code; quoted saving covers the guarded fast path only.'",
        "print(json.dumps(report,indent=2))":"report['source_sha256'][str(Path(_binding_template.__file__).resolve())]=sha(Path(_binding_template.__file__).resolve())\n    report['specialization']='Four exactly zero ramp increments; literal stock loop for all other increments'\n    report['standalone_fast_cases']=proof['fast_cases']\n    report['standalone_fallback_cases']=proof['fallback_cases']\n    report['standalone_fallback_saved_cycles']=proof['mean_saved_cycles_fallback']\n    (work/'BINDING.json').write_text(json.dumps(report,indent=2)+'\\n')\n    print(json.dumps(report,indent=2))",
    }
    for before,after in replacements.items():
        assert source.count(before)==1,('Frozen binding template drift',before)
        source=source.replace(before,after,1)
    namespace=dict(vars(template))
    namespace.update(__file__=str(Path(__file__).resolve()),_binding_template=template)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),namespace)
    namespace['main']()


if __name__=='__main__':main()
