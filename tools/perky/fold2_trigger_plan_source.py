#!/usr/bin/env python3
"""Validate and emit DSP56300 source for a qualified Fold Drum 2 trigger plan.

The plan itself is firmware-derived and lives only under ``out/``. This tracked
module is the single translation layer used by both the isolated executable
oracle gate and the hidden production candidate. Every source read and every
PRIMARY decision is made from a frozen pre-trigger snapshot so COPY/swap
semantics cannot depend on write ordering.
"""
from __future__ import annotations
from pathlib import Path
import json
WORDS=51;PRIMARY=50
PLAN_SCHEMA='octabam.perky.fold2-trigger-plan.v2';CONTRACT_SCHEMA='octabam.perky.fold2-trigger.v1'

def _fail(m):raise AssertionError('Fold2 trigger plan: '+m)
def _u16(v,w):
 if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=0xffff:_fail(f'{w}: invalid u16 {v!r}')
 return v

def _validate_primitive(o,w):
 k=o.get('op')
 if k=='SAME':return
 if k=='CONST':_u16(o.get('value'),w+'.value');return
 if k=='COPY':
  s=o.get('src')
  if not isinstance(s,int) or isinstance(s,bool) or not 0<=s<WORDS:_fail(f'{w}: invalid COPY source {s!r}')
  return
 if k=='XOR':_u16(o.get('mask'),w+'.mask');return
 if k=='ADD16':_u16(o.get('delta'),w+'.delta');return
 _fail(f'{w}: unsupported primitive {k!r}')

def validate_plan(p):
 if p.get('schema')!=PLAN_SCHEMA:_fail(f"unexpected schema {p.get('schema')!r}")
 if p.get('source_contract')!=CONTRACT_SCHEMA:_fail('unexpected source contract')
 if p.get('engine_zero_based')!=3:_fail('wrong engine index')
 if p.get('compact_words')!=WORDS or p.get('primary_word')!=PRIMARY:_fail('state geometry drifted')
 if p.get('observations')!=18:_fail('plan is not based on all 18 ARM observations')
 tw=p.get('trigger_changed_words');ops=p.get('operations')
 if not isinstance(tw,list) or not isinstance(ops,list):_fail('missing operation lists')
 if len(tw)!=len(ops) or [o.get('dst') for o in ops]!=tw:_fail('operation destinations mismatch')
 if len(tw)!=len(set(tw)):_fail('duplicate destination')
 if set(p.get('control_owned_words',[]))&set(tw):_fail('trigger/control ownership overlap')
 for n,o in enumerate(ops):
  d=o.get('dst')
  if not isinstance(d,int) or isinstance(d,bool) or not 0<=d<WORDS:_fail(f'operation {n}: invalid destination {d!r}')
  if o.get('op')=='BY_PRIMARY':
   b=o.get('branches')
   if not isinstance(b,dict) or set(b)!={'0','1'}:_fail(f'operation {n}: BY_PRIMARY needs exact 0/1 branches')
   _validate_primitive(b['0'],f'operation {n}/primary0');_validate_primitive(b['1'],f'operation {n}/primary1')
  else:_validate_primitive(o,f'operation {n}')
 return ops

def load_plan(path:Path):
 if not path.exists():raise FileNotFoundError(f'qualified Fold2 trigger plan missing: {path}; run tools/perky/qualify_fold2_trigger.py first')
 p=json.loads(path.read_text());return p,validate_plan(p)

def apply_primitive(o,pre,d):
 k=o['op']
 if k=='SAME':return pre[d]
 if k=='CONST':return o['value']&0xffff
 if k=='COPY':return pre[o['src']]&0xffff
 if k=='XOR':return (pre[d]^o['mask'])&0xffff
 if k=='ADD16':return (pre[d]+o['delta'])&0xffff
 _fail(f'cannot apply {k!r}')

def apply_plan(pre,ops):
 if len(pre)!=WORDS:_fail(f'pre-state has {len(pre)} words')
 s=pre[PRIMARY]
 if s not in (0,1):_fail(f'PRIMARY is {s}, expected 0/1')
 out=list(pre)
 for o in ops:
  a=o['branches'][str(s)] if o['op']=='BY_PRIMARY' else o
  out[o['dst']]=apply_primitive(a,pre,o['dst'])
 return out

def _hex(v):return f"{_u16(v,'immediate'):06x}"
def _emit_primitive(o,d,live,frozen):
 k=o['op'];ld=f'x:({live}+${d:x})';fd=f'x:({frozen}+${d:x})'
 if k=='SAME':return []
 if k=='CONST':return [f'        move #>${_hex(o["value"])},a',f'        move a1,{ld}']
 if k=='COPY':return [f'        move x:({frozen}+${o["src"]:x}),a',f'        move a1,{ld}']
 if k=='XOR':return [f'        move {fd},a',f'        eor #>${_hex(o["mask"])},a','        and #>$00ffff,a',f'        move a1,{ld}']
 if k=='ADD16':return [f'        move {fd},a',f'        add #>${_hex(o["delta"])},a','        and #>$00ffff,a',f'        move a1,{ld}']
 _fail(f'cannot emit {k!r}')

def emit_apply(ops,*,live_reg='r6',snapshot_reg='r5',branch_prefix='f2tp'):
 """Emit plan application; caller must have frozen all 51 words first."""
 lines=[]
 for n,o in enumerate(ops):
  d=o['dst']
  if o['op']!='BY_PRIMARY':lines+=_emit_primitive(o,d,live_reg,snapshot_reg);continue
  zero=f'{branch_prefix}_{n}z';done=f'{branch_prefix}_{n}d'
  lines += [f'        move x:({snapshot_reg}+${PRIMARY:x}),a','        tst a',f'        beq {zero}']
  lines += _emit_primitive(o['branches']['1'],d,live_reg,snapshot_reg)+[f'        bra {done}',zero+':']
  lines += _emit_primitive(o['branches']['0'],d,live_reg,snapshot_reg)+[done+':','        nop']
 return '\n'.join(lines)+('\n' if lines else '')

def emit_snapshot(*,live_reg='r6',snapshot_reg='r5'):
 lines=[]
 for i in range(WORDS):lines += [f'        move x:({live_reg}+${i:x}),a',f'        move a1,x:({snapshot_reg}+${i:x})']
 return '\n'.join(lines)+'\n'

def emit_routine(ops,*,label,live_reg='r6',snapshot_reg='r5',snapshot_address=None,branch_prefix='f2tp'):
 """Emit snapshot + apply + RTS. Branch labels intentionally cannot prefix-match label."""
 if branch_prefix.startswith(label) or label.startswith(branch_prefix):_fail(f'unsafe assembler label prefixes: {label!r}/{branch_prefix!r}')
 lines=[label+':']
 if snapshot_address is not None:
  if not 0<=snapshot_address<=0xffff:_fail(f'snapshot address out of X range: {snapshot_address:#x}')
  lines.append(f'        move #>${snapshot_address:06x},{snapshot_reg}')
 text='\n'.join(lines)+'\n'+emit_snapshot(live_reg=live_reg,snapshot_reg=snapshot_reg)
 text+=emit_apply(ops,live_reg=live_reg,snapshot_reg=snapshot_reg,branch_prefix=branch_prefix)
 return text+'        rts\n'
