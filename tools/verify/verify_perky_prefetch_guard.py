#!/usr/bin/env python3
"""Conservative shared-P boundary safety gate, not a silicon pipeline emulator."""
import argparse,hashlib,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--expect-unsafe',action='store_true',help='negative regression control for frozen PERKY4R')
    args=ap.parse_args();ledger=json.loads((args.build/'memory.json').read_text())
    limit=0x40000-6
    violations=[]
    for tag,c in ledger['cores'].items():
        for row in c['p_shards']:
            if row['name']=='mapped prefetch guard NOPs':continue
            if row['start']>=0x30000 and row['start']+row['length']>limit:
                violations.append((tag,row['name'],hex(row['start']+row['length']-1)))
    if args.expect_unsafe:
        assert hashlib.sha256((args.build/'fragmented-mainos.bin').read_bytes()).hexdigest()=='6499de13d66ab4099ad87521e93e3f362c4fa80259deb95b6e86190f20ecd495','unsafe negative control is not frozen PERKY4R'
        assert violations,'negative control no longer detects the preserved risk'
        print('[PASS] frozen-image negative control detects shared-P boundary risk:',violations)
        return
    assert not violations,('executable code enters six-word mapped prefetch margin',violations)
    records=json.loads((args.build/'p-records.json').read_text())
    assert records['A']==records['B'],'shared upload union differs'
    for tag in ('A','B'):
        words={address+i:word for address,chunk in records[tag] for i,word in enumerate(chunk)}
        assert all(words.get(address)==0 for address in range(limit,0x40000)),(tag,'guard not explicitly uploaded as NOPs')
    print('[PASS] both uploads explicitly pad the six mapped words before P:0x40000; code stays below them')

if __name__=='__main__':main()
