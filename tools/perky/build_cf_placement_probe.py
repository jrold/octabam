#!/usr/bin/env python3
"""Build the opt-in four-CF native-clock workload probe; no flash wrappers.

Production sources are transformed only in ignored generated output. Existing
PERKY4S DSP identity is enforced by the normal hybrid builder. This is a timing
and source-ownership experiment, not a release or complete UI/lifecycle port.
"""
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools','tools/build','tools/perky','tools/verify','modules/perky')]
import build_cf_dsp_hybrid as base
from remix.schema import Linked

DISPATCH=r'''
    unsigned voice=track==0u?0u:track==1u?1u:track==4u?2u:track==5u?3u:4u;
    if(voice==4u||!signed_track(part_base(),track))
        return ((int (*)(unsigned,unsigned,unsigned,unsigned))0x40004008u)(track,ping,start,end);
    if(!(placement_mask&(1u<<voice))) {
        if(track==0u||track==4u)return pk_render(track,ping,start,end);
        return ((int (*)(unsigned,unsigned,unsigned,unsigned))0x40004008u)(track,ping,start,end);
    }
    if(end<start||end>16u)return 0;
    uint32_t begin=pk_hybrid_profiler_enable?pk_hybrid_timer_now():0u;
    if((U8(0x46104d0cu+track)&16u)!=0u)placement_trigger[voice]=1u;
    if(end==16u) {
        volatile uint16_t *fp=(volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
        uint32_t *p=placement_inputs[voice];
        p[2]=(uint8_t)(fp[DECAY_SLOT]>>8);p[3]=(uint8_t)(fp[TUNE_SLOT]>>8);
        p[4]=(uint8_t)(fp[PARAM1_SLOT]>>8);p[5]=(uint8_t)(fp[PARAM2_SLOT]>>8);
        p[6]=255u;p[7]=45u;p[8]=start;p[9]=placement_trigger[voice];
        if(!placement_prepare(voice,p,p[9]!=0))placement_status=0;
    }
    if(!placement_segment(voice,start,end,start?1u:0u))placement_status=0;
    uint32_t n=end-start,words=4u+2u*n;
    volatile uint32_t *cursor=(volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    for(unsigned i=0;i<words;i++)cursor[i]=0;
    U32(0x80001c80u)=(uint32_t)(uintptr_t)(cursor+words);
    if(end==16u) {
        placement_pack(voice,start);
        pk_hybrid_commit_longs(pk_hybrid_fixed_slot(track,ping),placement_packets[voice],40u);
        placement_calls[voice]++;placement_trigger[voice]=0;
    }
    if(pk_hybrid_profiler_enable) {
        pk_hybrid_cur_cf_ticks+=pk_hybrid_timer_now()-begin;
        pk_hybrid_cur_voice_mask|=1u<<track;pk_hybrid_cur_has_data=1u;
    }
    return 0;
'''


def replace_once(source,old,new):
    assert source.count(old)==1,old[:80]
    return source.replace(old,new,1)


def transformed():
    source=(ROOT/'modules/perky/control_cf_dsp_hybrid.c').read_text()
    source=replace_once(source,'#include "cf_pcm_rice.h"',
                        '#include "cf_pcm_rice.h"\n#include "placement_cf_api.h"\nstatic uint32_t placement_trigger[4];')
    source=replace_once(source,'hi - lo > 0x40000u','hi - lo > 0x80000u')
    boot='''
    {extern const uint8_t pk_placement_closed[],pk_placement_open[],pk_placement_ride[];
     static const uint8_t *const p[16]={pk_asset_pitch,pk_asset_chromatic,pk_asset_envelope1,pk_asset_envelope2,
        pk_asset_wave0,pk_asset_wave1,pk_asset_wave2,pk_asset_wave3,pk_asset_m1_wave,
        pk_asset_res_interp_a,pk_asset_res_interp_b,pk_pcm_wt_base,pk_pcm_wt_bank,
        pk_placement_closed,pk_placement_open,pk_placement_ride};
     placement_bind(p);placement_init();}
'''
    source=replace_once(source,'    if (!pk_hybrid_ensure_pcm()) return 0;',
                        '    if (!pk_hybrid_ensure_pcm()) return 0;'+boot)
    signature='int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)\n{'
    start=source.index(signature)+len(signature);level=1;end=start
    while level:
        if source[end]=='{':level+=1
        if source[end]=='}':level-=1
        end+=1
    source=source[:start]+DISPATCH+source[end-1:]
    return source


def build(work, *, control_transform=None, additional_units=(), placement_source=None,
          version='PKCFP1', build_number=14, source_transform=None):
    work.mkdir(parents=True,exist_ok=True)
    baseline=work/'baseline'
    if not baseline.exists():baseline.symlink_to(ROOT/'out/perky/hybrid/baseline',target_is_directory=True)
    assets=ROOT/'out/perky/hybrid/cf-placement/assets'
    assert all((assets/(n+'.bin')).exists() for n in ('closed','open','ride')),'run the native-clock source benchmark first'
    original_generate=base.generate_hybrid_cf_units;original_module=base.build_hybrid_module
    extra=(('pkfold','cf_fold.c'),('pksimple','cf_simple_drum.c'),('pkcomplex','cf_complex_drum.c'),
           ('pkslap','cf_slap.c'),('pkhat','cf_noise_hat.c'),('pkacoustic','cf_acoustic_hats.c'))+tuple(additional_units)
    generated={};compiled_flags=[]
    def generate(out):
        out.mkdir(parents=True,exist_ok=True)
        control=out/'placement-control.c'
        text=transformed();control.write_text(control_transform(text) if control_transform else text)
        units=[('pkcontrol',control),*[(n,ROOT/'modules/perky'/s) for n,s in base.HYBRID_CF_UNITS if n!='pkcontrol'],
               *[(n,ROOT/'modules/perky'/s) for n,s in extra],
               ('pkplacement',placement_source or ROOT/'tools/harness/perky_cf/placement_cf_engine.c')]
        flags=[*base.generate_cf_final.FLAGS,'-ffunction-sections','-fdata-sections',
               '-Wno-unused-function','-Wno-unused-variable','-I',ROOT/'modules/perky',
               '-I',ROOT/'tools/harness/perky_cf','-I',ROOT/'out/perky/hybrid/cf-placement']
        compiled_flags[:]=list(map(str,flags))
        result=[]
        for name,source in units:
            if source_transform:
                replacement=source_transform(name,source)
                if replacement is not None:source=replacement
            destination=out/(name+'.s')
            subprocess.run(list(map(str,['m68k-elf-gcc',*flags,'-S',source,'-o',destination])),cwd=ROOT,check=True)
            generated[str(source.relative_to(ROOT))]=base.sha256_file(source)
            result.append(destination)
        hats=out/'pkhats.s'
        hats.write_text('.section .rodata\n'+''.join(f'.balign 4\n.globl pk_placement_{n}\npk_placement_{n}:\n.incbin "{assets/(n+".bin")}"\n' for n in ('closed','open','ride')))
        result.append(hats);return result
    def module(*args,**kwargs):
        result=original_module(*args,**kwargs);directory=kwargs['generated_dir']
        units=tuple(Linked(n,base.base.repo_relative(directory/(n+'.s')),dram=True) for n,_ in extra)
        units+=(Linked('pkplacement',base.base.repo_relative(directory/'pkplacement.s'),dram=True),
                Linked('pkhats',base.base.repo_relative(directory/'pkhats.s'),dram=True))
        return dataclasses.replace(result,linked=result.linked+units)
    base.generate_hybrid_cf_units=generate;base.build_hybrid_module=module
    base.PROBE_VERSION=version;base.PROBE_BUILD_NUMBER=build_number
    try:result=base.build_probe(work,wrap=False)
    finally:base.generate_hybrid_cf_units=original_generate;base.build_hybrid_module=original_module
    result['status']='EXPERIMENT_BUILT_NOT_QUALIFIED'
    result['tracks']={str(t):dict(firmware_track_index=t-1,logical_voice=v,
        runtime='diagnostic CF selector; frozen DSP source only on T1/T5 when CF is disabled')
        for t,v in ((1,'V1'),(2,'V2'),(5,'V3'),(6,'V4'))}
    result['experimental_contract']='Diagnostic selectors set generic engines/modes; current hybrid UI is not remapped. CF source evolution is 48 kHz with 24-bit source packing.'
    result['compiler_flags']=compiled_flags
    (work/'probe/BUILD.json').write_text(json.dumps(result,indent=2)+'\n')
    report=dict(schema='perky-cf-placement-probe-v1',status='EXPERIMENT_BUILT_NOT_RELEASE',hardware_validated=False,
        result=result,generated_sources=generated,
        implementation_sha256={str(p.relative_to(ROOT)):base.sha256_file(p) for p in
            (Path(__file__),ROOT/'tools/harness/perky_cf/placement_cf_engine.c',ROOT/'modules/perky/cf_native_clock.h',ROOT/'tools/harness/perky_cf/placement_cf_api.h')},
        limits=['Diagnostic algorithm/mode selectors are host-controlled; current hybrid menus are not remapped.',
                'Native control preparation cadence is the existing port contract; oscillator sample evolution runs at 48 kHz.',
                'Bank/Part lifecycle and dynamic backend migration are not qualified.',
                'Extended BSS is bounded to 512 KiB within the existing linker/arena reservation.'])
    (work/'EXPERIMENT_BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/cf-placement-integrated')
    build(p.parse_args().work.resolve())
