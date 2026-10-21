#!/usr/bin/env python3
"""Exhaustive reciprocal and complete source-clock equivalence gate."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'out/perky/hybrid/noise-hat-handoff'
sys.path.insert(0,str(ROOT/'tools/perky'))
import generate_noise_hat_handoff_clock as generator
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 table=W/'noise-hat-clock-table.h';mapping=generator.generate(table)
 source=W/'resample-gate.c'
 source.write_text('''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "cf_native_clock.h"
static uint32_t original_needed(const pk_cf_native_clock*c,uint32_t n){return pk_cf_native_needed(c,n);}
static void original_convert(pk_cf_native_clock*c,const int16_t*d,uint32_t n,int32_t*out){pk_cf_native_convert(c,d,n,out);}
#define NHB_CLOCK_TABLE "'''+str(table)+'''"
#include "noise_hat_handoff_resample.h"
static uint32_t rng=0x93ab2e71;static uint32_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int main(void){
 for(uint32_t n=0;n<=306179666u;n++)if(pk_nhb_div147(n)!=n/147u)return 1;
 for(unsigned i=0;i<100000;i++){uint32_t n=next();if(pk_nhb_div147(n)!=n/147u)return 2;}
 uint32_t frames=0;
 for(unsigned phase=0;phase<147;phase++)for(unsigned have=0;have<2;have++)for(unsigned n=0;n<=16;n++)for(unsigned kind=0;kind<16;kind++){
  int16_t data[20];int32_t a[16],b[16];for(unsigned k=0;k<20;k++)data[k]=kind==0?-32768:kind==1?32767:kind==2?(k&1?-32768:32767):(int16_t)next();
  pk_cf_native_clock old={phase,have,(int16_t)next()},now=old;
  if(original_needed(&old,n)!=pk_nhb_native_needed(&now,n))return 3;
  original_convert(&old,data,n,a);pk_nhb_native_convert(&now,data,n,b);
  if(memcmp(a,b,4*n)||memcmp(&old,&now,sizeof(old)))return 4;frames++;
 }
 pk_cf_native_clock old={0},now={0};
 for(unsigned i=0;i<65536;i++){
  if((i&31)==0){pk_cf_native_reset(&old);pk_cf_native_reset(&now);}
  unsigned n=1+next()%16,need=original_needed(&old,n);int16_t data[20];int32_t a[16],b[16];
  if(need!=pk_nhb_native_needed(&now,n))return 5;
  for(unsigned k=0;k<20;k++)data[k]=(int16_t)next();if(old.have)data[0]=(int16_t)old.carry;
  original_convert(&old,data,n,a);pk_nhb_native_convert(&now,data,n,b);
  if(memcmp(a,b,4*n)||memcmp(&old,&now,sizeof(old)))return 6;frames++;
 }
 printf("%u\\n",frames);return 0;}
''')
 exe=W/'resample-gate';cmd=['cc','-O3','-std=c11','-I'+str(ROOT/'modules/perky'),str(source),'-o',str(exe)]
 subprocess.run(cmd,check=True);frames=int(subprocess.check_output([str(exe)],text=True));assert frames==145504
 report=dict(status='PASS_EXHAUSTIVE_AUDIO_DIVISION_AND_ORIGINAL_SOURCE_CLOCK',division_cases=generator.MAX_AUDIO_DIVIDEND+1+100000,source_clock_frames=frames,table=mapping,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/perky/generate_noise_hat_handoff_clock.py',ROOT/'modules/perky/noise_hat_handoff_resample.h',ROOT/'modules/perky/cf_native_clock.h')},table_sha256=sha(table),executable_sha256=sha(exe),commands=[cmd])
 (W/'RESAMPLE_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
