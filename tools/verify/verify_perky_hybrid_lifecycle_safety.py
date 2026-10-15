#!/usr/bin/env python3
"""Target-code selection/persistence and generation regressions for retained hybrid.

Executes the linked PK signature writer and dispatcher, not a reimplementation.
Stock continuation is intercepted in component cases; real stock UI/Bank/Part/
STOP/DMA behavior belongs to the separate full-machine panel run. No test here
claims power-loss persistence or physical concurrency.
"""
import argparse
import json
from pathlib import Path
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.m68k_const import UC_M68K_REG_A0, UC_M68K_REG_D0, UC_M68K_REG_D1
import verify_perky_hybrid_runtime as rt


def run(probe, output):
    image,elf=probe/'mainos_PKHYB2P.bin',probe/'platform/runtime.elf'
    r,s=rt.machine(image,elf,True);u=r.uc
    call=rt.g.emu._call
    if not any(lo<=0x100a0000<=hi for lo,hi,_ in u.mem_regions()):
        u.mem_map(0x100a0000,0x10000)
    bank=rt.word(u,rt.g.emu.PART_PTR)
    stride=0x100000
    u.mem_map(bank+stride,0x100000)
    u.mem_write(bank+stride,bytes(u.mem_read(bank,stride)))
    sizes=rt.sizes(elf)
    state_addr=s['pk_hybrid_voices']; state_n=sizes['pk_hybrid_voices']
    sizes_inst=state_n//2
    result={'schema':'octabam.perky.hybrid.lifecycle-safety.v1','status':'RUNNING',
            'image_sha256':rt.digest(image),'elf_sha256':rt.digest(elf),'tests':{}}

    def mark(bank_index,part_index,track,on):
        rt.w32(u,rt.g.emu.PART_PTR,bank+bank_index*stride)
        u.mem_write(0x100b14cf,bytes((part_index,)))
        part=bank+bank_index*stride+0x8ed80+part_index*0x18b2
        u.mem_write(part+0x22+track,b'\x01')
        u.reg_write(UC_M68K_REG_A0,part)
        u.reg_write(UC_M68K_REG_D0,track)
        u.reg_write(UC_M68K_REG_D1,int(on))
        call(u,s['pk_sig_write'])
        return part

    transitions=0
    for b in range(2):
        for p in range(4):
            for t in (0,1,4,5):
                part=mark(b,p,t,False)
                part=mark(b,p,t,True)
                sig=part+60+30*t
                mirror=0x100a4ece+p*0x18b2+60+30*t
                assert bytes(u.mem_read(sig,3))==b'PK\x01'
                assert bytes(u.mem_read(mirror,3))==b'PK\x01'
                donor=part+0x2cb+5*t
                donor_mirror=0x100a4ece+p*0x18b2+0x2cb+5*t
                assert u.mem_read(donor,1)==u.mem_read(donor_mirror,1)==bytes((128+t,))
                # Already selected PERKY keeps the stored sound.
                vals=bytes((17,94,1,73,25,2))
                u.mem_write(part+48+30*t,vals)
                mark(b,p,t,True)
                assert bytes(u.mem_read(part+48+30*t,6))==vals
                mark(b,p,t,False)
                assert bytes(u.mem_read(sig,3))==bytes(3)
                assert bytes(u.mem_read(mirror,3))==bytes(3)
                mark(b,p,t,True)
                assert bytes(u.mem_read(part+48+30*t,6))==bytes(u.mem_read(s['pk_defaults'],6))
                transitions+=1
    result['tests']['linked_selection_and_SRAM_mirror']={'cases':transitions,'status':'PASS',
        'scope':'Two bank pointers, all four Parts, T1/T2/T5/T6; actual signature writer; no file-save claim'}

    stock=[]
    def stock_entry(mu,pc,size,data):
        sp=mu.reg_read(rt.g.emu.UC_M68K_REG_A7)
        stock.append(tuple(rt.word(mu,sp+4*i) for i in range(1,5)))
        mu.reg_write(UC_M68K_REG_D0,0)
        mu.reg_write(rt.g.emu.UC_M68K_REG_PC,rt.word(mu,sp))
        mu.reg_write(rt.g.emu.UC_M68K_REG_A7,sp+4)
    hook=u.hook_add(UC_HOOK_CODE,stock_entry,begin=0x40004008,end=0x40004008)
    u.ctl_flush_tb()
    writes=[]
    wh=u.hook_add(UC_HOOK_MEM_WRITE,lambda mu,k,a,z,v,d:writes.append((a,z)),
                  begin=0x80001c90,end=0x8000318f)
    for t in (0,1,4,5):
        mark(0,0,t,False)
        before=bytes(u.mem_read(state_addr,state_n));writes.clear()
        rt.args_for(u,t,0,7,s)
        assert not writes and before==bytes(u.mem_read(state_addr,state_n))
        assert stock[-2:]==[(t,0,0,7),(t,1,7,16)]
        mark(0,0,t,True);writes.clear()
        rt.args_for(u,t,0,7,s)
        assert writes
    u.hook_del(hook);u.hook_del(wh)
    result['tests']['deselection_dispatch_and_reselection']={'tracks':4,'stock_calls':len(stock),'status':'PASS',
        'scope':'Actual dispatcher; intercepted stock FLEX continuation. CF state and source slots untouched during delegation'}

    # Reference first-trigger record/state after clean generation handoff.
    clean,cs=rt.machine(image,elf,True)
    expected=[];observed=[]
    for t in (1,5):
        expected.append(rt.args_for(clean.uc,t,0,0,cs))
    expected_state=bytes(clean.uc.mem_read(cs['pk_hybrid_voices'],state_n))
    for cycle,(b,p) in enumerate(((1,1),(0,3),(1,2),(0,0))):
        for t in (1,5): mark(b,p,t,True)
        before=bytes(u.mem_read(state_addr,state_n))
        for tr in (0,1,4,5,2,7):
            u.mem_write(0x100b14cc,bytes((tr,)))
            call(u,s['pk_ui_tick'])
        assert before==bytes(u.mem_read(state_addr,state_n)), 'UI reset live engine state'
        now=[rt.args_for(u,t,0,0,s) for t in (1,5)]
        assert now==expected, ('generation first-trigger records',cycle)
        assert bytes(u.mem_read(state_addr,state_n))==expected_state, ('generation state/RNG',cycle)
        # Dirty both voices before the next generation.
        for frame in range(1,9):
            for t in (1,5): rt.args_for(u,t,frame,frame%16,s)
        observed+=now
    result['tests']['generation_handoff_first_trigger']={'transitions':4,'exact_records':len(observed),
        'complete_state_RNG_bytes_per_comparison':state_n,'status':'PASS',
        'scope':'Bank/Part pointers changed through signature writer setup; real UI tick interleaved, callback resets at boundary; real-load panel test separate'}
    result['status']='PASS_COMPONENT_SCOPES'
    result['missing']=['Actual saved-project save/reload and power-loss replay',
        'All stock sampler/recorder/streaming modes', 'Physical cache/eDMA timing']
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe',type=Path,default=Path('out/perky/hybrid/probe'))
    ap.add_argument('--out',type=Path,default=Path('out/perky/hybrid/safety-final/LIFECYCLE_COMPONENT.json'))
    a=ap.parse_args();run(a.probe.resolve(),a.out.resolve())
