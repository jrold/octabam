#!/usr/bin/env python3
"""Wrap locally checked runtime diagnostics; never label them stable releases."""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import build_machine_canary as base

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--builds',type=Path,required=True)
    ap.add_argument('--delivery',type=Path,required=True)
    args=ap.parse_args()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT),'commit source before packaging'
    assert sha(base.EFT)=='c42f39e4a908abbdb4c65df706025a97fb024d1d869a55092e958f127d6bb619','qualified wrapper tool required'
    args.delivery.mkdir(parents=True,exist_ok=True)
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    files={}; variants=[]
    for version in ('P4RPLACE','P4RNDISP','P4ROLDDSP'):
        work=args.builds/version
        diagnostic=json.loads((work/'diagnostic.json').read_text())
        assert diagnostic['source_parent']==source_commit,'rebuild from clean committed source'
        image=work/'fragmented-mainos.bin'
        assert sha(image)==diagnostic['mainos_sha256']
        assert 'PASS' in (work/'boot.log').read_text()
        card,midi,_=base.wrap_flashable(image,version)
        command=[sys.executable,str(ROOT/'tools/verify/verify_perky_final_wrappers.py'),'--mainos',str(image),'--elek',str(base.firmware_paths(version)[0]),'--card',str(card),'--midi',str(midi),'--eft',str(base.EFT),'--version',version,'--work',str(work/'wrapper-verify')]
        with (work/'wrapper.log').open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        variant=dict(name=version,mainos_sha256=sha(image),changes=diagnostic['changes'],wrapper_command=command,artifacts={})
        for label,p,suffix in [('card',card,'.bin'),('midi',midi,'.syx'),('provenance',work/'diagnostic.json','_provenance.json'),('memory',work/'memory.json','_memory.json')]:
            dst=args.delivery/(version+suffix);shutil.copy2(p,dst)
            files[dst.name]=sha(dst);variant['artifacts'][label]=dict(path=str(dst.resolve()),bytes=dst.stat().st_size,sha256=sha(dst))
        variants.append(variant)
    (args.delivery/'SHA256.txt').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    receipt=dict(status='hardware discrimination builds; physical stability unresolved',source_commit=source_commit,branch='codex/perky4r-runtime-regression',eft=dict(path=str(base.EFT),sha256=sha(base.EFT)),variants=variants)
    (args.delivery/'provenance.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('[PASS] three diagnostic card/MIDI wrapper round trips; source',source_commit,flush=True)

if __name__=='__main__':main()
