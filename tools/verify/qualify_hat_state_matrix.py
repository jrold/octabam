#!/usr/bin/env python3
"""Original production matrix with honest no-shadow worker admission."""
import inspect
import json
from pathlib import Path
import qualify_perky_full_map_matrix as matrix


def main():
    source = inspect.getsource(matrix.main)
    old = "'pk_nhb_produced','pk_nhb_completed')"
    assert source.count(old) == 1
    source = source.replace(old, "'pk_nhb_produced','pk_nhb_completed','pk_nhr_consumed','pk_nhb_inner_calls','pk_nhb_snapshot_requests')")
    old = "events[-1]['counts']['pk_nhb_completed']>0"
    assert source.count(old) == 1
    source = source.replace(old, "events[-1]['counts']['pk_nhr_consumed']>0 and events[-1]['counts']['pk_nhb_inner_calls']==events[-1]['counts']['pk_nhb_snapshot_requests']==0")
    namespace = dict(vars(matrix))
    namespace['__file__'] = str(Path(__file__).resolve())
    exec(compile(source, __file__, 'exec'), namespace)
    namespace['main']()
    path = matrix.W / 'MATRIX.json'
    result = json.loads(path.read_text())
    result['state_handoff'] = dict(status='PASS_PRODUCTION_MATRIX_WITHOUT_CF_HAT_SHADOW',
                                   counters=result['events'][-1]['counts'],
                                   source_sha256={str(Path(__file__).resolve()): matrix.f.c.sha(Path(__file__).resolve()),
                                                  str(Path(matrix.__file__).resolve()): matrix.f.c.sha(Path(matrix.__file__).resolve())})
    path.write_text(json.dumps(result, indent=2) + '\n')
    (matrix.W / 'matrix/MATRIX_ADAPTER.py').write_text(source)
    print(result['state_handoff']['status'])


if __name__ == '__main__':
    main()
