#!/usr/bin/env python3
"""Validate/compile the evidence-derived Fold Drum 2 trigger contract.

The ARM delta includes trigger plus the mandatory post-trigger update. Words
already written by pk_fold2_apply_controls are excluded. Remaining mutations
must be exact across all 18 observations, optionally conditioned on pre-trigger
PRIMARY so fixed OSC_A/OSC_B storage can represent inactive-oscillator reset
and swap behavior.
"""
from pathlib import Path
import argparse,json,sys
R=Path(__file__).resolve().parents[2]; W=51; PRIMARY=50
CONTRACT=R/'out/perky/fold2-trigger-contract.json'; PLAN=R/'out/perky/fold2-trigger-plan.json'
CONTROL={14,20,31,32,33,42,44}; PHASES=('first_trigger','active_retrigger')

def infer(cs,d):
 p=[c['pre'] for c in cs];q=[c['post'] for c in cs]
 if all(a[d]==b[d] for a,b in zip(p,q)):return {'op':'SAME'}
 v={b[d] for b in q}
 if len(v)==1:return {'op':'CONST','value':next(iter(v))}
 v={(b[d]^a[d])&65535 for a,b in zip(p,q)}
 if len(v)==1 and next(iter(v)):return {'op':'XOR','mask':next(iter(v))}
 v={(b[d]-a[d])&65535 for a,b in zip(p,q)}
 if len(v)==1 and next(iter(v)):return {'op':'ADD16','delta':next(iter(v))}
 s=[i for i in range(W) if i!=d and all(b[d]==a[i] for a,b in zip(p,q))]
 if len(s)==1:return {'op':'COPY','src':s[0]}

def apply(o,p,d):
 k=o['op']
 if k=='SAME':return p[d]
 if k=='CONST':return o['value']
 if k=='XOR':return (p[d]^o['mask'])&65535
 if k=='ADD16':return (p[d]+o['delta'])&65535
 if k=='COPY':return p[o['src']]
 raise ValueError(k)

def exact(o,cs,d):return o is not None and all(apply(o,c['pre'],d)==c['post'][d] for c in cs)

def resolve(cs,d):
 o=infer(cs,d)
 if exact(o,cs,d):return o
 if sorted({c['pre'][PRIMARY] for c in cs})!=[0,1]:return None
 b={}
 for s in (0,1):
  x=[c for c in cs if c['pre'][PRIMARY]==s];o=infer(x,d)
  if not exact(o,x,d):return None
  b[str(s)]=o
 return b['0'] if b['0']==b['1'] else {'op':'BY_PRIMARY','branches':b}

def match(o,c,d):
 if o['op']=='BY_PRIMARY':o=o['branches'][str(c['pre'][PRIMARY])]
 return apply(o,c['pre'],d)==c['post'][d]

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--contract',type=Path,default=CONTRACT);a.add_argument('--plan',type=Path,default=PLAN);a.add_argument('--allow-unresolved',action='store_true');x=a.parse_args()
 # A plan is valid only for the contract being checked in THIS invocation.
 # Remove any prior success before reading/validating the new ARM evidence so
 # an interrupted, malformed or newly-unresolved run can never reuse stale law.
 if x.plan.exists():x.plan.unlink()
 if not x.contract.exists():print('Fold2 trigger contract missing; regenerate ARM fixtures first.',file=sys.stderr);raise SystemExit(2)
 c=json.loads(x.contract.read_text());assert c.get('schema')=='octabam.perky.fold2-trigger.v1' and c.get('compact_words')==W and c.get('engine_zero_based')==3
 cs=[]
 for phase in PHASES:
  p=c[phase];assert len(p['cases'])==9;changed=set()
  for z in p['cases']:
   pre=z['pre'];post=z['post'];assert len(pre)==len(post)==W and all(isinstance(v,int) and 0<=v<=65535 for v in pre+post)
   changed|={i for i,(m,n) in enumerate(zip(pre,post)) if m!=n};cs.append({'pre':pre,'post':post})
  assert sorted(changed)==p['changed_indices']
  assert sorted(w['index'] for w in p['words'])==sorted(changed)
 assert len(cs)==18 and set(z['pre'][PRIMARY] for z in cs)<=set((0,1))
 changed=sorted({i for z in cs for i,(m,n) in enumerate(zip(z['pre'],z['post'])) if m!=n});trig=[i for i in changed if i not in CONTROL]
 ops=[];bad=[]
 for d in trig:
  o=resolve(cs,d)
  if o is None or not all(match(o,z,d) for z in cs):bad.append(d)
  else:ops.append({'dst':d,**o})
 if bad:
  msg='unresolved Fold2 trigger words: '+','.join(map(str,bad))
  if not x.allow_unresolved:raise RuntimeError(msg)
  print('Fold Drum 2 trigger contract: ANALYSIS ONLY\n'+msg+'\nNo shipping trigger plan emitted.');return
 plan={'schema':'octabam.perky.fold2-trigger-plan.v2','source_contract':c['schema'],'engine_zero_based':3,'compact_words':W,'primary_word':PRIMARY,'control_owned_words':sorted(CONTROL),'observations':18,'semantics':['all reads/conditions use pre-trigger state','control-owned words are applied by pk_fold2_apply_controls','DSP executable seam gate remains authoritative for write ordering'],'changed_words_all':changed,'trigger_changed_words':trig,'operations':ops}
 x.plan.parent.mkdir(parents=True,exist_ok=True);x.plan.write_text(json.dumps(plan,indent=2)+'\n')
 print(f"Fold Drum 2 trigger contract: PASS (18 ARM cases; {len(ops)} trigger writes; {sum(o['op']=='BY_PRIMARY' for o in ops)} PRIMARY-conditioned)")
 print('plan:',x.plan)
if __name__=='__main__':main()