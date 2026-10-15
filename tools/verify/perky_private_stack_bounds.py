#!/usr/bin/env python3
"""Static stack graph for the approved image; unknown edges remain blocking.

Constant propagation resolves register-held literal callees. It never uses an
observed high-water mark as a callee bound. The underlying SP accounting keeps
the interrupted exception record outside the private-stack analysis boundary.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
import verify_perky_hybrid_stack_structure as base

ROOT=Path(__file__).resolve().parents[2]
REG=re.compile(r'%([ad][0-7]|fp)$')
def reg(s):return 'a6' if s=='%fp' else (s[1:] if REG.fullmatch(s) else None)


class ImageAudit(base.Audit):
    def __init__(self, probe):
        self.probe=probe
        assert base.sha(probe/'mainos_PKHYB2P.bin')=='d254bc2f72a1c78d75f1652f89311d0b841246ad228fc6dc3324fd6717c00f48', 're-audit contracts for changed MAIN'
        assert base.sha(probe/'platform/runtime.elf')=='3ec97322ae4ff9fbe53c6d58e051a7174bac324abe594e90db20ca0d702d9bcf', 're-audit contracts for changed ELF'
        image=probe/'mainos_PKHYB2P.bin'
        self.data=image.read_bytes()
        self.layout=json.loads((probe/'platform/layout.json').read_text())
        self.raw=(probe/'platform/runtime.raw').read_bytes()
        self.code={}
        self.symbols={}
        for line in subprocess.check_output(['m68k-elf-nm','-n',str(probe/'platform/runtime.elf')],text=True).splitlines():
            if len(a:=line.split())==3:self.symbols[a[2]]=int(a[0],16)
        for cmd in (
            ['m68k-elf-objdump','-D','-b','binary','-m','m68k:cfv4e','--adjust-vma=0x40000400',str(image)],
            ['m68k-elf-objdump','-d',str(probe/'platform/runtime.elf')]):
            for line in subprocess.check_output(cmd,text=True).splitlines():
                m=re.match(r'^([0-9a-f]+):\s*((?:[0-9a-f]{4}\s+)+)\s*(\S+)\s*(.*)$',line)
                if m:
                    a,words,op,args=m.groups()
                    args=re.sub(r'\b([0-9a-f]{8}) <[^>]+>',r'0x\1',args)
                    self.code[int(a,16)]=(len(words.split())*2,op,args.strip())
        self.function_code={};self.children={}
        self.done={};self.active=[];self.visited=0;self.instruction_limit=100000
        # These ColdFire register-only forms are omitted by GNU's decoder.
        # Decode only the exact families implemented/audited in v4e.cpp.
        for pc,(n,op,args) in list(self.code.items()):
            if op=='.short':
                opcode=int(args,16)
                if opcode&0xfff8 in (0x00c0,0x02c0,0x04c0):
                    self.code[pc]=(2,'v4ereg','%d'+str(opcode&7))
        # RAM vtable written by the pinned card selector, both valid modes.
        self.ram={0x460d16cc:frozenset([0x46c85c76]),
            0x46c85c76:frozenset([0x400157b4,0x400157dc]),
            0x46c85c7a:frozenset([0x40015828,0x4001586c]),
            0x46c85c7e:frozenset([0x40015804,0x40015848]),
            0x46c85c82:frozenset([0x4001588c]),0x46c85c86:frozenset([0x400158cc])}
        # Unique post-boot UART setup callers and the sole UI callback writer.
        self.ram.update({0x460ba97c:frozenset([0x40092bbc]),
            0x460ba980:frozenset([0x40092254]),
            0x460ba984:frozenset([0x40092f88,0x40092fac]),
            0x460d1e60:frozenset([0x40043418,0x4007b408])})
        # Sequencer's LFO index is masked to31 at 0x40003f3e..40.
        base.FIXED_CALLS[0x40003f5e]=tuple(sorted(set(next(iter(self.literal(0x400d6290+4*i,4))) for i in range(32))))
        base.FIXED_CALLS[0x4000d022]=tuple(sorted(set(next(iter(self.literal(0x400d6210+4*i,4))) for i in range(32))))
        # Compiler switch: unsigned range check against5 precedes six signed
        # word offsets at 0x4009a024 (0x4009a010..20).
        for site,table,count in ((0x4009a020,0x4009a024,6),(0x4009a1a0,0x4009a1a4,6),(0x400a51a0,0x400a51a4,64),(0x4007ea1a,0x4007ea1e,8)):
            base.FIXED_CALLS[site]=tuple(table+int.from_bytes(self.data[table-0x40000400+2*i:table-0x40000400+2*i+2],'big',signed=True) for i in range(count))
        # Seven-stage DMA dispatcher; count is reset by the audio frame and
        # advances through these states. Mask-lowering/nesting is audited
        # separately; this table alone is not a nesting bound.
        base.FIXED_CALLS[0x40004860]=tuple(next(iter(self.literal(0x400ab61a+4*i,4))) for i in range(7))
        # Mutable previous/current audio source callbacks are populated only
        # from the masked (type & 7) renderer table, or reset to the empty
        # renderer by 0x40004768. Never use their initial MAIN bytes as values.
        renderers=frozenset(next(iter(self.literal(0x400d6434+4*i,4))) for i in range(8))
        for address in range(0x400d61d0,0x400d6210,4):self.ram[address]=renderers
        for site in (0x4000d43e,0x4000d52c):base.FIXED_CALLS[site]=tuple(sorted(renderers))
        # Renderer local fp-68 has exactly two dominating assignments:
        # 0x40008132 and 0x40008142, selecting static/flex sample readers.
        for site in (0x4000853c,0x4000854c,0x400086c0,0x40008b14,0x40008b24,0x40008c9c):
            base.FIXED_CALLS[site]=(0x40095bdc,0x400932e8)
        for site,table in ((0x40008d28,0x40008d2c),(0x40008d88,0x40008d8c),(0x4000874e,0x40008752),(0x400087b2,0x400087b6),(0x40001034,0x40001038),(0x40001158,0x4000115c),(0x4000127c,0x40001280),(0x400013a0,0x400013a4)):
            base.FIXED_CALLS[site]=tuple(table+2*i for i in range(4))
        base.FIXED_CALLS[0x40007fa8]=tuple(0x40007fac+int.from_bytes(self.data[0x7bac+2*i:0x7bae+2*i],'big',signed=True) for i in range(5))
        # All literal list arguments at the twenty register calls to
        # 0x4007e760. List+4 points to sentinel-terminated 14-byte bindings;
        # 0x4007e760/0x4007e81c rebuild the eight RAM dispatch records.
        ui_lists=(0x400b9e16,0x400c0a8c,0x400c0c04,0x400c0c10,0x400c0c1c,
            0x400c0c28,0x400bebfe,0x400babba,0x400c0c34,0x400bb2e6,
            0x400c09b0,0x400ccc08,0x400ce2e8,0x400cfeea,0x400cff28,
            0x400d0398,0x400d0a1c)
        callbacks=set()
        for a in ui_lists:
            table=next(iter(self.literal(a+4,4)))
            for i in range(9):
                key=next(iter(self.literal(table+14*i,4)))
                if key&0x80000000:break
                assert key<8
                callback=next(iter(self.literal(table+14*i+4,4)))
                if callback:callbacks.add(callback)
            else:raise base.OpenBound('UI binding without bounded sentinel')
        base.FIXED_CALLS[0x4007e9b8]=tuple(sorted(callbacks))
        for site,table in ((0x40008614,0x400d1cd0),(0x40008bf0,0x400d1cd0)):
            base.FIXED_CALLS[site]=tuple(next(iter(self.literal(table+4*i,4))) for i in range(4))
        for site,table in ((0x40004510,0x40004514),(0x4000455e,0x40004562)):
            base.FIXED_CALLS[site]=tuple(table+2*i for i in range(5))
        # GNU spills the sole helper pointer to fp-244 across the two
        # commit paths. All call loads of that slot in pk_render correspond
        # to pk_hybrid_commit_longs in control_cf_dsp_hybrid.c.
        commit=self.symbols['pk_hybrid_commit_longs']
        end=self.symbols['pk_render']+0x9762
        for pc,(n,op,args) in self.code.items():
            if self.symbols['pk_render']<=pc<end and op=='moveal' and args.startswith('%fp@(-244),'):
                following=self.code.get(pc+n)
                if following and following[1]=='jsr' and following[2]==args.split(',')[1]+'@':
                    base.FIXED_CALLS[pc+n]=(commit,)
        for site in (0x40c53bde,0x40c53cde,0x40c54e1c,0x40c55cd4):
            base.FIXED_CALLS[site]=tuple(self.symbols[n] for n in ('res_update_bass_impl.constprop.0','res_update_snare_impl.constprop.0'))
        base.FIXED_CALLS[0x40c4ec1e]=(commit,)
        base.FIXED_CALLS[0x40c533a6]=(commit,)
        self.explicit_calls=set(base.FIXED_CALLS)
        self.resolutions={}
        self.flow_cache={}
        self.decodes=[]
        self.private_boundary=self.symbols['pk_hybrid_irq_restore']
        # Valid stock machine types0..7; null entries are guarded at d482.
        base.FIXED_CALLS[0x4000d49c]=tuple(sorted(set(next(iter(self.literal(0x400d6454+4*i,4))) for i in range(8))-{0}))

        # ColdFire byte/word pushes use two bytes on A7; the inherited
        # auditor only has long pushes. Normalize their SP effect explicitly.
        for pc,(n,op,args) in list(self.code.items()):
            if args.endswith('%sp@-') and op in ('movew','clrw','moveb','clrb'):
                self.code[pc]=(n,'subql','#2,%sp')
            elif '%sp@+' in args and op in ('movew','moveb'):
                self.code[pc]=(n,'addql','#2,%sp')

    def decode_at(self, pc):
        start=self.layout['base'] if self.layout['base']<=pc<self.layout['base']+len(self.raw) else 0x40000400
        path=self.probe/'platform/runtime.raw' if start!=0x40000400 else self.probe/'mainos_PKHYB2P.bin'
        out=subprocess.check_output(['m68k-elf-objdump','-D','-b','binary','-m','m68k:cfv4e',
            f'--adjust-vma={start:#x}',f'--start-address={pc:#x}',f'--stop-address={pc+512:#x}',str(path)],text=True)
        for line in out.splitlines():
            m=re.match(r'^([0-9a-f]+):\s*((?:[0-9a-f]{4}\s+)+)\s*(\S+)\s*(.*)$',line)
            if m:
                a,words,op,args=m.groups();at=int(a,16)
                if at==self.private_boundary:self.code[at]=(6,'rte','')
                elif op=='.short' and int(args,16)&0xfff8 in (0x00c0,0x02c0,0x04c0):
                    self.code[at]=(2,'v4ereg','%d'+str(int(args,16)&7))
                else:self.code[at]=(len(words.split())*2,op,args.strip())
        self.decodes.append(pc)

    def word(self, a, n):
        # MAIN and runtime are writable SDRAM. Values read from arbitrary
        # loaded data are not immutable constants. Only explicit contracts
        # above may supply pointer values to the flow analysis.
        return self.ram.get(a) if n==4 else None

    def literal(self, a, n):
        for start,data in ((0x40000400,self.data),(self.layout['base'],self.raw)):
            if start<=a and a+n<=start+len(data):
                return frozenset([int.from_bytes(data[a-start:a-start+n],'big')])
        return None

    def address(self, source, state):
        if re.fullmatch(r'0x[0-9a-f]+',source):return frozenset([int(source,16)])
        m=re.fullmatch(r'%pc@\((0x[0-9a-f]+)\)',source)
        if m:return frozenset([int(m[1],16)])
        m=re.fullmatch(r'%(a[0-7]|fp)@(?:\((-?\d+)\))?',source)
        if m:
            values=state.get('a6' if m[1]=='fp' else m[1])
            return frozenset((a+int(m[2] or 0))&0xffffffff for a in values) if values is not None else None
        return None

    def flow(self, entry):
        if entry in self.flow_cache:return self.flow_cache[entry]
        nodes={};pending=deque([(entry,{})]);targets={};count=0
        while pending:
            pc,state=pending.popleft();state=dict(state)
            if pc in nodes:
                old=nodes[pc];merged={}
                for k in old.keys()|state.keys():
                    a,b=old.get(k),state.get(k)
                    v=(a|b) if a is not None and b is not None else None
                    # Widen changing loop counters/pointers immediately;
                    # retain finite unions only for actual code addresses.
                    if a!=b and v is not None and any(x not in self.code for x in v):v=None
                    merged[k]=v if v is None or len(v)<=64 else None
                if merged==old:continue
                state=merged
            nodes[pc]=state.copy();count+=1
            if count>100000:raise base.OpenBound(f'constant-flow limit at {entry:#x}')
            if pc not in self.code:self.decode_at(pc)
            if pc not in self.code:continue
            n,op,args=self.code[pc];nxt=pc+n
            if op in ('rts','rte','halt','illegal','stop'):continue
            call=op.startswith(('jsr','bsr'))
            jump=op=='jmp'
            if call or jump:
                direct=re.fullmatch(r'(?:%pc@\()?(0x[0-9a-f]+)\)?',args)
                if direct:dest=frozenset([int(direct[1],16)])
                elif pc in base.FIXED_CALLS:dest=frozenset(base.FIXED_CALLS[pc])
                else:
                    m=re.fullmatch(r'%(a[0-7]|fp)@',args)
                    dest=state.get('a6' if m and m[1]=='fp' else m[1]) if m else None
                targets[pc]=dest if pc not in targets else (targets[pc]|dest if targets[pc] is not None and dest is not None else None)
                if jump:
                    if pc==0x4001ee7c:
                        dest=(0x4001ee8e,0x4001eefc,0x4001ee5c,0x4001efce,0x4001ef72,0x4001f03c,0x4001f210)
                    if dest:
                        for a in dest:pending.append((a,state))
                    continue
                # Stock C ABI: calls preserve d2..d7/a2..a6. Every used
                # callee remains subject to the separate SP/callee audit.
                for r in ('d0','d1','a0','a1'):state[r]=None
            else:
                if ',' in args:source,destination=args.rsplit(',',1)
                else:source,destination='',args
                d=reg(destination)
                if d and op not in ('cmpl','cmpal','cmpil','cmpib','cmpiw','cmpb','cmpw','cmpaw','tstl','tstw','tstb','btst'):
                    previous=state.get(d)
                    value=None
                    if op.startswith('clr'):value=frozenset([0])
                    elif op=='lea':value=self.address(source,state)
                    elif op.startswith(('move','mvs','mvz')):
                        if source.startswith('#'):
                            try:value=frozenset([int(source[1:],0)&0xffffffff])
                            except ValueError:pass
                        elif reg(source):value=state.get(reg(source))
                        else:
                            addresses=self.address(source,state)
                            width=1 if op.endswith('b') else 2 if op.endswith('w') else 4
                            if addresses is not None:
                                reads=[self.word(a,width) for a in addresses]
                                if all(v is not None for v in reads):value=frozenset().union(*reads)
                    elif op.startswith(('addq','subq','adda','suba','addi','subi')) and source.startswith('#') and state.get(d) is not None:
                        v=int(source[1:],0)*(1 if op.startswith('add') else -1)
                        value=frozenset((a+v)&0xffffffff for a in state[d])
                    if (op.startswith(('move','clr')) and op.endswith(('b','w')) and not op.startswith('movea')):
                        bits=8 if op.endswith('b') else 16;mask=(1<<bits)-1
                        value=(frozenset((a&~mask)|(b&mask) for a in previous for b in value)
                               if previous is not None and value is not None else None)
                    elif op in ('moveaw','mvsb','mvsw') and value is not None:
                        bits=8 if op.endswith('b') else 16;mask=(1<<bits)-1
                        value=frozenset(((v&mask) if not(v&(1<<(bits-1))) else (v|~mask))&0xffffffff for v in value)
                    state[d]=value
                if op=='moveml' and source.startswith('%sp@'):
                    # Restored values require stack-value analysis; do not
                    # reuse a local literal after restoring the caller's reg.
                    ordered=['d0','d1','d2','d3','d4','d5','d6','d7','a0','a1','a2','a3','a4','a5','a6','a7']
                    for part in destination.split('/'):
                        values=part.split('-');first=reg(values[0]);last=reg(values[-1])
                        if first in ordered and last in ordered:
                            for r in ordered[ordered.index(first):ordered.index(last)+1]:state[r]=None
            # Auto-update EA modes change address registers even when the
            # instruction destination is memory. Forget them conservatively.
            for altered in re.findall(r'%(a[0-7]|fp)@[-+]',args):
                state['a6' if altered=='fp' else altered]=None
            branch=re.fullmatch(r'b(?:ra|cc|cs|eq|ne|ge|gt|le|lt|hi|ls|pl|mi|vc|vs)[sw]?',op)
            if branch:
                m=re.fullmatch(r'0x([0-9a-f]+)',args)
                if m:pending.append((int(m[1],16),state))
                if op.startswith('bra'):continue
            pending.append((nxt,state))
        self.flow_cache[entry]=targets
        return targets

    def bound(self, entry):
        if entry==0x40006820:
            # stop(track): arguments >7 fan out to eight sequential calls
            # with arguments0..7, which all take the non-recursive arm.
            # Each arm retains8 saved bytes +4 argument +4 JSR bytes.
            # The recursive call therefore has depth at most one.
            result=32+self.bound(0x4000672c)
            self.done[entry]=result
            return result
        targets=self.flow(entry)
        for pc,values in targets.items():
            if pc in self.explicit_calls:continue
            if values and all(v in self.code for v in values):
                prior=self.resolutions.get(pc,frozenset())
                merged=prior|values
                if prior and merged!=prior:
                    raise base.OpenBound(f'context-dependent targets require new fixed-point audit at {pc:#x}')
                base.FIXED_CALLS[pc]=tuple(sorted(merged))
                self.resolutions[pc]=merged
            elif pc in self.resolutions:
                raise base.OpenBound(f'context lost a prior literal target at {pc:#x}')
        return super().bound(entry)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe',type=Path,default=ROOT/'out/perky/hybrid/private-stack/probe')
    ap.add_argument('--out',type=Path,default=ROOT/'out/perky/hybrid/private-stack/static/BOUNDS.json')
    ap.add_argument('--selftest',action='store_true')
    a=ap.parse_args()
    if a.selftest:unittest.main(argv=[sys.argv[0]])
    audit=ImageAudit(a.probe)
    restore=audit.symbols['pk_hybrid_irq_restore']
    assert audit.code[restore][1]=='moveal'
    audit.code[restore]=(6,'rte','') # analysis ends BEFORE A7 returns to the task
    roots={'private_audio':audit.symbols['pk_hybrid_irq_on_private'],
        'storage':0x4001ee30,'keyrepeat':0x4005593c,'UI':0x40056c40,
        'sequencer':0x400a1e0c,'UART0':0x400106ec,'UART1':0x400109bc,
        'eDMA':0x40004840,'ATA':0x40015304,'USB':0x4001e594,
        'counter':0x4001c244,'PIT1':0x40020d38,'ATA_DMA':0x400152a4,'serial2':0x40010b88,
        'DTIM0':0x40055cb8,'DTIM1':0x400409f4,'DTIM2':0x40092bf4,'DTIM3':0x4009228c,
        'voice':0x40005540,'p2a':0x40091d18,'p2b':0x400921c4,'p2c':0x4009203c,
        'engine':0x4008445c,'p1b':0x40098a5c,'sys':0x40061a94}
    results={}
    for name,entry in roots.items():
        audit.active=[];audit.visited=0
        try:results[name]={'status':'CLOSED_SCOPED','bytes_below_entry_SP':audit.bound(entry)}
        except base.OpenBound as e:results[name]={'status':'OPEN','reason':str(e)}
    def reachable(root):
        functions=set();pending=[root]
        while pending:
            f=pending.pop()
            if f in functions:continue
            functions.add(f);pending.extend(audit.children.get(f,()))
        return set().union(*(audit.function_code.get(f,set()) for f in functions))
    special={}
    for name in ('private_audio','eDMA','UART0','UART1','sequencer','DTIM0','DTIM1','DTIM2','DTIM3','USB','PIT1','ATA','ATA_DMA','serial2'):
        pcs=reachable(roots[name]);special[name]={hex(pc):audit.code[pc][1:] for pc in sorted(pcs)
            if '%sr' in audit.code[pc][2] or audit.code[pc][1]=='trap'}
    required=('private_audio','storage','keyrepeat','UI','sequencer','UART0','UART1','eDMA',
        'ATA','USB','PIT1','ATA_DMA','serial2','DTIM0','DTIM1','DTIM2','DTIM3','counter')
    closed=all(results[n]['status']=='CLOSED_SCOPED' for n in required)
    budgets=None
    if closed:
        b=lambda n:results[n]['bytes_below_entry_SP']
        # One exception at each permitted level. eDMA case5 lowers6->5;
        # state is already6, whose successor does not lower. UART6 masks7.
        # Include max(UART0, UART1, DMAcase6) inside that window, and allow
        # THREE alignment bytes at every exception, even for aligned callers.
        irq6=b('eDMA')+11+max(b('UART0'),b('UART1'),16)+11
        levels={1:b('DTIM1')+11,2:b('PIT1')+11,
            3:max(b('sequencer'),b('DTIM0'),b('ATA_DMA'))+11,
            4:max(b('USB'),b('serial2'),b('DTIM2'),b('DTIM3'))+11,
            5:max(b('ATA'),b('counter'),0)+11,6:irq6}
        # Audio contributes only its original exception prefix/tail to a task.
        # Its possible6 nesting is already represented by the level6 term.
        assert levels[5]>=11
        private=b('private_audio')+irq6
        residual={n:b(n)+4+sum(levels.values()) for n in ('storage','keyrepeat','UI')}
        assert private<=4096 and all(v<=2048-32 for v in residual.values())
        # No scheduling TRAP in audio/higher graphs. PIT0 scheduling is IPL1.
        for name in ('private_audio','eDMA','UART0','UART1'):
            assert not any(op=='trap' for op,args in special[name].values())
        for pc,(op,args) in special['private_audio'].items():
            if args.endswith(',%sr') and args.startswith('#'):
                assert (int(args.split(',')[0][1:],0)>>8)&7>=5
        budgets={'private_audio_including_higher_nesting_bytes':private,
            'private_capacity_bytes':4096,'private_remaining_bytes':4096-private,
            'residual_by_level_bytes':levels,'residual_irq_sum_bytes':sum(levels.values()),
            'residual_task_including_exit_and_all_IRQ_bytes':residual,
            'task_capacity_bytes':2048,'bottom_instrumentation_bytes':32,
            'comparison_only_other_tasks':'Audio prefix/tail cannot exceed the old audio exception/frame requirement. Their unchanged base call graphs below remain outside this bounded correction; no new all-path stock-OS proof is claimed.'}
    report={'status':'PASS_SCOPED_PRIVATE_AND_THREE_VULNERABLE_TASK_BUDGETS' if closed else 'OPEN',
        'budgets':budgets,'special_control_instructions':special,'roots':results,'literal_register_resolutions':{hex(k):[hex(v) for v in vs] for k,vs in sorted(audit.resolutions.items())},
        'closed_subgraphs':{hex(k):v for k,v in sorted(audit.done.items())},
        'anchored_redecodes':[hex(v) for v in audit.decodes],
        'image_sha256':base.sha(a.probe/'mainos_PKHYB2P.bin'),
        'limits':['Uses the pinned firmware C ABI: d2..d7/a2..a6 preserved across calls; valid stock tables/indices and seven-stage eDMA protocol. Contract provenance is documented in PRIVATE_STACK_QUALIFICATION.md.','Unknown callbacks/jump tables remain blocking.','Private boundary excludes original exception frame; nested IRQ costs must be added.']}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(results,indent=2))
    return 0 if closed else 1


class Tests(unittest.TestCase):
    def flow(self,code):
        a=ImageAudit.__new__(ImageAudit)
        a.code=code;a.flow_cache={};a.ram={}
        return a.flow(0)

    def test_loaded_memory_is_not_immutable(self):
        a=ImageAudit.__new__(ImageAudit);a.ram={}
        self.assertIsNone(a.word(0x400d61d0,4))

    def test_auto_update_invalidates_pointer(self):
        result=self.flow({0:(6,'lea','0x10,%a0'),6:(2,'movel','%a0@+,%d2'),
            8:(2,'jsr','%a0@'),10:(2,'rts',''),16:(2,'rts','')})
        self.assertIsNone(result[8])

    def test_partial_word_is_not_complete_address(self):
        result=self.flow({0:(4,'movew','#16,%d0'),4:(2,'moveal','%d0,%a0'),
            6:(2,'jsr','%a0@'),8:(2,'rts',''),16:(2,'rts','')})
        self.assertIsNone(result[6])

    def test_volatile_register_is_clobbered_by_call(self):
        result=self.flow({0:(6,'lea','0x18,%a0'),6:(6,'jsr','0x18'),
            12:(2,'jsr','%a0@'),14:(2,'rts',''),24:(2,'rts','')})
        self.assertIsNone(result[12])

    def test_dominating_literal_and_branch_union(self):
        result=self.flow({0:(6,'lea','0x18,%a2'),6:(2,'beqs','0xe'),
            8:(6,'lea','0x1a,%a2'),14:(2,'jsr','%a2@'),16:(2,'rts',''),
            24:(2,'rts',''),26:(2,'rts','')})
        self.assertEqual(result[14],frozenset((24,26)))


if __name__=='__main__':sys.exit(main())
