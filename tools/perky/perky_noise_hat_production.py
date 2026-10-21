"""Production epoch reset, resident on A; no additional transport words."""
import perky_noise_hat_handoff as H
RESET_TABLE=0x3a34
_build_program=H.build_program

def service():
 p=H.service();regs=H.REGISTERS;saved=H.SAVED
 oldsave=''.join(f' move {r},x:>${saved+i:x}\n' for i,r in enumerate(regs))
 oldrestore=''.join(f' move x:>${saved+i:x},{r}\n' for i,r in reversed(list(enumerate(regs))))
 # Preserve address and modulo before using a linear private-memory cursor.
 save=''.join(f' move {r},x:>${saved+regs.index(r):x}\n' for r in ('r1','m1'))
 save+=f' move #>$ffffff,m1\n move #>${saved:x},r1\n'
 save+=''.join(' move (r1)+\n' if r in ('r1','m1') else f' move {r},x:(r1)+\n' for r in regs)
 restore=f' move #>${saved+len(regs)-1:x},r1\n'
 restore+=''.join(' move (r1)-\n' if r in ('r1','m1') else f' move x:(r1)-,{r}\n' for r in reversed(regs))
 restore+=''.join(f' move x:>${saved+regs.index(r):x},{r}\n' for r in ('m1','r1'))
 for name in ('frame','embed'):
  assert p[name].count(oldsave)==p[name].count(oldrestore)==1
  p[name]=p[name].replace(oldsave,save).replace(oldrestore,restore)
 marker=' move x:(r4)+,a\n and #>$ffff,a\n move a1,a\n move a1,x:>$39bc\n'
 assert p['segment'].count(marker)==1
 p['segment']=p['segment'].replace(marker,''' move x:>$39b9,a
 jclr #9,a1,nhg_keep_epoch
 jsrl nhg_epoch_reset
nhg_keep_epoch:
'''+marker)
 p['epoch_reset']='''nhg_epoch_reset:
 move #>$3800,r1
 clr a
 do #>180,nhg_zero_done
 move a1,x:(r1)+
nhg_zero_done:
 nop
 move #>$3970,r1
 do #>6,nhg_side_done
 move a1,x:(r1)+
nhg_side_done:
 nop
 move #>1,a
 move a1,x:>$3972
 move #>$3a34,r1
 do #>47,nhg_values_done
 move x:(r1)+,b
 move b1,a
 lsr #>16,a
 add #>$3800,a
 move a1,r2
 and #>$ffff,b
 move b1,b
 move b1,x:(r2)
nhg_values_done:
 nop
 rts
'''
 return p

def build_program(work,asm):
 original=H.service;H.service=service
 # H.build_program resolves service in its module; retain the original here.
 global _base_service
 _base_service=original
 try:return _build_program(work,asm)
 finally:H.service=original
# service must call the captured original even while H.service is replaced.
_base_service=H.service
_service=service
def service():
 original=H.service;H.service=_base_service
 try:return _service()
 finally:H.service=original
