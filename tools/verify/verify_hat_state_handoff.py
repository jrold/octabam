#!/usr/bin/env python3
"""Execute CF/DSP takeovers against independent original source histories.

Untimed direct calls use the actual candidate CF image and DSP upload. Ordinary
ring/snapshot feedback is delivered three frames later. Main gets bounded
worker opportunities; no synthesis state is copied from the target to oracle.
Whole-machine lifecycle and fixed-budget measurements remain separate gates.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess

import verify_perky_hybrid_runtime as rt
import verify_hat_state_snapshot as snap

ROOT=rt.ROOT
U16,U32,I32=C.c_uint16,C.c_uint32,C.c_int32

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--frames',type=int,default=800)
    p.add_argument('--out',type=Path,help='Separate evidence directory, including receipt, for a comparison or negative control')
    a=p.parse_args();assert a.frames>=800
    w=a.build.resolve();out=a.out.resolve() if a.out else w/'handoff-gate';out.mkdir(parents=True,exist_ok=True)
    receipt=out/'HANDOFF_GATE.json' if a.out else w/'HANDOFF_GATE.json'
    build=json.loads((w/'BUILD.json').read_text())
    image=w/'probe'/('mainos_'+build['version']+'.bin');elf=image.parent/'platform/runtime.elf'
    assert sha(image)==build['main_sha256'] and sha(elf)==build['runtime_sha256']
    dll,bridge_command,bridge_sources=snap.build_bridge(out)
    dsp=C.CDLL(str(dll));dsp.fm_snapshot_open.argtypes=[C.c_char_p,C.c_char_p,U32]
    dsp.fm_snapshot_open.restype=C.c_void_p
    dsp.fm_snapshot_step.argtypes=[C.c_void_p,C.POINTER(U16),U32,C.POINTER(I32),C.POINTER(U16),C.POINTER(U16),C.POINTER(U32),C.POINTER(U16)]
    dsp.fm_snapshot_return_pc.argtypes=[C.c_void_p];dsp.fm_snapshot_return_pc.restype=U32
    dsp.fm_snapshot_close.argtypes=[C.c_void_p];dsp.fm_dsp_error.restype=C.c_char_p
    code,data=snap.flatten(w,out)
    entry=json.loads((w/'program/resident-symbols.json').read_text())['source_entry']
    handle=dsp.fm_snapshot_open(str(code).encode(),str(data).encode(),entry)
    assert handle,dsp.fm_dsp_error()
    reference=ROOT/'out/perky/hybrid/full-map-release/observer/full-map-oracle.dylib'
    ref=C.CDLL(str(reference))
    ref.fm_ref_init.argtypes=[C.POINTER(C.c_void_p)]
    ref.fm_ref_segment.argtypes=[U32,U32,U32]
    ref.fm_ref_prepare.argtypes=[U32,C.POINTER(U32),U32]
    ref.fm_ref_pcm.argtypes=[U32,C.POINTER(I32)]
    ref.fm_ref_hat.argtypes=[C.POINTER(U16),C.POINTER(U16),C.POINTER(U32)]
    ref.fm_ref_clock.argtypes=[U32,C.POINTER(U32)]
    names=('pitch','chromatic','envelope1','envelope2','w0','w1','w2','w3','m1','interp_a','interp_b','wt_base','wt_bank','closed','open','ride')
    assets=ROOT/'out/perky/hybrid/cf-placement/assets'
    buffers=[C.create_string_buffer((assets/(n+'.bin')).read_bytes()) for n in names]
    ref.fm_ref_init((C.c_void_p*16)(*[C.addressof(b) for b in buffers]))
    boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
    def machine():
        r,s=rt.machine(image,elf,True);u=r.uc
        if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
        if 'fma_ready' in s:
            for name in ('closed','open','ride'):u.mem_write(s['pk_placement_'+name],(assets/(name+'.bin')).read_bytes())
            rt.w32(u,s['fma_ready'],0x41484f4b)
        return r,s
    # A separate, fresh target proves startup-disabled ownership through the
    # public audio entry. Its one source frame never enters the main target or
    # independent oracle history used for the complete wrap trajectory.
    startup_r,startup_s=machine();startup_u=startup_r.uc
    rt.w32(startup_u,startup_s['pk_nhr_enabled'],0)
    rt.w32(startup_u,startup_s['pk_prod_generation'],1)
    initial=[5,0,96,31,17,11,255,45,0,1]
    startup_u.mem_write(startup_s['placement_inputs']+120,b''.join(v.to_bytes(4,'big') for v in initial))
    rt.g.emu._call(startup_u,startup_s['pk_nhr_frame'],(0,0x48010000))
    assert rt.word(startup_u,startup_s['placement_status'])==1
    assert rt.word(startup_u,startup_s['pk_nhb_owner'])==0
    assert rt.word(startup_u,startup_s['pk_nhr_sequence'])==0
    assert rt.word(startup_u,startup_s['pk_nhb_snapshot_requests'])==0
    if 'nhs_transport_started' in startup_s:assert rt.word(startup_u,startup_s['nhs_transport_started'])==0
    r,s=machine();u=r.uc
    # Before the first audio call, require the actual reset to initialize its
    # epoch deterministically even for the poisoned value that would otherwise
    # collide with the initial imported-epoch marker on the first request.
    rt.w32(u,s['nhs_epoch'],0xfffffffe)
    started=s.get('nhs_transport_started')
    if started is not None:rt.w32(u,started,0xffffffff)
    consumed_valid=s.get('nhr_last_consumed_valid')
    if consumed_valid is not None:
        rt.w32(u,consumed_valid,1);rt.w32(u,s['nhr_last_consumed'],0xffffffff)
        u.mem_write(s['pk_nhr_mail'],bytes.fromhex('4e52'))
    rt.g.emu._call(u,s['pk_nhb_reset'])
    assert rt.word(u,s['nhs_epoch'])==1
    assert rt.word(u,s['nhs_imported_epoch'])!=2
    if started is not None:assert rt.word(u,started)==0
    if consumed_valid is not None:
        assert rt.word(u,consumed_valid)==0
        assert rt.word(u,s['nhr_last_consumed'])==0
        assert bytes(u.mem_read(s['pk_nhr_mail'],2))==bytes(2)
    # Seed transport counters only before the first direct audio frame. This
    # fixture crosses both the 16-bit wire and full 32-bit transport wrap.
    rt.w32(u,s['pk_nhr_sequence'],0xffffff80);rt.w32(u,s['pk_nhr_consumed'],0xffffff80)
    # Native delay feedback counters wrap much sooner than frame sequence.
    # Seed the empty queue as an initial condition, then let only real source
    # production and normal delayed ring feedback move these counters.
    for name in ('nht_issued','nht_committed'):rt.w32(u,s[name],0xfffffff0)
    layout=out/'offsets.c'
    layout.write_text('#include <stddef.h>\n#include <stdio.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\nint main(void){printf("%zu %zu\\n",sizeof(pk4_track),offsetof(pk4_track,nh));}\n')
    subprocess.run(['cc','-I'+str(ROOT/'modules/perky'),str(layout),'-o',str(out/'offsets')],check=True)
    stride,nh_offset=map(int,subprocess.check_output([str(out/'offsets')],text=True).split())
    assert stride==rt.word(u,s['placement_layout'])
    rng_offset=rt.word(u,s['placement_layout']+28);hold_offset=rt.word(u,s['placement_layout']+48)
    raw=s['placement_engine']+3*stride+nh_offset
    packet_at,raw_at=0x48010000,0x48020000
    pcm=(I32*16)();state=(U16*180)();side=(U16*6)();clock=(U32*3)();mail=(U16*24)()
    want_pcm=(I32*16)();want_state=(U16*180)();want_side=(U16*6)();want_clock=(U32*3)();writes=(U32*60)()
    counters=('pk_nhb_inner_calls','pk_nhb_snapshot_requests','pk_nhb_snapshot_completed',
              'pk_nhb_snapshot_rejected','pk_nhb_snapshot_words','pk_nhb_replay_frames','pk_nhb_handoff_jobs')
    def count():return {n:rt.word(u,s[n]) for n in counters}
    def call(name,values=()):rt.g.emu._call(u,s[name],values)
    def cf_compact():
        u.mem_write(raw_at,bytes(360))
        call('pk_nha_codec',(raw,0,raw_at,0));call('pk_nha_codec',(raw,1,raw_at,0))
        call('pk_nha_codec',(raw+0x2c98,2,raw_at+242,0))
        return list(struct.unpack('>180H',u.mem_read(raw_at,360)))
    pending=[];events=[];owners={0:0,1:0};generation=1;wrap=False;full_wrap=False;normal_sequences=set()
    zero_sequence_request=False;zero_sequence_repeat=False
    ring_previous={name:rt.word(u,s[name]) for name in ('nht_issued','nht_committed')}
    ring_wraps={name:False for name in ring_previous}
    steady_before=None;steady_after=None
    try:
        for frame in range(a.frames):
            if frame==96:
                steady_before=count();assert all(v==0 for v in steady_before.values()),steady_before
            desired=1
            if 96<=frame<104 or 112<=frame<240 or 300<=frame<480 or 520<=frame<670:desired=0
            # Cancel while still collecting, emit the source packet whose full
            # sequence is zero, then request CF at precisely that boundary.
            if frame==127:desired=1
            rt.w32(u,s['pk_nhr_enabled'],desired)
            if frame==320:generation+=1
            rt.w32(u,s['pk_prod_generation'],generation)
            if frame==131:
                # Normal sequence-zero feedback was consumed on frame130.
                # Let its real mailbox persist one extra frame: a valid zero
                # return must be deduplicated without replaying ring/snapshot
                # writes. Every new return remains queued, now four frames late.
                assert bytes(u.mem_read(s['pk_nhr_mail'],4))==bytes.fromhex('4e520000')
                assert rt.word(u,s['nhr_last_consumed'])==0
                if consumed_valid is not None:assert rt.word(u,consumed_valid)==1
                repeat_before={name:rt.word(u,s[name]) for name in
                               ('pk_nhr_consumed','nht_committed','pk_nhb_snapshot_words')}
            elif len(pending)>=3:u.mem_write(s['pk_nhr_mail'],pending.pop(0))
            split=0 if frame==0 or frame==320 else frame%17
            mode=1 if 280<=frame<340 else (frame//7)%3
            algo=3 if 535<=frame<575 else 5
            values=[algo,mode,96+(frame%32),(frame*7+31)%128,(frame*13+17)%128,(frame*19+11)%128,255,45,split,int(frame%4==0)]
            inputs=(U32*10)(*values)
            u.mem_write(s['placement_inputs']+120,b''.join(v.to_bytes(4,'big') for v in values))
            ref.fm_ref_start();assert ref.fm_ref_segment(3,0,split)
            assert ref.fm_ref_prepare(3,inputs,generation)
            assert ref.fm_ref_segment(3,split,16)
            ref.fm_ref_pcm(3,want_pcm);ref.fm_ref_hat(want_state,want_side,writes);ref.fm_ref_clock(3,want_clock)
            if frame==128:
                assert rt.word(u,s['pk_nhr_sequence'])==0
                assert rt.word(u,s['pk_nhb_owner'])==1
                assert rt.word(u,s['nhs_state'])==0
                previous_requests=rt.word(u,s['pk_nhb_snapshot_requests'])
            call('pk_nhr_frame',(split,packet_at))
            assert rt.word(u,s['placement_status'])==1,(frame,'placement')
            owner=rt.word(u,s['pk_nhb_owner']);owners[owner]+=1
            if frame==128:
                assert owner==1,('sequence zero bypassed nonblocking DSP takeover',owner)
                assert rt.word(u,s['pk_nhb_snapshot_requests'])==previous_requests+1
                assert rt.word(u,s['nhs_state'])==2
                zero_sequence_request=True
            if frame==131:
                assert rt.word(u,s['pk_nhr_failures'])==0,('valid repeated sequence-zero return rejected',rt.word(u,s['pk_nhr_failures']))
                assert {name:rt.word(u,s[name]) for name in repeat_before}==repeat_before
                zero_sequence_repeat=True
            packet=(U16*168)(*struct.unpack('>168H',u.mem_read(packet_at,336)))
            assert dsp.fm_snapshot_step(handle,packet,168,pcm,state,side,clock,mail),dsp.fm_dsp_error()
            returned=dsp.fm_snapshot_return_pc(handle)
            if owner:
                assert returned==0x426,(frame,'DSP return',hex(returned))
                assert list(pcm)==list(want_pcm),(frame,'DSP PCM',list(pcm),list(want_pcm))
                assert list(state)==list(want_state),(frame,'DSP state',[(i,x,y) for i,(x,y) in enumerate(zip(state,want_state)) if x!=y][:8])
                assert list(side)==list(want_side),(frame,'DSP side',list(side),list(want_side))
                if algo==5:
                    assert list(clock[:2])==list(want_clock[:2]),(frame,'DSP clock')
                    if clock[1]:assert clock[2]&65535==want_clock[2]&65535,(frame,'DSP carry')
                sequence=rt.word(u,s['pk_nhr_sequence']);normal_sequences.add(sequence)
                wrap|=(sequence&65535)==0
                full_wrap|=sequence==0
            else:
                assert returned==0x5002,(frame,'CF return',hex(returned))
                actual=list(struct.unpack('>16i',u.mem_read(s['placement_output']+192,64)))
                assert actual==list(want_pcm),(frame,'CF PCM',actual,list(want_pcm))
                actual_state=cf_compact()
                assert actual_state==list(want_state),(frame,'CF state',[(i,x,y) for i,(x,y) in enumerate(zip(actual_state,want_state)) if x!=y][:8])
                hold_at=s['placement_engine']+hold_offset
                rng_at=s['placement_engine']+3*stride+rng_offset
                low,high=rt.word(u,rng_at),rt.word(u,rng_at+4)
                actual_side=[*struct.unpack('>2H',u.mem_read(hold_at,4)),low&65535,low>>16,high&65535,high>>16]
                assert actual_side==list(want_side),(frame,'CF side',actual_side,list(want_side))
                actual_clock=[rt.word(u,s['placement_clocks']+36+4*i) for i in range(3)]
                assert actual_clock[:2]==list(want_clock[:2]),(frame,'CF clock',actual_clock,list(want_clock))
                if actual_clock[1]:assert actual_clock[2]==want_clock[2],(frame,'CF carry',actual_clock,list(want_clock))
            pending.append(struct.pack('>24H',*mail))
            # Catch-up must get more than one work opportunity per audio frame.
            # This changes no source state except through the real target API.
            for _ in range(8):
                if rt.word(u,s['pk_nhb_completed'])==rt.word(u,s['pk_nhb_produced']):break
                call('pk_nhb_work')
            for name in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors'):
                assert rt.word(u,s[name])==0,(frame,name,rt.word(u,s[name]))
            assert rt.word(u,s['pk_nhb_completed'])<=rt.word(u,s['pk_nhb_produced']),(frame,'completion overrun')
            for name,previous in ring_previous.items():
                current=rt.word(u,s[name]);ring_wraps[name]|=current<previous;ring_previous[name]=current
            if frame in (95,103,111,126,127,128,130,131,239,259,319,339,479,499,534,574,669,699,a.frames-1):
                event=dict(frame=frame,desired=desired,owner=owner,generation=generation,counters=count(),switches=rt.word(u,s['pk_nhb_switches']))
                events.append(event);(out/'EVENTS.json').write_text(json.dumps(events,indent=2)+'\n');print(json.dumps(event),flush=True)
            if frame==700:steady_after=count()
        final=count();assert steady_after==final,('steady DSP resumed duplicate work',steady_after,final)
        assert owners[0]>64 and owners[1]>64 and wrap and full_wrap and zero_sequence_request and zero_sequence_repeat
        assert max(normal_sequences)>0xffff0000 and min(normal_sequences)==0
        assert started is not None and rt.word(u,started)==1
        assert consumed_valid is not None and rt.word(u,consumed_valid)==1
        assert all(ring_wraps.values()),ring_wraps
        assert final['pk_nhb_inner_calls']>0 and final['pk_nhb_snapshot_completed']>=3
        assert rt.word(u,s['pk_nhb_switches'])>=6
        result=dict(status='PASS_ACTUAL_CF_DSP_NONBLOCKING_STATE_HANDOFF',frames=a.frames,owners=owners,
                    events=events,counters=final,steady_before=steady_before,steady_after=steady_after,
                    transport_sequence_wrap=True,full_transport_sequence_wrap=True,
                    zero_sequence_cf_request=True,startup_disabled_cf=True,startup_flag_poisoned_reset=True,
                    repeated_zero_sequence_feedback=True,poisoned_consumer_valid_reset=True,
                    native_ring_counters_wrap=True,native_ring_counter_wraps=ring_wraps,
                    native_ring_fixture_initial_value='0xfffffff0',
                    sequence_fixture_initial_value='0xffffff80',feedback_delay_frames=3,
                    feedback_delay_frames_after_zero_repeat=4,worker_calls_per_frame_max=8,
                    poisoned_epoch_reset=True,epoch_fixture_initial_value='0xfffffffe',
                    image_sha256=sha(image),elf_sha256=sha(elf),
                    inputs={str(p):sha(p) for p in (image,elf,w/'dsp-A.upload.bin',reference,code,data,dll)},
                    source_sha256={str(p):sha(p) for p in (Path(__file__),Path(snap.__file__),*bridge_sources)},
                    limits=['Direct calls and three-frame delayed mail, increased to four by one deliberate repeat, test state/audio, not whole-machine scheduling or hardware timing.',
                            'Transport and empty native-ring counters seeded near full 32-bit wrap before first direct frame; subsequent state follows only real controls/transport/worker APIs.',
                            'Whole-machine lifecycle tests independently exercise interrupted worker execution.'])
        receipt.write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
    finally:dsp.fm_snapshot_close(handle)

if __name__=='__main__':main()
