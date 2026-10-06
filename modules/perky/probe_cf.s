| PERKY milestone-0 ColdFire probe writer.
|
| This is intentionally tiny and handwritten so the transport/DSP canary does
| not depend on regenerating the full control.c runtime.  In the isolated
| perky-probe remix it temporarily replaces FLEX's source renderer.  It keeps
| FLEX's record-span accounting exactly like the measured Analog BD renderer,
| but writes only the four longs the DSP canary needs:
|
|   CF long 0: 0x504b0000   -> DSP words: $504b ('PK'), $0000
|   CF long 1: 0x59310000|t -> DSP words: $5931 ('Y1'), $000t
|   CF long 2: 0
|   CF long 3: 0
|
| `t` is one only when the stock per-track trigger byte has bit 4 set.  The
| DSP hook reads the stock event offset from X:$20c, so the CF side does not
| invent timing.
|
| ABI: stock FLEX renderer pointer at 0x400d6438 is
|     int render(unsigned track, unsigned ping, unsigned start, unsigned end)
| with d0/d1/a0/a1 caller-saved under the firmware's m68k ABI.
|
| DEVELOPMENT ONLY: every FLEX track in the perky-probe remix becomes an
| impulse source.  The real PERKY machine will gate this writer on its PK/1
| Part signature once the complete generated control runtime is linked.

        .text
        .align  2
        .global pk_probe_render
        .type   pk_probe_render,@function

        .equ    CURSOR_PTR, 0x80001c80
        .equ    RECORD_BASE, 0x80001c90
        .equ    PING_STRIDE, 0x0a80
        .equ    TRACK_STRIDE, 336
        .equ    TRIG_BASE, 0x46104d0c

pk_probe_render:
        | n = (end > start && end <= 16) ? end-start : 0
        move.l  16(%sp),%d0
        cmpi.l  #16,%d0
        bhi.s   .count_zero
        move.l  12(%sp),%d1
        cmp.l   %d1,%d0
        bls.s   .count_zero
        sub.l   %d1,%d0
        bra.s   .count_ready
.count_zero:
        clr.l   %d0
.count_ready:

        | Reserve/clear exactly 4 + 2*n longs, as FLEX/Analog BD do.  The
        | global cursor is advanced even on the first half-render, preserving
        | every later track's fixed record boundary.
        movea.l (CURSOR_PTR).l,%a0
        movea.l %a0,%a1
        add.l   %d0,%d0
        addq.l  #4,%d0
.clear_record:
        clr.l   (%a1)+
        subq.l  #1,%d0
        bne.s   .clear_record
        move.l  %a1,(CURSOR_PTR).l

        | Only the second half-render publishes the fixed per-track record.
        move.l  16(%sp),%d0
        cmpi.l  #16,%d0
        bne.s   .done

        | record = BASE + (ping&1)*0xa80 + 336*track
        move.l  8(%sp),%d0
        andi.l  #1,%d0
        mulu.w  #PING_STRIDE,%d0
        move.l  4(%sp),%d1
        mulu.w  #TRACK_STRIDE,%d1
        add.l   %d1,%d0
        add.l   #RECORD_BASE,%d0
        movea.l %d0,%a1

        move.l  #0x504b0000,(%a1)
        move.l  #0x59310000,%d1

        | C reference: (U8(0x46104d0c + track) & 16) != 0.
        move.l  4(%sp),%d0
        add.l   #TRIG_BASE,%d0
        movea.l %d0,%a0
        moveq   #0,%d0
        move.b  (%a0),%d0
        andi.l  #16,%d0
        beq.s   .no_trig
        ori.l   #1,%d1
.no_trig:
        move.l  %d1,4(%a1)
        clr.l   8(%a1)
        clr.l   12(%a1)

.done:
        clr.l   %d0
        rts

        .size   pk_probe_render,.-pk_probe_render
