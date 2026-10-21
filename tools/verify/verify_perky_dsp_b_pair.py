#!/usr/bin/env python3
"""Price two independent oscillator contexts on the specialized DSP-B program.

All samples run the complete native-clock source seam at final P addresses.
Pair PCM and every context word must match separate invocations. The wrapper
is a test dispatcher at P:5000, outside the candidate's resource ledger.
An over-budget result is a feasibility finding, not a failed correctness gate.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/p) for p in ('tools', 'tools/build', 'tools/perky', 'modules/perky', 'tools/verify')]
os.environ.setdefault('REMIX', 'perky-machine')
import ab_records as A
import build_bus as B
import perky_dsp_b_specialization as S
import verify_perky_controlled_voice_exec as c

LIMIT = 23040
X_WORDS = 616
PAIRS = ((0, 3), (0, 5), (2, 3), (2, 5))


def invocation(record, label, dynamic=False):
    select = (f' move x:>$100,a\n asl #>$5,a,a\n add #>${record:x},a\n move a1,r4\n'
              if dynamic else f' move #>${record:x},r4\n')
    return select+f'''
 move r4,x:>$209
 clr a
 move a1,x:>$418
 move #>$4080,a
 move a1,x:>$20b
 move x:>$10c,a
 move a1,x:>$20c
 clr b
 tst a
 blt {label}
 move #>$1,b
{label}:
 or #>$030000,b
 move b1,x:(r4+$3)
 jsrl pkb_source_thunk
'''


def wrapper(kind, dynamic=False):
    one = invocation(0x1000 if dynamic else 0x500, 'pkbflag_first', dynamic)
    two = invocation(0x2000 if dynamic else 0x600, 'pkbflag_second', dynamic)
    # The live seam discards its own JSR return before stock continuation.
    # Supply that real stack shape so the test continuation returns here.
    thunk = 'pkb_source_thunk:\n jsrl $ENTRY\n rts\n'
    if kind == 'first':
        return 'pkb_harness:\n'+one+' rts\n'+thunk
    if kind == 'second':
        return 'pkb_harness:\n'+two+' rts\n'+thunk
    return ('pkb_harness:\n'+one+'''
 move #>$0,r1
 move #>$0,r2
 do #>$20,pkb_save_first
 move x:(r1)+,a
 move a1,y:(r2)+
pkb_save_first:
 nop
''' + f' jsrl $EXCHANGE\n' + two + f' jsrl $EXCHANGE\n' + '''
 move #>$0,r1
 move #>$0,r2
 do #>$10,pkb_merge_channels
 move x:(r1),a
 move a1,x:(r1+1)
 move y:(r2),b
 move b1,x:(r1)+
 move (r1)+
 move (r2)+
 move (r2)+
pkb_merge_channels:
 nop
 rts
'''+thunk)


def load_program(work, kind, dynamic=False):
    upload = (work/'dsp-B.upload.bin').read_bytes()
    records, _ = A.records(upload, A.BASE, len(upload))
    planned, _, entry = S.plan(work/'multi.asm', 'B')
    text = wrapper(kind,dynamic).replace('$ENTRY', f'${entry:06x}').replace('$EXCHANGE', f'${S.SWAP_ORG:06x}')
    words, syms = B.assemble_syms(text, 0x5000, 'pkb_'+kind, strict_layout=True)
    flat = [0]*0x40000
    for space, addr, count, offset in records:
        if space == 0:
            flat[addr:addr+count] = [A.rd(upload, offset+3*i) for i in range(count)]
    for addr, expected in planned:
        assert flat[addr:addr+len(expected)] == expected
    # Test-only return instead of stock AMP/FX continuation.
    flat[0x221] = 0x00000c
    flat[0x5000:0x5000+len(words)] = words
    path = work/f'pair-{kind}{"-switch" if dynamic else ""}.bin'
    path.write_bytes(b''.join(v.to_bytes(3, 'little') for v in flat))
    return path, syms['pkb_harness']


def record(engine, mode, corner):
    rows = ((0, 428, 0, 0), (2046, 29, 2046, 2046), (4092, 6, 4092, 4092))
    values = rows[corner]
    if engine == 2:
        values = ((0, 65535, 65535, 0), (2048, 428, 1040, 1024), (4095, 1, 1, 2047))[corner]
    if engine == 5:
        values = (values[0], values[1], 99+values[2]//4, values[3])
    return [v for w in values for v in (w>>8, w&255)]+[mode, (254,31,3)[corner] if engine == 5 else 0, 0, engine]


def run(work, program, name, first, second, events, *, dirty=False, timeline=None):
    state = c.words(work/'state_init.words')
    tables = c.words(work/'tables.words')
    mem = [0]*X_WORDS
    mem[:len(state)] = state
    mem[0x3964-0x3800] = 0xffff
    if dirty:
        # All owned state except RNG and immutable wave data is dirty. Force
        # an invalid cache tag, as required by the upload ABI.
        for base, count in S.CONTEXT:
            if base == 0x38e8:
                continue
            for i in range(count):
                mem[base-0x3800+i] = (0x555500+i)&0xffffff
        mem[0x3964-0x3800] = 0xffff
    bank = [mem[a-0x3800+i] for a,n in S.CONTEXT for i in range(n)]
    mem[S.BANK_BASE-0x3800:S.BANK_BASE-0x3800+len(bank)] = bank
    data = work/'pair.data'
    data.write_text('X 3800 '+' '.join(f'{v:06x}' for v in mem)+'\n'
                    +'Y 7a5 '+' '.join(f'{v:06x}' for v in tables)+'\n'
                    +'X 500 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{v|0x030000:06x}' for v in first)+'\n'
                    +'X 600 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{v|0x030000:06x}' for v in second)+'\n')
    if timeline:
        assert len(timeline) == len(events) <= 127
        with data.open('a') as out:
            for i, (one,two) in enumerate(timeline):
                for base, values in ((0x1000,one),(0x2000,two)):
                    row = [0x504b,0,0x5931,0,0,0,0,0]+values
                    assert len(row) <= 32
                    row += [0]*(32-len(row))
                    out.write(f'X {base+32*i:x} '+' '.join(f'{v|0x030000:06x}' for v in row)+'\n')
    script = work/'pair.script'
    script.write_text(''.join(str(i if timeline else 0)+' '+'0 '*11+str(e)+'\n' for i,e in enumerate(events)))
    raw, states, meter = [work/('pair.'+suffix) for suffix in ('raw','state','meter')]
    binary, entry = program
    result = subprocess.run([str(c.HOST), '-code', str(binary), '-org', '0', '-entry', f'{entry:x}',
                             '-data', str(data), '-script', str(script), '-out', str(raw),
                             '-state', str(states), '-statebase', '3800', '-state-words', str(X_WORDS),
                             '-meter', str(meter), '-cycle-meter', '1', '-frames', '16'],
                            cwd=ROOT, capture_output=True, text=True, check=True, timeout=120)
    assert 'HUNG' not in result.stdout+result.stderr, name
    audio = list(struct.unpack('<'+str(raw.stat().st_size//4)+'i', raw.read_bytes()))
    rows = [[int(v,16) for v in line.split()][:X_WORDS] for line in states.read_text().splitlines()]
    meters = [int(v) for v in meter.read_text().split()]
    assert len(rows) == len(meters) == len(events) and len(audio) == len(events)*32
    return audio, rows, meters


def context(row):
    return [row[a-0x3800+i] for a,n in S.CONTEXT for i in range(n)]


def initialized_context(values):
    # The exchange conservatively includes dormant slot markers, reserved
    # clock words and the whole transient FIFO. Unconsumed FIFO tail words
    # need not be cleared. Carry PCM lives in clock +2, not in that tail.
    addresses = [a+i for a,n in S.CONTEXT for i in range(n)]
    reserved = {0x38ec, 0x38ef, 0x38f0, 0x38f1, 0x39b8, 0x39b9, 0x39c0}
    return [v for a,v in zip(addresses,values) if a not in reserved and not 0x3980 <= a < 0x39a8]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, default=ROOT/'out/perky/hybrid/dsp-b-feasibility')
    args = p.parse_args()
    work = args.work.resolve()
    c.build_host()
    programs = {kind: load_program(work,kind) for kind in ('first','second','pair')}
    program_hashes = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path,entry in programs.values()}
    rows = []
    # Every offset appears in an active retrigger. Repeated native clock
    # phases and release blocks sit between those triggers.
    events = [i//4 if i%4 == 0 else -1 for i in range(64)]
    for (e1,e2), m1, m2, corner in itertools.product(PAIRS, range(3), range(3), range(3)):
        r1, r2 = record(e1,m1,corner), record(e2,m2,2-corner)
        a1,s1,t1 = run(work,programs['first'],'first',r1,r2,events)
        a2,s2,t2 = run(work,programs['second'],'second',r1,r2,events)
        audio,states,timing = run(work,programs['pair'],'pair',r1,r2,events)
        assert audio[::2] == a1[::2] and audio[1::2] == a2[::2], (e1,e2,m1,m2,corner,'paired PCM')
        for i, (got,one,two) in enumerate(zip(states,s1,s2)):
            assert context(got) == context(one), (e1,e2,i,'first context')
            assert got[S.BANK_BASE-0x3800:S.BANK_BASE-0x3800+S.CONTEXT_WORDS] == context(two), (e1,e2,i,'second context')
            assert got[58:230] == c.words(work/'state_init.words')[58:230], 'immutable fourth wave corrupted'
        row = dict(engines=[e1,e2], modes=[m1,m2], corners=[corner,2-corner], blocks=len(events),
                   pair_max=max(timing), paired_solo_max=max(a+b for a,b in zip(t1,t2)),
                   exchange_and_harness_max=max(p-a-b for p,a,b in zip(timing,t1,t2)),
                   exceeds_conservative_allowance=max(timing)>LIMIT)
        rows.append(row)
        if m1 == m2 == corner == 0:
            print(f'[PASS] pair {e1}/{e2}: exact PCM and 142-word contexts; observed {row["pair_max"]} modeled cycles', flush=True)
    # Dirty-state parity, including independent caches, FIFO and init words.
    for e1,e2 in PAIRS:
        records = record(e1,0,1),record(e2,2,2)
        clean = run(work,programs['pair'],'clean',*records,events)
        dirty = run(work,programs['pair'],'dirty',*records,events,dirty=True)
        assert clean[0] == dirty[0], (e1,e2,'dirty PCM')
        start = S.BANK_BASE-0x3800
        assert all(initialized_context(context(a)) == initialized_context(context(b)) and
                   initialized_context(a[start:start+S.CONTEXT_WORDS]) == initialized_context(b[start:start+S.CONTEXT_WORDS])
                   for a,b in zip(clean[1],dirty[1])), (e1,e2,'dirty initialized context')
    programs = {kind:load_program(work,kind,True) for kind in ('first','second','pair')}
    program_hashes.update({path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path,entry in programs.values()})
    transitions = []
    for old, new, mode, offset in itertools.product(PAIRS, PAIRS, range(3), range(16)):
        before = [record(e,mode,1) for e in old]
        after = [record(e,(mode+1)%3,2) for e in new]
        prefix = [list(v) for v in before]
        for v in prefix:
            v[10] = 0xa5
        timeline = [before,[after[i]+prefix[i] for i in range(2)],after]
        reference1 = run(work,programs['first'],'switch-first',*before,[0,offset,-1],timeline=timeline)
        reference2 = run(work,programs['second'],'switch-second',*before,[0,offset,-1],timeline=timeline)
        got = run(work,programs['pair'],'switch-pair',*before,[0,offset,-1],timeline=timeline)
        assert got[0][::2] == reference1[0][::2] and got[0][1::2] == reference2[0][::2], (old,new,mode,offset,'transition PCM')
        start = S.BANK_BASE-0x3800
        for i,(pair,one,two) in enumerate(zip(got[1],reference1[1],reference2[1])):
            assert context(pair) == context(one) and pair[start:start+S.CONTEXT_WORDS] == context(two), (old,new,mode,offset,i,'transition contexts')
        transitions.append(dict(old=list(old),new=list(new),mode=mode,offset=offset,
                                pair_max=max(got[2]),paired_solo_max=max(a+b for a,b in zip(reference1[2],reference2[2]))))
    report = dict(schema='perky-dsp-b-pair-v1', hardware_validated=False,
                  image_sha256=hashlib.sha256((work/'fragmented-mainos.bin').read_bytes()).hexdigest(),
                  correctness='passed', conservative_allowance=LIMIT, context_words=S.CONTEXT_WORDS,
                  program_sha256=program_hashes,
                  host_sha256=hashlib.sha256(c.HOST.read_bytes()).hexdigest(),
                  harness_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  pair_blocks=sum(r['blocks'] for r in rows), cases=rows,
                  transitions=transitions, transition_blocks=3*len(transitions), dirty_pairs=len(PAIRS),
                  worst_pair=max(r['pair_max'] for r in rows+transitions),
                  timing_decision='does not fit unchanged conservative allowance' if any(r['pair_max']>LIMIT for r in rows+transitions) else 'screening allowance met; integrated qualification required',
                  limitations=['Source harness, not stock T1/T2 dispatch or simultaneous CF/DSP firmware workload.',
                               'Context exchange and harness overhead are included; no calibrated silicon prediction.',
                               'PCM/state reference is single-instance execution; original-author parity is a separate gate.'])
    (work/'pair-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'[PASS] {report["pair_blocks"]} fixed paired blocks, {len(transitions)} interior transitions, all mode pairs/offsets, dirty contexts; {report["timing_decision"]}; worst {report["worst_pair"]}')


if __name__ == '__main__':
    main()
