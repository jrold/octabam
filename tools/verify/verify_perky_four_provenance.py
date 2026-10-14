#!/usr/bin/env python3
"""Verify committed PERKY4 sources, qualification receipts and artifact hashes."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,required=True)
    r=json.loads(ap.parse_args().report.read_text());commit=r['source_commit']
    assert r['version'] in ('PERKY4','PERKY4R') and r['hardware_qualified'] is False
    assert r['algorithms']==['Fold Drum 1','Fold Drum 2','Simple Drum','Complex Drum']
    assert r['controls']==['TUNE','DECAY','ALGO','PAR1','PAR2','MODE'] and r['voices']==['T1','T5']
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==commit
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT)
    for name,v in r['artifacts'].items():
        assert digest(v['path'])==v['sha256'] and Path(v['path']).stat().st_size==v['bytes'],name
    for v in r['component_reports'].values():
        assert digest(v['artifact']['path'])==v['artifact']['sha256']
        assert json.loads(Path(v['artifact']['path']).read_text())==v['results']
    for v in r['inputs']:assert digest(v['path'])==v['sha256'],v['path']
    sources=json.loads(Path(r['artifacts']['source_manifest']['path']).read_text())
    sources.update(r['extra_sources'])
    for path,sha in sources.items():
        assert digest(ROOT/path)==sha,(path,'working source drift')
        assert hashlib.sha256(subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)).hexdigest()==sha,(path,'commit drift')
    for c in r['commands']:
        assert c['returncode']==0 and digest(c['log'])==c['sha256'],c['command']
        assert not (c['targeted'] and c['skip_lines']),c['command']
    names={Path(c['command'][1]).name for c in r['commands'] if len(c['command'])>1}
    assert {'verify_perky_four_renderer.py','verify_perky_four_clock_audio.py','verify_perky_four_controls.py',
        'verify_perky_four_src_ui.py','verify_perky_four_ui.py','verify_perky_four_startup.py',
        'verify_perky_synth_port.py','verify_perky_four_fx.py','verify_perky_four_project.py',
        'verify_perky_two_core_regression.py','verify_perky_final_wrappers.py'}<=names
    if r['version']=='PERKY4R':
        assert {'verify_perky_complex_au.py','verify_perky_complex_control_contract.py'}<=names
        captures=[c for c in r['commands'] if len(c['command'])>1 and Path(c['command'][1]).name=='verify_perky_complex_au.py']
        assert len(captures)==6 and sum('--baseline' in c['command'] for c in captures)==4
        for tag in ('A','B'):
            report=r['component_reports'][f'out/perky/au-regression/{tag}/report.json']['results']
            assert len(report['comparisons'])==27 and all(c['peak_error_lsb']==0 for c in report['comparisons'])
            for path,sha in report['source_sha256'].items():assert digest(ROOT/path)==sha,(tag,path,'AU-qualified source drift')
            assert len(report['dynamic_AU_native'])==3 and len(report['integrated_AU_clock_trim'])==9
    assert r['committed_rebuild_sha256']==r['artifacts']['mainos']['sha256']
    print(f'[PASS] {r["version"]} provenance: {len(sources)} committed sources, {len(r["inputs"])} inputs, '
          f'{len(r["commands"])} successful commands, {len(r["artifacts"])} artifacts; hardware pending')
if __name__=='__main__':main()
