#!/usr/bin/env python3
"""Compare optimized HW4 with its qualified generic kernels, byte for byte.

Reads the actual persistent X arena and the entire 2048-word Karplus Y ring.
Scratch is permitted to differ. No firmware bytes or baseline dumps are tracked.
Also exercises the fixed-constant RNG on seeded and carry-boundary inputs.
"""
from pathlib import Path
import random
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/verify'), str(ROOT/'tools/perky'), str(ROOT/'modules/perky')]
import verify_perky_hw4_realtime_budget as timing
import verify_perky_controlled_voice_exec as c
import hw4_optimized_source as optimized
import noise_tone_word_model as model

OUT = ROOT/'out/perky/hw4-optimization'


def compare():
    for variant, optimize in (('reference', False), ('optimized', True)):
        timing.OUT = OUT/variant
        timing.WORK = OUT/(variant+'-assets')
        timing.measure(optimize=optimize)
    reference, changed = OUT/'reference', OUT/'optimized'
    for case, _records in timing.scenarios():
        for engine, slot in ((0, 0), (10, 32), (3, 0), (8, 32)):
            tag = f'{case}-engine-{engine}-slot-{slot:02x}'
            assert (reference/(tag+'.raw')).read_bytes() == (changed/(tag+'.raw')).read_bytes(), tag+' PCM'
            old = [line.split() for line in (reference/(tag+'.state')).read_text().splitlines()]
            new = [line.split() for line in (changed/(tag+'.state')).read_text().splitlines()]
            assert len(old) == len(new) == 256, tag
            # Four legacy overlays, RNG, event/markers; persistent cache + snapshots;
            # then all 2048 ring words. X:3900..397f is renderer scratch.
            indices = list(range(0, 0xf2)) + list(range(0x180, 0x1e4)) + list(range(2048, 4096))
            for block, (before, after) in enumerate(zip(old, new)):
                assert len(before) == len(after) == 4096
                differences = [(i, before[i], after[i]) for i in indices if before[i] != after[i]]
                if differences:
                    raise AssertionError(f'{tag} block {block}: persistent state {differences[:12]}')
            print(f'PASS {tag}: 4096 PCM samples, 256 complete voice/cache/trigger/RNG/ring snapshots')

def rng():
    c.OUT = OUT/'rng'
    c.OUT.mkdir(parents=True, exist_ok=True)
    c.STATE_BASE = c.YSTATE_BASE = 0x200
    c.STATE_WORDS = 64
    c.CYCLE_METER = True
    c.build_host()
    source = '''pk_controlled_voice_exec:
        do n7,hwr_loop_done
        jsrl pk_rng_step
        move x:(r5+$10),a
        move a1,x:(r0)+
        move a1,x:(r0)+
hwr_loop_done:
        nop
        rts
''' + optimized.rng_source()
    binary, entry = c.assemble(source)
    generator = random.Random(56300)
    # This low word makes low32(oldLow*B)==ffffffff and forces the carry
    # into newHigh. Also cover maximal limbs and independent zero halves.
    carry = (-pow(0x4c957f2d, -1, 1<<32)) & 0xffffffff
    seeds = [(0,0), (0xffffffff,0xffffffff), (carry,0), (carry,0xffffffff),
             (0xffffffff,0), (0,0xffffffff)]
    seeds += [(generator.getrandbits(32), generator.getrandbits(32)) for _ in range(122)]
    def write_data(path, words, _tables):
        path.write_text('X 200 '+' '.join(f'{v:06x}' for v in words)+'\n')
        return words[:4]
    c.write_data = write_data
    for index, (low, high) in enumerate(seeds):
        state = model.WordRng.from_ints(low, high)
        words = [state.low.lo, state.low.hi, state.high.lo, state.high.hi]+[0]*60
        want = [model.next_random(state).lo for _ in range(16)]
        audio, snapshots, _ = c.run(binary, entry, f'seed-{index:03d}', words, [], [(tuple([0]*12), -1)])
        assert audio[0] == want, (index, 'RNG return sequence')
        final = [state.low.lo, state.low.hi, state.high.lo, state.high.hi]
        assert snapshots[0][:4] == final, (index, 'RNG state')
        assert [snapshots[0][i] for i in (8,9,16,17)] == final, (index, 'RNG mirrors')
    print('PASS HW4 RNG: 2048 exact transitions, including low32 carry into high32')


def main():
    compare()
    rng()
    print('PERKY HW4 optimization: PASS (generic qualified kernels; actual persistent state; exact PCM)')


if __name__ == '__main__':
    main()
