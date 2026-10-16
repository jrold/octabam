#!/usr/bin/env python3
"""Build an explicit PERKY diagnostic/performance configuration in this checkout.

The performance configuration changes one loaded initial enable word. Both
configurations retain the full profiler and the same synthesis/transport code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import build_cf_dsp_hybrid as builder


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(work,profile,version,number,wrap):
    assert re.fullmatch(r'[A-Z0-9]{6}',version), 'use a unique six-character tag'
    assert not (work/'probe'/f'mainos_{version}.bin').exists(), 'refusing to overwrite an existing candidate'
    baseline=work/'baseline'
    work.mkdir(parents=True,exist_ok=True)
    if not baseline.exists():
        baseline.symlink_to(builder.ROOT/'out/perky/hybrid/baseline',target_is_directory=True)
    enabled=1 if profile=='diagnostic' else 0
    previous=builder.generate_cf_final.FLAGS
    try:
        builder.generate_cf_final.FLAGS=[*previous,f'-DPK_HYBRID_PROFILER_DEFAULT={enabled}']
        builder.PROBE_VERSION=version;builder.PROBE_BUILD_NUMBER=number
        builder.build_probe(work,wrap=wrap)
    finally:
        builder.generate_cf_final.FLAGS=previous
    probe=work/'probe';elf=probe/'platform/runtime.elf';raw=probe/'platform/runtime.raw'
    rows=subprocess.check_output(['m68k-elf-nm','-S',str(elf)],text=True)
    symbol=next(line.split() for line in rows.splitlines() if line.endswith(' pk_hybrid_profiler_enable'))
    assert len(symbol)==4 and int(symbol[1],16)==4 and symbol[2] in ('d','D'), 'enable word must be loaded, never BSS'
    address=int(symbol[0],16)
    assert int.from_bytes(raw.read_bytes()[address-0x40c005e0:address-0x40c005e0+4],'big')==enabled
    notes=probe/f'{version}_PROBE_NOTES.txt'
    if notes.exists():
        notes.write_text(f'CONFIGURATION: {profile.upper()}; profiling defaults {"ON" if enabled else "OFF"}.\n'
                         'Both CF voices and all algorithms remain unrestricted.\n'
                         'Use the diagnostic configuration for timing captures.\n\n'+notes.read_text())
    build=json.loads((probe/'BUILD.json').read_text())
    # BUILD binds the optional notes; update only that descriptive artifact's
    # metadata immediately after creation, before qualification receipts exist.
    if notes.exists() and 'notes' in build['artifacts']:
        build['artifacts']['notes']=builder.item_meta(notes)
        (probe/'BUILD.json').write_text(json.dumps(build,indent=2)+'\n')
    receipt=dict(schema='octabam.perky.hybrid.configuration.v1',status='BUILT_NOT_QUALIFIED',
        profile=profile,version=version,profiler_default_enabled=bool(enabled),
        profiler_loaded_word_address=hex(address),firmware_source_commit=build['git_commit'],
        source_tree_clean=build['source_tree_clean'],compiler_flags=build['compiler_flags'],
        wrapper_source=dict(path=str(Path(__file__).resolve()),sha256=sha(Path(__file__))),
        inputs={str(probe/n):sha(probe/n) for n in ('BUILD.json','MEMORY.json','platform/runtime.elf','platform/runtime.raw')})
    (probe/'CONFIGURATION.json').write_text(json.dumps(receipt,indent=2)+'\n')
    alias=probe/'mainos_PKHYB2P.bin'
    if not alias.exists():alias.symlink_to(f'mainos_{version}.bin')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--profile',choices=('diagnostic','performance'),required=True)
    ap.add_argument('--version',required=True);ap.add_argument('--build-number',type=int,required=True)
    ap.add_argument('--no-wrap',action='store_true')
    a=ap.parse_args();run(a.work.resolve(),a.profile,a.version,a.build_number,not a.no_wrap)
