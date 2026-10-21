"""Bounded assembly packet loops; retain every source read and target write.

Small computed-entry loops remove per-word branches without omitting clears
or changing publication order. Other lengths take the original loops.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def generate(work):
    text = (ROOT / 'modules/perky/production_publish.s').read_text()
    text = text.replace(' lea -8(%sp),%sp\n movem.l %d2-%d3,(%sp)',
                        ' lea -12(%sp),%sp\n movem.l %d2-%d3/%a2,(%sp)', 1)
    text = text.replace(' move.l 12(%sp),%a0\n move.l 16(%sp),%a1\n move.l 20(%sp),%d3',
                        ' move.l 16(%sp),%a0\n move.l 20(%sp),%a1\n move.l 24(%sp),%d3', 1)
    text = text.replace(' movem.l (%sp),%d2-%d3\n lea 8(%sp),%sp',
                        ' movem.l (%sp),%d2-%d3/%a2\n lea 12(%sp),%sp', 1)
    marker = ' tst.l %d0\n beq .Lprod_record_end\n.Lprod_pcm:\n'
    assert text.count(marker) == 1
    bounded = ''' cmp.l #16,%d0
 bhi .Lprod_pcm
 lsl.l #3,%d0
 lea .Lprod_unrolled_end(%pc),%a2
 suba.l %d0,%a2
 jmp (%a2)
'''
    bounded += ''' move.l (%a1)+,%d2
 lsl.l #8,%d2
 move.l %d2,(%a0)+
 move.l %d2,(%a0)+
''' * 16
    bounded += '.Lprod_unrolled_end:\n rts\n.Lprod_pcm:\n'
    text = text.replace(marker, bounded, 1)
    marker = ' moveq #0,%d1\n cmp.l #16,%d0\n'
    assert text.count(marker) == 1
    bounded = ''' moveq #0,%d1
 cmp.l #36,%d0
 bhi .Lprod_clear_generic
 add.l %d0,%d0
 lea .Lprod_clear_unrolled_end(%pc),%a1
 suba.l %d0,%a1
 jmp (%a1)
'''
    bounded += ' move.l %d1,(%a0)+\n' * 36
    bounded += '''.Lprod_clear_unrolled_end:
 move.l %a0,%d0
 rts
.Lprod_clear_generic:
 cmp.l #16,%d0
'''
    text = text.replace(marker, bounded, 1)
    target = Path(work) / 'production-publish-unrolled.s'
    target.write_text(text)
    return target
