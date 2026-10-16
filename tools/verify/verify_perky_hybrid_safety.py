#!/usr/bin/env python3
"""Build an isolated host observer; run bounded actual-image safety scenarios.

Does not build firmware or alter the shared emulator. The staged instrumentation
inserts RAM/register observations before every instruction on all three stepping
paths, and records eDMA source ownership from start through completion. This is
model evidence, never silicon timing or an exhaustive stack bound.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build(work, source_header=None, test_source=None):
    work.mkdir(parents=True, exist_ok=True)
    source_header = source_header or ROOT/'tools/harness/perky_hybrid_safety/observer.h'
    hdr=work/'observer.h';hdr.write_bytes(source_header.read_bytes())
    machine = (ROOT/'tools/emu/ot_emu/machine.cpp').read_text()
    # Include after the CPU headers, outside namespace ot. Fail on source drift.
    marker = '#include "mc68k/cpuState.h"\n'
    assert machine.count(marker)==1
    machine = machine.replace(marker, marker+f'#include "{hdr}"\n')
    for signature, pc_expr in [('bool Machine::step()', 'pc()'),
                               ('bool Machine::stepFast()', 'pcFast()')]:
        marker = signature+'\n\t{\n'
        assert machine.count(marker)==1
        machine=machine.replace(marker,marker+f'\t\thybrid_safety::observer.step(*this, {pc_expr});\n')
    marker='\t\t\tconst auto p = pc();\n'
    assert machine.count(marker)==1
    machine=machine.replace(marker, marker+'\t\t\thybrid_safety::observer.step(*this, p);\n')
    marker='\t\tm_pcField = &getCpuState()->pc;\n'
    assert machine.count(marker)==1
    machine=machine.replace(marker,marker+'''        addWriteWatch(0x80001c90, 0x8000318f,
            [](uint32_t a,uint8_t s,uint32_t,uint32_t pc) {
                hybrid_safety::observer.write(a,s,pc);
            });
        for(const auto& pair : hybrid_safety::observer.stacks) {
            const auto tcb=pair.first;
            addWriteWatch(pair.second.lo,pair.second.lo+31,
                [tcb](uint32_t,uint8_t,uint32_t,uint32_t) {
                    hybrid_safety::observer.guard(tcb);
                });
        }
''')
    periph=(ROOT/'tools/emu/ot_emu/periph.cpp').read_text()
    periph=f'#include "{hdr}"\n'+periph
    for marker,extra in [
        ('void Edma::start(const uint32_t _ch, const bool _paced)\n\t{',
         '\n hybrid_safety::observer.start(_ch,field(_ch,0,4),field(_ch,8,4),minorLoops(_ch),static_cast<int16_t>(field(_ch,6,2)));'),
        ('void Edma::complete(const uint32_t _ch)\n\t{',
         '\n hybrid_safety::observer.done(_ch);')]:
        assert periph.count(marker)==1
        periph=periph.replace(marker,marker+extra)
    flags=(ROOT/'out/emu/CMakeFiles/ot_machine.dir/flags.make').read_text()
    options=[]
    for key in ('CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS'):
        options+=shlex.split(next(line.split(' = ',1)[1] for line in flags.splitlines() if line.startswith(key+' = ')))
    commands=[]
    for name,source in [('machine',machine),('periph',periph)]:
        cpp=work/(name+'.cpp');cpp.write_text(source)
        cmd=['/usr/bin/c++',*options,'-c',str(cpp),'-o',str(work/(name+'.o'))]
        subprocess.run(cmd,check=True);commands.append(cmd)
    libs=ROOT/'out/emu'
    # Replacement objects resolve first; archive supplies all untouched members.
    cmd=['/usr/bin/c++','-O3','-flto','-arch','arm64',
         str(libs/'CMakeFiles/ot_emu.dir/main.cpp.o'),str(work/'machine.o'),str(work/'periph.o'),
         '-o',str(work/'ot_emu_safety'),*[str(libs/p) for p in (
             'libot_machine.a','mc68k/lib68kEmu.a','dsp56300/dsp56kEmu/libdsp56kEmu.a',
             'dsp56300/dsp56kBase/libdsp56kBase.a','dsp56300/asmjit/libasmjit.a')],'-lpthread']
    subprocess.run(cmd,check=True);commands.append(cmd)
    selftest=test_source or ROOT/'tools/harness/perky_hybrid_safety/observer_test.cpp'
    testcmd=['/usr/bin/c++',*options,'-I',str(hdr.parent),str(selftest),str(work/'machine.o'),str(work/'periph.o'),
             '-o',str(work/'observer_test'),*cmd[cmd.index(str(libs/'libot_machine.a')):]]
    # Assertions are the negative controls; override the release build's NDEBUG.
    testcmd.insert(1,'-UNDEBUG')
    testcmd.insert(testcmd.index(str(selftest)),'-UNDEBUG')
    subprocess.run(testcmd,check=True);commands.append(testcmd)
    subprocess.run([str(work/'observer_test')],check=True);commands.append([str(work/'observer_test')])
    result={'commands':commands,'source_hashes':{str(p):sha(p) for p in [source_header,hdr,Path(__file__),
        selftest,*[ROOT/'tools/emu/ot_emu'/name for name in
            ('machine.cpp','machine.h','periph.cpp','periph.h','rtos.h','main.cpp')]]},
        'binary_sha256':sha(work/'ot_emu_safety'),
        'staged_sha256':{n:sha(work/n) for n in ('machine.cpp','periph.cpp')},
        'linked_inputs':{str(p):sha(p) for p in [libs/'CMakeFiles/ot_emu.dir/main.cpp.o',
            libs/'libot_machine.a',libs/'mc68k/lib68kEmu.a',
            libs/'dsp56300/dsp56kEmu/libdsp56kEmu.a',libs/'dsp56300/dsp56kBase/libdsp56kBase.a',
            libs/'dsp56300/asmjit/libasmjit.a']}}
    (work/'OBSERVER_BUILD.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/safety-final/observer')
    ap.add_argument('--panel', action='store_true', help='Use the prebuilt observer and staged fixture/card.img')
    args=ap.parse_args(); work=args.work.resolve()
    if not args.panel:
        build(work)
    else:
        probe=ROOT/'out/perky/hybrid/probe'
        report=work.parent/'panel-stack.json'
        events=work.parent/'panel-events.txt'
        script=ROOT/'tools/harness/perky_hybrid_safety/panel.txt'
        card=work.parent/'fixture/card.img'
        elf=probe/'platform/runtime.elf'
        symbols=subprocess.check_output(['m68k-elf-nm','-n',str(elf)],text=True)
        render=next(row.split()[0] for row in symbols.splitlines() if row.endswith(' T pk_render'))
        cmd=[str(work/'ot_emu_safety'),'--image',str(probe/'mainos_PKHYB2P.bin'),
             '--card',str(card),'--set','OCTABAM','--project','RIG','--load-ms','90000',
             '--dsp','--dsp-dirty','123','--mkii','--pit-clock-hz','132000000',
             '--cf-cycles-clock','1.0','--live-script',str(script)]
        env=dict(os.environ,HYBRID_SAFETY_REPORT=str(report),HYBRID_SAFETY_EVENTS=str(events),HYBRID_RENDER_PC='0x'+render)
        inputs=[probe/'mainos_PKHYB2P.bin',elf,card,script,work/'ot_emu_safety']
        binding={str(p):sha(p) for p in inputs}
        with (work.parent/'panel.log').open('w') as log:
            result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        assert binding=={str(p):sha(p) for p in inputs}, 'inputs changed during run'
        logtext=(work.parent/'panel.log').read_text()
        assert 'DID NOT RETURN' not in logtext and 'unknown kind' not in logtext
        assert 'on quit' in logtext and '0 panel byte(s) still queued' in logtext
        observed=json.loads(report.read_text())
        assert observed['frames']==observed['frame_returns']>0
        assert observed['source_DMA_starts']>0 and observed['DMA_read_write_overlaps']==0
        assert observed['guard_writes_after_dispatch']==0
        assert not any(t['outside_extent'] for t in observed['stacks'])
        receipt={'command':cmd,'exit_status':result.returncode,'inputs':binding,
                 'outputs':{str(p):sha(p) for p in [report,events,work.parent/'panel.log']}}
        (work.parent/'PANEL_RUN.json').write_text(json.dumps(receipt,indent=2)+'\n')
        raise SystemExit(result.returncode)
