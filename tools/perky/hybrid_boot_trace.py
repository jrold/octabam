"""Boot-only, bounded MIDI breadcrumbs for the PERKY hybrid loader.

No RT/audio hooks are added. All original early-loader registers are restored;
if MIDI UART0 is not ready, each byte is skipped after a finite poll budget.

Boot MIDI CC119 values (channel 1; no stuck Note Ons):
  40 hybrid loader entered
  41 preboot DSP payload started (once per payload)
  42 stock DSP continuation entered
  43 stock DSP continuation returned
  44 packed ColdFire runtime copy/decode started
  45 ColdFire runtime loaded, C boot initializer entered
  46 C boot initializer returned with success
  79 loader integrity/init failure (fatal stop)

This trace starts at the hybrid loader. No notes at all suggests an earlier
stage or an unavailable UART; it does not prove an earlier-stage failure.
"""

# Based on the bounded UART0 sender already used by modules/boot-trace/trace.s.
# Crucially, unlike the old helper, a failed TXRDY poll does not emit a byte.
TRACE_ASM = '''
| Hybrid startup MIDI trace; no audio-IRQ cost, no unbounded UART wait.
hybrid_boot_trace:
        lea     (-16,%sp),%sp
        movem.l %d0-%d3,(%sp)
        move.l  %d0,%d3
        move.l  #0xb0,%d1
        bsr.s   hybrid_boot_tx
        moveq   #119,%d1
        bsr.s   hybrid_boot_tx
        move.l  %d3,%d1
        bsr.s   hybrid_boot_tx
        movem.l (%sp),%d0-%d3
        lea     (16,%sp),%sp
        rts
hybrid_boot_tx:
        move.l  #200000,%d2
1:      move.b  (0xfc060004).l,%d0
        btst    #2,%d0
        bne.s   2f
        subq.l  #1,%d2
        bne.s   1b
        rts
2:      move.b  %d1,(0xfc06000c).l
        rts
'''


def _replace_once(source: str, original: str, replacement: str) -> str:
    if source.count(original) != 1:
        raise ValueError(f'hybrid cold-boot loader anchor missing/ambiguous: {original!r}')
    return source.replace(original, replacement, 1)


def _note(number: int) -> str:
    assert 0 < number < 128
    return (f'        move.l  %d0,-(%sp)\n'
            f'        moveq   #{number},%d0\n'
            f'        bsr.w   hybrid_boot_trace\n'
            f'        move.l  (%sp)+,%d0\n')


def instrument_loader(source: str, boot_init: int) -> str:
    """Apply boot markers while retaining the original DSP-preboot/depack flow.

    The exact boot-init insertion this replaces is intentionally owned here:
    failure cannot silently bypass the boot initializer or the integrity stop.
    """
    assert 0x40000000 <= boot_init <= 0x4fffffff, hex(boot_init)
    source = _replace_once(source, 'octabam_bootstrap:\n',
                           'octabam_bootstrap:\n' + _note(40))
    source = _replace_once(source, 'pnext:\n', 'pnext:\n' + _note(41))
    source = _replace_once(source, '        jsr     (BOOT_CONTINUE).l\n',
                           _note(42) + '        jsr     (BOOT_CONTINUE).l\n' + _note(43))
    source = _replace_once(source, '\nnext:\n', '\nnext:\n' + _note(44))
    anchor = 'done:\n        movem.l (%sp),%d0-%d7/%a0-%a2'
    init = (f'done:\n' + _note(45)
            + f'        jsr     (0x{boot_init:08x}).l\n'
            + '        tst.l   %d0\n        beq.w   fatal\n'
            + _note(46) + '        movem.l (%sp),%d0-%d7/%a0-%a2')
    source = _replace_once(source, anchor, init)
    source = _replace_once(source, 'fatal:\n        bra.w   fatal\n',
                           'fatal:\n' + _note(79)
                           + 'hybrid_boot_fatal_stop:\n        bra.w   hybrid_boot_fatal_stop\n')
    source = _replace_once(source, '        .include "early.inc"\n',
                           TRACE_ASM + '\n        .include "early.inc"\n')
    return source
