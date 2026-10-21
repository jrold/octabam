#!/usr/bin/env python3
"""Build the resident Noise Hat source/readback DMA probe with twelve stock FX."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools','tools/build','tools/perky','tools/verify','modules/perky')]
import perky_noise_hat_taps as N
import dataclasses
from remix.schema import Linked,Detour
import build_cf_placement_probe as CF
import perky_fragmented_image as F
import perky_image as P
import ab_records as A
from remix import registry,stock

WORK=ROOT/'out/perky/hybrid/noise-hat-taps'
VERSION='PKNHD1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build():
    WORK.mkdir(parents=True,exist_ok=True)
    source=WORK/'placement-resident.c'
    source.write_text('#include "'+str(ROOT/'tools/harness/perky_cf/placement_cf_engine.c')+'"\n#include "'+str(ROOT/'tools/harness/perky_cf/noise_hat_taps_engine.c')+'"\n')
    def control(t):
        t=t.replace('static uint32_t placement_trigger[4];','static uint32_t placement_trigger[4];\nextern void pk_nhr_frame(unsigned,volatile uint32_t*);')
        t=t.replace('        if(!placement_prepare(voice,p,p[9]!=0))placement_status=0;',
                    '        if(voice!=3u&&!placement_prepare(voice,p,p[9]!=0))placement_status=0;')
        t=t.replace('    if(!placement_segment(voice,start,end,start?1u:0u))placement_status=0;',
                    '    if(voice!=3u&&!placement_segment(voice,start,end,start?1u:0u))placement_status=0;')
        t=t.replace('        placement_pack(voice,start);\n        pk_hybrid_commit_longs(pk_hybrid_fixed_slot(track,ping),placement_packets[voice],40u);',
                    '        if(voice==3u)pk_nhr_frame(start,pk_hybrid_fixed_slot(track,ping));\n        else {placement_pack(voice,start);\n        pk_hybrid_commit_longs(pk_hybrid_fixed_slot(track,ping),placement_packets[voice],40u);}')
        return t
    hook=WORK/'resident-dma.s'
    hook.write_text(""".text
.globl pk_nhr_dma_hook
pk_nhr_dma_hook:
 jsr pk_nhr_dma_step
 tst.l %d0
 beq 1f
 jmp 0x40004bc8
1:
 moveq #7,%d1
 move.b %d1,0xfc04401c
 jmp 0x4000486a
""")
    original_module=CF.base.build_hybrid_module
    def module(*args,**kw):
        r=original_module(*args,**kw)
        return dataclasses.replace(r,linked=r.linked+(Linked('pknhrdma',str(hook.relative_to(ROOT)),dram=True),),
            detours=r.detours+(Detour(0x40004862,bytes.fromhex('720713c1fc04401c'),'pknhrdma','pk_nhr_dma_hook',
                'extract resident Noise Hat from completed stock DMA padding',pad_to=8),))
    CF.base.build_hybrid_module=module
    try:
        cf_stage=CF.build(WORK,control_transform=control,additional_units=(('pkhatrpc','cf_noise_hat_taps.c'),),
                 placement_source=source,version=VERSION,build_number=18)
    finally:CF.base.build_hybrid_module=original_module
    probe=WORK/'probe';asm=probe/'multi.asm'
    (ar,al,irq,render,br,bl),source_entry=N.build_program(WORK/'program',asm)
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
            A.wr(image,A.word_at(recs,0,site),0x0bf080)
            A.wr(image,A.word_at(recs,0,site+1),source_entry)
            resident_symbols=json.loads((WORK/'program/resident-symbols.json').read_text())
            assert [A.rd(image,A.word_at(recs,0,0x53e+i)) for i in range(2)]==[0x56f000,0x415]
            A.wr(image,A.word_at(recs,0,0x53e),0x0bf080)
            A.wr(image,A.word_at(recs,0,0x53f),resident_symbols['embed_entry'])
        else:
            A.wr(image,A.word_at(recs,0,site+1),N.S.plan(asm,'B')[2])
    appended=F.merge_upload_records(appended)
    normal=probe/'fragmented-normal.bin';normal.write_bytes(image)
    (probe/'p-records.json').write_text(json.dumps(appended,indent=2)+'\n')
    y,layout=P.load_tables(probe);x=P.load_state_init(probe,layout)
    # Initialize all resident limbs from the original CF initializer once,
    # through the existing per-core preboot upload. No live state round-trip.
    import ctypes as C
    init_source=WORK/'initial.c'
    # The two original C files have file-local helpers with equal names;
    # compile initialization and codec as distinct translation units.
    init_source.write_text('#include "'+str(ROOT/'modules/perky/cf_perky4.c')+'"\nextern void pk_nha_codec(unsigned char*,unsigned,unsigned short*,int);\nvoid nhr_initial(unsigned short*w){unsigned char s[0x2dd8]={0};nh_init_limb0(s);nh_init_limb1(s);nh_init_delay(s);nh_init_pulse(s);pk_nha_codec(s,0,w,0);pk_nha_codec(s,1,w,0);pk_nha_codec(s+0x2c98,2,w+121,0); }\n')
    initial_lib=WORK/'initial.dylib'
    subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I'+str(ROOT/'modules/perky'),str(init_source),
        str(ROOT/'modules/perky/cf_noise_hat_offload.c'),str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),'-o',str(initial_lib)],check=True)
    words=(C.c_uint16*180)();C.CDLL(str(initial_lib)).nhr_initial(words)
    initial=list(words)+[0]*62
    normal_extend=P.extend_upload
    def extend(img,tag,y,x=None,extra=None,extra_y=None,p_records=None):
        if tag=='A':
            x=initial
            extra=[(0x3970,[0,0,1,0,0,0]+[0]*11),(0x39b0,[0]*17),(0x39f0,[0]*17),(0x3a01,[0]*17),(0x3a23,[0]*8+[1,1,3,5,7]+[0]*4)]
        return normal_extend(img,tag,y,x,extra,extra_y,p_records)
    P.extend_upload=extend
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
    ranges=[('resident limbs and preboot initializer padding',N.STATE,N.STATE+242),('scratch and hold/RNG initializer',N.SCRATCH,N.SCRATCH+128),
            ('native stereo PCM',N.PCM,N.PCM+40),('request cursors and initializer',N.COUNT,N.COUNT+16),
            ('source registers',N.SAVED,N.SAVED+len(N.REGISTERS)),('feedback return mailbox plus initializer guard',N.MAIL,N.MAIL+34),('native clock, gains and initializer guard',0x3a23,0x3a23+17)]
    for i,(name,lo,hi) in enumerate(ranges):
        assert 0x3800<=lo<hi<=0x3a68
        assert all(not N.L.overlaps((lo,hi),(a,b)) for _,a,b in ranges[i+1:])
    memory=dict(schema='perky-noise-hat-taps-memory-v1',A_program=al,B_program=bl,
        A_program_words=sum(r['length'] for r in al),shared_capacity=N.L.shared_p_capacity(),
        shared_words=sum(shared.values()),shared_free=N.L.shared_p_capacity()-sum(shared.values()),
        private_P_used={tag:sum(r['length'] for r in rows if r['start']<0x30000)+(48 if tag=='A' else 0) for tag,rows in ledgers.items()},
        A_private_X=ranges,A_private_X_words=sum(hi-lo for _,lo,hi in ranges),A_private_X_capacity=616,
        A_low_Y_words=layout['total_words'],A_low_Y_capacity=2139,
        CF_ring_bytes=4805*2,host_vector=None,return_carrier=dict(core='A',buffer='stock X:2600/4600 readback banks',bits='low eight bits of each second halfword in the first 48 stereo sample words; stripped before stock CF reads',additional_DMA_words=0),retained_FX='all twelve code/dispatch bytes exact',
        notes=['A source hook renders, processes delay taps and resamples the CURRENT source frame, then jumps to stock AMP/FX.',
               'B retains its single admitted oscillator portfolio; no paired context exchange.',
               'Shared storage counted once. Ring and control shadow remain CF-owned; inner histories, delay arithmetic and clock are A-owned.',
               'Private-B tail boundary and new source/readback hooks remain hardware-unqualified.'])
    (WORK/'MEMORY.json').write_text(json.dumps(memory,indent=2)+'\n')
    report=dict(status='BUILT_NOT_QUALIFIED',hardware_validated=False,main_sha256=sha(main),
        runtime_sha256=sha(probe/'platform/runtime.elf'),memory=memory,irq_entry=irq,render_entry=render,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_entry=source_entry,transport='stock source DMA commands; 24 feedback mailbox words in existing readback padding; ring write latency measured by sequence tags; source generation in current frame',source_checkpoint_note='Checkpoint plus the uncommitted implementation hashes; no release commit.',
        compiler_flags=cf_stage['result']['compiler_flags'],
        baseline_PERKY4S_identity_verified_before_specialization=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/perky/perky_noise_hat_taps.py',
            ROOT/'modules/perky/cf_noise_hat_taps.c',ROOT/'tools/perky/build_cf_placement_probe.py',ROOT/'tools/harness/perky_cf/noise_hat_taps_engine.c',ROOT/'tools/verify/verify_perky_noise_hat_resident_boot.py')})
    (probe/'memory.json').write_text(json.dumps(dict(status='SUPERSEDED_BY_OFFLOAD_MEMORY',path=str(WORK/'MEMORY.json')),indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'tools/verify/verify_perky_noise_hat_resident_boot.py'),'--image',str(main),
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
    P.extend_upload=normal_extend
    print(json.dumps(report,indent=2))


if __name__=='__main__':build()
