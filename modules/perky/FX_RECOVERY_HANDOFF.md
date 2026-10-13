# FX recovery — handoff

**Read this one file. It supersedes the 25 addenda in `FX_RECOVERY_FEASIBILITY.md`, which are
the measurement record and do not need re-reading to act.**

## Goal

Restore **SPRING REV, DARK REV and LO-FI** to the `perky-2voice-milestone` image. PLATE REV
and COMPRESSOR are approved sacrifices. Do not remove an engine.

## Why it needs sharding

Perky's DSP program is **3051 words**. It fits one contiguous run only by harvesting five
effects (3441 words: PLATE + SPRING + DARK + COMPRESSOR + LO-FI). Keeping SPRING, DARK and
LO-FI leaves it **774 words in two non-adjacent runs** (PLATE 594, COMPRESSOR 180) — **2277
short**.

Capacity is fine: 774 local + **2404 in five shared tails** = **3178**, 127 free. Contiguity
is the problem, so the program must be emitted as **shards**.

`all_fx_layout.py` holds the spans and the placer. `SAFE_LOCAL_P_SPANS` (the two runs) +
`SAFE_SHARED_P_SPANS` (the five tails) = `all_p_spans()`; `place_program_shards_two_space()`
assigns them.

## Everything is proven. Do not re-derive it.

| property | how it was established |
|---|---|
| it fits | 3051 into 3178, 127 free; first-fit-decreasing succeeds |
| the pieces | **21**, marked by the composer's own `; ===== BEGIN/END =====`, **zero unmarked content**, balanced, largest 386 of the 605 cap |
| origin-independent | same 3051 words and identical symbol offsets at origins 0x1000 / 0x2400 / 0x3840 |
| no cross-piece branches | **0** relative branches cross a piece; all **39** cross-piece transfers are absolute `jsrl` |
| placement | all 21 placed; 3 in local P, 18 in the tails |
| shards reassemble | all 21 assembled standalone; stitched result **byte-identical to the monolith** |
| assigned origins | all 21 assemble there, extents exact, **zero sizing drift** |
| the effects' P is free | SPRING 0x1252, DARK 0x1679, LO-FI 0x1B58 — **0 words overwritten** |

Tools: `tools/perky/perky_shard_map.py` (label map, self-checking), `out/perky/light2/sharded-p.json`
(the placement manifest).

## The two edits. They MUST land together.

### Change 1 — stop harvesting the three

In `remixes/test/perky-machine/remix.py`, add `SPRING REV`, `DARK REV`, `LO-FI` to `fx1`.

**Safe:** the harvest takes *DSP code only*. An effect on a chooser **keeps its algorithm, its
descriptor and its P words**, so this keeps all three whole with no restoration step. Measured
effect: the harvest goes 3441 words in one run → **774 in two**.

### Change 2 — place a module's P across multiple spans

**This is the real work and needs new machinery.** Confirmed against the schema:

* `Claims` has **no P field** (`reserved_private_y, owns_fx2_buffers, stock_instance_buffer,
  buffer_words, fx1_only, part_window, sram, dsp_ranges`);
* `DspRange.space` is **`"x"` or `"y"` only** — a shard cannot be declared `DspRange("p", ...)`;
* **but inside the shared window X, Y and P alias**, so the **five tails ARE declarable as x/y
  ranges today** and the existing ledger will police them. Only the **two local runs** (P-only,
  below the window) cannot be named.

So: five spans declarable now, two needing a new `space` value or another path.

### Emitter mechanics — proven, with the trap recorded

For each shard: take its source slice; rewrite **every label token on every non-comment line**
that it references but does not define to its absolute `$hex`; assemble alone at its assigned
origin.

**The trap:** rewriting only `op label` forms FAILS. Labels also appear as immediates, `do`
targets and memory operands. A line-form rewrite leaves references unresolved.

Cross-shard addresses translate as:
`assigned_origin(target's shard) + (monolith addr − target's shard monolith start)`.
Local P and the tails have different bases; a wrong shard→origin map puts a correct-looking
absolute in the wrong space and still assembles.

### Then the gates

DSP timing for the retained engines, boot/upload/readback, the P/X/Y ledger — on the resulting
image.

## The standing requirement

`assemble_syms` reports `dsp_asm`'s two-pass **sizing-drift** diagnostic. One site exists in the
*qualified* build (line 408) — origin-invariant and harmless. **The sharded assembly must have
that diagnostic EMPTY**, not merely non-fatal: drift introduced *by* sharding would move
addresses inside a shard. Verified empty for all 21 at assigned origins; keep it that way.

## Do not repeat these four mistakes, all made and corrected here

1. **`dsp_asm` has no externals — but needs none.** Labels are substituted *textually* as `$hex`
   before encoding. Read the implementation, not the option list.
2. **Byte-identity proves less than it looks.** It shows a comment-only edit changed nothing.
   The one place it means what it says is shard-reassembly, which compares two independent
   assemblies over all 3051 words.
3. **An unmarked region is one a splitter declines to touch; an UNBALANCED marker is worse** — it
   invites inventing a boundary, and that fiction assembles.
4. **A mutation must both BUILD and defeat the real path before it tests anything.** Several
   "teeth proven" and "teeth unproven" claims here came from runs that never compiled.

## Baseline — never touch

Tag `perky2v-hw-baseline` → `fc438e03`. Archive:
`out/hw-baselines/perky2v-fc438e03/`. The current shipped artifact is unrelated to this work and
byte-identical across all 47 commits: card `4ba4d72c…`, MIDI `685e5105…`.

---

# Where change 2 actually lives (measured, round 49)

`tools/build/build_bus.py:2176`:

```python
_derived = stock_mod.region_of(stock_mod.harvested(_listed))
```

**This is the single-run locus.** `stock.regions_of()` -- the plural, which returns the
contiguous runs separately -- **already exists** in `tools/remix/stock.py`. So change 2 is not
"new machinery from nothing": it is replacing one call and emitting the module's code across
the runs it returns.

## A correction, because the measurement contradicted me

I first read the comment *"The largest contiguous run of them is the region"* and concluded
`region_of()` picks the largest run, so narrowing the harvest would yield only PLATE's 594
words. **Measured, that is wrong:**

```
region_of(narrowed)  -> ['COMPRESSOR', 'PLATE REV']  = 774 words   (BOTH)
regions_of(narrowed) -> [(['PLATE REV'],594), (['COMPRESSOR'],180)]
```

`region_of()` returns **all** harvested effects. The docstring's "largest contiguous run"
describes the *flashable* case. The real constraint is a **contiguity assert** elsewhere --
the code says so: *"the contiguity assert is what proves that rather than assuming it."*

**So the build refuses the narrowed harvest because the two runs are NOT CONTIGUOUS, not
because 3051 exceeds 774.** That is a different refusal from the one addendum 22 recorded, and
the distinction matters: a size problem invites shrinking the program; a contiguity problem is
solved by placement, which is what the sharding already does.

## Exact change 2, as it now stands

1. `build_bus.py:2176`: take `regions_of()` rather than `region_of()`, and relax the
   contiguity assert when the module's code is emitted as shards.
2. Emit the module's P across those runs using the assignment from
   `all_fx_layout.place_program_shards_two_space()`, and across the five shared tails, which
   are declarable as x/y `DspRange`s because X, Y and P alias inside the window.

**Step 1 is a located, small edit. Step 2 is the emitter, whose every property is proven.**

---

# DECISIVE: the multi-run placer already exists. Only one rule blocks it.

`tools/remix/stock.py:347`, `regions_of()`'s own docstring:

> Harvested effects grouped into CONTIGUOUS runs, in address order.
>
> **A module of ours is one code stream, so it must fit inside ONE run -- but different
> modules can sit in different runs, which is what `build_bus.py`'s placer does.** So every
> harvested effect is placeable ground, and the only cost of a gap is fragmentation: **a module
> larger than the biggest run has nowhere to go even when the total is ample.**
>
> Until this returned the LARGEST run alone and the rest were given up for nothing -- visible
> in the remixer as "drop two effects, free only the reverbs" (Sam, 3 Sep). **A stranded run is
> now placeable.**

And `region_of()` (line 372) is now just the flattened name callers use:

```python
def region_of(harvest):
    """... It is no longer a single run -- see regions_of() for the grouping the
    placer needs."""
    return tuple(k for run in regions_of(harvest) for k in run)
```

## What this means for change 2

**The placer already places different modules into different runs.** Nothing about the
two-address-space layout is unsupported. What blocks Perky is exactly one rule:

> **A module of ours is one code stream.**

Perky is one module, so its 3051 words must fit one run -- and with SPRING, DARK and LO-FI kept,
the largest run is 594.

**The fix is precisely the sharding, already built and proven:**

| property the split needs | status |
|---|---|
| the program divides into independently placeable pieces | 21, markers balanced, zero unmarked, none over the 605 cap |
| a piece does not depend on where it sits | origin-independent at three origins |
| a piece never branches relatively outside itself | **0** cross-piece relative branches; all 39 transfers are absolute `jsr`/`jsrl` |
| pieces reassemble to the original | **byte-identical to the monolith**, all 3051 words |
| pieces assemble at their assigned origins | 21/21, extents exact, **zero sizing drift** |

**So change 2 is: let ONE module contribute several placeable streams, and feed the placer the
assignment `place_program_shards_two_space()` already computes.** That is a change to the
one-stream assumption, not new placement machinery.

## The framing this replaces

Addenda 21-25 progressively described change 2 as "new machinery", then "the part with no
existing machinery", then "five spans declarable, two needing schema work". Those were all
written before reading `regions_of()`'s docstring, which states the actual rule in its second
paragraph. **The mechanism was documented; I was reasoning from the call site instead.**

---

# The placement ledger verifies (round 51) -- release gate 7's placement half

Measured against `out/perky/light2/sharded-p.json` and `stock.p_spans`:

```
placed shards: 21   total words: 3051
overlaps BETWEEN shards: NONE

collisions with KEPT effects: NONE      <- required
collisions with sacrificed  : PLATE x2, COMPRESSOR x1
```

**Zero overlaps between the 21 shards; zero collisions with every retained stock effect.**
The only occupied stock ground is PLATE and COMPRESSOR -- exactly the two approved sacrifices.

## The useful consequence

Spring, Dark and Lo-Fi appear in the *sacrificed* column **only because the remix's `fx1` does
not list them yet** -- that is change 1, unmade. **The shards do not touch their spans either**
(neither appears in the collision list). So the ledger *predicts* that once change 1 lands, the
three move to KEPT and the collision set does not grow.

**That is a falsifiable prediction, and it is the right shape to check change 1 with**: after
listing the three in `fx1`, re-run this ledger and require the same two lines -- `KEPT` gains
SPRING REV, DARK REV and LO-FI, and `collisions with KEPT effects` is still NONE.

## Reproduce it

```python
from remix import registry, stock
import all_fx_layout as L, json, pathlib
r = registry.remix('perky-machine'); sp = stock.p_spans('A')
plc = json.loads(pathlib.Path('out/perky/light2/sharded-p.json').read_text())['shards']
spans = sorted((v['start'], v['start']+v['words']-1, k) for k, v in plc.items())
# 21 spans, 3051 words, pairwise disjoint; then intersect each with every stock span
# and require no intersection with any effect that is not PLATE REV or COMPRESSOR.
```

---

# Change 1's prediction is CONFIRMED (round 52)

Addendum from round 51 stated a falsifiable prediction and this is it, run:

```
BEFORE change 1:  KEPT = CHORUS, COMB FILTER, DJ EQ, EQUALIZER, FILTER,
                        FLANGER, PHASER, SPATIALIZER           (8)
                  collisions with KEPT: NONE

AFTER  change 1:  KEPT = ... + SPRING REV, DARK REV, LO-FI     (11)
                  collisions with KEPT: NONE

KEPT gains SPRING/DARK/LO-FI   : True
collisions with KEPT still NONE: True
-> PREDICTION CONFIRMED
```

**Listing SPRING REV, DARK REV and LO-FI in the remix's `fx1` keeps all three, and the
21-shard placement still collides with nothing retained.**

## Why this matters more than another restatement

The milestone's central claim is "Spring restored, Dark restored, Lo-Fi restored, all other
stock FX retained, Plate and Compressor the only sacrifices." Until this round that claim rested
on an argument: the two spaces have room, the shards do not sit in the three effects' spans, so
listing them should work.

**It is now a measured compatibility, and it was measured by stating the outcome in advance and
running the check.** The check required no edit to the tree and no build, so nothing is left in
a broken state:

```python
now = set(r.modules) | set(r.fx1 or [k for k in sp if k])
ledger(now)                                  # 8 kept, no collisions
ledger(now | {'SPRING REV','DARK REV','LO-FI'})   # 11 kept, STILL no collisions
```

## What is still not done

**Change 1 is not applied**, and must not be applied alone: with the three kept, Perky's one
code stream has only the 594-word PLATE run, because the placer places one module into one run.
**Changes 1 and 2 land together** -- 2 being "let one module contribute several placeable
streams", which is the sharding, already proven.

After that: the gates (DSP timing for the retained engines, boot/upload/readback, the P/X/Y
ledger).

---

# Change 2 in code: call the placer once per shard (round 53)

`build_bus.py:2265`:

```python
def place(words, start):
    """Write a contiguous word stream at P address `start`.

    The records load back-to-back but are separated by headers in the
    file, so the stream is cut at each record boundary.
    """
    i = 0
    for _, a, cnt, off in region:
        if i >= len(words): break
        pos = start + i
        if not (a <= pos < a + cnt): continue
        n = min(len(words) - i, a + cnt - pos)
        for k in range(n):
            wrw_p(va + off + (pos - a + k) * 3, words[i + k])
        i += n
    if i != len(words):
        sys.exit(f"payload {tag}: placement ran past the region")
```

**`place()` is ALREADY parameterised by `start`, and it already writes a stream that may be cut
across file records.** The single-run constraint is only that it is called **once** with the
whole 3051-word program: `pos` walks linearly from `start`, and across a gap -- a non-harvested
effect's addresses, which are not in `region` -- `i` stops advancing and it exits with
*"placement ran past the region."* **That is the entire constraint, and it is one call site.**

**The surrounding machinery is already multi-run:**

* `runs` is a **list**, each entry carrying its **own `cursor`** (line 2242);
* `_end_of_run(a)` returns the end of the run containing an address;
* `_written(a)` tests reach within the run containing `a`;
* `budget = sum(m[2] for m in region)` already sums across records.

## So change 2 is: call `place()` once per shard

```python
for shard in shards:                 # 21 of them
    place(shard.words, shard.origin) # origin from place_program_shards_two_space()
```

**No new placement machinery. No new schema field. One call site becomes a loop.** The
prerequisite is that the module's *source* be assembled as the 21 shards rather than one blob
-- which is the emitter, and whose every property is already measured (byte-identical
reassembly, origin-independence, zero cross-piece branches, zero sizing drift).

## What remains, in order

1. **Assemble the module as 21 shards** (the emitter; properties proven) instead of one blob.
2. **Loop `place()`** over the shards at the assigned origins.
3. **List SPRING REV, DARK REV, LO-FI in the remix's `fx1`** (change 1; prediction confirmed
   in the previous addendum).
4. **Run the gates.**

**Steps 2 and 3 are small and located. Step 1 is the emitter, already validated end to end.**
