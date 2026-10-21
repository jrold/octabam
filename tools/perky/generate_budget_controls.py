"""Sparse original Hat control codec; native histories never pass this path."""
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def maps():
 result=[]
 for mode in range(3):
  fields={}
  def field(offset,k,width):
   fields[k]=(offset,width,0)
   if width==4:fields[k+1]=(offset,width,1)
  def env(base,k):
   for offset,width in zip((0,1,4,6,7,12,16,32,34),(1,1,1,1,1,4,4,2,2)):
    field(base+offset,k,width);k+=2 if width==4 else 1
  if mode==0:
   field(0xc4+6,1,1);env(0xc4+0x74,2)
   for i in range(6):field(0xc4+0x118+0x34*i+8,15+6*i,4)
  elif mode==1:
   field(0x318+6,81,1);env(0x318+0x74,82)
   field(0x318+0x9c+14,97,2);field(0x318+0xc2,104,1);field(0x318+0xc6,107,2)
  else:
   field(0x2c98+6,0,1);env(0x2c98+0x74,1)
   for i,offset in enumerate((0x11c,0x118,0x120,0x124,0x128,0x12c)):field(0x2c98+offset,40+2*i,4)
   field(0x2c98+0x130,54,4);field(0x2c98+0x138,58,2)
  result.append(fields)
 return result
def generate(work):
 source=(ROOT/'tools/harness/perky_cf/production_handoff_engine.c').read_text()
 keys=[[int(v) for v in re.search(r'nhr_control'+str(i)+r'\[\]=\{([^}]+)',source)[1].split(',')] for i in range(3)]
 text='''/* Generated from the same compact field layout as pk_nha_codec.
 * Only original control fields are copied; filters/phases/envelopes evolve
 * in their original owners. CF-owned full-state imports keep the full codec. */
static uint16_t budget_ctrl_cache[3][121];
static unsigned budget_ctrl_valid[3];
static void pk_budget_cache_clear(void){budget_ctrl_valid[0]=budget_ctrl_valid[1]=budget_ctrl_valid[2]=0;}
static void pk_budget_controls_read(const uint8_t*s,unsigned mode,uint16_t*w){
'''
 for mode,fields in enumerate(maps()):
  env=(2,82,1)[mode];selected=set(keys[mode]+[env,env+7,env+5,env+6])
  text+=(' if' if mode==0 else ' else if')+f'(mode=={mode})'+'{\n'
  for k in sorted(selected):
   offset,width,part=fields[k]
   value=f's[{offset}]' if width==1 else f'pk_cf_ld16(s,{offset+2*part})'
   text+=f'  w[{k}]={value};\n'
  text+=' }\n'
 text+='}\nstatic void pk_budget_controls_write(uint8_t*s,unsigned mode,const uint16_t*w,unsigned trig){\n'
 for mode,fields in enumerate(maps()):
  env=(2,82,1)[mode]
  text+=(' if' if mode==0 else ' else if')+f'(mode=={mode})'+'{\n'
  for k in keys[mode]:
   offset,width,part=fields[k]
   statement=f's[{offset}]=(uint8_t)w[{k}];' if width==1 else f'pk_cf_st16(s,{offset+2*part},w[{k}]);'
   text+='  '+statement+'\n'
  text+='  if(trig){\n'
  for k in (env,env+7):
   offset,width,part=fields[k]
   text+='   '+(f's[{offset}]=(uint8_t)w[{k}];' if width==1 else f'pk_cf_st16(s,{offset+2*part},w[{k}]);')+'\n'
  offset,_,_=fields[env+5]
  text+=f'   if(trig&2)pk_cf_st32(s,{offset},(uint32_t)w[{env+5}]|((uint32_t)w[{env+6}]<<16));\n'
  text+='  }\n }\n'
 text+='}\n'
 path=Path(work)/'budget-controls.h';path.write_text(text);return path
def transform(work,text):
 work=Path(work);header=generate(work)
 text='#include "'+str(header)+'"\n'+text
 old='    pk_nha_codec(t->nh+(mode==2?NH_PULSE:0),mode,w,0);';assert text.count(old)==1
 text=text.replace(old,'    if(apply||trig)pk_budget_controls_read(t->nh,mode,w);')
 marker='    nhr_segment*seg=&nhr_previous->seg[apply!=0];';assert text.count(marker)==1
 text=text.replace(marker,marker+'\n    if(seg->epoch_reset)pk_budget_cache_clear();')
 marker='    if(seg->epoch_reset)pk_budget_cache_clear();'
 text=text.replace(marker,marker+'''
    if(!need&&!apply){
        nhr_put((mode<<5)|(seg->mute<<8));nhr_put((unsigned)seg->mix);nhr_put(0);
        nhb_capture(seg,0,0,0);
        if(nhb_building)nhb_side(nhb_building->half[0].side,t);
        seg->ring_start=nht_ring_index;return;
    }
''')
 old='    for(unsigned i=0;i<count;i++)nhr_patch(mode,keys[i],w[keys[i]]);';assert text.count(old)==1
 text=text.replace(old,'    for(unsigned i=0;i<count;i++)nhr_patch(mode,dirty[i],w[dirty[i]]);')
 marker='    unsigned env=mode==0?2:mode==1?82:1;';assert text.count(marker)==1
 text=text.replace(marker,'''    uint8_t dirty[19];unsigned changed=0;
    for(unsigned i=0;i<count;i++){unsigned k=keys[i];if(!budget_ctrl_valid[mode]||budget_ctrl_cache[mode][k]!=w[k]){dirty[changed++]=k;budget_ctrl_cache[mode][k]=w[k];}}
    if(apply)budget_ctrl_valid[mode]=1;
    count=changed;
'''+marker)
 shadow=work/'full-map-shadow.h';s=shadow.read_text()
 start=s.index('        if(h->apply){',s.index('void pk_nhb_work('));end=s.index('        nhb_raw[0xb8]',start)
 s=s[:start]+'''        if(h->apply)pk_budget_controls_write(nhb_raw,s->mode,h->words,h->trig);
'''+s[end:]
 marker='    unsigned first=s->mode==1?81:0,count=s->mode==0?81:s->mode==1?28:59;'
 start=s.index(marker,s.index('static void nhb_capture('));end=s.index('\n}',start)
 s=s[:start]+'''    if(apply){
        const uint8_t*k=s->mode==0?nhr_control0:s->mode==1?nhr_control1:nhr_control2;
        unsigned count=s->mode==0?sizeof(nhr_control0):s->mode==1?sizeof(nhr_control1):sizeof(nhr_control2);
        for(unsigned i=0;i<count;i++)h->words[k[i]]=w[k[i]];
        unsigned env=s->mode==0?2:s->mode==1?82:1;
        h->words[env]=w[env];h->words[env+7]=w[env+7];
        if(trig&2){h->words[env+5]=w[env+5];h->words[env+6]=w[env+6];}
    }
'''+s[end:]
 marker='    pk_nhb_produced=pk_nhb_completed=0;';assert s.count(marker)==1
 s=s.replace(marker,marker+'pk_budget_cache_clear();')
 # Full-state CF imports also replace DSP control words. The last DSP-owned
 # packet's cache cannot describe those imports when ownership returns.
 marker='        pk_nhb_owner=1;';assert s.count(marker)==1
 s=s.replace(marker,'        pk_budget_cache_clear();\n'+marker)
 shadow.write_text(s)
 return text
