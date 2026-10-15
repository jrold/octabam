#!/usr/bin/env python3
"""One bounded actual-panel chooser/bank/Part test of the IPL3 trial image."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/verify'))
import stems_panel as panel

def run(image,card,work,emu,render_pc='0x40c4c5fa',prepare_pc='0x40c4656c'):
    work.mkdir(parents=True,exist_ok=True)
    owned=work/'card.img';shutil.copyfile(card,owned)
    panel.PORT_BIN=emu
    os.environ.update(HYBRID_SAFETY_REPORT=str(work/'stack.json'),
        HYBRID_GUARD_AUDIT=str(work/'events.txt'),HYBRID_RENDER_PC=render_pc,
        HYBRID_PREPARE_PC=prepare_pc)
    rows=[]
    def snapshot(p,name):
        bank=p.long(0x46c82456);part=p.peek(0x100b14cf,1)[0]
        live=bank+0x8ed80+part*0x18b2
        row={'name':name,'bank':bank,'part':part,'working_bank':p.peek(0x80000002,1)[0],
             'playing_bank':p.peek(0x800065bd,1)[0],'pattern':p.peek(0x800065be,1)[0],
             'selected_track':p.peek(0x100b14cc,1)[0],'transport':p.long(0x800065b8),
             'signatures':{t:p.peek(live+60+30*t,3).hex() for t in [0,1,4,5]},
             'controls':{t:list(p.peek(live+48+30*t,6)) for t in [0,1,4,5]}}
        rows.append(row);(work/'SNAPSHOTS.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps(row),flush=True);return row
    with panel.MenuPort(image,owned,'OCTABAM','RIG',True,log_path=work/'port.log',
            extra=('--load-ms','90000','--dsp-dirty','123','--pit-clock-hz','132000000',
                   '--cf-cycles-clock','1.0','--block-dump',str(work/'blocks.bin'))) as p:
        p.settle();p.poke(0x46c00010,b'\x01');snapshot(p,'loaded')
        p.press('play',hold=30,settle=120);snapshot(p,'playing')
        # Actual SRC SETUP chooser: signed PERKY row5 -> FLEX row1 -> PERKY.
        for track in [1,0,5,4]:
            p.press(f't{track+1}',hold=20,settle=50)
            p.chord('func','pg_playback',settle=60)
            p.png(work/f't{track+1}-chooser.png')
            cursor=p.long(0x460d5c30);print('CURSOR',track,cursor,flush=True)
            assert cursor==5,('chooser did not open at PERKY',track,cursor)
            for _ in range(4):p.press('up',hold=15,settle=25)
            assert p.long(0x460d5c30)==1
            p.press('yes',hold=20,settle=80);p.press('no',hold=20,settle=50)
            off=snapshot(p,f'T{track+1}-stock')
            assert off['signatures'][track]=='000000',off
            p.chord('func','pg_playback',settle=60)
            assert p.long(0x460d5c30)==1
            for _ in range(4):p.press('down',hold=15,settle=25)
            assert p.long(0x460d5c30)==5
            p.press('yes',hold=20,settle=80);p.press('no',hold=20,settle=50)
            on=snapshot(p,f'T{track+1}-perky')
            assert on['signatures'][track]=='504b01',on
        # Real Part chooser and real bank/pattern keys during playback.
        p.press('part',hold=20,settle=50);p.press('down',hold=20,settle=30)
        p.press('yes',hold=20,settle=100);snapshot(p,'Part-change')
        for bank in [1,0]:
            p.chord('bank',f'trig{bank+1}',settle=60)
            # BANK B: SELECT PTN is already open. Reopening PATTERN cancels
            # the temporary bank choice. Change quantization can exceed the
            # eight-step track loops, so allow the bounded four-second wait.
            p.press('trig1',hold=20,settle=80)
            for _ in range(10):
                if p.peek(0x800065bd,1)[0]==bank:break
                p.run(400)
            row=snapshot(p,f'bank-{bank}')
            assert row['playing_bank']==bank and row['working_bank']==bank,row
        p.press('stop',hold=20,settle=60);snapshot(p,'stopped')
    return rows

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image',type=Path,default=ROOT/'out/perky/hybrid/ipl3/trial-mainos.bin')
    ap.add_argument('--card',type=Path,default=ROOT/'out/perky/hybrid/ipl3/dense/card.img')
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/ipl3/lifecycle')
    ap.add_argument('--emu',type=Path,default=ROOT/'out/perky/hybrid/ipl3/audit/ot_emu_audit')
    args=ap.parse_args();run(args.image.resolve(),args.card.resolve(),args.work.resolve(),args.emu.resolve())
