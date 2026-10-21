#!/usr/bin/env python3
"""Exhaust the candidate tap kernel in a fresh, non-rewritten target region.

This microgate loads the generated assembly once at a distinct address. Final
admission still requires the composed candidate image and frozen timing port.
"""
import argparse,json,struct,subprocess,sys
from pathlib import Path
import unicorn.m68k_const as regs
import verify_perky_hybrid_runtime as rt
import calibrate_perky_hybrid_budget as c
sys.path.insert(0,str(c.ROOT/'tools/perky'))
import generate_fast_transport as taps

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--linked',action='store_true',help='Execute the actual candidate image symbol and bind its kernel bytes')
    a=p.parse_args();source=a.build.resolve();work=a.work.resolve();work.mkdir(parents=True,exist_ok=True)
    generated=taps.generate(work);asm=Path(generated['path']);obj=asm.with_suffix('.o');elf=asm.with_suffix('.elf');binary=asm.with_suffix('.bin')
    commands=[['m68k-elf-as','-mcpu=54455','-o',str(obj),str(asm)],
              ['m68k-elf-ld','-Ttext=0x48080000','-e','pk_budget_gather_taps','-o',str(elf),str(obj)],
              ['m68k-elf-objcopy','-O','binary',str(elf),str(binary)]]
    for command in commands:subprocess.run(command,check=True)
    build=json.loads((source/'BUILD.json').read_text());image=source/'probe'/('mainos_'+build['version']+'.bin')
    boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
    r,s=rt.machine(image,source/'probe/platform/runtime.elf',True);u=r.uc
    if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
    u.mem_write(0x48080000,binary.read_bytes())
    function=s['pk_budget_gather_taps'] if a.linked else 0x48080000
    size=rt.sizes(source/'probe/platform/runtime.elf')['pk_budget_gather_taps'] if a.linked else 0
    if a.linked:assert bytes(u.mem_read(function,size))==binary.read_bytes()[:size], 'linked kernel differs from generated proof unit'
    ring,out,last=0x48040000,0x48050000,0x48051000
    values=[((i*16381)^(i>>3)^0xa55a)&65535 for i in range(4805)]
    u.mem_write(ring,struct.pack('<4805H',*values)+b'\xa5\x5a');cases=0
    counts=(0,1,2,3,4,17,18,19,20)
    for cursor in range(4805):
        for n in counts:
            u.mem_write(out,b'\xa5'*210);u.mem_write(last,b'\x5a'*14)
            preserved={getattr(regs,'UC_M68K_REG_'+name):((0x9e3779b9*(i+1))^cursor^n)&0xffffffff for i,name in enumerate(('D2','D3','D4','D5','D6','D7','A2','A3','A4','A5','A6'))}
            for reg,value in preserved.items():u.reg_write(reg,value)
            rt.g.emu._call(u,function,(ring,out,cursor,n,last))
            assert all(u.reg_read(reg)==value for reg,value in preserved.items()),(cursor,n,'callee registers')
            assert u.reg_read(regs.UC_M68K_REG_D0)==(cursor+n)%4805
            expected=[values[(cursor+i-delay)%4805] for i in range(n) for delay in (573,1201,1538,3139,4804)]
            raw=struct.pack('>'+str(5*n)+'H',*expected)
            assert bytes(u.mem_read(out,210))==raw+b'\xa5'*(210-len(raw)),(cursor,n,'packet')
            want=struct.pack('>5H',*expected[-5:]) if n else b'\x5a'*10
            assert bytes(u.mem_read(last,14))==want+b'\x5a'*4,(cursor,n,'carry taps')
            cases+=1
    result=dict(status='PASS_LINKED_CANDIDATE_TAP_KERNEL_ALL_RING_CURSORS' if a.linked else 'PASS_CANDIDATE_TAP_KERNEL_ALL_RING_CURSORS',cases=cases,native_counts=counts,
                callee_registers_preserved=True,base_image_sha256=c.sha(image),generated=generated,commands=commands,
                actual_linked_symbol=a.linked,target_entry=function,target_bytes=size,
                inputs={str(p):c.sha(p) for p in (asm,elf,binary)},
                source_sha256={str(p.relative_to(c.ROOT)):c.sha(p) for p in (Path(__file__).resolve(),Path(taps.__file__).resolve(),c.ROOT/'modules/perky/budget_transport.s')},
                limits=['Actual linked kernel and generated-unit bytes checked; full composed-image audio/lifecycle/timing remain required.' if a.linked else
                        'Fresh-address kernel proof; composed-image exact audio, lifecycle and model timing remain required.'])
    c.save(work/'RESULT.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
