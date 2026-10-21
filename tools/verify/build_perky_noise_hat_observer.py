#!/usr/bin/env python3
"""Isolated port correction: peripherals must advance during a long DSP IRQ.

The vendored interpreter assigns dspExecNop to the long-interrupt dispatch
slot. Its normal peripheral clock therefore stops until RTI, making an HTDE
poll wait forever after the first host read. Keep the original port/libraries
unchanged and explicitly service the existing peripheral clock in this copy.
"""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-offload/observer'
BASE=ROOT/'out/perky/hybrid/cf-placement-integrated/observer'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def build(work=WORK, dsp_transform=None, exact_header=None):
    global WORK
    WORK=work
    if WORK.is_symlink():WORK.unlink()
    WORK.mkdir(parents=True,exist_ok=True)
    path=ROOT/'tools/emu/ot_emu/dsp.cpp';source=path.read_text()
    marker='\t\t++m_stats.interp[i];\n\t\tc.dsp->execInterpreter();'
    assert source.count(marker)==1
    change='''
        // Isolated qualification runtime: hardware peripherals keep running
        // while the core executes a long interrupt. The interpreter's long
        // IRQ dispatch slot is a NOP, so use its original timed service here.
        if(c.dsp->getProcessingMode() == dsp56k::DSP::LongInterrupt)
            c.dsp->getExecPeripheralsFunc()(c.dsp.get());
'''
    source=source.replace(marker,change+marker)
    staged=WORK/'dsp.cpp';staged.write_text(dsp_transform(source) if dsp_transform else source)
    flags=(ROOT/'out/emu/CMakeFiles/ot_machine.dir/flags.make').read_text();options=[]
    for key in ('CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS'):
        options+=shlex.split(next(line.split(' = ',1)[1] for line in flags.splitlines() if line.startswith(key+' = ')))
    compile=['/usr/bin/c++',*options,'-I'+str(path.parent),'-c',str(staged),'-o',str(WORK/'dsp.o')]
    subprocess.run(compile,check=True)
    machine=(BASE/'machine.cpp').read_text()
    header=exact_header or ROOT/'tools/harness/perky_cf/noise_hat_observer.h'
    marker='#include "mc68k/cpuState.h"\n';assert machine.count(marker)==1
    machine=machine.replace(marker,marker+'#include "'+str(header)+'"\n')
    for expression in ('pc()','pcFast()','p'):
        marker=f'hybrid_safety::observer.step(*this, {expression});'
        assert machine.count(marker)==1
        machine=machine.replace(marker,marker+f'\n noise_hat_exact::observer.step(*this, {expression});')
    (WORK/'machine.cpp').write_text(machine)
    compile_machine=['/usr/bin/c++',*options,'-I'+str(path.parent),'-c',str(WORK/'machine.cpp'),'-o',str(WORK/'machine.o')]
    subprocess.run(compile_machine,check=True)
    oracle=WORK/'oracle.dylib'
    subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I'+str(ROOT/'modules/perky'),
        str(ROOT/'modules/perky/cf_noise_hat.c'),'-o',str(oracle)],check=True)
    receipt=json.loads((BASE/'OBSERVER_BUILD.json').read_text())
    link=next(c for c in receipt['commands'] if str(BASE/'ot_emu_safety') in c and '-o' in c)
    link=list(link);link[link.index('-o')+1]=str(WORK/'ot_emu_safety')
    link[link.index(str(BASE/'machine.o'))]=str(WORK/'machine.o')
    link.insert(link.index('-o'),str(WORK/'dsp.o'));subprocess.run(link,check=True)
    report=dict(status='BUILT_ISOLATED_LONG_IRQ_PERIPHERAL_CLOCK',
        source_sha256=sha(path),staged_sha256=sha(staged),binary_sha256=sha(WORK/'ot_emu_safety'),
        commands=[compile,compile_machine,link],base_observer_receipt_sha256=sha(BASE/'OBSERVER_BUILD.json'),
        exact_observer_header_sha256=sha(header),oracle_sha256=sha(oracle),oracle_source_sha256=sha(ROOT/'modules/perky/cf_noise_hat.c'),
        scope='Same target instructions and clock; existing peripheral service continues inside long DSP interrupts. Default emulator untouched.')
    (WORK/'OBSERVER_BUILD.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':build()
