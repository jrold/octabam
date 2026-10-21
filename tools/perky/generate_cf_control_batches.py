"""Reuse the proven exact smoother batching for remaining source families."""
from pathlib import Path
import re


def transform(work, source_path):
    work = Path(work)
    source_path = Path(source_path)
    text = source_path.read_text()
    matches = re.findall(r'#include "([^"]*/cf_perky4_settle.c)"', text)
    assert len(matches) == 1
    old_path = Path(matches[0])
    engine = old_path.read_text()
    for count, expected in ((14, 1), (15, 4), (16, 3)):
        old = f'for(i=0;i<{count};i++)common_smooth_only(s,c->targets);'
        assert engine.count(old) == expected, (count, engine.count(old))
        engine = engine.replace(old, f'common_smooth_many(s,c->targets,{count}u);')
    target = work / 'cf-perky4-control-batches.c'
    target.write_text(engine)
    text = text.replace(str(old_path), str(target))
    old = 'for(i=0;i<(trig?15u:14u);i++)common_smooth_only(placement_ah_state,placement_ah_control.targets);'
    assert text.count(old) == 1
    text = text.replace(old, 'common_smooth_many(placement_ah_state,placement_ah_control.targets,trig?15u:14u);')
    path = work / 'placement-control-batches.c'
    path.write_text(text)
    return path
