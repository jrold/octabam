"""Strict logical-state comparison for certified alignment experiments.

Every original byte is retained, including original padding. Only the ten new
alignment bytes per voice may be omitted; every one must remain zero.
"""
import hashlib
import json
from pathlib import Path
import subprocess

FIELDS = {'wt':[0,672], 'snare':[672,468], 'bass':[1140,468],
          'nt':[1608,288], 'control':[1896,66], 'rng_low':[1962,4],
          'rng_high':[1966,4], 'active_algo':[1970,1], 'active_mode':[1971,1],
          'pad0':[1972,1], 'pad1':[1973,1]}
RNG4_FIELDS={name:[offset+(2 if offset>=1962 else 0),size]
             for name,(offset,size) in FIELDS.items()}

CONTROL4_FIELDS={name:([offset+6,size] if offset>=1962 else [offset,72] if name=='control' else [offset,size])
                 for name,(offset,size) in FIELDS.items()}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(data, stride, kind='tail'):
    assert stride in (1974,1984) and len(data)==2*stride, 'unreviewed voice layout'
    assert kind in ('tail','rng4','control4')
    if stride==1974:
        assert kind=='tail'
        return data
    if kind=='control4':
        result=[]
        for i in (0,1):
            voice=data[i*stride:(i+1)*stride]
            cells=[]
            for j in range(3):
                at=1896+24*j
                assert voice[at+22:at+24]==bytes(2), 'control cell padding changed'
                cells.append(voice[at:at+22])
            assert voice[1980:]==bytes(4), 'control alignment tail changed'
            result.append(voice[:1896]+b''.join(cells)+voice[1968:1980])
        return b''.join(result)
    if kind=='rng4':
        result=[]
        for i in (0,1):
            voice=data[i*stride:(i+1)*stride]
            assert voice[1962:1964]==bytes(2) and voice[1976:]==bytes(8), 'RNG alignment padding changed'
            result.append(voice[:1962]+voice[1964:1976])
        return b''.join(result)
    for instance in (0,1):
        assert data[instance*stride+1974:(instance+1)*stride] == bytes(10), 'new alignment padding changed'
    return b''.join(data[i*stride:i*stride+1974] for i in (0,1))


def validate_witness(witness,kind='tail'):
    assert kind in ('tail','rng4','control4')
    fields=CONTROL4_FIELDS if kind=='control4' else RNG4_FIELDS if kind=='rng4' else FIELDS
    expected=dict(size=1984,logical_end={'tail':1974,'rng4':1976,'control4':1980}[kind],alignment=16,fields=fields)
    if kind=='control4':expected['control_cell']=dict(stride=24,logical_bytes=22,value_offset=0,alignment=4)
    assert witness==expected, 'logical field layout changed'


def bind(probe, report_path):
    probe, report_path = Path(probe).resolve(), Path(report_path).resolve()
    report=json.loads(report_path.read_text())
    assert report['status']=='PASS_EXACT_PRODUCTION_CALLBACK_MEASUREMENTS'
    assert report['exactness']['callbacks']==25600
    for file,digest in report['inputs'].items():
        assert sha(file)==digest, 'layout evidence input drift: '+file
    for name,digest in report['outputs'].items():
        assert sha(report_path.parent/name)==digest, 'layout evidence output drift: '+name
    witness=report['compiler_layout_witnesses']['candidate']
    validate_witness(witness)
    build=json.loads((probe/'BUILD.json').read_text())
    elf=probe/'platform/runtime.elf'
    assert report['inputs'][str(elf)]==sha(elf), 'witness names another image'
    certificate=dict(schema='octabam.perky.voice-tail-layout.v1',status='PASS_EXACT_COMPILER_LAYOUT_AND_CALLBACKS',
        witness=witness,logical_bytes_per_voice=1974,zero_tail_bytes_per_voice=10,
        runtime_elf_sha256=sha(elf),control_source_sha256=build['sources']['modules/perky/control_cf_dsp_hybrid.c'],
        evidence=dict(path=str(report_path),sha256=sha(report_path),callbacks=25600))
    (probe/'VOICE_LAYOUT.json').write_text(json.dumps(certificate,indent=2)+'\n')
    return certificate


def layout(probe):
    probe=Path(probe)
    elf=probe/'platform/runtime.elf'
    nm=subprocess.check_output(['m68k-elf-nm','-S',str(elf)],text=True)
    size=next(int(v[1],16) for line in nm.splitlines() if len(v:=line.split())==4 and v[-1]=='pk_hybrid_voices')
    assert size in (3948,3968), 'unreviewed production voice extent'
    stride=size//2
    if stride==1984:
        certificate=json.loads((probe/'VOICE_LAYOUT.json').read_text())
        assert certificate['status']=='PASS_EXACT_COMPILER_LAYOUT_AND_CALLBACKS'
        assert certificate['runtime_elf_sha256']==sha(elf), 'layout certificate ELF drift'
        build=json.loads((probe/'BUILD.json').read_text())
        assert certificate['control_source_sha256']==build['sources']['modules/perky/control_cf_dsp_hybrid.c']
        kind=certificate.get('kind','tail')
        validate_witness(certificate['witness'],kind)
    else:kind='tail'
    fields=CONTROL4_FIELDS if kind=='control4' else RNG4_FIELDS if kind=='rng4' else FIELDS
    return dict(stride=stride,extent=size,logical_end={'tail':1974,'rng4':1976,'control4':1980}[kind],fields=fields,kind=kind,
                resonant_raw_offset=1960 if kind=='control4' else 1956,active_algo_offset=fields['active_algo'][0])


def bind_rng4(probe, reference, report_path):
    probe,reference,report_path=(Path(p).resolve() for p in (probe,reference,report_path))
    assert layout(reference)['kind']=='tail' and layout(reference)['stride']==1984
    report=json.loads(report_path.read_text())
    assert report['status']=='PASS_EXACT_PRODUCTION_CALLBACK_MEASUREMENTS'
    assert report['exactness']['callbacks']==25600
    validate_witness(report['compiler_layout_witnesses']['reference'])
    validate_witness(report['compiler_layout_witnesses']['candidate'],'rng4')
    for file,digest in report['inputs'].items():assert sha(file)==digest, 'RNG proof input drift: '+file
    for name,digest in report['outputs'].items():assert sha(report_path.parent/name)==digest, 'RNG proof output drift: '+name
    before=json.loads((reference/'BUILD.json').read_text())['sources']
    after=json.loads((probe/'BUILD.json').read_text())['sources']
    assert before.keys()==after.keys()
    assert {k for k in before if before[k]!=after[k]}=={'modules/perky/control_cf_dsp_hybrid.c'}
    for directory,build,label in ((reference,before,'reference'),(probe,after,'candidate')):
        assert report['inputs'][str(directory/'platform/runtime.elf')]==sha(directory/'platform/runtime.elf')
        snapshots=[Path(p) for p,digest in report['inputs'].items() if Path(p).suffix=='.c' and digest==build['modules/perky/control_cf_dsp_hybrid.c']]
        preferred=[p for p in snapshots if p.name==label+'-source.c']
        if preferred:snapshots=preferred
        assert len(snapshots)==1 and sha(snapshots[0])==build['modules/perky/control_cf_dsp_hybrid.c']
    old=next(Path(p).read_text() for p in report['inputs'] if Path(p).name=='reference-source.c')
    new=next(Path(p).read_text() for p in report['inputs'] if Path(p).name=='candidate-source.c')
    declaration='uint32_t __attribute__((aligned(4))) rng_low;'
    assert new.count(declaration)==1 and new.replace(declaration,'uint32_t rng_low;')==old
    certificate=dict(schema='octabam.perky.voice-rng4-layout.v1',kind='rng4',
        status='PASS_EXACT_COMPILER_LAYOUT_AND_CALLBACKS',witness=report['compiler_layout_witnesses']['candidate'],
        logical_bytes_per_voice=1974,zero_gap_bytes_per_voice=2,zero_tail_bytes_per_voice=8,
        runtime_elf_sha256=sha(probe/'platform/runtime.elf'),control_source_sha256=after['modules/perky/control_cf_dsp_hybrid.c'],
        evidence=dict(path=str(report_path),sha256=sha(report_path),callbacks=25600,
            original_bytes_compared_after_every_callback=3948,new_padding_bytes_checked=20,
            certified_reference=dict(path=str(reference/'VOICE_LAYOUT.json'),sha256=sha(reference/'VOICE_LAYOUT.json'))))
    (probe/'VOICE_LAYOUT.json').write_text(json.dumps(certificate,indent=2)+'\n')
    assert layout(probe)['kind']=='rng4'
    return certificate


def bind_control4(probe, reference, report_path):
    probe,reference,report_path=(Path(p).resolve() for p in (probe,reference,report_path))
    assert layout(reference)['kind']=='rng4'
    report=json.loads(report_path.read_text())
    assert report['status']=='PASS_EXACT_PRODUCTION_CALLBACK_MEASUREMENTS'
    assert report['predictor_state_isolated_per_image'] is True
    assert report['exactness']['callbacks']==25600 and report['commands'][-1][-1]=='control4'
    witnesses=report['compiler_layout_witnesses']
    before_witness=dict(witnesses['reference'])
    assert before_witness.pop('control_cell')==dict(stride=22,logical_bytes=22,value_offset=0,alignment=2)
    validate_witness(before_witness,'rng4');validate_witness(witnesses['candidate'],'control4')
    for file,digest in report['inputs'].items():assert sha(file)==digest, 'control alignment input drift: '+file
    for name,digest in report['outputs'].items():assert sha(report_path.parent/name)==digest, 'control alignment output drift: '+name
    builds=[json.loads((p/'BUILD.json').read_text())['sources'] for p in (reference,probe)]
    assert builds[0].keys()==builds[1].keys()
    assert {k for k in builds[0] if builds[0][k]!=builds[1][k]}=={'modules/perky/control_cf_dsp_hybrid.c'}
    sources=[]
    for directory,build,label in zip((reference,probe),builds,('reference','candidate')):
        assert report['inputs'][str(directory/'platform/runtime.elf')]==sha(directory/'platform/runtime.elf')
        snapshots=[Path(p) for p,digest in report['inputs'].items() if Path(p).suffix=='.c' and digest==build['modules/perky/control_cf_dsp_hybrid.c']]
        preferred=[p for p in snapshots if p.name==label+'-source.c']
        if preferred:snapshots=preferred
        assert len(snapshots)==1 and sha(snapshots[0])==build['modules/perky/control_cf_dsp_hybrid.c']
        sources.append(snapshots[0].read_text())
    old,new=sources
    insertion='typedef struct __attribute__((aligned(4))) { pk4_control value; } pk_hybrid_aligned_control;\n\n'
    restored=(new.replace(insertion,'').replace('pk_hybrid_aligned_control control[3];','pk4_control control[3];')
              .replace('&v->control[algo].value,','&v->control[algo],').replace('&v->control[2].value,','&v->control[2],'))
    assert new.count(insertion)==1 and restored==old
    certificate=dict(schema='octabam.perky.voice-control4-layout.v1',kind='control4',
        status='PASS_EXACT_COMPILER_LAYOUT_AND_CALLBACKS',witness=witnesses['candidate'],
        logical_bytes_per_voice=1974,zero_cell_padding_bytes_per_voice=6,zero_tail_bytes_per_voice=4,
        runtime_elf_sha256=sha(probe/'platform/runtime.elf'),control_source_sha256=builds[1]['modules/perky/control_cf_dsp_hybrid.c'],
        evidence=dict(path=str(report_path),sha256=sha(report_path),callbacks=25600,
            original_bytes_compared_after_every_callback=3948,new_padding_bytes_checked=20,
            certified_reference=dict(path=str(reference/'VOICE_LAYOUT.json'),sha256=sha(reference/'VOICE_LAYOUT.json'))))
    (probe/'VOICE_LAYOUT.json').write_text(json.dumps(certificate,indent=2)+'\n')
    assert layout(probe)['kind']=='control4'
    return certificate


def bind_same_layout(probe, reference, report_path):
    probe,reference,report_path=(Path(p).resolve() for p in (probe,reference,report_path))
    previous=layout(reference)
    report=json.loads(report_path.read_text())
    assert report['status']=='PASS_EXACT_PRODUCTION_CALLBACK_MEASUREMENTS'
    assert report['predictor_state_isolated_per_image'] is True
    assert report['exactness']['callbacks']==25600
    assert len(report['commands'][-1])==4, 'requires full raw-state comparisons'
    witnesses=report['compiler_layout_witnesses']
    assert witnesses['reference']==witnesses['candidate']
    validate_witness(witnesses['candidate'],previous['kind'])
    for file,digest in report['inputs'].items():assert sha(file)==digest, 'same-layout input drift: '+file
    for name,digest in report['outputs'].items():assert sha(report_path.parent/name)==digest, 'same-layout output drift: '+name
    builds=[json.loads((p/'BUILD.json').read_text())['sources'] for p in (reference,probe)]
    assert builds[0].keys()==builds[1].keys()
    changed={k for k in builds[0] if builds[0][k]!=builds[1][k]}
    allowed={'modules/perky/'+name for name in
             ('control_cf_dsp_hybrid.c','cf_wavetable.c','cf_resonant.c','cf_noise_tone.c')}
    assert changed<=allowed, 'not a PERKY CF-only implementation change'
    declarations=[]
    for directory,build,label in zip((reference,probe),builds,('reference','candidate')):
        assert report['inputs'][str(directory/'platform/runtime.elf')]==sha(directory/'platform/runtime.elf')
        snapshots=[Path(p) for p,digest in report['inputs'].items() if Path(p).suffix=='.c' and digest==build['modules/perky/control_cf_dsp_hybrid.c']]
        preferred=[p for p in snapshots if p.name==label+'-source.c']
        if preferred:snapshots=preferred
        assert len(snapshots)==1 and sha(snapshots[0])==build['modules/perky/control_cf_dsp_hybrid.c']
        source=snapshots[0].read_text();start=source.index('typedef struct __attribute__((aligned(16))) {\n    uint8_t wt[')
        end=source.index('} pk_hybrid_cf_voice;',start)+len('} pk_hybrid_cf_voice;')
        declarations.append(source[start:end])
    assert declarations[0]==declarations[1]
    certificate=json.loads((reference/'VOICE_LAYOUT.json').read_text())
    certificate.update(runtime_elf_sha256=sha(probe/'platform/runtime.elf'),
        control_source_sha256=builds[1]['modules/perky/control_cf_dsp_hybrid.c'],
        evidence=dict(path=str(report_path),sha256=sha(report_path),callbacks=25600,
            raw_voice_bytes_compared_after_every_callback=3968,
            changed_owned_implementations=sorted(changed),
            certified_reference=dict(path=str(reference/'VOICE_LAYOUT.json'),sha256=sha(reference/'VOICE_LAYOUT.json'))))
    (probe/'VOICE_LAYOUT.json').write_text(json.dumps(certificate,indent=2)+'\n')
    assert layout(probe)['kind']==previous['kind']
    return certificate


def inherit_noise_only(probe, reference, report_path):
    """Carry the compiler witness through a raw, full-state NT-only proof.

    This does not authorize a new layout. Both images must have the exact same
    control implementation and every other tracked build input, except NT.
    The production runner compares the entire 3968-byte array after each call.
    """
    probe,reference,report_path=(Path(p).resolve() for p in (probe,reference,report_path))
    assert layout(reference)['stride']==1984
    old_certificate=json.loads((reference/'VOICE_LAYOUT.json').read_text())
    old_build=json.loads((reference/'BUILD.json').read_text())['sources']
    new_build=json.loads((probe/'BUILD.json').read_text())['sources']
    assert old_build.keys()==new_build.keys()
    assert {k for k in old_build if old_build[k]!=new_build[k]}=={'modules/perky/cf_noise_tone.c'}, 'not an NT-only continuation'
    report=json.loads(report_path.read_text())
    assert report['status']=='PASS_EXACT_PRODUCTION_CALLBACK_MEASUREMENTS'
    assert report['exactness']['callbacks']==25600
    assert report['compiler_layout_witnesses']=={}, 'requires raw full-array comparison'
    for file,digest in report['inputs'].items():
        assert sha(file)==digest, 'callback input drift: '+file
    for name,digest in report['outputs'].items():
        assert sha(report_path.parent/name)==digest, 'callback output drift: '+name
    for directory in (probe,reference):
        elf=directory/'platform/runtime.elf'
        assert report['inputs'][str(elf)]==sha(elf)
        nm=subprocess.check_output(['m68k-elf-nm','-S',str(elf)],text=True)
        size=next(int(v[1],16) for line in nm.splitlines() if len(v:=line.split())==4 and v[-1]=='pk_hybrid_voices')
        assert size==3968
    certificate=dict(old_certificate)
    certificate.update(runtime_elf_sha256=sha(probe/'platform/runtime.elf'),
        evidence=dict(path=str(report_path),sha256=sha(report_path),callbacks=25600,
            raw_voice_bytes_compared_after_every_callback=3968,
            certified_reference=dict(path=str(reference/'VOICE_LAYOUT.json'),sha256=sha(reference/'VOICE_LAYOUT.json'))))
    (probe/'VOICE_LAYOUT.json').write_text(json.dumps(certificate,indent=2)+'\n')
    assert layout(probe)['stride']==1984
    return certificate


def selftest():
    # Every old byte, including the pre-existing pad0/pad1, must survive.
    original=bytes((i*37+11)&255 for i in range(3948))
    aligned=original[:1974]+bytes(10)+original[1974:]+bytes(10)
    assert canonical(aligned,1984)==canonical(original,1974)
    for at in (0,1972,1973,1984,1984+1972,1984+1973):
        changed=bytearray(aligned);changed[at]^=1
        assert canonical(changed,1984)!=original
    negatives=0
    for at in (*range(1974,1984),*range(3958,3968)):
        changed=bytearray(aligned);changed[at]=1
        try:canonical(changed,1984)
        except AssertionError:negatives+=1
        else:raise AssertionError('padding negative control passed')
    good=dict(size=1984,logical_end=1974,alignment=16,fields=FIELDS)
    validate_witness(good)
    for field in FIELDS:
        changed=json.loads(json.dumps(good));changed['fields'][field][0]+=2
        try:validate_witness(changed)
        except AssertionError:negatives+=1
        else:raise AssertionError('offset negative control passed')
    assert negatives==31
    moved=b''.join(original[i*1974:i*1974+1962]+bytes(2)+original[i*1974+1962:(i+1)*1974]+bytes(8) for i in (0,1))
    assert canonical(moved,1984,'rng4')==original
    for at in (1964,1974,1975,1984+1964,1984+1974,1984+1975):
        changed=bytearray(moved);changed[at]^=1
        assert canonical(changed,1984,'rng4')!=original
    for base in (0,1984):
        for at in (*range(1962,1964),*range(1976,1984)):
            changed=bytearray(moved);changed[base+at]=1
            try:canonical(changed,1984,'rng4')
            except AssertionError:negatives+=1
            else:raise AssertionError('RNG padding negative control passed')
    good=dict(size=1984,logical_end=1976,alignment=16,fields=RNG4_FIELDS)
    validate_witness(good,'rng4')
    for field in RNG4_FIELDS:
        changed=json.loads(json.dumps(good));changed['fields'][field][0]+=2
        try:validate_witness(changed,'rng4')
        except AssertionError:negatives+=1
        else:raise AssertionError('RNG offset negative control passed')
    assert negatives==62
    moved=b''.join(original[i*1974:i*1974+1896]+b''.join(original[i*1974+1896+j*22:i*1974+1918+j*22]+bytes(2) for j in range(3))+original[i*1974+1962:(i+1)*1974]+bytes(4) for i in (0,1))
    assert canonical(moved,1984,'control4')==original
    for at in (1896,1918+2,1968,1978,1979,1984+1979):
        changed=bytearray(moved);changed[at]^=1
        assert canonical(changed,1984,'control4')!=original
    for base in (0,1984):
        for at in (1918,1919,1942,1943,1966,1967,1980,1981,1982,1983):
            changed=bytearray(moved);changed[base+at]=1
            try:canonical(changed,1984,'control4')
            except AssertionError:negatives+=1
            else:raise AssertionError('control padding negative control passed')
    good=dict(size=1984,logical_end=1980,alignment=16,fields=CONTROL4_FIELDS,control_cell=dict(stride=24,logical_bytes=22,value_offset=0,alignment=4))
    validate_witness(good,'control4')
    for field in CONTROL4_FIELDS:
        changed=json.loads(json.dumps(good));changed['fields'][field][0]+=2
        try:validate_witness(changed,'control4')
        except AssertionError:negatives+=1
        else:raise AssertionError('control offset negative control passed')
    for field in good['control_cell']:
        changed=json.loads(json.dumps(good));changed['control_cell'][field]+=2
        try:validate_witness(changed,'control4')
        except AssertionError:negatives+=1
        else:raise AssertionError('control cell witness negative control passed')
    assert negatives==97
    return dict(status='PASS_STRICT_LOGICAL_BYTES_PADDING_AND_OFFSETS',negative_controls=negatives,
                original_bytes_compared=3948,tail_layout_padding_bytes_checked=20,
                rng4_layout_padding_bytes_checked=20,control4_layout_padding_bytes_checked=20)


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe',type=Path)
    ap.add_argument('--bind',type=Path)
    ap.add_argument('--inherit-noise-only',type=Path,help='Existing certified reference probe; --bind supplies raw callback proof')
    ap.add_argument('--rng4-reference',type=Path,help='Existing tail-aligned reference; --bind supplies strict RNG-field relocation proof')
    ap.add_argument('--control4-reference',type=Path,help='Existing RNG4 certificate; strict control-cell relocation proof')
    ap.add_argument('--same-layout-reference',type=Path,help='Existing certificate; require same type, compiler witnesses and full raw-array callback proof')
    args=ap.parse_args()
    print(json.dumps(selftest()))
    if args.bind:
        assert args.probe
        assert sum(bool(x) for x in (args.rng4_reference,args.inherit_noise_only,args.same_layout_reference,args.control4_reference))<=1
        if args.control4_reference:proof=bind_control4(args.probe,args.control4_reference,args.bind)
        elif args.same_layout_reference:proof=bind_same_layout(args.probe,args.same_layout_reference,args.bind)
        elif args.rng4_reference:proof=bind_rng4(args.probe,args.rng4_reference,args.bind)
        elif args.inherit_noise_only:proof=inherit_noise_only(args.probe,args.inherit_noise_only,args.bind)
        else:proof=bind(args.probe,args.bind)
        print(json.dumps(proof,indent=2))
