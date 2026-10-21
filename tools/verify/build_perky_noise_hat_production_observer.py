#!/usr/bin/env python3
"""Independent original-initializer witness for the production integration."""
import hashlib,json
from pathlib import Path
import build_perky_noise_hat_handoff_observer as h
ROOT=h.ROOT;WORK=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(profile=False):
 h.WORK=WORK;original=h.b.build
 def build():
  p=h.b.HEADER;text=p.read_text();extension=ROOT/'tools/harness/perky_cf/noise_hat_handoff_observer.h'
  marker='#include "'+str(extension)+'"';assert text.count(marker)==1
  production=ROOT/'tools/harness/perky_cf/production_lifecycle_observer.h'
  extension=production.read_text().replace('#include "cf_synthesis_observer.h"','#include "'+str(ROOT/'tools/harness/perky_cf/cf_synthesis_observer.h')+'"')
  if profile:
   extension=extension.replace('namespace noise_hat_exact {','namespace nhb_profile_base {').replace('inline Observer observer;','')
   extension+='\n#include "'+str(ROOT/'tools/harness/perky_cf/production_reset_profile.h')+'"'
   text='#include "'+str(h.b.base.BASE/'observer.h')+'"\n'+text
  text=text.replace(marker,extension)
  p.write_text(text);original()
 h.b.build=build
 oracle=ROOT/'tools/harness/perky_cf/production_stream_oracle.c'
 run=h.subprocess.run
 def substitute(cmd,*a,**kw):
  cmd=[str(oracle) if str(x)==str(ROOT/'tools/harness/perky_cf/noise_hat_handoff_oracle.c') else x for x in cmd]
  return run(cmd,*a,**kw)
 h.subprocess.run=substitute
 try:h.build()
 finally:h.b.build=original;h.subprocess.run=run
 p=WORK/'observer/OBSERVER_BUILD.json';r=json.loads(p.read_text());r['cycle_profile_enabled']=profile;
 if profile:r['source_sha256']['tools/harness/perky_cf/production_reset_profile.h']=sha(ROOT/'tools/harness/perky_cf/production_reset_profile.h')
 r['source_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__).resolve(),ROOT/'tools/harness/perky_cf/production_lifecycle_observer.h',oracle)})
 p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
