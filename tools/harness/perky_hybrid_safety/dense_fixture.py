#!/usr/bin/env python3
"""Reproduce the bounded dense fixture from the existing private safety card.

Never edits the input card or an existing output directory. No proprietary input
bytes belong in Git. The fixture retains the previous eight-track FX assignments.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/emu'),str(ROOT/'tools/hw')]
import emu_card
import ot_project as otp

def stage(destination):
    source=ROOT/'out/perky/hybrid/safety-final/fixture/card.img'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='a7a907bc6c841236f4ba133952150eac0a79d76c12d8e0c5f49b0227c69340d7'
    assert not destination.exists(),'choose a new generated-artifact directory'
    project=destination/'project';project.mkdir(parents=True)
    for name,data in emu_card.extract_image(source.read_bytes()).items():
        if name.startswith('OCTABAM/RIG/'):
            path=project/name.removeprefix('OCTABAM/RIG/')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    locks={step:[40+step*3,100+step,(step//2)%3,32+step*7,96-step*5,(step//2)%3] for step in (1,3,5,7)}
    for bank in project.glob('bank*.work'):
        def mutate(data):
            for part in range(otp.NPARTS_ALL):
                live=otp.PART_BASE+part*otp.PART_STRIDE+9
                for track in range(8):
                    page=live+0x11a+24*track;data[page:page+6]=bytes(6)
            for pattern in range(16):
                tail=otp.PTRN0+(pattern+1)*otp.PTRN_FSTRIDE-11
                data[tail+2:tail+4]=bytes([8,2])
                for track in range(8):
                    at=otp.trac_off(pattern,track)
                    data[at:at+64]=bytes(64);data[at+7]=255
                    data[at+0x50:at+0x52]=bytes([8,2]);data[at+0x54]=0
                    data[at+0x59:at+0x59+64*32]=bytes([255])*(64*32)
                    data[at+0x899:at+0x919]=bytes(128)
                    if track in (0,1,4,5):
                        for step,values in locks.items():
                            data[at+0x59+step*32:at+0x59+step*32+6]=bytes(values)
        otp._bank_write(project,int(bank.stem[4:]),mutate,guard=False)
    otp.set_tempo(project,300)
    expected={'tempo':300,'steps':8,'all_tracks_all_steps':True,'locks':locks,
        'samples_per_step':2205,'frames':4096,'expected_triggers_per_track':30,
        'initial_base_controls':{'0':[64,108,3,72,56,0],'1':[64,112,2,72,56,0],
                                 '4':[52,108,0,84,48,1],'5':[64,112,2,72,56,0]}}
    (destination/'EXPECTED.json').write_text(json.dumps(expected,indent=2)+'\n')
    subprocess.run([str(ROOT/'.venv/bin/python3'),str(ROOT/'tools/emu/ot_emu/stage_card.py'),
        str(project),'OCTABAM','RIG','--tree',str(destination/'tree'),'--out',str(destination/'card.img'),
        '--audio',str(ROOT/'out/perky/hybrid/safety-final/tone.wav')+':AUDIO/HYB_SAMPLER_440.wav'],check=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    stage(parser.parse_args().destination.resolve())
