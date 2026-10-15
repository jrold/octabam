#!/usr/bin/env python3
"""Check renderer EMAC compatibility with the qualified higher IRQ paths.

Reuse the closed eDMA/UART graph. The sole stock EMAC-using callee has a
reviewed full raw context save/restore; pin it to the qualified original.
Unknown EMAC users still fail. This is not a new whole-OS safety claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import perky_private_stack_bounds as bounds

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(work):
    contracts=json.loads((work/'STACK_CONTRACTS.json').read_text())
    audit=bounds.ImageAudit(work/'probe',contracts)
    roots={'eDMA':0x40004840,'UART0':0x400106ec,'UART1':0x400109bc}
    reference=work.parents[1]/'private-stack/probe/mainos_PKHYB2P.bin'
    assert sha(reference)=='d254bc2f72a1c78d75f1652f89311d0b841246ad228fc6dc3324fd6717c00f48'
    original=reference.read_bytes();start,end=0x400031a0,0x4000385a
    current_span=audit.data[start-0x40000400:end-0x40000400]
    assert current_span==original[start-0x40000400:end-0x40000400]
    # Reviewed stock routine: integer mode before raw saves; all four ACCs,
    # both extension registers, MASK and original MACSR restored before RTS.
    assert audit.code[0x400031ac][2]=='%macsr,%a1'
    assert audit.code[0x400031b0][2]=='%d0,%macsr'
    assert audit.code[0x400031c0][2]=='%d0-%d5/%a0-%a1,%a2@'
    assert audit.code[0x4000383a][2]=='%d0,%macsr'
    assert audit.code[0x4000383c][2]=='%a2@,%d0-%d5/%a0-%a1'
    for pc,args in ((0x40003840,'%d0,%acc0'),(0x40003842,'%d1,%acc1'),
                    (0x40003844,'%d2,%acc2'),(0x40003846,'%d3,%acc3'),
                    (0x40003848,'%d4,%accext01'),(0x4000384a,'%d5,%accext23'),
                    (0x4000384c,'%a0,%mask'),(0x4000384e,'%a1,%macsr')):
        assert audit.code[pc][2]==args,(hex(pc),audit.code[pc])
    result={};accesses=[];hazards=[]
    for name,root in roots.items():
        audit.active=[];audit.visited=0;audit.bound(root)
        functions=set();pending=[root]
        while pending:
            entry=pending.pop()
            if entry in functions:continue
            functions.add(entry);pending.extend(audit.children.get(entry,()))
        pcs=set().union(*(audit.function_code.get(entry,set()) for entry in functions))
        for pc in sorted(pcs):
            _,op,args=audit.code[pc]
            # All ColdFire MAC/EMAC instruction families are A-line opcodes.
            # Check raw opcodes too, including any GNU-decoder unknown forms.
            assert 0x40000400<=pc<0x40000400+len(audit.data)
            offset=pc-0x40000400;opcode=int.from_bytes(audit.data[offset:offset+2],'big')
            if opcode&0xf000==0xa000 or 'mac' in op or '%acc' in args or '%macsr' in args:
                entry={'pc':hex(pc),'opcode':hex(opcode),'op':op,'args':args}
                accesses.append(entry)
                if not start<=pc<end:hazards.append(entry)
        result[name]={'closed_functions':len(functions),'reachable_instructions':len(pcs)}
    assert not hazards,hazards
    exits={pc for pc in audit.function_code[start] if audit.code[pc][1] in ('rts','rte','rtd')}
    assert exits=={0x40003858},exits
    files=[work/'probe/mainos_PKHYB2P.bin',work/'probe/platform/runtime.elf',
           work/'STACK_CONTRACTS.json',reference,Path(__file__),Path(bounds.__file__),Path(bounds.base.__file__)]
    report={'status':'PASS_HIGHER_IRQ_EMAC_USE_FULLY_CONTEXT_PRESERVING',
        'paths':result,'EMAC_access_count':len(accesses),'unprotected_EMAC_accesses':hazards,
        'qualified_stock_context_preserver':{'start':hex(start),'end':hex(end),'sha256':hashlib.sha256(current_span).hexdigest(),'return':hex(next(iter(exits)))},'scope':'Existing qualified IPL5 audio / IPL6 eDMA and UART nesting, valid stock dispatch tables; no new whole-OS or silicon timing claim.',
        'inputs':{str(p):sha(p) for p in files}}
    (work/'EMAC_IRQ.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True)
    run(ap.parse_args().work.resolve())
