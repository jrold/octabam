#!/usr/bin/env python3
"""Audit the unchanged PERKY4S source closure and regenerate its DSP payload only."""
import sys, os, json, hashlib, subprocess, importlib.util
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--work',type=Path,required=True)
WORK=ap.parse_args().work.resolve()
assert WORK.is_relative_to(ROOT/'out')
WORK.mkdir(parents=True,exist_ok=True)
(WORK/'dependency-audit.json').write_text(json.dumps({'status':'RUNNING'})+'\n')
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ['REMIX']='perky-machine'
phase='payload_import'; enabled=True; opens={}; commands=[]
def audit(event,args):
    if not enabled:return
    if event=='open' and isinstance(args[0],(str,bytes)):
        p=Path(os.fsdecode(args[0])).absolute()
        mode=args[1];flags=args[2]
        write=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
        if write:
            if not p.is_relative_to(WORK):raise RuntimeError('unexpected audit write outside own work: '+str(p))
            return
        if not p.is_relative_to(ROOT) or p.is_relative_to(WORK):return
        stack=[];f=sys._getframe(1)
        while f and len(stack)<5:
            name=f.f_code.co_filename
            if str(ROOT) in name and not name.startswith(str(WORK)):
                stack.append({'file':str(Path(name).relative_to(ROOT)),'function':f.f_code.co_name,'line':f.f_lineno})
            f=f.f_back
        key=str(p.relative_to(ROOT))
        opens.setdefault(key,[])
        item={'phase':phase,'stack':stack}
        if item not in opens[key]:opens[key].append(item)
    elif event=='subprocess.Popen':
        commands.append({'phase':phase,'executable':str(args[0]),'argv':[str(x) for x in args[1]],'cwd':str(args[2])})
sys.addaudithook(audit)
import build_four_payload as four
phase='payload_build'
four.build(WORK/'payload',native_clock=True)
payload_modules={str(Path(m.__file__).resolve().relative_to(ROOT)) for m in tuple(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(ROOT) and not Path(m.__file__).resolve().is_relative_to(WORK)}
phase='placement_import'
import perky_fragmented_image as fragments
fragments.B._SCRATCH=WORK/'assembler-scratch';fragments.B._SCRATCH.mkdir(exist_ok=True)
phase='placement_build'
plans={}
for tag in ('A','B'):
    records,ledger,entry=fragments.plan(WORK/'payload/multi.asm',tag)
    plans[tag]={'entry':entry,'ledger':ledger,'records':[{'start':a,'words':len(w),'sha256_le24':hashlib.sha256(b''.join(v.to_bytes(3,'little') for v in w)).hexdigest()} for a,w in records]}
phase='installation_import'
placement_modules={str(Path(m.__file__).resolve().relative_to(ROOT)) for m in tuple(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(ROOT)}
import build_four_machine
phase='control_dependencies'
spec=importlib.util.spec_from_file_location('four_control_generator',ROOT/'modules/perky/generate.py');gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
argv=['m68k-elf-gcc',*gen.FLAGS,'-MM',str(ROOT/'modules/perky/control_four_candidate.c')]
r=subprocess.run(argv,text=True,capture_output=True,check=True)
cdeps=[str(Path(x).resolve().relative_to(ROOT)) for x in r.stdout.split(':',1)[1].replace('\\\n',' ').split()]
enabled=False
modules={str(Path(m.__file__).resolve().relative_to(ROOT)) for m in tuple(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(ROOT) and not Path(m.__file__).resolve().is_relative_to(WORK)}
def source_name(s):
 p=Path(s)
 if p.suffix=='.pyc':
  try:return str(Path(importlib.util.source_from_cache(str(ROOT/p))).relative_to(ROOT))
  except ValueError:return None
 return s
sources={}
for s in sorted(modules | set(opens) | set(cdeps)):
 name=source_name(s)
 if not name or (ROOT/name).resolve()==Path(__file__).resolve():continue
 p=ROOT/name
 if not p.is_file() or not name.startswith(('modules/','tools/','remixes/')):continue
 if p.suffix not in ('.py','.c','.h','.asm','.s','.S'):continue
 roles=[]
 if s in payload_modules:roles.append('payload-python-import')
 if s in modules and s not in payload_modules:roles.append('placement-python-import' if s in placement_modules else 'installation-python-import')
 if name in cdeps:roles.append('frozen-control-compiler-dependency')
 if s in opens:roles.append('observed-source-read')
 sources[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'roles':roles,'reads':opens.get(s,[])}
# Baseline transport asm and generation/installation/loader sources are explicit
# source-analysis additions; they are deliberately distinguished from observed reads.
extra=['modules/perky/generate.py','modules/perky/machine.s','modules/perky/machine_four_ui.s','tools/perky/build_four_machine.py','tools/perky/build_multi_machine_canary.py','tools/perky/perky_machine_module.py','tools/perky/perky_four_memory.py','tools/perky/repack_machine_loader.py','tools/build/perky_image.py','tools/remix/loader.S','tools/remix/platform_build.py','tools/remix/arena.py','tools/remix/pack.py']
for name in extra:
 p=ROOT/name
 assert p.is_file(),name
 sources.setdefault(name,{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'roles':[],'reads':[]})['roles'].append('frozen-transport-installation-static-trace')
inputs={}
for name,reads in opens.items():
 p=ROOT/name
 if p.is_file() and name not in sources and p.suffix!='.pyc' and not name.startswith(('modules/','tools/','remixes/')):
  inputs[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'reads':reads}
ref=ROOT/'out/perky/hybrid/baseline/reproduction'
artifacts={}
for name in ('multi.asm','four.asm','tables.bin','state_init.bin','tables.words','state_init.words','layout.json'):
 p=WORK/'payload'/name;q=ref/name
 artifacts[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'baseline_path':str(q),'equals_baseline':q.is_file() and p.read_bytes()==q.read_bytes()}
# The only subprocess that executes generated synthesis is dsp_asm; no image is built.
report={'schema':'perky.hybrid.frozen-dependency-audit.v1','status':'PASS','scope':'Executed frozen PERKY4S payload composition and per-core placement; compiler C include closure; explicitly marked static installation closure. No MAIN build, flash wrapper or hybrid image.','commands':commands,'sources':sources,'external_inputs':inputs,'payload_artifacts':artifacts,'placed_p':plans,'source_count':len(sources),'excluded_independent_cf_sources':['modules/perky/cf_perky4.c','modules/perky/cf_perky4.h','modules/perky/cf_wavetable.c','modules/perky/cf_resonant.c','modules/perky/cf_noise_tone.c','modules/perky/cf_math.h','modules/perky/cf_pcm_rice.h','modules/perky/control_cf_final.c'],'limitations':['Imports are a conservative dependency envelope, not proof every imported function contributes bytes. Static installation closure is labeled separately; actual MAIN reproduction and upload equality are separate gates.']}
assert all(artifacts[n]['equals_baseline'] for n in artifacts)
for name in report['excluded_independent_cf_sources']:assert name not in sources,name
report['status']='RUNNING'
(WORK/'dependency-audit.json').write_text(json.dumps(report,indent=2)+'\n')
(WORK/'sources.json').write_text(json.dumps({n:x['sha256'] for n,x in sorted(sources.items())},indent=2)+'\n')
print(json.dumps({'status':report['status'],'source_count':len(sources),'external_inputs':len(inputs),'artifact_equality':{n:r['equals_baseline'] for n,r in artifacts.items()},'report':str(WORK/'dependency-audit.json')}))

# Compare the conservative dependency envelope to the actual historical blobs,
# following submodule gitlinks where a parent-tree blob cannot name its files.
import re
b=json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())
p=json.loads((ref/'p-records.json').read_text())
u={}
for tag,plan in report['placed_p'].items():
    assert sum(x['words'] for x in plan['records'] if x['start']<0x30000)==770
    for row in plan['records']:
        if row['start']>=0x30000:
            if row['start'] in u:assert u[row['start']]==row
            u[row['start']]=row
for tag,records in p.items():
    expected=[{'start':a,'words':len(words),'sha256_le24':hashlib.sha256(b''.join(v.to_bytes(3,'little') for v in words)).hexdigest()} for a,words in records]
    assert expected==[u[a] for a in sorted(u)],tag
missing=[];changed=[];git_drift=[];subs={}
for name,row in sources.items():
    if name not in b['source_inventory']:missing.append(name)
    elif row['sha256']!=b['source_inventory'][name]:changed.append(name)
    sub=re.match(r'^(modules/[^/]+/upstream)/(.*)$',name)
    if sub:
        repository,path=sub.groups()
        revision=subprocess.check_output(['git','ls-tree',b['baseline_commit'],repository],text=True).split()[2]
        data=subprocess.check_output(['git','-C',repository,'show',f'{revision}:{path}'])
        current=subprocess.check_output(['git','-C',repository,'rev-parse','HEAD'],text=True).strip()
        subs[repository]={'baseline_commit':revision,'current_commit':current,'same':revision==current}
        row['historical_object']={'repository':repository,'commit':revision,'path':path}
    else:
        data=subprocess.check_output(['git','show',f"{b['baseline_commit']}:{name}"])
        row['historical_object']={'repository':'.','commit':b['baseline_commit'],'path':name}
    if hashlib.sha256(data).hexdigest()!=row['sha256']:git_drift.append(name)
assert not git_drift,git_drift
report['shared_upload_equality']={'PASS':True,'ordered_records':len(u),'words':sum(x['words'] for x in u.values()),'both_uploads':'exact equality to baseline reproduction p-records.json, ordered addresses, lengths, LE24 byte hashes'}
report['baseline_source_comparison']={'commit':b['baseline_commit'],'git_drift':git_drift,'legacy_inventory_missing':missing,'legacy_inventory_drift':changed,'submodules':subs}
report['status']='PASS'
(WORK/'dependency-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'historical_validation':'PASS','sources':len(sources),'legacy_inventory_missing_count':len(missing),'legacy_inventory_drift':changed,'baseline_git_drift':git_drift,'upload_words':sum(x['words'] for x in u.values()),'upload_records':len(u)}))
