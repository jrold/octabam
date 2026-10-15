| PERKY hybrid: CF-only boot and full frame instrumentation. No DSP changes.
        .include "remix.inc"
        .equ DTCN3, 0xfc07c00c
        .text
        .globl pk_hybrid_isr, pk_hybrid_isr_tail, pk_hybrid_isr_rte
        .globl pk_hybrid_poll1, pk_hybrid_poll2
pk_hybrid_isr:
        move.l %sp,pk_hybrid_irq_region+4160
        lea pk_hybrid_irq_region+4128,%sp
        .globl pk_hybrid_irq_on_private
pk_hybrid_irq_on_private:
        lea -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l DTCN3,%d0
        move.l %d0,pk_hybrid_isr_enter_ticks
        jsr pk_hybrid_frame_begin
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea 16(%sp),%sp
        jmp 0x4000aad0
pk_hybrid_isr_tail:
        jsr pk_hybrid_frame_end
        movem.l (%sp),%d0-%d7/%a0-%a6
        lea 252(%sp),%sp
        .globl pk_hybrid_irq_restore
pk_hybrid_irq_restore:
        move.l pk_hybrid_irq_region+4160,%sp
pk_hybrid_isr_rte:
        rte
| Keep the stock polling result and CCR exactly. These are separate stock
| HC wait sites, not assumed to be independent DSP core completion times.
pk_hybrid_poll1:
        lea -12(%sp),%sp
        movem.l %d0-%d1,(%sp)
        move.l DTCN3,%d1
1:      move.w 0x20000004,%d0
        tst.b %d0
        blt.s 1b
        movem.l %d0,(%sp)
        move.w %sr,%d0
        move.w %d0,8(%sp)
        move.l DTCN3,%d0
        sub.l %d1,%d0
        add.l %d0,pk_hybrid_wait_ticks
        move.w 8(%sp),%d0
        move.w %d0,%sr
        movem.l (%sp),%d0-%d1
        lea 12(%sp),%sp
        jmp 0x4000ab30
pk_hybrid_poll2:
        lea -12(%sp),%sp
        movem.l %d0-%d1,(%sp)
        move.l DTCN3,%d1
1:      move.w 0x20000004,%d0
        tst.b %d0
        blt.s 1b
        movem.l %d0,(%sp)
        move.w %sr,%d0
        move.w %d0,8(%sp)
        move.l DTCN3,%d0
        sub.l %d1,%d0
        add.l %d0,pk_hybrid_wait_ticks+4
        move.w 8(%sp),%d0
        move.w %d0,%sr
        movem.l (%sp),%d0-%d1
        lea 12(%sp),%sp
        jmp 0x4000a916
