"""Shared-only A service. Restore both stock FX donors and the B source path."""
import json
from pathlib import Path
import perky_full_map as F
import perky_noise_hat_offload as N
import ab_records as A
import perky_image as P
ROOT=Path(__file__).resolve().parents[2]
BASE_PROGRAM=F.build_program
MATH=0x37da3;CLEAR_A=0x37f10;CLEAR_B=0x37f40;GUARD=0x3fffa

def clear(tag,at):
 half=(0x30000,0x38000) if tag=='A' else (0x37f00,0x40000)
 protected=[(a,b) for a,b in N.L.SAFE_SHARED_P_SPANS if half[0]<=a<b<=half[1]]
 cursor=half[0];ranges=[(0x4000 if tag=='A' else 0x3f00,0xc000)]
 for lo,hi in protected:
  if cursor<lo:ranges.append((cursor,lo))
  cursor=hi
 if cursor<half[1]:ranges.append((cursor,half[1]))
 text='fm_boot_clear:\n clr a\n'
 for i,(lo,hi) in enumerate(ranges):text+=f' move #>${lo:x},r5\n move #>${hi-lo:x},b\n do b,fm_clear_end_{i}\n move a,y:(r5)+\nfm_clear_end_{i}:\n nop\n'
 text+=f' move #>$c000,r4\n move #>${half[1]:x},r5\n move #>${0x8000 if tag=="A" else 0x8100:x},b\n rts\n'
 words,_=N.B.assemble_syms(text,at,'full_fx_clear_'+tag,strict_layout=True);assert len(words)<=48
 return words+[0]*(48-len(words)),text

def build_program(work,asm):
 global READY
 work.mkdir(parents=True,exist_ok=True)
 emit=N.S.emit;plan=N.S.plan;local=N.L.local_p_spans
 original=emit(asm,'B');pieces,whole,dest,_,syms=original;dest=dict(dest);dest['noise_tone_math.asm']=MATH
 def final(addr):
  for name,a,b,_,_ in pieces:
   if a<=addr<b:return dest[name]+addr-a
  return addr
 math=next(p for p in pieces if p[0]=='noise_tone_math.asm')
 words,_=N.B.assemble_syms(N.E.rewrite(math[3],syms,final),MATH,'full_fx_math',strict_layout=True)
 assert len(words)==math[2]-math[1]
 records=[(MATH,words)];ledger=[dict(name='original shared RNG/math helper',start=MATH,length=len(words))]
 for tag,at in (('A',CLEAR_A),('B',CLEAR_B)):
  words,text=clear(tag,at);records.append((at,words));ledger.append(dict(name='stock startup clear '+tag,start=at,length=len(words)));(work/('clear-'+tag+'.asm')).write_text(text)
 records.append((GUARD,[0]*6));ledger.append(dict(name='shared prefetch guard',start=GUARD,length=6))
 N.S.emit=lambda asm,tag:(pieces,whole,dest,final,syms)
 N.S.plan=lambda asm,tag:(records,ledger,0)
 N.L.local_p_spans=lambda tag:() if tag=='A' else local(tag)
 try:
  result=BASE_PROGRAM(work,asm);READY=True;return result
 finally:N.S.emit=emit;N.S.plan=plan;N.L.local_p_spans=local

def restored_upload(extend,img,tag,y,x=None,extra=None,extra_y=None,p_records=None):
 if not READY:return extend(img,tag,y,x,extra,extra_y,p_records)
 pristine=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes();stock_records,_=A.records(pristine,*P.PAY[tag]['payload']);current,_=A.records(img,*P.PAY[tag]['payload']);image=bytearray(img)
 for space,at,n,off in stock_records:
  for i in range(n):A.wr(image,A.word_at(current,space,at+i),A.rd(pristine,off+3*i))
 def word(at,value):A.wr(image,A.word_at(current,0,at),value)
 end=0x4a if tag=='A' else 0x4b
 for at,value in zip(range(0x40,end),[0x0bf080,CLEAR_A if tag=='A' else CLEAR_B]+[0]*(end-0x42)):word(at,value)
 if tag=='A':
  symbols=json.loads((ACTIVE_WORK/'program/resident-symbols.json').read_text());word(0x39c,0x0bf080);word(0x39d,symbols['source_entry']);word(0x53e,0x0bf080);word(0x53f,symbols['embed_entry'])
 else:x=None;extra=None;extra_y=None
 return extend(image,tag,y,x,extra,extra_y,p_records)

ACTIVE_WORK=None
READY=False
