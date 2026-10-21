#!/usr/bin/env python3
"""Reuse Yves Rosius's existing PIO first-sector fix, proven by his build."""
import hashlib,json,re,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(elf):
 rows=subprocess.check_output(['m68k-elf-nm','-n',str(elf)],text=True)
 return {v[2]:int(v[0],16) for line in rows.splitlines() if len(v:=line.split())==3}
def text_bytes(elf):
 rows=subprocess.check_output(['m68k-elf-objdump','-h',str(elf)],text=True)
 row=next(v for line in rows.splitlines() if len(v:=line.split())>5 and v[1]=='.text')
 blob=elf.with_suffix('.text.bin');subprocess.run(['m68k-elf-objcopy','-O','binary','-j','.text',str(elf),str(blob)],check=True)
 return int(row[3],16),blob.read_bytes()
def prepare(work):
 d=work/'ata-author';d.mkdir(exist_ok=True);receipt=d/'REFERENCE.json';elf=d/'runtime.elf'
 sources=[ROOT/'modules/stems/stems.s',ROOT/'modules/stems/manifest.py',ROOT/'out/raw/section_3_MAIN_OS.bin']
 current={str(p.relative_to(ROOT)):sha(p) for p in sources}
 if not receipt.exists() or json.loads(receipt.read_text())['source_sha256']!=current:
  log=d/'build.log'
  with log.open('w') as f:subprocess.run(['make','bus','REMIX=stems'],cwd=ROOT,check=True,stdout=f,stderr=subprocess.STDOUT)
  shutil.copy2(ROOT/'out/platform/runtime/runtime.elf',elf);shutil.copy2(ROOT/'out/mainos_bus.bin',d/'mainos_stems.bin')
  syms=symbols(elf);base,blob=text_bytes(elf);start=syms['stems_ata_first'];end=syms['stems_task_create'];stub=blob[start-base:end-base];assert len(stub)==52
  report=dict(author='yvesrosius',source='modules/stems/stems.s:stems_ata_first',command=['make','bus','REMIX=stems'],source_sha256=current,elf_sha256=sha(elf),image_sha256=sha(d/'mainos_stems.bin'),build_log_sha256=sha(log),address=start,length=len(stub),stub_sha256=hashlib.sha256(stub).hexdigest())
  receipt.write_text(json.dumps(report,indent=2)+'\n')
 ref=json.loads(receipt.read_text());assert sha(elf)==ref['elf_sha256']
 # Retain the preceding author-written RTS so the standalone unit starts
 # on a four-byte boundary. GNU ld otherwise inserts a leading NOP for
 # its empty .text section at a 2-mod-4 -Ttext address (the GNU-as trap).
 syms=symbols(elf);base,blob=text_bytes(elf);fn=syms['stems_ata_first'];end=syms['stems_task_create']
 assert blob[fn-base-2:fn-base]==bytes.fromhex('4e75') and end-fn==52
 ref.update(reference_version=2,address=fn-2,length=54,function_address=fn,function_length=52,stub_sha256=hashlib.sha256(blob[fn-base-2:end-base]).hexdigest(),function_sha256=hashlib.sha256(blob[fn-base:end-base]).hexdigest())
 receipt.write_text(json.dumps(ref,indent=2)+'\n')
 original=sources[0].read_text();begin=original.index('        .global stems_ata_first\n');end=original.index('| ---- creating the task',begin)
 equates=[line for line in original.splitlines() if re.search(r'\.equ\s+ATA_(DATA|PTR|LEFT|RET),',line)];assert len(equates)==4
 destination=work/'ata-first.s';destination.write_text('/* Verbatim first-sector fix by Yves Rosius; see modules/stems/stems.s. */\n.section .text.pknhbata,"ax",@progbits\n.balign 2\n'+'\n'.join(equates)+'\n        rts | the preceding author RTS preserves reference alignment\n'+original[begin:end]+'.type stems_ata_first,@function\n.size stems_ata_first,.-stems_ata_first\n')
 # The small unit's reference must be exactly the author's 52-byte function.
 out=d/'unit';out.mkdir(exist_ok=True)
 commands=[['m68k-elf-as','-mcpu=54455','-o',str(out/'unit.o'),str(destination)],['m68k-elf-ld',f"-Ttext={ref['address']:#x}",'-o',str(out/'unit.elf'),str(out/'unit.o')],['m68k-elf-objcopy','-O','binary',str(out/'unit.elf'),str(out/'unit.bin')]]
 for cmd in commands:subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 assert sha(out/'unit.bin')==ref['stub_sha256'],('first-sector extraction differs from author',len((out/'unit.bin').read_bytes()),ref)
 return destination,ref

def verify(work,elf,reference):
 base,blob=text_bytes(elf);address=symbols(elf)['stems_ata_first'];stub=blob[address-base:address-base+reference['function_length']]
 assert hashlib.sha256(stub).hexdigest()==reference['function_sha256'],'relocated PIO fix differs from author'
 result=dict(status='PASS_AUTHOR_BUILD_AND_RELOCATED_FIRST_SECTOR_BYTES',reference=reference,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'modules/stems/stems.s',ROOT/'modules/stems/manifest.py')},candidate_address=address,candidate_elf_sha256=sha(elf),source_sha=sha(work/'ata-first.s'))
 (work/'ATA_GATE.json').write_text(json.dumps(result,indent=2)+'\n');return result
