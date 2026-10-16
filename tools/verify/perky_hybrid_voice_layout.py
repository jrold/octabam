"""Strict logical-state comparison for the certified tail-alignment experiment.

Every original byte is retained. Only the ten newly introduced tail bytes may
be omitted from the canonical stream, and every one must remain zero.
"""
import hashlib
import json
from pathlib import Path
import subprocess

FIELDS = {'wt':[0,672], 'snare':[672,468], 'bass':[1140,468],
          'nt':[1608,288], 'control':[1896,66], 'rng_low':[1962,4],
          'rng_high':[1966,4], 'active_algo':[1970,1], 'active_mode':[1971,1],
          'pad0':[1972,1], 'pad1':[1973,1]}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(data, stride):
    assert stride in (1974,1984) and len(data)==2*stride, 'unreviewed voice layout'
    if stride==1974:
        return data
    for instance in (0,1):
        assert data[instance*stride+1974:(instance+1)*stride] == bytes(10), 'new alignment padding changed'
    return b''.join(data[i*stride:i*stride+1974] for i in (0,1))


def validate_witness(witness):
    assert witness == dict(size=1984,logical_end=1974,alignment=16,fields=FIELDS), 'logical field layout changed'


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
        validate_witness(certificate['witness'])
    return dict(stride=stride,extent=size,logical_end=1974,fields=FIELDS,
                resonant_raw_offset=1956,active_algo_offset=1970)


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
    return dict(status='PASS_STRICT_LOGICAL_BYTES_PADDING_AND_OFFSETS',negative_controls=negatives,
                original_bytes_compared=3948,new_tail_bytes_checked=20)


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe',type=Path)
    ap.add_argument('--bind',type=Path)
    ap.add_argument('--inherit-noise-only',type=Path,help='Existing certified reference probe; --bind supplies raw callback proof')
    args=ap.parse_args()
    print(json.dumps(selftest()))
    if args.bind:
        assert args.probe
        proof=inherit_noise_only(args.probe,args.inherit_noise_only,args.bind) if args.inherit_noise_only else bind(args.probe,args.bind)
        print(json.dumps(proof,indent=2))
