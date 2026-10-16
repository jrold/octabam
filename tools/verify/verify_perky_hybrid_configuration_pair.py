#!/usr/bin/env python3
"""Require diagnostic/performance runtimes to differ in one loaded word only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def symbols(probe):
    result={}
    for line in subprocess.check_output(['m68k-elf-nm','-S',str(probe/'platform/runtime.elf')],text=True).splitlines():
        words=line.split()
        if len(words)==4:result[words[3]]=(int(words[0],16),int(words[1],16),words[2])
    return result


def run(diagnostic,performance,output):
    builds=[json.loads((p/'BUILD.json').read_text()) for p in (diagnostic,performance)]
    configs=[json.loads((p/'CONFIGURATION.json').read_text()) for p in (diagnostic,performance)]
    assert [c['profile'] for c in configs]==['diagnostic','performance']
    assert [c['profiler_default_enabled'] for c in configs]==[True,False]
    assert builds[0]['sources']==builds[1]['sources']
    assert builds[0]['git_commit']==builds[1]['git_commit']
    assert builds[0]['hybrid_source_id']==builds[1]['hybrid_source_id']
    flags=[b['compiler_flags'] for b in builds]
    assert flags[0].count('-DPK_HYBRID_PROFILER_DEFAULT=1')==1
    assert flags[1].count('-DPK_HYBRID_PROFILER_DEFAULT=0')==1
    assert flags[0]==[f.replace('-DPK_HYBRID_PROFILER_DEFAULT=0','-DPK_HYBRID_PROFILER_DEFAULT=1') for f in flags[1]]
    for p,c in zip((diagnostic,performance),configs):
        assert {str(p/n) for n in ('BUILD.json','MEMORY.json','platform/runtime.elf','platform/runtime.raw')}<=set(c['inputs']), 'configuration names another probe'
        for file,digest in c['inputs'].items():assert sha(Path(file))==digest,'configuration input drift'
    a,b=symbols(diagnostic),symbols(performance)
    assert a==b,'symbol addresses/sizes/types changed'
    address,size,kind=a['pk_hybrid_profiler_enable']
    assert size==4 and kind in ('d','D')
    raw=[(p/'platform/runtime.raw').read_bytes() for p in (diagnostic,performance)]
    offset=address-0x40c005e0
    assert raw[0][offset:offset+4]==bytes.fromhex('00000001')
    assert raw[1][offset:offset+4]==bytes(4)
    assert len(raw[0])==len(raw[1]) and raw[0][:offset]==raw[1][:offset] and raw[0][offset+4:]==raw[1][offset+4:], 'runtime differs outside initial enable word'
    files=[p/n for p in (diagnostic,performance) for n in
           ('BUILD.json','CONFIGURATION.json','platform/runtime.elf','platform/runtime.raw','DSP_IDENTITY.json')]
    report=dict(schema='octabam.perky.hybrid.configuration-pair.v1',status='PASS_SINGLE_LOADED_PROFILE_WORD_ONLY',
        firmware_source_commit=builds[0]['git_commit'],source_id=builds[0]['hybrid_source_id'],
        diagnostic_version=builds[0]['version'],performance_version=builds[1]['version'],
        runtime_bytes=len(raw[0]),identical_runtime_bytes=len(raw[0])-4,
        enable_word_address=hex(address),identical_symbols=len(a),
        scope='Every loaded code/data byte except the initial enable word is identical; all symbol addresses/extents/types match. Performance keeps full diagnostic code.',
        inputs={str(p):sha(p) for p in files})
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'])


def negative_controls(diagnostic,performance,output):
    address,_,_=symbols(performance)['pk_hybrid_profiler_enable'];offset=address-0x40c005e0
    raw=(performance/'platform/runtime.raw').read_bytes();rejected=[]
    with tempfile.TemporaryDirectory(prefix='configuration-negative-',dir=output.parent) as temporary:
        fixture=Path(temporary);(fixture/'platform').mkdir()
        for name in ('BUILD.json','MEMORY.json','DSP_IDENTITY.json','platform/runtime.elf'):
            (fixture/name).symlink_to(performance/name)
        for label,at in [('nonboolean_enable',offset+3),('unrelated_code_byte',0)]:
            mutated=bytearray(raw);mutated[at]^=2
            (fixture/'platform/runtime.raw').write_bytes(mutated)
            config=json.loads((performance/'CONFIGURATION.json').read_text())
            # Bind the deliberately modified input correctly: the one-word
            # comparison, not a stale input checksum, must reject it.
            config['inputs']={str(fixture/n):sha(fixture/n) for n in
                             ('BUILD.json','MEMORY.json','platform/runtime.elf','platform/runtime.raw')}
            (fixture/'CONFIGURATION.json').write_text(json.dumps(config))
            try:run(diagnostic,fixture,fixture/'unexpected-pass.json')
            except AssertionError:rejected.append(label)
            else:raise AssertionError('configuration mutation accepted: '+label)
    assert len(rejected)==2
    (output.parent/'CONFIGURATION_NEGATIVE_CONTROLS.json').write_text(json.dumps(dict(status='PASS',rejected=rejected),indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('diagnostic','performance','out'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--selftest',action='store_true')
    a=ap.parse_args();run(a.diagnostic.resolve(),a.performance.resolve(),a.out.resolve())
    if a.selftest:negative_controls(a.diagnostic.resolve(),a.performance.resolve(),a.out.resolve())
