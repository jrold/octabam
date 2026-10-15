#!/usr/bin/env python3
"""Actual hybrid MKII panel SAVE PROJECT and cold reload, with scoped assertions."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
import verify_perky_hybrid_safety as safety
ROOT=safety.ROOT
sys.path[:0]=[str(ROOT/'tools/emu'),str(ROOT/'tools/hw')]
import emu_card
import ot_project as otp


def run(work,card,reuse_save=False,image=None,emu=None,environment=None):
    work.mkdir(parents=True,exist_ok=True)
    image=image or ROOT/'out/perky/hybrid/probe/mainos_PKHYB2P.bin'
    script=ROOT/'tools/harness/perky_hybrid_safety/save.txt'
    elf=image.parent/'platform/runtime.elf'
    emu=emu or ROOT/'out/emu/ot_emu'
    base=[str(emu),'--image',str(image),'--set','OCTABAM','--project','RIG',
          '--load-ms','90000','--dsp','--dsp-dirty','123','--mkii',
          '--pit-clock-hz','132000000','--cf-cycles-clock','1.0']
    saved=work/'saved-card.img'
    inputs={str(p):safety.sha(p) for p in (image,elf,script,card,emu)}
    savecmd=[*base,'--card',str(card),'--live-script',str(script),'--card-out',str(saved)]
    commands=[]
    def execute(cmd,name):
        with (work/(name+'.log')).open('w') as log:
            rc=subprocess.run(cmd,cwd=ROOT,env=environment(name) if environment else None,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
        commands.append({'command':cmd,'exit_status':rc,'log_sha256':safety.sha(work/(name+'.log'))})
        assert rc==0, (name,rc)
        return (work/(name+'.log')).read_text()
    if reuse_save:
        prior=json.loads((work/'SAVED_PROJECT.json').read_text())
        assert prior['inputs']==inputs, 'saved execution inputs drifted'
        assert prior['commands'][0]['command']==savecmd
        assert prior['commands'][0]['log_sha256']==safety.sha(work/'save.log')
        assert prior['saved_card_sha256']==safety.sha(saved)
        commands.append(prior['commands'][0]); log=(work/'save.log').read_text()
    else:
        log=execute(savecmd,'save')
    result={'status':'RUNNING','commands':commands,'inputs':inputs,'tests':{}}
    try:
        assert 'on quit' in log and 'FAULT:' not in log and 'ILLEGAL' not in log
        assert '0 panel byte(s) still queued' in log
        original=emu_card.extract_image(card.read_bytes());files=emu_card.extract_image(saved.read_bytes())
        changed={k for k in files if original.get(k)!=files[k]}
        assert any(k.lower().endswith('bank01.strd') for k in changed), ('real save did not persist bank',sorted(changed))
        checked=0
        for key,data in files.items():
            if re.search(r'/bank\d+\.(?:work|strd)$',key,re.I) and key in original:
                for p in range(4):
                    for t in (0,1,4,5):
                        at=otp.PART_BASE+p*otp.PART_STRIDE+9+60+30*t
                        if original[key][at:at+3]==b'PK\x01':
                            assert data[at:at+3]==b'PK\x01', ('lost saved signature',key,p,t)
                            checked+=1
        assert checked>0
        default_at=otp.PART_BASE+9+48+30
        expected=bytes((71,112,2,72,56,0))
        for suffix in ('work','strd'):
            key='OCTABAM/RIG/bank01.'+suffix
            assert files[key][default_at:default_at+6]==expected, ('saved controls',key)
        result['saved_six_controls']=list(expected)
        result['tests']['panel_save']={'status':'PASS','changed_files':sorted(changed),'saved_signatures':checked,
            'scope':'Real SAVE PROJECT through MKII panel and stock FAT/ATA; four working Parts per bank; no power-loss atomicity claim'}
        syms=subprocess.check_output(['m68k-elf-nm','-n',str(elf)],text=True)
        render=int(next(row.split()[0] for row in syms.splitlines() if row.endswith(' T pk_render')),16)
        dump=work/'reload-records.bin'
        controls=work/'reload-controls.bin'
        cmd=[*base,'--card',str(saved),'--sequencer','--internal-clock','--bank','0',
             '--frames','512','--watch-pc',hex(render),'--block-dump',str(dump),
             '--mem-dump',f'{0x400e21e0+0x8ed80+48+30:#x},6={controls}']
        reload_log=execute(cmd,'reload')
        assert re.search(r'frames run\s*:\s*512 .*REACHED',reload_log)
        assert 'FAULT:' not in reload_log and 'ILLEGAL' not in reload_log
        assert dump.stat().st_size>0
        assert controls.read_bytes()==expected, 'cold reload did not restore all six controls'
        sys.path.insert(0,str(ROOT/'tools/harness'))
        import blockdump as bd
        import recloop as rl
        classes=bd.classes(bd.read(dump)); audio={}
        for tr in (1,2,5,6):
            chain=rl.readback_audio(classes,tr)
            significant=sum(abs(v)>64 for v in chain)
            assert significant>64, ('silent reloaded hybrid chain',tr,significant)
            audio[tr]={'chain_samples':len(chain),'significant':significant}
            if tr in (2,6):
                source=rl.track_audio(classes,tr)
                assert sum(abs(v)>64 for v in source)>64, ('silent CF source',tr)
        result['reload_audio']=audio
        result['tests']['cold_reload']={'status':'PASS_CONTROLS_AND_ACTIVE_CHAINS','frames':512,'block_dump_bytes':dump.stat().st_size,
            'scope':'Real saved card loaded by current hybrid after a fresh emulator boot; all six persisted controls exact and four active hybrid post-FX chains; no full PCM equivalence claim'}
        result['status']='PASS_SCOPED_SAVE_RELOAD'
    except AssertionError as e:
        result['status']='FAIL_OR_UNESTABLISHED';result['failure']=str(e)
    result['saved_card_sha256']=safety.sha(saved)
    result['input_hashes_unchanged']=inputs=={str(p):safety.sha(p) for p in (image,elf,script,card,emu)}
    result['commands']=commands
    (work/'SAVED_PROJECT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return result['status']=='PASS_SCOPED_SAVE_RELOAD'

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/safety-final/saved-project')
    ap.add_argument('--card',type=Path,default=ROOT/'out/perky/hybrid/safety-final/fixture/card.img')
    ap.add_argument('--reuse-save',action='store_true',help='Reanalyze hash-verified save output; execute the fresh reload only')
    a=ap.parse_args();raise SystemExit(0 if run(a.work.resolve(),a.card.resolve(),a.reuse_save) else 1)
