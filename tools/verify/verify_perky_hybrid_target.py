#!/usr/bin/env python3
"""Execute isolated two-instance CF synthesis and PKR1 endian/readiness probes.

No firmware image is built. Sources are compiled with the existing production
ColdFire flags and run through the existing, tested ot::Machine libraries.
These observations exclude the stock callback, DSP, arbitration and hardware.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, os, re, shlex, shutil, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware',type=Path,required=True)
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--harness-dir',type=Path)
    args=ap.parse_args()
    root=next((p for p in Path(__file__).resolve().parents if (p/'tools/emu/ot_emu/machine.h').is_file()),None)
    if root is None: raise SystemExit('run inside the existing Octabam checkout')
    work=args.work.expanduser().resolve();work.mkdir(parents=True,exist_ok=True)
    hd=(args.harness_dir or root/'tools/harness/perky_cf').resolve()
    fw=args.firmware.expanduser().resolve();sys.path[:0]=[str(root/'tools/perky'),str(root/'tools')]
    import perky_cf_assets
    from remix import pack, arena
    spec=importlib.util.spec_from_file_location('generator',root/'modules/perky/generate_cf_final.py')
    generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    report={'schema':'octabam.perky.hybrid.isolated-target.v1','status':'RUNNING','hardware_feasibility':'UNVERIFIED','commands':[],'inputs':{'firmware':{'path':str(fw),'sha256':sha(fw)}}}
    def save(): (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(argv,name):
        argv=list(map(str,argv));start=time.monotonic()
        with (work/(name+'.log')).open('w') as f: result=subprocess.run(argv,cwd=root,stdout=f,stderr=subprocess.STDOUT)
        report['commands'].append({'argv':argv,'exit_status':result.returncode,'duration_seconds':time.monotonic()-start,'log':str(work/(name+'.log'))});save()
        if result.returncode: raise RuntimeError(f'{name} exited {result.returncode}; see {work/(name+".log")}')
        return (work/(name+'.log')).read_text()
    try:
        inventory=json.loads(run(['ctest','--test-dir',root/'out/emu','--show-only=json-v1'],'instrument-inventory'))
        if 'mc68kColdFireTimingTest' not in {t['name'] for t in inventory['tests']}:raise RuntimeError('corrected ColdFire timing test absent')
        run(['ctest','--test-dir',root/'out/emu','--no-tests=error','--output-on-failure'],'instrument')
        report['instrument_tests']=[t['name'] for t in inventory['tests']]
        tools={n:Path(shutil.which(n) or '') for n in ('m68k-elf-gcc','m68k-elf-objcopy','m68k-elf-nm','m68k-elf-size','m68k-elf-objdump','c++')}
        if any(not p.is_file() for p in tools.values()): raise RuntimeError('required existing compiler/tool absent')
        report['tools']={n:{'path':str(p),'sha256':sha(p)} for n,p in tools.items()}
        report['compiler_version']=run([tools['m68k-elf-gcc'],'--version'],'compiler-version').splitlines()[0]
        blobs=perky_cf_assets.extract(fw)
        asset_names={'pk_asset_pitch':'pitch','pk_asset_chromatic':'chromatic','pk_asset_envelope1':'envelope1','pk_asset_envelope2':'envelope2','pk_asset_wave0':'w0','pk_asset_wave1':'w1','pk_asset_wave2':'w2','pk_asset_wave3':'w3','pk_asset_m1_wave':'m1','pk_asset_res_interp_a':'interp_a','pk_asset_res_interp_b':'interp_b','pk_asset_wt_base':'wt_base','pk_asset_wt_bank':'wt_bank'}
        ad=work/'assets';ad.mkdir(exist_ok=True)
        for label,name in asset_names.items(): (ad/(name+'.bin')).write_bytes(blobs[label])
        report['assets']={name:{'bytes':len(blobs[label]),'sha256':hashlib.sha256(blobs[label]).hexdigest()} for label,name in asset_names.items()}
        stream=perky_cf_assets.pcm_stream(blobs);(work/'packed.pkr').write_bytes(stream)
        flags=[*generator.FLAGS,'-ffunction-sections','-fdata-sections','-fstack-usage','-MMD','-I',root/'modules/perky']
        target_sources=[hd/'hybrid_cf_bench.c',*[root/'modules/perky'/(n+'.c') for n in ('cf_wavetable','cf_resonant','cf_noise_tone')]]
        native_sources=[hd/'hybrid_cf_shadow_native.c',*target_sources[1:]]
        native_flags=['-x','c','-std=c99','-O3','-ffunction-sections','-fdata-sections','-I',hd,'-I',root/'modules/perky']
        # Discover every target C dependency before compiling any object, then
        # snapshot it. A header changing during compilation must fail even if
        # the final source set is otherwise self-consistent.
        objects=[];source_closure=set(target_sources)
        all_target_sources=[*target_sources,hd/'hybrid_cf_decode.c',hd/'hybrid_cf_callback.c']
        for source in all_target_sources:
            dependency=work/(source.stem+'-before.d')
            run([tools['m68k-elf-gcc'],*flags,'-MM','-MF',dependency,source],source.stem+'-dependencies')
            source_closure.update(Path(p).resolve() for p in shlex.split(dependency.read_text().replace('\\\n',' ').split(':',1)[1]))
        for source in native_sources:
            dependency=work/(source.stem+'-native-before.d')
            run([tools['c++'],*native_flags,'-MM','-MF',dependency,source],source.stem+'-native-dependencies')
            source_closure.update(Path(p).resolve() for p in shlex.split(dependency.read_text().replace('\\\n',' ').split(':',1)[1]))
        source_closure.update([Path(__file__).resolve(),root/'modules/perky/generate_cf_final.py',root/'tools/verify/verify_perky_cf_odd_access.py',*hd.glob('hybrid_cf_*'),*(root/'modules/perky').glob('*.c'),*(root/'modules/perky').glob('*.h')])
        compile_hashes={str(p):sha(p) for p in source_closure}
        report['source_sha256_before_compile']=dict(sorted(compile_hashes.items()));save()
        generated=work/'generated/production'
        diagnostic_assembly=work/'generated/diagnostic';diagnostic_assembly.mkdir(parents=True,exist_ok=True)
        run([sys.executable,root/'modules/perky/generate_cf_final.py','--out',generated],'production-codegen')
        assembly=list(generated.glob('*.s'))
        if len(assembly)!=len(generator.SOURCES) or any(not p.stat().st_size for p in assembly):raise RuntimeError('missing production generated assembly')
        odd=run([sys.executable,root/'tools/verify/verify_perky_cf_odd_access.py','--generated',generated],'production-odd-access')
        if '[SKIP]' in odd or not re.search(r'PASS \([1-9][0-9]* word/long operands, none odd\)',odd):raise RuntimeError('empty or skipped production odd-access audit')
        # Also inspect the exact diagnostic translation units: their layout and
        # inlining differ from the generic production adapter.
        for source in all_target_sources:
            run([tools['m68k-elf-gcc'],*flags,'-S',source,'-o',diagnostic_assembly/(source.stem+'.s')],source.stem+'-assembly')
        # Diagnostic layouts may use odd bases plus odd displacements. Their
        # actual effective-address alignment is checked by calibrated read/write
        # watches during every target call; keep the production static gate above.
        report['generated_assembly_sha256']={str(p):sha(p) for p in [*generated.glob('*.s'),*diagnostic_assembly.glob('*.s')]}
        for source in target_sources:
            obj=work/(source.stem+'.o');dep=work/(source.stem+'.d')
            run([tools['m68k-elf-gcc'],*flags,'-MF',dep,'-c',source,'-o',obj],source.stem+'-compile');objects.append(obj)
            source_closure.update(Path(p).resolve() for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]))
            for p in source_closure:
                current=sha(p)
                if compile_hashes.get(str(p))!=current:raise RuntimeError('source changed during target compilation: '+str(p))
        run([tools['m68k-elf-gcc'],'-mcpu=54455','-nostdlib','-Wl,--gc-sections','-Wl,--undefined=bench_prepare','-Wl,--undefined=bench_render','-Wl,--undefined=ready_cookie','-Wl,--undefined=bench_layout','-T',hd/'hybrid_cf_bench.ld',*objects,'-lgcc','-Wl,-Map='+str(work/'target.map'),'-o',work/'target.elf'],'target-link')
        run([tools['m68k-elf-objcopy'],'-O','binary',work/'target.elf',work/'target.bin'],'target-binary')
        (work/'target.nm').write_text(run([tools['m68k-elf-nm'],'-S','--size-sort',work/'target.elf'],'target-symbols'))
        sections=run([tools['m68k-elf-size'],'-A',work/'target.elf'],'target-sections')
        disassembly=run([tools['m68k-elf-objdump'],'-d',work/'target.elf'],'target-disassembly')
        renderer_lines=[];active=False
        for line in disassembly.splitlines():
            symbol=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
            if symbol: active=symbol.group(1).startswith('pk_cf_') or symbol.group(1)=='bench_render'
            if active: renderer_lines.append(line)
        bad=[line for line in renderer_lines if re.search(r'\b(?:div[us]?[wl]?|rem[us]?[wl]?)\b|__(?:u?div|u?mod|u?divmod|mul)(?:si|di)[34]',line)]
        if bad:raise RuntimeError('renderer division/helper escaped audit: '+str(bad[:4]))
        report['renderer_division_audit']={'instruction_count':len(renderer_lines),'division_or_wide_helper_sites':bad}
        report['linked_diagnostic_sections']={m.group(1):int(m.group(2)) for m in re.finditer(r'^(\.\w+)\s+(\d+)\s+\d+',sections,re.M)}
        run([tools['m68k-elf-gcc'],*flags,'-MF',work/'decode.d','-c',hd/'hybrid_cf_decode.c','-o',work/'decode.o'],'decode-compile')
        source_closure.update(Path(p).resolve() for p in shlex.split((work/'decode.d').read_text().replace('\\\n',' ').split(':',1)[1]))
        for p in source_closure:
            current=sha(p)
            if compile_hashes.get(str(p))!=current:raise RuntimeError('source changed during decoder compilation: '+str(p))
        run([tools['m68k-elf-gcc'],'-mcpu=54455','-nostdlib','-Wl,--gc-sections','-Wl,-e,bench_decode','-T',hd/'hybrid_cf_bench.ld',work/'decode.o','-lgcc','-o',work/'decode.elf'],'decode-link')
        run([tools['m68k-elf-objcopy'],'-O','binary',work/'decode.elf',work/'decode.bin'],'decode-binary')
        (work/'decode.nm').write_text(run([tools['m68k-elf-nm'],'-S','--size-sort',work/'decode.elf'],'decode-symbols'))
        # Compile the actual shipping private ensure/cookie path in its source
        # TU. Section GC discards unrelated OS callbacks. The generated incbin
        # stays under --work and is never a committed firmware asset.
        packed_path=str(work/'packed.pkr').replace('\\','\\\\').replace('"','\\"')
        (work/'callback-assets.s').write_text('.section .rodata.pcm,"a"\n.balign 4\n.global pk_asset_pcm_rice\n.global pk_asset_pcm_rice_end\npk_asset_pcm_rice:\n.incbin "'+packed_path+'"\npk_asset_pcm_rice_end:\n')
        run([tools['m68k-elf-gcc'],*flags,'-MF',work/'callback.d','-c',hd/'hybrid_cf_callback.c','-o',work/'callback.o'],'callback-compile')
        source_closure.update(Path(p).resolve() for p in shlex.split((work/'callback.d').read_text().replace('\\\n',' ').split(':',1)[1]))
        for p in source_closure:
            current=sha(p)
            if compile_hashes.get(str(p))!=current:raise RuntimeError('source changed during callback compilation: '+str(p))
        run([tools['m68k-elf-gcc'],'-mcpu=54455','-c',work/'callback-assets.s','-o',work/'callback-assets.o'],'callback-assets-compile')
        run([tools['m68k-elf-gcc'],'-mcpu=54455','-nostdlib','-Wl,--gc-sections','-Wl,-e,bench_callback_pcm','-T',hd/'hybrid_cf_bench.ld',work/'callback.o',work/'callback-assets.o','-lgcc','-o',work/'callback.elf'],'callback-link')
        run([tools['m68k-elf-objcopy'],'-O','binary',work/'callback.elf',work/'callback.bin'],'callback-binary')
        (work/'callback.nm').write_text(run([tools['m68k-elf-nm'],'-n',work/'callback.elf'],'callback-symbols'))
        run([tools['m68k-elf-size'],'-A',work/'callback.elf'],'callback-sections')
        libraries=[root/'out/emu'/p for p in ('libot_machine.a','mc68k/lib68kEmu.a','dsp56300/dsp56kEmu/libdsp56kEmu.a','dsp56300/dsp56kBase/libdsp56kBase.a','dsp56300/asmjit/libasmjit.a')]
        library_hashes={str(p):sha(p) for p in libraries}
        host_flags=['-std=c++17','-O3','-DNDEBUG','-DASMJIT_STATIC','-DDSP56300_DEBUGGER=0','-I'+str(root/'vendor'),'-I'+str(root/'tools/emu/ot_emu'),'-I'+str(root/'vendor/dsp56300/source'),'-I'+str(root/'vendor/dsp56300/source/asmjit/src')]
        native_objects=[]
        for source in native_sources:
            obj=work/(source.stem+'-native.o');dep=work/(source.stem+'-native.d')
            run([tools['c++'],*native_flags,'-MMD','-MF',dep,'-c',source,'-o',obj],source.stem+'-native-compile')
            native_objects.append(obj)
            for dependency in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                source_path=Path(dependency).resolve()
                if compile_hashes.get(str(source_path))!=sha(source_path):raise RuntimeError('native dependency changed: '+str(source_path))
        for name,source in [('runner','hybrid_cf_bench_runner.cpp'),('decode_runner','hybrid_cf_decode_runner.cpp'),('callback_runner','hybrid_cf_callback_runner.cpp')]:
            run([tools['c++'],*host_flags,'-I'+str(hd),hd/source,*(native_objects if name=='runner' else []),*libraries,*(['-Wl,-dead_strip'] if sys.platform=='darwin' else ['-Wl,--gc-sections']),'-lpthread','-o',work/name],name+'-compile')
            run([work/name,work,ad],name+'-execute')
        report['effective_address_alignment']={name:json.loads((work/(name+'-alignment.json')).read_text()) for name in ('bench','decode','callback')}
        for name,a in report['effective_address_alignment'].items():
            if not a['calibrated_even_and_odd_word_and_long'] or not a['wide_reads'] or not a['wide_writes'] or a['odd_reads'] or a['odd_writes']:raise RuntimeError('target alignment failed: '+name)
        report['target_native_exact']=json.loads((work/'shadow-result.json').read_text())
        exact=report['target_native_exact']
        if exact['status']!='PASS_EXACT_TARGET_NATIVE' or exact['byte_mismatches'] or (exact['init_checks'],exact['prepare_checks'],exact['render_checks'])!=(252,1953,20403) or exact['target_stream_sha256']!=exact['native_stream_sha256']:raise RuntimeError('incomplete or inexact target/native differential')
        report['decode']=json.loads((work/'decode-result.json').read_text())
        if report['decode']['byte_mismatches'] or report['decode']['status']!=1: raise RuntimeError('target decoded bytes are not exact original assets')
        report['decode']['sha256']=sha(work/'decoded-target.bin')
        report['shipping_pcm_readiness']=json.loads((work/'callback-result.json').read_text())
        report['shipping_pcm_readiness']['decoded_sha256']=sha(work/'callback-decoded-target.bin')
        report['readiness']=json.loads((work/'readiness.json').read_text())
        rows=list(csv.DictReader((work/'costs.csv').open()));phases={};totals=defaultdict(int)
        for phase in sorted({r['phase'] for r in rows}):
            rs=[r for r in rows if r['phase']==phase];v=sorted(int(r['cycles']) for r in rs)
            phases[phase]={'count':len(v),'min':v[0],'mean':sum(v)/len(v),'median':v[len(v)//2],'p95':v[(len(v)-1)*95//100],'max':v[-1],'max_stack_bytes':max(int(r['stack_bytes']) for r in rs),'worst_case':max(rs,key=lambda r:int(r['cycles']))}
        for r in rows:
            if r['phase']!='init':totals[('tail' if r['phase']=='tail-render' else 'matrix',r['left'],r['right'],r['corner'],r['frame'])]+=int(r['cycles'])
        report['timing']={'clock_hz':266000000,'clock_source':'tools/emu/ot_emu/periph.h:g_cfClockHz','sample_rate_hz':44100,'samples_per_frame':16,'frame_us':16*1000000/44100,'phases':phases,'max_control_plus_render_cycles':max(totals.values()),'max_control_plus_render_us':max(totals.values())/266,'decode_us':report['decode']['cycles']/266,'cycles_conversion':'microseconds = observed corrected-model cycles / 266'}
        frame_budget_cycles=16*266000000/44100
        observed_stack_bytes=max([p['max_stack_bytes'] for p in phases.values()]+[report['decode']['stack_bytes'],report['shipping_pcm_readiness']['first_decode_stack_bytes'],report['shipping_pcm_readiness']['ready_call_stack_bytes']]+[c['stack_bytes'] for c in report['shipping_pcm_readiness']['rejected_cold_asset_counts']])
        if max(totals.values())>=frame_budget_cycles:raise RuntimeError('observed isolated control+render cost exhausts the 16-sample frame')
        if observed_stack_bytes>1024:raise RuntimeError('observed target stack exceeds the proposed 1024-byte reserve')
        report['timing']['frame_budget_cycles']=frame_budget_cycles
        report['timing']['observed_control_plus_render_within_frame']=True
        report['timing']['observed_stack_within_1024_byte_reserve']=True
        if len([r for r in rows if r['phase']=='clean-render'])!=243 or len([r for r in rows if r['phase']=='prepare-clean'])!=243 or len([r for r in rows if r['phase']=='init'])!=243 or len([r for r in rows if r['phase']=='render'])!=15552 or len([r for r in rows if r['phase']=='tail-render'])!=4608: raise RuntimeError('incomplete benchmark matrix')
        # Concrete diagnostic allocation, deliberately separate from production.
        # Full PERKY4S four DSP preboot windows and runtime are kept occupied.
        baseline=json.loads((root/'modules/perky/hybrid/BASELINE.json').read_text())
        def ledger(x):
            if isinstance(x,dict):
                if 'ColdFire_DRAM_bytes' in x:return x['ColdFire_DRAM_bytes']
                for v in x.values():
                    found=ledger(v)
                    if found:return found
            elif isinstance(x,list):
                for v in x:
                    found=ledger(v)
                    if found:return found
        frozen=ledger(baseline)
        decoded=sum(len(blobs[k]) for k in ('pk_asset_wt_base','pk_asset_wt_bank'))
        static=sum(len(blobs[k]) for k in asset_names)-decoded
        image=(work/'target.bin').read_bytes()+(work/'decode.bin').read_bytes()+b''.join(blobs[k] for k in asset_names if k not in ('pk_asset_wt_base','pk_asset_wt_bank'))+stream
        os.environ['OCTABAM_NO_CACHE']='1';packed=pack.PACKED_MAGIC+len(image).to_bytes(4,'big')+pack.pack(image,128)
        (work/'diagnostic-runtime.gka').write_bytes(packed)
        begin=(frozen['stage_end']+4095)&~4095
        loaded=len(image);bss=report['linked_diagnostic_sections'].get('.bss',0)+8
        scratch=1024;stage=(begin+loaded+bss+decoded+scratch+4095)&~4095;end=stage+4+len(packed)
        if end>frozen['reserved_ceiling']:raise RuntimeError('measured diagnostic allocation escapes preserved reserve')
        report['memory']={'kind':'measured diagnostic components plus explicit prospective placement; no hybrid runtime linked','frozen_perky4s':frozen,'diagnostic_runtime_loaded_bytes':loaded,'diagnostic_bss_bytes':bss,'decoded_wt_bytes':decoded,'static_asset_bytes':static,'pkr1_stream_bytes':len(stream),'pkr1_sha256':sha(work/'packed.pkr'),'two_instance_state_bytes':report['readiness']['two_instance_bytes'],'observed_max_stack_bytes':observed_stack_bytes,'proposed_stack_reserve_bytes':scratch,'proposed_cached_start':begin,'proposed_cached_end':end,'proposed_uncached_start':begin+0x08000000,'proposed_uncached_end':end+0x08000000,'proposed_loader_stage':stage,'diagnostic_packed_stage_bytes':4+len(packed),'remaining_after_proposal_bytes':frozen['reserved_ceiling']-end}
        card=root/'out/frozen/PERKY4S/OCTATRACK_PERKY4S.bin'
        container=root/'out/frozen/PERKY4S/elek_PERKY4S.bin'
        card_bytes=card.read_bytes();container_bytes=container.read_bytes()
        if card_bytes[:4]!=b'ELUP' or container_bytes[:4]!=b'ELEK':raise RuntimeError('frozen packaging input signature drift')
        expected_card_size=12+((4+len(container_bytes)+3)&~3)
        if len(card_bytes)!=expected_card_size:raise RuntimeError('frozen ELUP/ELEK container accounting mismatch')
        component_capacity_bytes=len(card_bytes)+((12+loaded+3)&~3)
        if component_capacity_bytes>0x100000+12:raise RuntimeError('diagnostic components exceed even the card payload capacity')
        report['packaging']={'frozen_card':{'path':str(card),'sha256':sha(card),'bytes':len(card_bytes)},'frozen_elek':{'path':str(container),'sha256':sha(container),'bytes':len(container_bytes)},'component_capacity_file_bytes':component_capacity_bytes,'component_capacity_margin_bytes':0x100000+12-component_capacity_bytes,'component_capacity_scope':'Arithmetic capacity check adding complete uncompressed diagnostic components and loader framing to preserved baseline card; actual eventual hybrid container must be rebuilt and checked in Goal2.','card_file_cap_bytes':0x100000+12,'encrypted_payload_cap_bytes':0x100000,'framing':'ELUP bytes = 8 magic/seed + align4(4 + ELEK bytes) + 4 checksum','diagnostic_only':True,'hybrid_flashable_image_built':False,'main_uncompressed_size_is_not_payload_size':True,'actual_hybrid_container_size':'not built in this foundation stage'}
        source_closure.update([Path(__file__).resolve(),root/'modules/perky/generate_cf_final.py',root/'tools/perky/perky_cf_assets.py',root/'tools/perky/pcm_rice.py',root/'tools/remix/pack.py',root/'tools/emu/ot_emu/machine.h',root/'tools/emu/ot_emu/machine.cpp',root/'tools/emu/ot_emu/periph.h',root/'vendor/mc68k/Musashi/m68kcpu.h',root/'vendor/mc68k/Musashi/m68kcfcycles.h',*hd.glob('hybrid_cf_*')])
        for name,expected in compile_hashes.items():
            if sha(name)!=expected:raise RuntimeError('source changed during benchmark: '+name)
        report['source_sha256']={str(p):sha(p) for p in sorted(source_closure)}
        for p,h in library_hashes.items():
            if sha(p)!=h:raise RuntimeError('emulator library changed during benchmark: '+p)
        report['linked_library_sha256']=library_hashes
        report['artifact_sha256']={p.name:sha(p) for p in work.iterdir() if p.is_file() and p.name!='report.json'}
        report['limits']=['Isolated target-code lower-level costs, not full-machine or hardware feasibility.','Profiles share unchanged production helper bodies; original-reference profile distinctions are checked by separate correctness gates.','Synthesis timing excludes the production adapter, stock callback, DSP traffic, cache behavior, stalls and arbitration.','Branch predictor state persists across ordered cases; maxima are observed, not exhaustive timing bounds.','Long tails cover8192 samples without retrigger; there is no public explicit-release entry in the production CF API.','Shipping PCM readiness is executed directly with poisoned BSS; integration into an eventual hybrid callback remains Goal2.','Memory placement is a concrete checked proposal inside the frozen reserve, not a linked production hybrid image.']
        report['status']='PASS_ISOLATED_TARGET_CHECKS';save()
        print('Isolated two-instance target checks: PASS; hardware feasibility UNVERIFIED')
        print(f"max control+render {report['timing']['max_control_plus_render_cycles']} cycles / {report['timing']['max_control_plus_render_us']:.3f} us; frame {16e6/44100:.3f} us")
        print('report:',work/'report.json')
    except Exception as exc:
        report['status']='FAIL';report['failure']=str(exc);save();raise
if __name__=='__main__':main()
