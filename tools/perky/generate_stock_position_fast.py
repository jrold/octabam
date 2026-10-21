"""Candidate guarded replacements for both stock sample-position loops.

All inputs are tested at the actual loop boundary. Equal positive step and
period, 0<=fraction<period and a nonnegative count imply exactly one position
increment/decrement per sample and an unchanged fraction. Every other input
uses the original recurrence. No opcode controls, sample data or FX change.
"""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=0x40000400
SITES=(
    dict(name='forward',address=0x4000888e,end=0x400088a8,
         sha256='8d6e2a6aca3168bff115b13028f09c76c7ec345a94149dcb7c7611758da0040a'),
    dict(name='reverse',address=0x40008e64,end=0x40008e7e,
         sha256='48fe3f685af4051ed9a81ba1871817750142e5e64dfc9c999a5d7fa80fe7b97f'),
)

def expected_span(site):
    blob=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    data=blob[site['address']-BASE:site['end']-BASE]
    assert hashlib.sha256(data).hexdigest()==site['sha256'],('stock position span drift',site)
    return data

def generate(work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    text='''/* Exact guarded stock sample-position recurrence. Integer registers
 * only; preserve all registers except the original d0/d1/d4 outputs, and
 * restore the original final subtraction's complete CCR, including X. */
.text
.balign 2
'''
    sites=[]
    for site in SITES:
        expected_span(site)
        name=site['name'];label='pk_fast_stock_position_'+name
        prefix='.Lposition_'+name+'_'
        position_op='add' if name=='forward' else 'sub'
        text+=f'''.globl {label}
.type {label},@function
{label}:
 move.l %d5,-(%sp)
 tst.l %d4
 bmi {prefix}fallback
 cmp.l %d2,%d3
 bne {prefix}fallback
 tst.l %d3
 bmi {prefix}fallback
 move.l 132(%a2),%d5
 cmp.l 140(%a2),%d5
 bne {prefix}fallback
 tst.l %d3
 bne {prefix}positive
 tst.l %d5
 beq {prefix}fallback
{prefix}positive:
 cmp.l %d3,%d0
 bhi {prefix}fallback
 blo {prefix}fraction_ok
 cmp.l %d5,%d1
 bhs {prefix}fallback
{prefix}fraction_ok:
 tst.l %d4
 beq {prefix}finish
 {position_op}.l %d4,68(%a2)
{prefix}finish:
 move.l (%sp)+,%d5
 moveq #0,%d4
 subq.l #1,%d4
 bge {prefix}fast_return
{prefix}fast_return:
 jmp 0x{site['end']:x}
{prefix}fallback:
 move.l (%sp)+,%d5
 bra {prefix}tail
{prefix}sample:
 sub.l 132(%a2),%d1
 subx.l %d2,%d0
 bge {prefix}tail
{prefix}period:
 {position_op}q.l #1,68(%a2)
 add.l 140(%a2),%d1
 addx.l %d3,%d0
 blt {prefix}period
{prefix}tail:
 subq.l #1,%d4
 bge {prefix}sample
 jmp 0x{site['end']:x}
.size {label},.-{label}
'''
        sites.append(dict(site,entry=label,pad_to=site['end']-site['address']))
    path=work/'stock-position-fast.s';path.write_text(text)
    return dict(path=str(path),sites=sites,
                guard='count>=0, step=period>0, 0<=fraction<period',
                preserved='All registers and full CCR match at the original continuation; private stack use4 bytes',
                fallback='Original per-sample 64-bit recurrence for every rejected guard')
