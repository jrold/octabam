#!/usr/bin/env python3
"""Actual source gate with the original diagnostic trace also compared."""
import hashlib
import inspect
from pathlib import Path

import verify_perky_full_map_sources as original


def main():
    text = inspect.getsource(original.main)
    old = " version=json.loads((W/'BUILD.json').read_text()).get('version','PKFM1');"
    assert text.count(old) == 1
    text = text.replace(old, " trace_ref=(I32*192).in_dll(native,'placement_trace');trace_enable_ref=U32.in_dll(native,'placement_trace_enabled');trace_counts=[0,0]\n" + old, 1)
    old = '    split=0 if mode_row==frame==0 else frame;trig=frame%4==0\n'
    assert text.count(old) == 1
    text = text.replace(old, old + "    tracing=(frames//17)%2;trace_enable_ref.value=tracing;rt.w32(u,s['placement_trace_enabled'],tracing);trace_counts[tracing]+=1\n", 1)
    old = "      actual=struct.unpack('>16i',u.mem_read(s['placement_output']+64*tr,64));"
    assert text.count(old) == 1
    text = text.replace(old, "      actual_trace=struct.unpack('>48i',u.mem_read(s['placement_trace']+192*tr,192));assert list(actual_trace)==list(trace_ref[48*tr:48*(tr+1)]),(combo,mode_row,frame,tr,'diagnostic trace')\n" + old, 1)
    old = " (W/'SOURCE_GATE.json').write_text(json.dumps(result,indent=2)+'\\n');"
    assert text.count(old) == 1
    text = text.replace(old, " result['trace_enabled_frame_counts']=trace_counts;assert all(trace_counts)\n result['source_sha256'][str(Path(_original_driver).relative_to(ROOT))]=sha(Path(_original_driver))\n result['proof_adapter_sha256']=hashlib.sha256(_adapter.encode()).hexdigest()\n (out/'PROOF_ADAPTER.py').write_text(_adapter)\n" + old, 1)
    namespace = dict(vars(original))
    namespace.update(__file__=str(Path(__file__).resolve()), _original_driver=original.__file__, _adapter=text)
    exec(compile(text, str(Path(__file__).resolve()) + ':adapter', 'exec'), namespace)
    namespace['main']()


if __name__ == '__main__':
    main()
