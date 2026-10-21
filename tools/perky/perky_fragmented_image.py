"""Install relocated PERKY shards using existing local records and extended uploads.

The normal builder places only the source seam in Plate's donor record. This
module checks that placement, fills the remaining Plate/Compressor words, and
returns shared-tail records for the existing preboot upload path. No changes to
the generic firmware builder are needed.
"""
from pathlib import Path
import re

import ab_records as A
import build_bus as B
import perky_emit_shards as E
import all_fx_layout as L


def plan(asm, tag, *, pad_guard=True, emitter=E.emit, extra_private_spans=()):
    pieces, whole, dest, final, syms = emitter(asm, tag)
    records = []
    ledger = []
    for name, lo, hi, text, _ in pieces:
        words, _ = B.assemble_syms(E.rewrite(text, syms, final), dest[name], name, strict_layout=True)
        assert len(words) == hi-lo, (name, len(words), hi-lo)
        assert any(a <= dest[name] and dest[name]+len(words) <= b
                   for a, b in L.local_p_spans(tag) + L.SAFE_SHARED_P_SPANS
                   + tuple(extra_private_spans)), name
        records.append((dest[name], words))
        ledger.append(dict(name=name, start=dest[name], length=len(words)))
    for i, (a, w) in enumerate(records):
        assert all(not L.overlaps((a, a+len(w)), (b, b+len(v)))
                   for b, v in records[i+1:])
    if pad_guard and any(name == 'pk_multi_complex_init' for name, *_ in pieces):
        from perky_four_placement import PREFETCH_GUARD_START, PREFETCH_GUARD_WORDS
        assert all(addr<0x30000 or addr+len(words)<=PREFETCH_GUARD_START for addr,words in records),'executable shard overlaps prefetch guard'
        records.append((PREFETCH_GUARD_START, [0] * PREFETCH_GUARD_WORDS))
        ledger.append(dict(name='mapped prefetch guard NOPs',
                           start=PREFETCH_GUARD_START, length=PREFETCH_GUARD_WORDS))
    # The stock startup clears the complete aliased half-window AFTER upload.
    # Keep its local-Y clear and all stock-owned shared words; skip code tails.
    local=L.local_p_spans(tag)
    start=local[0][1]-48
    half=(0x30000,0x38000) if tag=='A' else (0x37f00,0x40000)
    protected=[(a,b) for a,b in L.SAFE_SHARED_P_SPANS if half[0]<=a<b<=half[1]]
    cursor=half[0]; clear=[(0x4000 if tag=='A' else 0x3f00,0xc000)]
    for lo,hi in protected:
        if cursor<lo:clear.append((cursor,lo))
        cursor=hi
    if cursor<half[1]:clear.append((cursor,half[1]))
    text='pf_boot_clear:\n clr a\n'
    for i,(lo,hi) in enumerate(clear):
        text+=f' move #>${lo:x},r5\n move #>${hi-lo:x},b\n do b,pf_loop_end_{i}\n move a,y:(r5)+\npf_loop_end_{i}:\n nop\n'
    text+=f' move #>$c000,r4\n move #>${half[1]:x},r5\n move #>${0x8000 if tag=='A' else 0x8100:x},b\n rts\n'
    words,_=B.assemble_syms(text,start,'fragment_clear_'+tag,strict_layout=True)
    assert len(words)<=48
    words+= [0]*(48-len(words))
    records.append((start,words))
    ledger.append(dict(name='stock startup clear preserving code tails',start=start,length=48))
    return records, ledger, final(syms['pk_probe_source'])


def seam_source(asm, output):
    if '; PERKY3_CORE_OWNED' in Path(asm).read_text():
        # Generic placement supplies the guarded source hook and reserves the
        # approved donors. install() moves this hook to the private entry only
        # after independently assembling every final shard.
        Path(output).write_text('pk_probe_source:\n move a,x:>$20e\n rts\n')
        return {}
    pieces, whole, dest, final, syms = E.emit(asm)
    seam = next(p for p in pieces if p[0] == 'synth_seam_glue.asm')
    assert dest[seam[0]] == 0x1000, 'builder seam origin changed'
    # Let the normal per-payload substitution carry every cross-shard
    # reference, including calls into the payload-specific local donor spans.
    text=seam[3].replace('$000426', '@CONT@')
    substitutions={tag:{'@CONT@':{'A':'$000426','B':'$000221'}[tag]} for tag in ('A','B')}
    final_by_tag={tag:E.emit(asm,tag)[3] for tag in ('A','B')}
    for label in sorted(E.externals(seam[3],syms), key=len, reverse=True):
        marker='@PK_'+label+'@'
        text=re.sub(r'\b'+re.escape(label)+r'\b',marker,text)
        for tag in ('A','B'):
            substitutions[tag][marker]='$%06x'%final_by_tag[tag](syms[label])
    Path(output).write_text(text)
    return substitutions



def merge_upload_records(appended):
    """Union physically shared records, retaining ordinary P on its own core.

    An appended record below the private-P ceiling is NOT shared. In
    particular B's unused upload tail overlaps live stock code on A.
    """
    private = {tag: [] for tag in ('A', 'B')}
    shared = {}
    for tag, rows in appended.items():
        for addr, words in rows:
            end = addr + len(words)
            assert words and (0 <= addr < end <= 0x2000 or
                              0x30000 <= addr < end <= 0x40000), ('P record crosses memory domains', tag, hex(addr))
            if addr < 0x2000:
                private[tag].append((addr, words))
            else:
                if addr in shared:
                    assert shared[addr] == words, ('shared helper drift', hex(addr))
                shared[addr] = words
    ordered = sorted(shared.items())
    for (a, w), (b, v) in zip(ordered, ordered[1:]):
        assert a + len(w) <= b, ('cross-core shared P overlap', hex(a), hex(b))
    result = {}
    for tag, rows in private.items():
        rows = sorted(rows)
        for (a, w), (b, v) in zip(rows, rows[1:]):
            assert a + len(w) <= b, ('private P overlap', tag, hex(a), hex(b))
        result[tag] = rows + ordered
    return result


def install(image, asm, *, planner=plan):
    img = bytearray(image)
    owned='; PERKY3_CORE_OWNED' in Path(asm).read_text()
    appended, ledgers = {}, {}
    for tag, (va, ln) in zip(('A', 'B'), (A.PAYLOAD_A, A.PAYLOAD_B)):
        recs, _ = A.records(img, va, ln)
        records, ledger, entry = planner(asm, tag)
        site = {'A': 0x39c, 'B': 0x1a2}[tag]
        hook = A.word_at(recs, 0, site)
        hook_entry=L.local_p_spans(tag)[0][0] if owned else entry
        assert [A.rd(img, hook+3*i) for i in range(2)] == [0x0bf080, hook_entry]
        if owned:A.wr(img,hook+3,entry)
        # Replace only the original clear loop. The stock continuation,
        # including A's CLR B and B's mailbox staging, remains in place.
        end=0x4a if tag=='A' else 0x4b
        expected=([0x57f400,0x8000,0x64f400,0x4000,0x65f413,0x30000,
                   0x06cf00,0x49,0x5e5c00,0x5e5d00] if tag=='A' else
                  [0x57f400,0x8100,0x64f400,0x3f00,0x65f400,0x37f00,
                   0x200013,0x06cf00,0x4a,0x5e5c00,0x5e5d00])
        assert [A.rd(img,A.word_at(recs,0,a)) for a in range(0x40,end)]==expected
        clear_entry=ledger[-1]['start']
        for a,word in zip(range(0x40,end),[0x0bf080,clear_entry]+[0]*(end-0x42)):
            A.wr(img,A.word_at(recs,0,a),word)
        appended[tag] = []
        for addr, words in records:
            if any(lo <= addr and addr+len(words) <= hi for lo, hi in L.local_p_spans(tag)):
                for i, word in enumerate(words):
                    A.wr(img, A.word_at(recs, 0, addr+i), word)
            else:
                appended[tag].append((addr, words))
        # Both approved sacrifices must dispatch to the null stub even when
        # the generic builder's seam alone did not reach Compressor's run.
        for effect in ('PLATE REV','COMPRESSOR'):
            effect_id=B._MODS[effect].menu.fx2_id
            for index,target in ((effect_id,B.PP[tag]['nul_i']),
                                 (32+effect_id,B.PP[tag]['nul_p'])):
                A.wr(img,B.PP[tag]['xtab']-A.BASE+3*index,target)
        ledgers[tag] = ledger
    if owned:
        # Both uploads install the same shared union. Shared cold helpers
        # must be identical; core-owned shared copies have distinct physical
        # extents. Ordinary private additions remain exclusive to their core.
        appended = merge_upload_records(appended)
    assert ([r for r in appended['A'] if r[0] >= 0x30000] ==
            [r for r in appended['B'] if r[0] >= 0x30000]), 'shared memory cannot hold payload-specific code'
    return bytes(img), appended, ledgers
