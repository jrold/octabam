; PERKY Simple Drum v1.2.1 oscillator-frequency converter.
;
; Native ARM semantics:
;   shifted = signed32(frequency << 20)
;   high    = high32(shifted * 0x057619f1)
;   result  = (high >> 10) - (shifted >> 31)
;
; Since frequency<<20 preserves only frequency bits 0..11, let
;   z = sign_extend_12(frequency & $fff).
; For every nonzero z in [-2048,2047], the native expression is exactly
; truncation toward zero of:
;   z * $057619f1 / 2^22
; = 21*z + z*$3619f1/2^22.
;
; Both z and $3619f1 fit the DSP56300 signed 24-bit multiplier. MPY is
; fractionally aligned (product << 1), so ASR #23 produces floor(product/2^22).
; Negative nonzero products need +1 to convert arithmetic-floor to truncation
; toward zero. The final result is bounded to [-44739,44717] and fits signed24.
;
; Standalone executable-probe ABI:
;   n7             number of samples this call (bd909_host supplies 16)
;   X:(r5+$40)     persistent input index, initially 0
;   Y:$1000..$1fff 4096 input frequencies, one per DSP word
;   output          signed result duplicated stereo at X:(r0)+
;
; The shipping renderer will call pk_simple_frequency with x0=input and consume
; signed24 A1. The probe entry merely loops over the exhaustive input table.

pk_simple_frequency_probe:
        do      n7,pksf_probe_done
        move    x:(r5+$40),a
        move    a1,n1
        move    #>$001000,r1
        move    y:(r1+n1),x0
        jsr     pk_simple_frequency
        move    a1,x:(r0)+
        move    a1,x:(r0)+
        move    x:(r5+$40),a
        add     #>$1,a
        move    a1,x:(r5+$40)
pksf_probe_done:
        nop
        rts

; input  x0 = frequency (only low 12 bits are significant)
; output A1 = exact signed native oscillator increment
pk_simple_frequency:
        ; z = sign_extend_12(x0 & $fff).
        move    x0,a
        and     #>$000fff,a
        btst    #11,a1
        bcc     pksf_z_ready
        sub     #>$001000,a
pksf_z_ready:
        move    a1,x1                   ; x1 = signed z

        ; integer part = 21*z = (16 + 4 + 1)*z; keep it in scratch y1.
        move    x1,b
        asl     #$4,b,b
        move    b1,y1                   ; 16*z
        move    x1,b
        asl     #$2,b,b                 ; 4*z
        add     y1,b
        add     x1,b
        move    b1,y1                   ; y1 = 21*z

        ; fractional part = trunc0(z * $3619f1 / 2^22).
        move    x1,x0
        move    #>$3619f1,y0
        mpysu   x0,y0,a
        asr     #$17,a,a                ; product<<1 / 2^23 = floor(product/2^22)
        move    a0,a

        ; Signed ASR floors negative non-integral values. No nonzero z in this
        ; 12-bit domain makes z*$3619f1 divisible by 2^22 (constant is odd),
        ; so add one exactly when z < 0 to obtain truncation toward zero.
        move    x1,b
        tst     b
        bpl     pksf_fraction_ready
        add     #>$1,a
pksf_fraction_ready:
        add     y1,a
        rts
