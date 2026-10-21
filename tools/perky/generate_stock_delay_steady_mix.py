"""Exact stock DELAY mixer specialization for four zero ramp increments.

The original entry assigns its fixed16-sample count. Every memory and EMAC
operation remains ordered identically. Only additions of known zero and inner
counter updates are removed; all other increments retain the stock loop.
"""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=0x40000400
SITE=dict(name='stock_delay_steady_mix',address=0x40003734,end=0x40003740,
          continuation=0x4000377a,sha256='6d11c1a055cdbcb901c3df7e72400d3a16d197c51c62dae7597dd6cf29f994a5')
BLOCK_SHA256='85f0ddde1e0dd2b27983d4c804e8576dccbdbbb7bc0b011b7a1c56e412669908'


def expected_span(site=SITE):
    data=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    block=data[site['address']-BASE:site['continuation']-BASE]
    assert hashlib.sha256(block).hexdigest()==BLOCK_SHA256,'stock DELAY mixer drift'
    span=data[site['address']-BASE:site['end']-BASE]
    assert hashlib.sha256(span).hexdigest()==site['sha256'],'stock DELAY mixer entry drift'
    return span


def generate(work):
    expected_span();work=Path(work);work.mkdir(parents=True,exist_ok=True)
    stock=str(ROOT/'out/raw/section_3_MAIN_OS.bin')
    def include(a,e):return f' .incbin "{stock}",{a-BASE},{e-a}\n'
    body=''.join(include(a,e)for a,e in ((0x40003738,0x4000375c),(0x4000375e,0x40003768),
                                      (0x4000376a,0x4000376e),(0x40003770,0x40003774)))
    text='''/* Retain original source preload and fixed count, then specialize
 * only the mathematically unchanged zero ramp additions. No stack use. */
.text
.balign 2
.globl pk_stock_delay_steady_mix
.type pk_stock_delay_steady_mix,@function
pk_stock_delay_steady_mix:
 move.l (%a1)+,%d0
 moveq #16,%d2
 tst.l %d4
 bne .Ldelay_original_loop
 tst.l %d5
 bne .Ldelay_original_loop
 tst.l %d6
 bne .Ldelay_original_loop
 tst.l %d7
 bne .Ldelay_original_loop
'''
    text+=body*16
    text+=''' sub.l %d2,%d2
 jmp 0x4000377a
.Ldelay_original_loop:
'''
    text+=include(0x40003738,0x40003776)
    text+=''' subq.l #1,%d2
 bne .Ldelay_original_loop
 jmp 0x4000377a
.size pk_stock_delay_steady_mix,.-pk_stock_delay_steady_mix
'''
    path=work/'stock-delay-steady-mix.s';path.write_text(text)
    return dict(path=str(path),sites=[dict(SITE,entry='pk_stock_delay_steady_mix',pad_to=12)],
                guard='D4==D5==D6==D7==0; fixed16 count assigned by original entry',
                fallback='Original arithmetic/memory body and16 counter updates for every nonzero ramp',
                preserved='All source/ring reads and writes, EMAC order, all registers and full CCR/raw EMAC')
