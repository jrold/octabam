"""Opt-in DSP-B placement experiment; never changes PERKY4S admission.

The private tails are candidates, not hardware-qualified reservations. The
six-word upper guard is an experimental allowance. All renderer text and
shared helper destinations come from the existing four-engine composition.
"""
from pathlib import Path

import all_fx_layout as L
import build_bus as B
import perky_emit_shards as E
import perky_fragmented_image as F

BASE_EMIT = E.emit

PRIVATE_TAILS = {'A': (0x1fdf, 0x2000), 'B': (0x1d9f, 0x2000)}
GUARD_WORDS = 6
RELOCATED = ('fold_drum_voice.asm', 'fold_drum2_voice.asm',
             'complex_drum_production_voice')
CONTEXT = ((0x3800, 58), (0x38e8, 4), (0x38ec, 6),
           (0x3964, 17), (0x3980, 40), (0x39b0, 17))
BANK_BASE = 0x39c1
CONTEXT_WORDS = sum(n for _, n in CONTEXT)
SWAP_ORG = 0x33da3


def swap_source():
    """Exchange the resident fixed-address context with its independent bank.

    Scratch and Fold2's two temporary words are intentionally shared. Both
    voices retain their own RNG, init markers, pitch cache, FIFO and clock.
    The exchange cost is included in paired measurements.
    """
    text = f'pkb_context_exchange:\n move #>${BANK_BASE:x},r2\n'
    for i, (base, count) in enumerate(CONTEXT):
        text += (f' move #>${base:x},r1\n do #>{count},pkb_exchange_end_{i}\n'
                 ' move x:(r1),a\n move x:(r2),b\n'
                 ' move b1,x:(r1)+\n move a1,x:(r2)+\n'
                 f'pkb_exchange_end_{i}:\n nop\n')
    return text + ' rts\n'


def emit(asm, tag='B'):
    assert tag == 'B', 'only B retains the oscillator portfolio'
    pieces, whole, dest, _, syms = BASE_EMIT(Path(asm), tag)
    dest = dict(dest)
    cursor, ceiling = PRIVATE_TAILS[tag]
    for name in RELOCATED:
        size = next(b-a for n, a, b, _, _ in pieces if n == name)
        assert cursor + size <= ceiling - GUARD_WORDS, (name, 'private tail overflow')
        dest[name] = cursor
        cursor += size

    def final(addr):
        for name, a, b, _, _ in pieces:
            if a <= addr < b:
                return dest[name] + addr - a
        return addr

    return pieces, whole, dest, final, syms


def plan(asm, tag):
    if tag == 'A':
        # The experiment builder restores A's stock source hook afterwards.
        records, ledger, entry = F.plan(asm, tag)
        return records[-1:], ledger[-1:], entry
    records, ledger, entry = F.plan(
        asm, tag, emitter=emit, extra_private_spans=(PRIVATE_TAILS[tag],))
    guard = PRIVATE_TAILS[tag][1] - GUARD_WORDS
    records.insert(-1, (guard, [0] * GUARD_WORDS))
    ledger.insert(-1, dict(name='experimental private upper guard NOPs',
                           start=guard, length=GUARD_WORDS))
    words, _ = B.assemble_syms(swap_source(), SWAP_ORG, 'pkb_exchange', strict_layout=True)
    assert any(a <= SWAP_ORG < SWAP_ORG+len(words) <= b for a, b in L.SAFE_SHARED_P_SPANS)
    assert all(not L.overlaps((SWAP_ORG, SWAP_ORG+len(words)),
                             (a, a+len(w))) for a, w in records)
    records.insert(-1, (SWAP_ORG, words))
    ledger.insert(-1, dict(name='experimental context exchange', start=SWAP_ORG, length=len(words)))
    return records, ledger, entry
