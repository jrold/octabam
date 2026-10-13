#!/usr/bin/env python3
"""Execute the packaged stock machine-letter drawer with the PERKY4 hook."""
import argparse
import itertools
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/emu')]
import emu_bringup as e


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,default=ROOT/'out/perky/four')
    w=ap.parse_args().build
    r=e.boot(str(w/'fragmented-mainos.bin'));assert r.clean,(r.stopped,r.error)
    u=r.uc;e._prime_part(r)
    db=e._u32(u,e.PART_PTR)
    def w32(a,v):u.mem_write(a,v.to_bytes(4,'big'))
    def w8(a,v):u.mem_write(a,bytes([v]))
    # Drawn Part can differ from the parameter editor's Part.
    w8(0x100b14cf,2);w32(0x80000012,0);w8(0x80000034,0)
    stock=[e._u32(u,0x400a81a4+4*i) for i in range(5)]
    calls=[]
    def capture(mu,pc,size,data):
        sp=mu.reg_read(e.UC_M68K_REG_A7)
        calls.append((e._u32(mu,sp+4),e._u32(mu,sp+12),e._u32(mu,sp+16)))
    u.hook_add(e.UC_HOOK_CODE,capture,begin=0x400128a8,end=0x400128a8)
    u.ctl_flush_tb();count=0
    for part in range(4):
        w8(0x80000003,part)
        p=db+0x8ed80+part*0x18b2
        for machine in range(5):
            for signed in (False,True):
                for track in range(8):
                    w8(p+0x22+track,machine)
                    u.mem_write(p+60+30*track,b'PK\x01' if signed else bytes(3))
                before=bytes(u.mem_read(p,0x18b2))
                # Force the stock renderer's actual cached row redraw.
                u.mem_write(0x400c0c50,b'\xff'*68)
                calls.clear();e._call(u,0x4003fed8)
                assert len(calls)==8,(part,machine,signed,calls)
                expected=[stock[4] if signed and machine==1 and t in (0,4) else stock[machine] for t in range(8)]
                assert [c[0] for c in calls]==expected,(part,machine,signed,calls,expected)
                assert bytes(u.mem_read(p,0x18b2))==before,'drawer mutated Part/internal type/signature'
                count+=8
    # P comes from exactly the same glyph as Pickup. Its stock caller still
    # sees the original FLEX type in a4, so Pickup-only badges stay excluded.
    report={'stock_glyphs':[hex(p) for p in stock],'track_draws':count,
            'part_bytes_unchanged':True,'signed_PERKY':'stock P','unsigned_FLEX':'stock F',
            'STATIC_Pickup_THRU_Neighbor':'original bitmaps','trig_icons':'not yet qualified'}
    symbols={name:int(address,16) for address,kind,name in
             (line.split() for line in subprocess.check_output(['m68k-elf-nm','-n',str(w/'platform/runtime.elf')],text=True).splitlines() if len(line.split())==3)}
    # Original stock flag combinations independently determine the expected
    # bitmap/priority decisions. PERKY supplies only the first (play) bit.
    old=e.boot(str(ROOT/'out/raw/section_3_MAIN_OS.bin'))
    assert old.clean;v=old.uc;e._prime_part(old)
    ref_calls=[]
    def ref_capture(mu,pc,size,data):
        sp=mu.reg_read(e.UC_M68K_REG_A7)
        ref_calls.append((e._u32(mu,sp+4),e._u32(mu,sp+12),e._u32(mu,sp+16)))
    v.hook_add(e.UC_HOOK_CODE,ref_capture,begin=0x400128a8,end=0x400128a8);v.ctl_flush_tb()
    def draw(mu,target):
        mu.mem_write(0x400c0c94,b'\xff'*68);target.clear()
        e._call(mu,0x4004bd48)
        return list(target)
    for mu in (u,v):
        mu.mem_write(0x80000003,b'\x00');mu.mem_write(0x100b14cf,b'\x00')
        mu.mem_write(0x80000012,bytes(4));mu.mem_write(0x8000184a,b'\x00')
        part=e._u32(mu,e.PART_PTR)+0x8ed80
        for track in range(8):
            mu.mem_write(part+0x22+track,b'\x01')
            mu.mem_write(part+60+30*track,b'PK\x01' if track in (0,4) else bytes(3))
            mu.mem_write(0x800049d8+168*track,bytes(168))
    fp=0x80008000;icon_cases=0
    def publish(track,algo,trig,start=0,end=16):
        for k,value in enumerate((64,64,algo,64,64,0)):
            u.mem_write(fp+2*k,(value<<8).to_bytes(2,'big'))
        w32(0x800062a8,fp);w32(0x80001c80,0x80010000);w8(0x46104d0c+track,16 if trig else 0)
        e._call(u,symbols['pk_render'],(track,0,start,end))
    for track in (0,4):
        for algo in range(4):
            for other in range(4):
                for muted,selected in itertools.product(range(2),range(8)):
                    for mu in (u,v):
                        mu.mem_write(0x8000184a,bytes([((1<<track) if muted else 0)]))
                        mu.mem_write(0x80000000,bytes([selected]))
                        mu.mem_write(0x100b14cc,bytes([selected]))
                    # Drain any previous UI event, then publish an untriggered
                    # prefix. A p-lock's post-event controls cannot flash early.
                    e._call(u,symbols['pk_ui_playing'],(track,0))
                    for mu in (u,v):
                        for t in range(8):
                            flags=bytes((0,(other&1) if t==track else 0,(other>>1) if t==track else 0))
                            mu.mem_write(0x800049d8+168*t,flags)
                    flags_before=bytes(u.mem_read(0x800049d8,168*8))
                    publish(track,algo,False,0,7)
                    assert draw(u,calls)==draw(v,ref_calls),(track,algo,other,'prefix/empty-step icons')
                    publish(track,algo,True,7,16)
                    packet=bytes(u.mem_read(0x80001c90+336*track,64))
                    assert packet[:8]==bytes.fromhex('504b000059310001'),'UI latch lacks real source trig record'
                    assert packet[39]==(0,3,2,5)[algo],'source ALGO dispatch byte'
                    v.mem_write(0x800049d8+168*track,b'\x01')
                    assert draw(u,calls)==draw(v,ref_calls),(track,algo,other,'stock play glyph/priority')
                    assert bytes(u.mem_read(0x800049d8,168*8))==flags_before,'UI changed sample-player/sequencer state'
                    v.mem_write(0x800049d8+168*track,b'\x00')
                    assert draw(u,calls)==draw(v,ref_calls),(track,algo,other,'one repaint consumes trig latch')
                    # Unlocked continuation cannot fabricate a new event.
                    publish(track,0,False)
                    assert draw(u,calls)==draw(v,ref_calls),(track,algo,other,'untriggered continuation icon')
                    icon_cases+=1
    # Ordinary machine play/stop/record priorities remain exactly stock,
    # including selection and mute. Signatures have been removed here.
    stock_icon_cases=0
    for machine,track,flags,muted in itertools.product(range(5),range(8),range(8),range(2)):
        for mu in (u,v):
            part=e._u32(mu,e.PART_PTR)+0x8ed80
            mu.mem_write(0x8000184a,bytes([(1<<track) if muted else 0]))
            mu.mem_write(0x80000000,bytes([track]));mu.mem_write(0x100b14cc,bytes([track]))
            for t in range(8):
                mu.mem_write(part+0x22+t,bytes([machine]))
                mu.mem_write(part+60+30*t,bytes(3))
                mu.mem_write(0x800049d8+168*t,bytes(((flags&1),(flags>>1)&1,(flags>>2)&1)) if t==track else bytes(3))
        assert draw(u,calls)==draw(v,ref_calls),(machine,track,flags,muted,'stock machine glyph priorities changed')
        stock_icon_cases+=1
    report['trig_icons']={'source_event_cases':icon_cases,'stock_priority_combinations':4,'mute_states':2,'selected_tracks':8,'ordinary_stock_draws':stock_icon_cases,
                          'prefix_flashes':0,'sample_player_bytes_changed':0,
                          'behavior':'actual PK/Y1 trig publication latched until next stock track-strip repaint'}
    (w/'ui-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'[PASS] PERKY4 P indicator: {count} executed stock track draws, all Parts/types/signatures/tracks; exact bitmap arguments; Parts byte-identical')
    print(f'[PASS] unchanged ordinary machine play glyphs: {stock_icon_cases} stock type/track/status/mute combinations')
    print(f'[PASS] PERKY4 stock play glyph: {icon_cases} packaged CF producer -> real trig record -> stock drawer cases, all algorithms/cores/priority bits/mute/selection; prefix and empty steps unchanged; no sequencer/player writes')


if __name__=='__main__':main()
