#!/usr/bin/env python3
"""Compare guarded stock-loop helpers to the untouched actual stock spans."""
import argparse,json,random,struct,subprocess,sys
from pathlib import Path
import unicorn.m68k_const as regs
import verify_perky_hybrid_runtime as rt
import calibrate_perky_hybrid_budget as c
sys.path.insert(0,str(c.ROOT/'tools/perky'))
import generate_stock_position_fast as position

MASK=(1<<64)-1
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--linked',action='store_true',help='Execute actual linked candidate helpers; compare pristine pinned stock spans')
    args=parser.parse_args();source=args.build.resolve();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    generated=position.generate(work);asm=Path(generated['path']);obj=asm.with_suffix('.o');elf=asm.with_suffix('.elf');binary=asm.with_suffix('.bin')
    sr_source=work/'observe-sr.s';sr_object=sr_source.with_suffix('.o')
    sr_source.write_text('''.text
.globl pk_position_observe_sr
pk_position_observe_sr:
 move.w %sr,%d5
 seq %d0
 scs %d1
 smi %d2
 svs %d3
 moveq #0,%d4
 addx.l %d4,%d4
 move.l %d0,0x4807ff00
 move.l %d1,0x4807ff04
 move.l %d2,0x4807ff08
 move.l %d3,0x4807ff0c
 move.l %d4,0x4807ff10
 move.l %d5,0x4807ff14
 jmp 0x4808ff00
''')
    commands=[['m68k-elf-as','-mcpu=54455','-o',str(obj),str(asm)],
              ['m68k-elf-as','-mcpu=54455','-o',str(sr_object),str(sr_source)],
              ['m68k-elf-ld','-Ttext=0x48080000','-e',generated['sites'][0]['entry'],'-o',str(elf),str(obj),str(sr_object)],
              ['m68k-elf-objcopy','-O','binary',str(elf),str(binary)]]
    for command in commands:subprocess.run(command,check=True)
    build=json.loads((source/'BUILD.json').read_text());image=source/'probe'/('mainos_'+build['version']+'.bin')
    boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
    r,s=rt.machine(image,source/'probe/platform/runtime.elf',True);u=r.uc
    if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
    u.mem_write(0x48080000,binary.read_bytes());symbols=c.integrated.private.symbols(elf)
    def observe_sr():
        u.emu_start(symbols['pk_position_observe_sr'],0x4808ff00,count=30)
        assert u.reg_read(regs.UC_M68K_REG_PC)==0x4808ff00
        z,carry,negative,overflow,extend,upper=struct.unpack('>6I',u.mem_read(0x4807ff00,24))
        return (upper&0xffe0)|((extend&1)<<4)|((negative&1)<<3)|((z&1)<<2)|((overflow&1)<<1)|(carry&1)
    # Calibrate each architectural CCR bit independently. Host SR reads (and
    # even MOVE SR) can expose untranslated lazy flags at a direct-call stop.
    for bits in range(32):
        u.reg_write(regs.UC_M68K_REG_SR,0x2700|bits)
        assert observe_sr()==0x2700|bits,('CCR observer calibration',bits)
    general=[getattr(regs,'UC_M68K_REG_'+name) for name in
             ('D0','D1','D2','D3','D4','D5','D6','D7','A0','A1','A2','A3','A4','A5','A6','A7','SR')]
    object_at,stack=0x48070000,0x480f0000
    rng=random.Random(0x88908e66);inputs=[]
    for period in (1,2,65535,0xffffffff,0x100000000,0x7fffffffffffffff):
        for fraction in sorted({0,period//2,period-1}):
            for count in (0,1,2,8,16,18,127):inputs.append((fraction,period,period,count))
    for _ in range(2000):
        period=rng.randrange(1,1<<61);step=rng.randrange(0,4*period+1)
        fraction=rng.randrange(period);count=rng.randrange(21)
        inputs.append((fraction,step,period,count))
    for period in (0,1,0xffffffffffffffff,0x8000000000000000):
        for count in (-2,-1,0,1,18):inputs.append((0,0,period,count))
    for count in (1,2,18):inputs.append((0,MASK,1,count))
    cases=guard_hits=0
    bound_sites=[]
    for site_index,site in enumerate(generated['sites']):
        if args.linked:
            oracle_entry=0x48090000+256*site_index
            u.mem_write(oracle_entry,position.expected_span(site))
            candidate_entry=s[site['entry']]
            assert bytes(u.mem_read(site['address'],6))==b'\x4e\xf9'+candidate_entry.to_bytes(4,'big'),('site does not jump to actual linked helper',site)
            size=rt.sizes(source/'probe/platform/runtime.elf')[site['entry']]
            assert bytes(u.mem_read(candidate_entry,size))==bytes(u.mem_read(symbols[site['entry']],size)), 'linked helper differs from generated proof unit'
        else:
            assert bytes(u.mem_read(site['address'],site['pad_to']))==position.expected_span(site)
            oracle_entry=site['address'];candidate_entry=symbols[site['entry']]
        oracle_end=oracle_entry+site['pad_to']
        bound_sites.append(dict(name=site['name'],original_site=site['address'],candidate_entry=candidate_entry,oracle_entry=oracle_entry))
        for fraction,step,period,count in inputs:
            initial=bytearray(rng.randbytes(256));sample_position=rng.getrandbits(32)
            initial[68:72]=struct.pack('>I',sample_position)
            initial[120:128]=struct.pack('>Q',fraction)
            initial[128:136]=struct.pack('>Q',step)
            initial[136:144]=struct.pack('>Q',period)
            before={reg:rng.getrandbits(32) for reg in general}
            before.update({regs.UC_M68K_REG_D0:fraction>>32,regs.UC_M68K_REG_D1:fraction&0xffffffff,
                           regs.UC_M68K_REG_D2:step>>32,regs.UC_M68K_REG_D3:period>>32,
                           regs.UC_M68K_REG_D4:count&0xffffffff,regs.UC_M68K_REG_A2:object_at,
                           regs.UC_M68K_REG_A7:stack,regs.UC_M68K_REG_SR:0x2700|rng.randrange(32)})
            def execute(entry,end):
                u.mem_write(object_at,bytes(initial))
                for reg,value in before.items():u.reg_write(reg,value)
                u.emu_start(entry,end,count=20000)
                assert u.reg_read(regs.UC_M68K_REG_PC)==end,('nonterminating fixture',site['name'],fraction,step,period,count)
                state={reg:u.reg_read(reg) for reg in general}
                state[regs.UC_M68K_REG_SR]=observe_sr()
                return bytes(u.mem_read(object_at,256)),state
            expected=execute(oracle_entry,oracle_end);actual=execute(candidate_entry,site['end'])
            assert actual==expected,(site['name'],fraction,step,period,count,
                                      [(reg,hex(actual[1][reg]),hex(expected[1][reg])) for reg in general if actual[1][reg]!=expected[1][reg]],
                                      [(i,x,y) for i,(x,y) in enumerate(zip(actual[0],expected[0])) if x!=y][:8])
            guard=count>=0 and step==period and 0<period<(1<<63) and fraction<period
            if guard:
                delta=count if site['name']=='forward' else -count
                assert int.from_bytes(actual[0][68:72],'big')==(sample_position+delta)&0xffffffff
                assert int.from_bytes(actual[0][120:128],'big')==fraction
                guard_hits+=1
            cases+=1
    result=dict(status='PASS_LINKED_STOCK_POSITION_HELPERS_ALL_REGISTERS_SR_AND_RAW_OBJECT' if args.linked else 'PASS_STOCK_POSITION_HELPERS_ALL_REGISTERS_SR_AND_RAW_OBJECT',cases=cases,guard_hits=guard_hits,
                image_sha256=c.sha(image),generated=generated,commands=commands,
                actual_linked_symbols=args.linked,bound_sites=bound_sites,
                checked=['D0-D7','A0-A7','architectural SR including X','all256 object bytes','forward and reverse','unity and generic fallback','position wrap'],
                inputs={str(p):c.sha(p) for p in (asm,elf,binary)},
                architectural_sr_observer_sha256=c.sha(sr_source),
                architectural_ccr_calibration_cases=32,
                source_sha256={str(p.relative_to(c.ROOT)):c.sha(p) for p in (Path(__file__).resolve(),Path(position.__file__).resolve())},
                limits=['Actual linked helpers and detour targets checked against pristine pinned stock spans at fresh addresses; full composed-image timing/audio/lifecycle remain required.' if args.linked else
                        'Fresh-address helper proof against actual original spans; composed-image timing/audio/lifecycle remain required.'])
    c.save(work/'RESULT.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
