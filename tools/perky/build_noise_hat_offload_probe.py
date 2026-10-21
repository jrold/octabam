#!/usr/bin/env python3
"""Build the opt-in split Noise Hat RPC probe, preserving twelve stock FX."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools','tools/build','tools/perky','tools/verify','modules/perky')]
import perky_noise_hat_offload as N
import build_cf_placement_probe as CF
import perky_fragmented_image as F
import perky_image as P
import ab_records as A
from remix import registry,stock

WORK=ROOT/'out/perky/hybrid/noise-hat-offload'
VERSION='PKNHA1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build():
    WORK.mkdir(parents=True,exist_ok=True)
    source=WORK/'placement-offload.c'
    source.write_text('#define pk_cf_nh_render pk_cf_nh_offload\n#include "'+str(ROOT/'tools/harness/perky_cf/placement_cf_engine.c')+'"\n')
    def control(t):
        return CF.replace_once(t,'placement_bind(p);placement_init();',
            'placement_bind(p);placement_init();extern void pk_nha_bind_port(void);pk_nha_bind_port();')
    cf_stage=CF.build(WORK,control_transform=control,additional_units=(('pkhatrpc','cf_noise_hat_offload.c'),),
             placement_source=source,version=VERSION,build_number=15)
    probe=WORK/'probe';asm=probe/'multi.asm'
    ar,al,irq,render,br,bl=N.build_program(WORK/'program',asm)
    pristine=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    original=(probe/'fragmented-normal.bin').read_bytes();image=bytearray(original)
    appended={};plans={'A':ar,'B':br};ledgers={'A':al,'B':bl}
    for tag,c in P.PAY.items():
        recs,_=A.records(image,*c['payload']);old,_,entry=F.plan(asm,tag)
        for address,words in old:
            if address<0x2000:
                assert [A.rd(image,A.word_at(recs,0,address+i)) for i in range(len(words))]==words
        appended[tag]=[]
        for address,words in plans[tag]:
            if any(lo<=address and address+len(words)<=hi for lo,hi in N.L.local_p_spans(tag)):
                for i,v in enumerate(words):A.wr(image,A.word_at(recs,0,address+i),v)
            else:appended[tag].append((address,words))
        site=0x39c if tag=='A' else 0x1a2
        if tag=='A':
            sr,_=A.records(pristine,*c['payload'])
            for address in (site,site+1):A.wr(image,A.word_at(recs,0,address),A.rd(pristine,A.word_at(sr,0,address)))
            assert [A.rd(image,A.word_at(recs,0,N.VECTOR+i)) for i in range(2)]==[0x0c002c,0]
            for address,v in ((N.VECTOR,0x0bf080),(N.VECTOR+1,irq)):
                A.wr(image,A.word_at(recs,0,address),v)
        else:
            A.wr(image,A.word_at(recs,0,site+1),N.S.plan(asm,'B')[2])
    appended=F.merge_upload_records(appended)
    normal=probe/'fragmented-normal.bin';normal.write_bytes(image)
    (probe/'p-records.json').write_text(json.dumps(appended,indent=2)+'\n')
    y,layout=P.load_tables(probe);x=P.load_state_init(probe,layout)
    for tag,c in P.PAY.items():
        upload,_=P.extend_upload(bytes(image),tag,y,x,P.extra_state_init(layout),P.load_extra_y_init(probe,layout),appended[tag])
        path=WORK/f'dsp-{tag}.upload.bin';path.write_bytes(upload)
        rr,_=A.records(pristine,*c['payload']);ur,_=A.records(upload,A.BASE,len(upload))
        for name,(address,count) in stock.p_spans(tag).items():
            if name in ('PLATE REV','COMPRESSOR'):continue
            assert [A.rd(upload,A.word_at(ur,0,address+i)) for i in range(count)]==[A.rd(pristine,A.word_at(rr,0,address+i)) for i in range(count)],(tag,name)
            effect_id=registry.modules()[name].menu.fx2_id
            for base in (0x215,0x235):
                assert A.rd(upload,A.word_at(ur,1,base+effect_id))==A.rd(pristine,A.word_at(rr,1,base+effect_id))
        for address,words in plans[tag]:
            assert [A.rd(upload,A.word_at(ur,0,address+i)) for i in range(len(words))]==words
    main=probe/f'mainos_{VERSION}.bin'
    CF.base.repack_hybrid_loader(normal,probe,main,platform_dir=ROOT/'out/platform',
        work=probe/'platform-loader',p_records=appended)
    shared={a:len(w) for a,w in appended['A'] if a>=0x30000}
    ranges=[('active compact state',N.STATE,N.STATE+121),('scratch and hold/RNG',N.SCRATCH,N.SCRATCH+119),
            ('native stereo PCM',N.PCM,N.PCM+40),('request and pending host word',N.COUNT,N.PENDING+2),
            ('interrupted registers',N.SAVED,N.SAVED+len(N.REGISTERS))]
    for i,(name,lo,hi) in enumerate(ranges):
        assert 0x3800<=lo<hi<=0x3a68
        assert all(not N.L.overlaps((lo,hi),(a,b)) for _,a,b in ranges[i+1:])
    memory=dict(schema='perky-noise-hat-offload-memory-v1',A_program=al,B_program=bl,
        A_program_words=sum(r['length'] for r in al),shared_capacity=N.L.shared_p_capacity(),
        shared_words=sum(shared.values()),shared_free=N.L.shared_p_capacity()-sum(shared.values()),
        private_P_used={tag:sum(r['length'] for r in rows if r['start']<0x30000)+(48 if tag=='A' else 0) for tag,rows in ledgers.items()},
        A_private_X=ranges,A_private_X_words=sum(hi-lo for _,lo,hi in ranges),A_private_X_capacity=616,
        A_low_Y_words=layout['total_words'],A_low_Y_capacity=2139,
        CF_ring_bytes=4805*2,host_vector=[N.VECTOR,N.VECTOR+2],retained_FX='all twelve code/dispatch bytes exact',
        notes=['A original oscillator source hook restored to stock; source PCM from CF passes normal AMP/FX.',
               'B retains its single admitted oscillator portfolio; no paired context exchange.',
               'Shared P/X/Y alias storage counted once. Ring and raw history remain in CF RAM.',
               'Private-B tail boundary and new host vector remain hardware-unqualified.'])
    (WORK/'MEMORY.json').write_text(json.dumps(memory,indent=2)+'\n')
    report=dict(status='BUILT_NOT_QUALIFIED',hardware_validated=False,main_sha256=sha(main),
        runtime_sha256=sha(probe/'platform/runtime.elf'),memory=memory,irq_entry=irq,render_entry=render,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_checkpoint_note='Checkpoint plus the uncommitted implementation hashes; no release commit.',
        compiler_flags=cf_stage['result']['compiler_flags'],
        baseline_PERKY4S_identity_verified_before_specialization=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/perky/perky_noise_hat_offload.py',
            ROOT/'modules/perky/cf_noise_hat_offload.c',ROOT/'tools/perky/build_cf_placement_probe.py')})
    (probe/'memory.json').write_text(json.dumps(dict(status='SUPERSEDED_BY_OFFLOAD_MEMORY',path=str(WORK/'MEMORY.json')),indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'tools/verify/verify_perky_machine_boot.py'),'--image',str(main),
        '--packed',str(probe),'--platform',str(probe/'platform'),'--platform-work',str(probe/'platform-loader'),
        '--normal-image',str(normal),'--p-records',str(probe/'p-records.json'),
        '--runtime-init-cookie','pk_hybrid_prof_cookie=504b5443:504b5452',
        '--runtime-init-cookie','pk_hybrid_rt_cookie=504b4843:504b4852',
        '--runtime-init-cookie','pk_hybrid_pcm_cookie=504b5043:504b5052'],cwd=ROOT,check=True)
    report['boot_status']='PASS_EXACT_RUNTIME_AND_UPLOAD_READBACK_WITH_EXPLICIT_LOADED_COOKIE_TRANSITIONS'
    (WORK/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    (WORK/'CF_STAGE_BUILD.json').write_text(json.dumps(cf_stage,indent=2)+'\n')
    for path in (probe/'BUILD.json',WORK/'EXPERIMENT_BUILD.json'):
        path.write_text(json.dumps(report,indent=2)+'\n')
    identity=probe/'DSP_IDENTITY.json'
    if identity.exists():
        (probe/'CF_STAGE_DSP_IDENTITY.json').write_bytes(identity.read_bytes())
        identity.write_text(json.dumps(dict(status='SUPERSEDED_BY_OFFLOAD_RETAINED_FX_CHECK',
            current_main_sha256=report['main_sha256'],retained_FX='all twelve code and dispatch bytes exact',
            qualification='new DSP program; PERKY4S whole-payload identity applies only to the earlier CF build stage'),indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':build()
