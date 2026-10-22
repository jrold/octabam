"""pk_render, the per-chunk source dispatcher, in assembly (modules/perky/cf_render.s).

The C dispatcher (pk_hybrid_render, exported as pk_render) is pinned here by
the SHA-256 of its text, so the assembly can only replace the body it was
written against. It becomes pk_render_c. The assembly takes a chunk when the
track is a placed PĒRKONS voice (tracks 1, 2, 5, 6) with a signed project
slot, its placement bit set and valid bounds, and from there makes the same
calls with the same arguments in the same order: placement_production_observe,
fm_voice_engine, placement_boundary_noop, placement_segment, placement_prepare,
pk_prod_clear, pk_prod_pack or pk_nhr_frame. Every other chunk jumps, stack
untouched, to pk_render_c. The decision reads only memory; nothing is written
before it.

The dispatcher's file-scope statics and the project ABI constants are exported
from the control unit as symbols, so the assembly hard-codes neither.
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = (('pkrenderasm', ROOT / 'modules/perky/cf_render.s'),)

ANCHOR = 'int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)\n    __asm__("pk_render");'
BODY_SHA256 = '07e78d3d498d7fdc21cc1f290c2f3e66c881f7aee2962d80efeac0e552b912f1'
# The helpers the assembly inlines, pinned the same way: (file, first line, sha256).
HELPERS = (
    ('abi', 'static unsigned signed_track(const volatile uint8_t *part, unsigned track)\n',
     'e063d096c576a5a5f4948826434b0c27cb20bac797d897dc6b57da71ae8bbf92'),
    ('abi', 'static volatile uint8_t *part_base(void)\n',
     'de223dbb9f4ba500c2b666e7b3722c18bedc903cbc466170c7fcd1abf3c65e77'),
    ('unit', 'static void pk_hybrid_observe_generation(void)\n',
     'cb5d206a49d422195e484ad1af21c13012416b4a6e73ccaea50a3c83b7352428'),
    ('unit', 'static volatile uint32_t *pk_hybrid_fixed_slot(unsigned track, unsigned ping)\n',
     '4f9ea65b4eb94b91d2a67cbe9cda6da7bcad493c87afca601b5c541b8b958800'),
    ('unit', 'static inline uint32_t pk_hybrid_timer_now(void)\n',
     '609d21023650dec2e0d768862006c449e248b3837b9932fb6673bbdc8e995904'),
    ('unit', '#define PK_HYB_DTCN3 ',
     '5e6cebd59af03ce99d6f8fd63600acce5eb30663edde26e6e35209319dc84dad'),
)

EXPORTS = r'''
/* PKFM30: statics and constants for modules/perky/cf_render.s. */
#define PK_R_SYM(name,operand) ".globl " #name "\n.set " #name ", %c" #operand "\n"
__attribute__((used)) static void pk_render_export_layout(void)
{
    __asm__ volatile(
        PK_R_SYM(pk_r_trigger,0) PK_R_SYM(pk_r_bank,1) PK_R_SYM(pk_r_part,2) PK_R_SYM(pk_r_generation,3)
        PK_R_SYM(pk_r_prof_handoff,4) PK_R_SYM(pk_r_cf_ticks,5) PK_R_SYM(pk_r_voice_mask,6)
        ::"i"(placement_trigger),"i"(&pk_hybrid_bank),"i"(&pk_hybrid_part),"i"(&pk_hybrid_generation),
          "i"(&pk_hybrid_prof.handoff_generation),"i"(&pk_hybrid_cur_cf_ticks),"i"(&pk_hybrid_cur_voice_mask));
    __asm__ volatile(
        PK_R_SYM(PK_R_BANK,0) PK_R_SYM(PK_R_PART_IDX,1) PK_R_SYM(PK_R_PART_OFF,2) PK_R_SYM(PK_R_PART_STRIDE,3)
        PK_R_SYM(PK_R_SIG,4) PK_R_SYM(PK_R_TUNE,5) PK_R_SYM(PK_R_DECAY,6) PK_R_SYM(PK_R_ALGO,7)
        PK_R_SYM(PK_R_PARAM1,8) PK_R_SYM(PK_R_PARAM2,9)
        ::"i"(BANK),"i"(PART_IDX),"i"(PART_OFF),"i"(PART_STRIDE),"i"(SIG),"i"(2u*TUNE_SLOT),"i"(2u*DECAY_SLOT),
          "i"(2u*ALGO_SLOT),"i"(2u*PARAM1_SLOT),"i"(2u*PARAM2_SLOT));
    __asm__ volatile(
        PK_R_SYM(PK_R_MODE,0) PK_R_SYM(PK_R_SLOT_BASE,1) PK_R_SYM(PK_R_PING_BYTES,2) PK_R_SYM(PK_R_SLOT_BYTES,3)
        ::"i"(2u*MODE_SLOT_FINAL),"i"(PK_HYB_SLOT_BASE),"i"(PK_HYB_PING_BYTES),"i"(PK_HYB_SLOT_BYTES));
}
'''


def pinned(text, head):
    assert text.count(head) == 1, ('helper anchor changed', head)
    start = text.index(head)
    end = text.index('\n', start) + 1 if head.startswith('#define') else text.index('\n}\n', start) + 3
    return hashlib.sha256(text[start:end].encode()).hexdigest()


def transform(work, source_path):
    text = Path(source_path).read_text()
    assert text.count(ANCHOR) == 1, 'pk_render anchor changed'
    abi = Path(re.search(r'#include "([^"]*project-abi/)control_four_candidate\.c"', text).group(1)) / 'control.c'
    files = dict(unit=text, abi=abi.read_text())
    for where, head, digest in HELPERS:
        assert pinned(files[where], head) == digest, ('inlined helper changed; re-derive cf_render.s', head)
    body = text[text.index(ANCHOR):]
    assert hashlib.sha256(body.encode()).hexdigest() == BODY_SHA256, \
        'pk_render C body changed; re-derive modules/perky/cf_render.s'
    text = text.replace(ANCHOR, ANCHOR.replace('__asm__("pk_render")', '__asm__("pk_render_c")'), 1)
    text = text.rstrip('\n') + '\n' + EXPORTS
    target = Path(work) / 'control-render-asm.c'
    target.write_text(text)
    return target
