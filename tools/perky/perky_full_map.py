"""Mixed current-frame CF PCM and resident Hat segments on DSP-A.

The ordinary stock source DMA carries both kinds of segment. No additional
transfer, wait or source latency; CF and DSP keep the original shared RNG.
"""
import perky_noise_hat_production as G
import perky_noise_hat_handoff as H
_build_program=H.build_program

def service():
 p=G.service()
 marker=' move x:>$39b9,a\n jclr #7,a1,nht_no_reset\n'
 assert p['segment'].count(marker)==1
 p['segment']=p['segment'].replace(marker,''' move x:>$39b9,a
 jset #10,a1,fm_pcm_segment
'''+marker)
 p['external']='''fm_pcm_segment:
 move x:>$3a26,a
 asl a
 move a1,r0
 move x:>$39bb,b
 tst b
 beq fm_pcm_done
 move x:>$39b2,r4
 do b,fm_pcm_loop
 move x:(r4)+,a
 and #>$ff,a
 lsl #>16,a
 move a1,x0
 move x:(r4)+,a
 and #>$ffff,a
 or x0,a
 move a1,a
 move a1,x:(r0)+
 move a1,x:(r0)+
fm_pcm_loop:
 nop
 move r4,x:>$39b2
fm_pcm_done:
 move x:>$3a26,a
 move x:>$39bb,x0
 add x0,a
 move a1,x:>$3a26
 rts
'''
 return p

def build_program(work,asm):
 original=H.service;H.service=service
 # H's builder resolves its service at run time. G.service temporarily
 # restores its captured base, so no recursive generator substitution.
 try:return _build_program(work,asm)
 finally:H.service=original
