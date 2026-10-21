#!/usr/bin/env python3
"""New signed-EMAC converter against the frozen rational/CF proof harness."""
import hashlib
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky')]
import generate_cf_resample_signed as generator
import verify_perky_resample_lut as original


def main():
    text = inspect.getsource(original.main)
    text = text.replace("default=ROOT / 'out/perky/hybrid/full-map-state-v4'",
                        "default=ROOT / 'out/perky/hybrid/full-map-remaining-cf-mix-v1'")
    text = text.replace("default=ROOT / 'out/perky/hybrid/resample-lut-v1'",
                        "default=ROOT / 'out/perky/hybrid/stock-cf-optimization/resample-signed'")
    before = '''  int64_t product=(a<<5)*c;
  int64_t q=product>=0?product/(1LL<<31):-((-product+(1LL<<31)-1)/(1LL<<31));
  q^=sign;'''
    after = '''  int64_t product=(int64_t)d*32*c;
  int64_t q=product>=0?product/(1LL<<31):-((-product+(1LL<<31)-1)/(1LL<<31));'''
    assert text.count(before) == 1
    text = text.replace(before, after)
    text = text.replace('PASS_EXACT_RATIONAL_LUT_SOURCE_PCM_CLOCK_EMAC_ABI',
                        'PASS_EXACT_SIGNED_RATIONAL_SOURCE_PCM_CLOCK_EMAC_ABI')
    old = '''    (work / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\\n')'''
    assert text.count(old) == 1
    new = '''    paths = (Path(_new_driver), Path(_old_driver), Path(generator.previous.__file__),
             Path(rt.__file__), Path(rt.g.emu.__file__))
    result['source_sha256'].update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    artifacts = [image, elf, helper_elf, lib, work / 'canary.elf', work / 'canary.bin']
    if not args.linked: artifacts.append(work / 'helper.bin')
    result['inputs'] = {str(p): sha(p) for p in artifacts}
    result['proof_adapter_sha256'] = hashlib.sha256(_adapter.encode()).hexdigest()
    (work / 'PROOF_ADAPTER.py').write_text(_adapter)
''' + old
    text = text.replace(old, new)
    namespace = dict(vars(original))
    namespace.update(generator=generator, _new_driver=str(Path(__file__).resolve()),
                     _old_driver=original.__file__, _adapter=text)
    exec(compile(text, str(Path(__file__).resolve()) + ':adapter', 'exec'), namespace)
    namespace['main']()


if __name__ == '__main__':
    main()
