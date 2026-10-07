#!/usr/bin/env python3
"""Assemble and structurally gate the hidden Fold Drum 2 production composition.

Requires the local ARM-derived trigger plan/fixtures.  This gate deliberately
allows the source to exceed PERKY4's current 2,724-word donor so it can measure
the exact additional P requirement before effect-memory reclamation.  It emits
no firmware updater and does not expose Fold2 in the browser.
"""
from pathlib import Path
import re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/perky'))
import build_fold2_candidate as candidate
import build_noise_tone_synth_source as synth
OUT=ROOT/'out/perky/fold2-production-candidate'
CURRENT_DONOR=2724
PRIVATE_X_BASE=0x3800;PRIVATE_X_WORDS=616;PRIVATE_X_END=PRIVATE_X_BASE+PRIVATE_X_WORDS-1
LIVE_RANGES=((0x3800,0x38e7,'four 58-word overlay slots'),(0x38e8,0x38eb,'shared RNG'),
             (0x38ec,0x38ec,'event offset'),(0x38ed,0x38ed,'admission latch'),
             (0x38ee,0x38f1,'overlay type markers'),(0x3900,0x3963,'renderer scratch'),
             (0x3964,0x3974,'pitch cache'))

def overlap(a0,a1,b0,b1):return max(a0,b0)<=min(a1,b1)
def main():
 if not candidate.PLAN.exists():
  print('Fold2 production candidate: SKIP (qualified local trigger plan missing)',file=sys.stderr);raise SystemExit(2)
 case=candidate.FIX/'engine-4-mode-1-corner-0/wrapper-window-before.bin'
 if not case.exists():
  print('Fold2 production candidate: SKIP (local ARM fixture missing)',file=sys.stderr);raise SystemExit(2)
 s0=candidate.SHADOW_X;s1=s0+candidate.trigger.WORDS-1
 if not PRIVATE_X_BASE<=s0<=s1<=PRIVATE_X_END:raise AssertionError(f'trigger shadow ${s0:x}..${s1:x} outside measured private X')
 for a,b,name in LIVE_RANGES:
  if overlap(s0,s1,a,b):raise AssertionError(f'trigger shadow overlaps {name}: ${a:x}..${b:x}')
 source,_=candidate.build(OUT)
 for needle in ('cmp #>$3,a\n        beq pks_fold2_entry','pks_fold2_entry:','jsrl pk_fold2_apply_controls',
                'jsrl pk_fold2_candidate_trigger','jsrl pk_fold2_voice','pk_multi_fold2_init:'):
  if needle not in source:raise AssertionError('missing production Fold2 seam: '+needle)
 # Browser/ColdFire shipping selector stays untouched: hidden composition is DSP-only.
 control=(ROOT/'modules/perky/control.c').read_text()
 if 'FOLD DRUM 2' in control or 'engine_labels[3]' in control:raise AssertionError('Fold2 was exposed in stable browser/control.c')
 labels=re.findall(r'(?m)^([A-Za-z0-9_]+):',source)
 for i,a in enumerate(labels):
  for b in labels[i+1:]:
   if a!=b and (a.startswith(b) or b.startswith(a)):raise AssertionError(f'DSP assembler prefix collision: {a}/{b}')
 asm=OUT/'candidate-full.asm';binary=OUT/'candidate-full.bin';asm.write_text(source.replace('@CONT@','$000426'))
 r=subprocess.run([str(synth.ASM),'-in',str(asm),'-org','1000','-out',str(binary)],capture_output=True,text=True)
 if r.returncode:raise AssertionError('Fold2 candidate assembler failed:\n'+r.stdout[-5000:]+r.stderr[-3000:])
 if binary.stat().st_size%3:raise AssertionError('candidate binary is not whole DSP words')
 words=binary.stat().st_size//3;overflow=max(0,words-CURRENT_DONOR)
 print(f'Fold2 hidden production composition: PASS ({words} P words; current PERKY4 donor {CURRENT_DONOR}; overflow {overflow})')
 print(f'trigger shadow: X:${s0:04x}..${s1:04x}; measured private-X ceiling ${PRIVATE_X_END:04x}; browser unchanged')
 if overflow:print('P placement remains BLOCKED until the approved stock-effect reclamation supplies this additional program space.')
if __name__=='__main__':main()
