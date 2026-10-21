"""Isolated guarded fusion of stock scratch reduction and envelope passes.

The source pairs remain ahead of the compacted envelope output. The original
recurrence and all final scratch words are retained. Unproven counts and an
envelope field that aliases the conservative scratch window use stock code.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 0x40000400
SITE = dict(name='background_envelope', address=0x400984d2,
            end=0x400984de, continuation=0x40098534,
            sha256='9964a4961b3a3c409e0e210858e6dfe791b2cd08fe4c22375551bc1f7d4386bc')


def expected_span(site=SITE):
    data = (ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()[site['address']-BASE:site['end']-BASE]
    assert hashlib.sha256(data).hexdigest() == site['sha256'], 'stock envelope entry drift'
    return data


def generate(work):
    expected_span()
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    path = work/'stock-envelope-fusion.s'
    path.write_text('''/* Pairwise maxima feed the unchanged EMAC recurrence directly.
 * No stack use, scratch registers or additional state. All registers,
 * complete CCR and raw EMAC state match at the original continuation. */
.text
.balign 2
.globl pk_stock_envelope_fusion
.type pk_stock_envelope_fusion,@function
pk_stock_envelope_fusion:
 move.l 48(%sp),%d7
 tst.l %d7
 ble .Lenvelope_fallback
 cmp.l #768,%d7
 bhi .Lenvelope_fallback
 lea 44(%a2),%a0
 cmpa.l #0x8000695c,%a0
 bcs .Lenvelope_safe
 cmpa.l #0x8000796c,%a0
 bcs .Lenvelope_fallback
.Lenvelope_safe:
 movea.l #0x8000696c,%a0
 movea.l #0x80006968,%a1
 move.l #0x7ffffffe,%d4
 move.l #0x0020c281,%d5
 move.l 44(%a2),%d1
 move.l %d1,%acc0
.Lenvelope_pair:
 move.l (%a0)+,%d0
 cmp.l (%a0)+,%d0
 bge .Lenvelope_maximum
 move.l -4(%a0),%d0
.Lenvelope_maximum:
 move.l %d4,%d2
 move.l %acc0,%d1
 cmp.l %d1,%d0
 bge .Lenvelope_coefficient
 move.l %d5,%d2
.Lenvelope_coefficient:
 mac.l %d2,%d0,%acc0
 msac.l %d2,%d1,%acc0
 move.l %d1,(%a1)+
 subq.l #2,%d7
 bgt .Lenvelope_pair
 /* Stock's last parallel load reads this unused raw word. Read it before
  * the final compacted result, preserving both its value and its address. */
 move.l 4(%a1),%d0
 move.l %acc0,%d1
 move.l %d1,(%a1)+
 move.l %d1,44(%a2)
 lea 4(%a1),%a0
 jmp 0x40098534
.Lenvelope_fallback:
 movea.l #0x8000696c,%a0
 movea.l #0x8000696c,%a1
 jmp 0x400984de
.size pk_stock_envelope_fusion,.-pk_stock_envelope_fusion
''')
    return dict(path=str(path), sites=[dict(SITE, entry='pk_stock_envelope_fusion', pad_to=12)],
                guard='1<=count<=768 and object+44 outside [scratch-16,scratch+4096)',
                fallback='Unmodified stock reduction and EMAC passes',
                preserved='Full scratch memory, all D/A registers, full CCR and raw EMAC; no stack use')
