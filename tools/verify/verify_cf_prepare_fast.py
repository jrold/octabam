#!/usr/bin/env python3
"""Differential no-op event preparation proof using PKFM17 engine bodies.

Reuse the existing all-family control history/poison campaign. A counted
production observation remains in both paths; actual generations are checked
by final-image source and lifecycle gates rather than this native fixture.
"""
import inspect
from pathlib import Path

import verify_cf_control_batches as controls


def main():
    import sys
    sys.path.insert(0, str(controls.c.ROOT / 'tools/perky'))
    import generate_cf_prepare_fast as prepare
    source = inspect.getsource(controls.main)
    old = "baseline/'cf_perky4_settle.c'"
    assert source.count(old) == 1
    source = source.replace(old, "baseline/'cf-perky4-control-batches.c'")
    marker = "source=work/'placement-original.c';source.write_text(original)"
    assert source.count(marker) == 1
    source = source.replace(marker, '''original = 'unsigned prep_observed,pk_prod_algorithms[4],pk_prod_modes[4];\\nvoid placement_production_event(unsigned tr,unsigned algo){prep_observed++;}\\n' + original
    observation='    placement_production_event(tr,algo);\\n    pk_prod_algorithms[tr]=algo;pk_prod_modes[tr]=mode;\\n'
    anchor='    if(algo>10||mode>2||tr>3)return 0;\\n'
    assert original.count(anchor)==1
    original=original.replace(anchor,anchor+observation,1)
    source=work/'placement-original.c';source.write_text(original)''')
    source = source.replace('candidate=batches.transform(work,source)', 'candidate=prepare.transform(work,source)')
    source = source.replace("check((i,tr,values));previous[tr]=values;events+=1", "check((i,tr,values));assert [C.c_uint.in_dll(lib,'prep_observed').value for lib in libs]==[i+1,i+1];previous[tr]=values;events+=1")
    source = source.replace("'PASS_CONTROL_BATCHES_ALL_PREPARE_PATHS_AND_UNSIGNED_FALLBACK'", "'PASS_FAST_PREPARE_ALL_FAMILY_STATE_CLOCK_AND_EVENT_OBSERVATION'")
    source = source.replace('Path(batches.__file__).resolve()', 'Path(prepare.__file__).resolve()')
    source = source.replace("limits=['Native compilation proves the control transformation; actual ColdFire source/lifecycle gates remain required.']", "limits=['Native differential proof checks no-op preparation, dirty/fresh/triggered fallbacks and counted production observations. Actual ColdFire generation/source/lifecycle admission remains separate.']")
    namespace = dict(vars(controls))
    namespace.update(__file__=str(Path(__file__).resolve()), prepare=prepare)
    exec(compile(source, __file__, 'exec'), namespace)
    namespace['main']()


if __name__ == '__main__':
    main()
