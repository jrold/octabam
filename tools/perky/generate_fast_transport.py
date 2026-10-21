"""Candidate-only exact no-wrap tap gather; retain the proven wrap fallback.

The caller bounds each request to at most twenty native samples. Test every
ring cursor and retain the original filter symbol when replacing pkbudget.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def once(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new,1)

def generate(work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    source=ROOT/'modules/perky/budget_transport.s'
    text=source.read_text()
    guard=''' /* A whole segment normally crosses none of the five ring ends.
  * Check all spans once; the existing wrapped loop handles every exception. */
 move.l %d5,%d0
 add.l %d0,%d0
 move.l %d7,%d1
 sub.l %d0,%d1
 cmp.l %d1,%a0
 bhi .Lbudget_taps_loop
 cmp.l %d1,%a1
 bhi .Lbudget_taps_loop
 cmp.l %d1,%a2
 bhi .Lbudget_taps_loop
 cmp.l %d1,%a3
 bhi .Lbudget_taps_loop
 cmp.l %d1,%a4
 bhi .Lbudget_taps_loop
 cmp.l #4,%d5
 blo .Lbudget_fast_tail
.Lbudget_fast_four:
'''
    for offset in (0,2,4,6):
        for register in ('%a0','%a1','%a2','%a3','%a4'):
            guard+=f' move.l {offset}({register}),%d0\n byterev %d0\n move.w %d0,(%a5)+\n'
    for register in ('%a0','%a1','%a2','%a3','%a4'):
        guard+=f' lea 8({register}),{register}\n'
    guard+=''' subq.l #4,%d5
 cmp.l #4,%d5
 bhs .Lbudget_fast_four
.Lbudget_fast_tail:
 tst.l %d5
 beq .Lbudget_taps_last
.Lbudget_fast_one:
'''
    for register in ('%a0','%a1','%a2','%a3','%a4'):
        guard+=f' move.l ({register}),%d0\n byterev %d0\n move.w %d0,(%a5)+\n addq.l #2,{register}\n'
    guard+=''' subq.l #1,%d5
 bne .Lbudget_fast_one
 bra .Lbudget_taps_last
'''
    text=once(text,' .macro TAP_READ reg\n',guard+' .macro TAP_READ reg\n')
    text=once(text,' move.l 64(%sp),%a0\n','.Lbudget_taps_last:\n move.l 64(%sp),%a0\n')
    target=work/'budget-transport-fast.s';target.write_text(text)
    return dict(path=str(target),parent=str(source),symbol='pk_budget_gather_taps',
                preserved_symbols=['pk_budget_slap_filter'],
                dispatch='All five complete spans fit before their ring ends; otherwise use original wrap loop',
                native_count_bound=20,ring_words=4805)
