#!/usr/bin/env python3
"""Execute the packaged ColdFire SRC/LFO formatter on signed and stock tracks."""
import argparse, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/emu')]
import emu_bringup as emu
sys.path[:0]=[str(ROOT/'modules/perky')]
import simple_drum_control as controls


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,default=ROOT/'out/perky/four')
    args=ap.parse_args();work=args.build
    image=work/'fragmented-mainos.bin'
    symbols={name:int(address,16) for address,kind,name in
             (line.split() for line in subprocess.check_output(['m68k-elf-nm','-n',str(work/'platform/runtime.elf')],text=True).splitlines() if len(line.split())==3)}
    boot=emu.boot(str(image))
    assert boot.clean,('ColdFire UI boot',boot.stopped,boot.error)
    uc=boot.uc
    def w32(a,v):uc.mem_write(a,v.to_bytes(4,'big'))
    def w8(a,v):uc.mem_write(a,bytes([v]))
    db=0x43000000;part=db+0x8ed80;buf=0x47f00800
    w32(0x46c82456,db);w8(0x100b14cf,0);w8(0x80000003,0)
    for track in range(8):
        w8(part+0x22+track,1)
        uc.mem_write(part+60+30*track,b'PK\x01' if track in (0,4) else bytes(3))
    labels=('TUNE','DECAY','ALGO','PAR1','PAR2','MODE')
    stock=[]
    for track in (0,1,4,5):
        w8(0x80000000,track);w8(0x100b14cc,track)
        got=[]
        for destination in range(6):
            uc.mem_write(buf,bytes(64))
            formatter=int.from_bytes(uc.mem_read(0x400d38d8,4),'big')
            assert formatter==symbols['pk_lfo_format'],'packaged PMTR formatter'
            emu._call(uc,formatter,(buf,destination))
            name=emu._cstr(uc,buf,6);group=emu._cstr(uc,buf+(6 if track in (0,4) else 5),5)
            got.append((name,group))
            if track in (0,4):assert name==labels[destination] and group=='SRC',(track,destination,name,group)
        if track in (1,5):
            assert tuple(name for name,group in got)==('PTCH','STRT','LEN','RATE','RTRG','RTIM'),(track,'stock labels',got)
            stock.append(got)
        print(f'[PASS] T{track+1}: ColdFire PMTR formatter '+str(got))
    assert stock[0]==stock[1]
    for internal in range(4):
        uc.mem_write(buf,bytes(16));emu._call(uc,0x4003c718,(buf,internal))
        assert emu._cstr(uc,buf,8)==str(internal+1),'stock ALGO/MODE display is one-based'
    drawn=[]
    def capture(mu,pc,size,user):
        sp=mu.reg_read(emu.UC_M68K_REG_A7)
        pointer=int.from_bytes(mu.mem_read(sp+24,4),'big')
        drawn.append(emu._cstr(mu,pointer,16))
    hook=uc.hook_add(emu.UC_HOOK_CODE,capture,begin=emu.DRAW_STRING,end=emu.DRAW_STRING)
    uc.ctl_flush_tb()
    for track in (0,1,4,5):
        w8(0x100b14cc,track);w8(0x80000000,track);drawn.clear()
        emu._call(uc,symbols['pk_lfo_widget'],(0,0,0,1,0,symbols['pk_lfo_format'],0))
        assert drawn==(['DECAY','SRC'] if track in (0,4) else ['STRT','PB']),(track,'actual PMTR widget text',drawn)
    uc.hook_del(hook)
    print('[PASS] executed packaged PMTR widget draws complete DECAY/SRC and unchanged stock STRT/PB')
    # Run stock's real LFO destination arithmetic, then the packaged PERKY
    # renderer. The oracle derives the record from the original control law;
    # merely changing a label cannot satisfy either assertion.
    fp=0x80008000;lfo=0x430f0000;scratch=0x47e00000
    # Firmware LFO output is signed Q23, not Q31. Its surrounding frame
    # code seeds acc1/acc2 with the high/low saturation biases.
    setup=bytes.fromhex('a93c00000020203c7fff8000a300203c80000000a500')
    uc.mem_write(scratch,setup)
    for track in (0,4):
        for destination in range(6):
            slots=[64,64,0,64,64,0]
            uc.mem_write(fp,bytes(48))
            for k,v in enumerate(slots):uc.mem_write(fp+2*k,(v<<8).to_bytes(2,'big'))
            uc.mem_write(fp+0x12,((2 if destination in (2,5) else 32)<<8).to_bytes(2,'big'))
            w8(fp+0x1e,destination);w32(lfo+8,0x400000)
            emu._run_until(uc,scratch,scratch+len(setup))
            for reg,value in ((emu.UC_M68K_REG_A0,fp),(emu.UC_M68K_REG_A2,fp),
                              (emu.UC_M68K_REG_A3,lfo),(emu.UC_M68K_REG_A5,fp),
                              (emu.UC_M68K_REG_D2,0),(emu.UC_M68K_REG_D7,0)):
                uc.reg_write(reg,value)
            assert emu._run_until(uc,0x4000d032,0x4000d07c) is None,'stock LFO arithmetic fault'
            staged=[int.from_bytes(uc.mem_read(fp+2*k,2),'big') for k in range(6)]
            expected=[v<<8 for v in slots]
            expected[destination]+=(1 if destination in (2,5) else 16)<<8
            assert staged==expected,(track,destination,'actual LFO routing',staged,expected)
            # Alternate Parts to reset the independently persisted smoother.
            for part_idx in (1,0):
                w8(0x100b14cf,part_idx)
                p=part+part_idx*0x18b2
                w8(p+0x22+track,1);uc.mem_write(p+60+30*track,b'PK\x01')
                w32(0x800062a8,fp);w32(0x80001c80,0x80010000)
                w8(0x46104d0c+track,16)
                emu._call(uc,symbols['pk_render'],(track,0,0,16))
            values=[v>>8 for v in expected]
            tune,decay,algo,p1,p2,mode=values
            prepared=[controls.settle_from_zero(controls.panel_to_target(v)) for v in (tune,decay,p1,p2)]
            engine=(0,3,2,5)[algo]
            wanted=[prepared[0],controls._envelope_decay_rate(controls._time_parameter(prepared[1]),50,7280),prepared[2],prepared[3]]
            record=bytes(uc.mem_read(0x80001c90+336*track,40))
            got=[int.from_bytes(record[16+4*i:20+4*i],'big') for i in range(4)]
            assert got==[((v>>8)<<16)|(v&255) for v in wanted],(track,destination,'ColdFire controls -> DSP record',got,wanted)
            assert record[33]==mode and record[39]==engine,(track,destination,'MODE/ALGO routing',record.hex())
        print(f'[PASS] T{track+1}: executed stock LFO A..F -> staged controls -> packaged PERKY parameter preparation -> DSP record')
    for track in (0,4):
        for old_algo in range(4):
            for new_algo in range(4):
                for part_idx in (1,0):
                    w8(0x100b14cf,part_idx);p=part+part_idx*0x18b2
                    w8(p+0x22+track,1);uc.mem_write(p+60+30*track,b'PK\x01')
                    for k,value in enumerate((64,64,old_algo,64,64,0)):
                        uc.mem_write(fp+2*k,(value<<8).to_bytes(2,'big'))
                    w32(0x800062a8,fp);w32(0x80001c80,0x80010000);w8(0x46104d0c+track,16)
                    emu._call(uc,symbols['pk_render'],(track,0,0,16))
                address=0x80001c90+336*track
                old=bytes(uc.mem_read(address+16,24))
                w32(0x80001c80,0x80010000);w8(0x46104d0c+track,0)
                emu._call(uc,symbols['pk_render'],(track,0,0,7))
                for k,value in enumerate((52,96,new_algo,12,104,2)):
                    uc.mem_write(fp+2*k,(value<<8).to_bytes(2,'big'))
                w8(0x46104d0c+track,16)
                emu._call(uc,symbols['pk_render'],(track,0,7,16))
                raw=bytes(uc.mem_read(address,64))
                expected=old[:20]+bytes.fromhex('00a500')+bytes([(0,3,2,5)[old_algo]])
                assert raw[40:64]==expected,(track,old_algo,new_algo,'pre-trig tuple transport',raw[40:64].hex(),expected.hex())
                assert raw[39]==(0,3,2,5)[new_algo] and raw[33]==2,(track,old_algo,new_algo,'locked tuple')
                assert raw[:16]==bytes.fromhex('504b0000593100010000000000000000'),'stock source header ABI changed'
        print(f'[PASS] T{track+1}: packaged CF pre/post p-lock producer, all 16 engine transitions; old tuple retained, new tuple delivered, header unchanged')
    emu._call(uc,symbols['pk_track_page'],(part+0x22,))
    p=uc.reg_read(emu.UC_M68K_REG_D0)
    assert emu._cstr(uc,p+9,13)=='SRC','footer left legend'
    emu._call(uc,symbols['pk_machine_name'],(5,))
    assert emu._cstr(uc,uc.reg_read(emu.UC_M68K_REG_D0),16)=='PERKY','footer machine legend'
    assert int.from_bytes(uc.mem_read(p+0x9a+2*4,4),'big')==4,'exact four-engine ALGO count'
    raw=image.read_bytes();base=0x40000400
    stock_raw=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    for address,size in ((0x400791e4,8),(0x4006d784,8),(0x40077b5c,6)):
        assert raw[address-base:address-base+size]==stock_raw[address-base:address-base+size],('retired browser detour',hex(address))
    assert int.from_bytes(uc.mem_read(0x400d3908,4),'big')==symbols['pk_lfo_widget'],'packaged PMTR widget'
    print('[PASS] packaged SRC legend, four-engine count, stock double-tap/list/title bytes restored')


if __name__=='__main__':main()
