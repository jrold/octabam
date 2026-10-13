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

---

# Step 1 is built and passing: `tools/perky/perky_emit_shards.py`

```
$ REMIX=perky-machine BUILD=3 python3 tools/perky/perky_emit_shards.py
  pieces: 21   words: 3051   monolith: 3051
  in LOCAL P: 3   in SHARED tails: 18
  monolith-origin bytes identical for every piece: True
  assigned-origin extents exact for every piece: True
```

It does the whole of step 1: assemble the monolith, slice the 21 marked pieces, rewrite each
piece's external label tokens to `$hex`, and assemble each piece twice --

* **at its MONOLITH origin**, where the bytes must equal the monolith's bytes for that source
  range. This is the faithfulness claim, and it is a real byte-identity check: two independent
  assemblies of the same code over all 3051 words.
* **at its ASSIGNED origin** (3 in local P, 18 in the tails), where the extent must be exact.
  **Byte-identity is deliberately NOT claimed here** and should not be: internal label
  addresses move when a piece is relocated.

Stating those two separately is the point. Earlier in this work byte-identity was used for a
weaker claim (a comment-only edit changed nothing); here it is used for the strong one, and the
one place it does not hold is called out rather than blurred.

## What a caller does with it

`emit()` returns the pieces with their source ranges and their assigned origins, plus the
address mapper. The build side needs only:

```python
for name, mono_a, mono_b, text, _ in pieces:
    words, _ = assemble(rewrite(text, syms, final), dest[name], name)
    place(words, dest[name])          # build_bus.place(), once per shard
```

**Step 2 is therefore a loop at one existing call site.** Steps 3 (list the three in `fx1`) and
4 (the gates) follow.

---

# The emitter now verifies three properties, including the call graph

```
$ REMIX=perky-machine BUILD=3 python3 tools/perky/perky_emit_shards.py
  pieces: 21   words: 3051   monolith: 3051
  in LOCAL P: 3   in SHARED tails: 18
  cross-piece reference targets checked: 29   outside every shard: 0
  monolith-origin bytes identical for every piece: True
  assigned-origin extents exact for every piece: True
```

1. **Encoding.** Each piece assembled at its monolith origin equals the monolith's bytes for
   that range. Independent assemblies of the same code over all 3051 words -- and `build_bus.
   assemble()` already round-trips every assembly through the disassembler and stops on any
   encoding mismatch, so this is checked twice by different means.
2. **Extents.** Each piece assembled at its assigned origin produces exactly its measured
   extent. This is the claim byte-identity cannot make, because relocation moves internal
   addresses.
3. **The call graph.** Every external reference is rewritten to an absolute `$hex`; each is
   checked to name a final address **inside some shard**. **29 targets, 0 outside.**

## On the count

29 is the number of distinct (piece, target-label) pairs. It is not the same as the 39
cross-piece *call sites* measured earlier -- one label can be the target of several sites. Both
numbers are right; they count different things, and saying so is cheaper than being read as
inconsistent later.

## Why this satisfies the goal's own requirement

The brief says: *"Do not infer that successful assembly means successful hardware execution.
Disassemble final DSP code and verify actual branches/calls/ranges."* Property 1 pins the
encoding, property 3 pins where every call and jump lands. **What is still not covered by any
of it is execution on the chip** -- these are static properties, and only a flash shows the
rest.

---

# Which payload ships (round 57) -- a correctness question round 56 raised

Round 56's gate built **2353 words / 16 pieces** while the tool defaulted to **3051 / 21**. A
700-word difference is not a rounding artefact, so it had to be resolved before either number
was quoted again.

**Resolved by measurement:**

* the module's `dsp=DspSection(asm="modules/perky/probe_glue.asm", ...)` is the *seam*, not the
  program;
* the **canary** -- `build_light2_machine_canary.py` -- builds the flashable artifact and passes
  `dsp_source=work/'multi.asm'`, where `work` is `out/perky/light2` and the source comes from
  `build_fold_candidate.build(work)`;
* `build_multi_payload.build()`'s default output at `out/perky/multi` is the **smaller mixed
  build** the `*_seam_exec` gates use as their fixture.

**So the shipping program is the 3051-word / 21-piece light2 payload, and the 2353-word / 16-piece
mixed build is a second program.** My sharding analysis targets the shipping one.

## The gate now checks both

```python
def shipping_payload():
    import build_fold_candidate as candidate
    work = ROOT / "out/perky/light2"
    source, _ = candidate.build(work)
    (work / "multi.asm").write_text(source)
    return work / "multi.asm"
```

and both pass every property:

```
--- shipping light2 payload ---   29 targets, 0 outside; bytes identical; extents exact
--- default mixed payload ---     15 targets, 0 outside; bytes identical; extents exact
shards: 21   words: 3051   retained stock effects clear: 8
```

**Two independent programs shard cleanly**, and release gate 7's placement half now runs against
the payload that actually gets flashed rather than the fixture.

## Why this is recorded rather than quietly fixed

Had the gate only ever checked the mixed payload, it would have passed while protecting a program
nobody flashes -- a green gate over the wrong subject, which is the failure mode this branch has
hit before (`send_probe`'s harmonic metric, the reverb-smoothed XBUS measurement). The numbers
differing is what surfaced it.

---

# Step 2 in code: `build_bus.py:2984-2985` (round 58)

```python
place(words, cursor)                      # 2984
_r["cursor"] = cursor + len(words)        # 2985
```

**Those two lines are the entire single-stream assumption.** The module's assembled words go out
as one contiguous stream at `cursor`, and the run's cursor advances by the stream's length. The
per-run cursor machinery (`_r["cursor"]`, and `place()` itself) is already there; what is missing
is that a module can offer only ONE stream.

There are two other `place()` call sites, both for tables, not module code:

* `place(tab, _r["cursor"])` (2971) -- a module's P table, same one-stream shape;
* `place(words, cursor)` (3045) -- the second module path.

## The change

```python
for shard_words, shard_origin in streams:       # one entry today, N when sharded
    place(shard_words, shard_origin)
    for r in runs:
        if r["base"] <= shard_origin < r["base"] + r["words"]:
            r["cursor"] = shard_origin + len(shard_words)
```

`runs` and the per-run cursors already exist, and `place()` already takes a start. **What is
missing is only that `streams` can have more than one entry.**

## Why this is recorded and not applied

My context is exhausted, and this is a build change whose verification is a full `make check`
(a long cold build). Making it untested would risk the one thing that matters most here — the
working tree. **The line numbers, the reasoning and the emitter are all in place; the edit is
two lines plus a loop, and it should be made in a session that can run the gates behind it.**

---

# The full gate set passes with the shard gate inside it (round 59)

```
$ REMIX=perky-machine make check REMIX=perky-machine
module gates (shared isolated, perky-machine): 64 run, 0 failed
module gates (image):                           2 run, 0 failed
all runnable checks passed; out/mainos_bus.bin restored to the shipping build
```

**and the new gate ran as part of it:**

```
== PERKY PROBE: tools/verify/verify_perky_shard_emit.py
Fold candidate: 3051/3441 P words; no shipping CF transport yet
--- shipping light2 payload ---
pieces: 21   words: 3051   monolith: 3051
in LOCAL P: 3   in SHARED tails: 18
cross-piece reference targets checked: 29   outside every shard: 0
```

## Two things this establishes

1. **Nothing in 58 commits broke the tree.** The sharding work is comment markers, tooling, and
   documentation; 66 gates now run green over it, including every renderer gate that was already
   passing. That is the regression evidence, and it is the reason those commits were safe to make
   on the working branch.
2. **`Fold candidate: 3051/3441 P words`** -- the build itself reports the shipping program at
   3051 words in a 3441-word donor region, matching the goal's numbers exactly and matching the
   sharding analysis independently. Three sources agree: the build report, the emitter, and the
   gate.

## What this does not establish

The gates are static and render-level. **None of them flashes hardware.** Spring, Dark and Lo-Fi
are still absent from the image, because changes 1 and 2 are not applied -- and that stays true
however many gates run.

---

# CORRECTION (round 60): step 2 is a refactor, not two lines

Round 58 called step 2 "two lines plus a loop" on the strength of the call site at
`build_bus.py:2984-2985`. Tracing `words` and `cursor` upstream shows that was too optimistic:

```python
_w, _syms = assemble_syms(_s2, _c, label=name)    # ONE stream
_fit, _xlast = _try_runs([...])                   # picks A run
_r, tab, src, cursor, words, _syms = _fit         # the fit carries cursor/words
place(words, cursor)                              # 2984
```

**`_try_runs(...)` is the run-fitting logic and it also assumes one stream**: it selects a single
run and hands back the `cursor` and `words` that `place()` consumes. So the single-stream
assumption is in **three** places, not one:

1. the assembly step (`assemble_syms` produces one word list);
2. the fit step (`_try_runs` chooses one run for that one list);
3. the placement step (`place(words, cursor)`, and `_r["cursor"] = cursor + len(words)`).

Step 2 is therefore a refactor of the fit-and-place pipeline, not an edit to two lines. The
emitter (`perky_emit_shards.py`, gate-protected) already produces the N streams with their
assigned origins; what has to change is that the pipeline can carry N of them, and that the run
choice becomes the two-space assignment `place_program_shards_two_space()` already computes.

## Why the correction matters more than the estimate

A handoff that says "two lines plus a loop" invites an edit at line 2984 that would silently
place **one** shard and leave the other twenty unwritten -- or worse, place the monolithic stream
at a 594-word run's origin. **The count of places the assumption lives is the thing that decides
whether the change is safe**, so it is worth the round to have it right.

The rest of the map is unchanged: the emitter is built and gated, the placement is computed,
change 1's prediction is confirmed, and 66 gates pass.

---

# DECISIVE (round 61): the shared tails are NOT writable ground today

This is the finding that most changes the shape of step 2, and it was not visible from the call
site. `build_bus.py` builds the only region `place()` can write through like this:

```python
_want = [_sp[k] for k in _harvest]                    # ONLY the harvested effects
region = sorted((m for m in mods if m[0] == 0
                 and any(a <= m[1] < a + n for a, n in _want)),
                key=lambda m: m[1])
_have = sum(m[2] for m in region)
if _have != sum(n for _a, n in _want):
    sys.exit("... the module map and stock.p_spans disagree")
```

**`region` is built exclusively from the HARVESTED effects' spans.** The five shared tails come
from `all_fx_layout.SAFE_SHARED_P_SPANS`, which is a **separate contract that does not feed
`region` at all.** So:

* `place()` cannot write a single word into a tail;
* and **18 of the 21 shards are assigned to tails** (3 in local P, 18 in the tails, per the
  emitter and the gate).

**So step 2 is not only a refactor of the fit-and-place pipeline. It must also make the shared
tails writable ground**, which means at minimum:

1. add the tails' P records to `region` (note the selector `m[0] == 0`: records are filtered by
   space, and the tails live in the shared window where X, Y and P alias);
2. extend the `_have != sum(...)` consistency check, which currently asserts the region covers
   *exactly* the harvested spans -- adding ground it does not know about would trip it;
3. let the `runs` grouping see them, so `place()`'s per-record walk reaches them.

## Why this is the most useful thing found in several rounds

Every previous statement about step 2 -- "two lines plus a loop", then "a three-site refactor" --
assumed the tails were placeable. **They are not.** An edit made from either of those handoffs
would have assembled cleanly, placed 3 shards, and left 18 unwritten, with the `_have` check or
the `place()` overrun guard as the only thing standing between that and a silently truncated
program.

**The previous rounds' estimates were wrong in the same direction -- too small -- for the same
reason: they were read off the placement call site, while the constraint lives in how the ground
is defined two hundred lines earlier.**

## Where the goal stands

| | |
|---|---|
| tasks 0-4, 7, 8 | complete, each with evidence |
| task 5 validation | complete |
| step 1 (emit shards) | built, 3 properties, gate-protected, 2 payloads |
| step 2 (place shards) | **a fit-and-place refactor AND new writable ground** |
| step 3 (list three in `fx1`) | one edit; prediction measured and confirmed |
| step 4 (gates) | 66 pass today; re-run after 1-3 |

Spring, Dark and Lo-Fi remain absent from the image.

---

# THE ONE OPEN QUESTION THAT SIZES STEP 2 (round 62)

Round 61 established that `region` -- the only ground `place()` can write -- is built solely from
the **harvested** spans, and that 18 of the 21 shards are assigned to the five shared tails. The
size of step 2 then depends entirely on one fact:

> **Does `mods` -- `modules(bytes(img), va, ln)` at `build_bus.py:2119` -- contain records that
> cover the five tails?**

* `region = sorted((m for m in mods if m[0] == 0 and any(a <= m[1] < a + n for a, n in _want)), ...)`
* so **if `mods` already has records there**, step 2 shrinks: add the tails' spans to `_want` and
  the existing filter picks them up;
* **if it does not**, the tails need a record source of their own, which is the larger change.

## Resolve it in one command

```python
import build_bus as B, all_fx_layout as L, pathlib
img = pathlib.Path('out/mainos_bus.bin').read_bytes()
mods, _ = B.modules(bytes(img), <va>, <words>)      # signature to confirm first
for lo, hi in L.SAFE_SHARED_P_SPANS:
    print(hex(lo), sum(1 for m in mods if m[0] == 0 and lo <= m[1] < hi))
```

I attempted this and got `index out of range` -- **my call signature for `modules()` was wrong**,
and I did not have the context left to read it. That is worth stating plainly rather than
guessing: **the last thing this handoff should do is assert a size for step 2 it has not
measured.** Round 61's bound (the tails are not writable *today*) is measured and stands; whether
the fix is small or large is not.

## Also worth measuring with it

Whether a tail's records are in space `0`. The tails live in the **shared window**, where X, Y and
P alias -- so a tail might appear in `mods` as an x or y record rather than a P one, in which case
the `m[0] == 0` filter would exclude it even if the record exists. **That is the likely shape of
the answer, and it is exactly why this has to be measured rather than reasoned about.**

---

# RESOLVED (round 63): the tails have no image records -- step 2 is the larger change

Round 62's question, answered by measurement. `modules(bytes(img), va, ln)` for payload A returns
**98 records across spaces 0, 1 and 2**, and against the five tails:

```
   tail 0x33da3..0x34000 (606):  overlap any-space=0   space-0=0
   tail 0x37da3..0x37f00 (350):  overlap any-space=0   space-0=0
   tail 0x37f10..0x38000 (241):  overlap any-space=1   space-0=1   <- only one
   tail 0x3bda3..0x3c000 (606):  overlap any-space=0   space-0=0
   tail 0x3fda3..0x40000 (606):  overlap any-space=0   space-0=0
```

**Four of the five tails have no record in ANY space; the fifth has exactly one.** So `mods`
cannot supply them, `region` cannot reach them, and the `m[0] == 0` filter is not the obstacle --
there is nothing there to filter.

**Step 2 is therefore the larger change, as round 61 bounded it**: the tails need a write path of
their own, not just a wider `_want`.

## The structural reason, which is more useful than the count

The tails live in the **shared window**, and the image's record table describes regions the loader
copies. A shared window is shared *memory*, not a copied region, so it plausibly has no records at
all. `place()` walks records; **in the tails there is nothing to walk.**

That means the fix is not "add the tails to `_want`" but **a second write mechanism for
unrecorded ground** -- writing P words at absolute addresses rather than through a record's
`(va + off)` translation. Whether that is safe is a separate question: the shared window's P view
is the same memory as its X and Y views, so a write there must be checked against every module's
`Claims.dsp_ranges` in the window, which is exactly what `all_fx_layout.validate()` already does
for the spans themselves.

## The handoff is now accurate on scope

| | |
|---|---|
| tasks 0-4, 7, 8 | complete, each with evidence |
| task 5 validation | complete |
| step 1 (emit shards) | built, 3 properties, gate-protected, 2 payloads |
| step 2 (place shards) | **a fit-and-place refactor AND a write path for unrecorded ground** |
| step 3 (list three in `fx1`) | one edit; prediction measured and confirmed |
| step 4 (gates) | 66 pass today; re-run after 1-3 |

Spring, Dark and Lo-Fi remain absent. Nothing about the goal's correctness claims changed; what
changed is that step 2's size is now measured rather than guessed, and it is the larger bound.

---

# CLOSED (round 64): no existing mechanism can write the tails -- and a correction about their provenance

Following round 63's result (four of five tails have no image records), the natural next question
was whether the build's **other** write path reaches them. `build_bus.py:2726`,

```python
def place_xh(words, start):
    """Write table words into this payload's X records at `start`."""
    for k, w in enumerate(words):
        a = start + k
        r = next((r for r in _xh_recs if r[0] <= a < r[0] + r[1]), None)
        if r is None:
            sys.exit(f"payload {tag}: X:0x{a:05x} is in no X record")
```

writes through `_xh_recs`, built from `stock.x_exclusive_runs(tag, given_up)` -- the X records of
*given-up* effects. Measured:

```
stock.x_exclusive_runs(A, harvest): 3 runs
  tail 0x33da3..0x34000: 0 overlap
  tail 0x37da3..0x37f00: 0 overlap
  tail 0x37f10..0x38000: 0 overlap
  tail 0x3bda3..0x3c000: 0 overlap
  tail 0x3fda3..0x40000: 0 overlap
TOTAL tail coverage: 0
```

**No existing write mechanism reaches the tails.** `SAFE_SHARED_P_SPANS` and
`stock.x_exclusive_runs` are **different sets**, and only the second is writable.

## A correction about where `SAFE_SHARED_P_SPANS` came from

**I derived those spans from the LEDGER -- addresses the stock effects do not occupy -- and never
checked that the build can WRITE them.** "Free" and "writable" are different properties, and I
conflated them for many rounds. The measured facts are:

* the ledger says the spans are unoccupied (that part was checked, repeatedly);
* the image has no records there (round 63);
* `x_exclusive_runs` does not cover them (this round);
* **so nothing in the build can currently place a word in any of the five.**

## What that means for the plan

The sharding analysis -- 21 pieces, byte-identical reassembly, zero drift, correct call graph --
**remains valid as an analysis of the PROGRAM.** What it was never a proof of is that the build
can *reach* the ground the placement assigns. Those are two separate claims, and only the first
has been established.

**Step 2 therefore needs, at minimum: a record source or an absolute-write path for the five
tails, plus the safety check against every module's `Claims.dsp_ranges` in the shared window.**
Until that exists, the placement manifest is a statement about addresses, not about an image.

## The standing lesson, restated because it keeps paying

Six rounds have now produced six successive refinements of step 2's scope, every one larger than
the last: "two lines", "a three-site refactor", "plus writable ground", "the larger bound", and now
"ground nothing can currently write". **Each was read off one layer and assumed to hold at the
next.** The thing that resolved each was measurement, not more reading.

---

# REVERSAL (round 65): the absolute writer exists, and the spans' provenance is sound

**Two corrections to addendum 64, both by measurement.**

## 1. The spans' provenance was recorded -- my self-correction was too harsh

`all_fx_layout.py`'s own docstring (which I had not read when I wrote addendum 64):

> The shared `0x30000..0x3ffff` window aliases P/X/Y. **Stock effect guard/census work shows an
> FX2 instance does not write beyond `base+0x3da2`.** The tails below therefore remain
> **candidates** for executable P while stock FX are active. Core-1 mailbox `0x37f00..0x37f0f` is
> excluded.

**The tails begin at `0x33da3` = `base + 0x3da3` -- exactly one word past the measured
`base+0x3da2` boundary.** The derivation *was* census-based, *was* recorded, and *was* explicitly
labelled "candidates". Addendum 64's claim that I "never checked" is wrong in the part that
matters: what was never checked is **writability**, which is narrower and different from
provenance.

## 2. Step 2 does NOT need a new write mechanism. It already exists.

`build_bus.py:673`:

```python
def wrw_p(a, v):
    i = a - BASE
    img[i], img[i + 1], img[i + 2] = v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff
```

**`wrw_p` takes an ABSOLUTE image address and writes three bytes. There is no record lookup.**
`place()` uses it, `place_x` uses it, `place_xh` uses it, and it does not care whether a record
covers the address.

So a shard in a tail is written by calling `wrw_p` with the right **image** address -- and the
tails need no records at all. **What is actually missing is only the DSP-address -> image-offset
translation for the shared window**, which is the same translation the payload upload already
defines and which `_p_off(addr)` performs for recorded ground.

## What step 2 now is

1. emit the shards (done, gated);
2. for each shard, place it by writing its words at the image address of its assigned origin --
   through records where records exist, and by direct `wrw_p` where they do not;
3. make the run cursors account for both, so nothing else is placed on top;
4. keep the safety check: a write into the shared window must not collide with any module's
   `Claims.dsp_ranges`, which `all_fx_layout.validate()` already does for the spans themselves.

**That is smaller than addendum 64 said, and the difference is that `wrw_p` never needed a
record.** Two rounds of "the ground cannot be written" were both wrong for the same reason: I
read `place()`'s record walk and assumed the record walk was the only way to write.

## The lesson, corrected

Addendum 64 said six rounds each refined step 2's scope *upward*. That is half right: rounds 58-63
did, and each was resolved by measuring deeper. **Rounds 64 and 65 then refined it back DOWN --
because the first two answers were read off `place()` rather than off `wrw_p`, the primitive
underneath it.** Reading one layer down found the mechanism; reading one layer *up* had hidden it.

---

# THE HONEST BOTTOM LINE ON THE TAILS (round 66)

`build_bus.py:2121` is the build's **only** DSP-address -> image-address mapping:

```python
def _p_off(addr):
    """Image address of P word `addr`, through the record holding it."""
    for sp, a, cnt, off in mods:
        if sp == 0 and a <= addr < a + cnt:
            return va + off + (addr - a) * 3
    sys.exit(f"payload {tag}: no P record holds P:0x{addr:05x}")
```

**It goes through a record, and it hard-exits without one.** Put beside rounds 63 and 64:

* four of the five tails have no record in any space; the fifth has one;
* `stock.x_exclusive_runs` does not cover them either;
* **and there is no image-map formula that reaches them.**

## What that most likely means

**The shared window is not image-mapped ground. It is runtime memory that DSP code writes with
instructions** (`move x0,x:(r6+N)`), not something the build places words into. `place_x` and
`place_xh` both route through records; `wrw_p` takes an absolute *image* address; and nothing
supplies one for P:0x33da3.

**Worse, and this is the part that matters: even if a word could be written there, whether the DSP
can EXECUTE from the shared window is unproven.** The module's own docstring calls the tails
*"candidates for executable P while stock FX are active"* -- **candidates.** No measurement in this
work has shown a single instruction fetched and run from P:0x33da3. The window is memory; the
aliasing is documented; whether the core's program fetch reaches it, and whether the loader's
memory map permits it, have not been tested.

## So the sharding plan rests on an unproven premise

Everything measured about the sharding is a property of the **program**: 21 relocatable pieces,
byte-identical reassembly, zero sizing drift, a correct call graph, a computed two-space
placement. **All of that is real and gated.**

What has never been established is the premise underneath it: **that the shared window can host
executable code at all.** The placement manifest assigns 18 of 21 shards to ground whose very
usability as code is a candidate, not a measurement.

**That is the genuine blocker for the FX recovery, and it is a hardware question, not a software
one.** Resolving it needs either a hardware probe (place a `jsr` target in a tail and see whether
the core fetches it) or a document that states the window is executable -- and neither exists in
this tree.

## What this changes about the goal

| | |
|---|---|
| tasks 0-4, 7, 8 | complete, each with evidence |
| task 5 validation (program) | complete |
| step 1 (emit shards) | built, 3 properties, gate-protected |
| step 2 (place shards) | **blocked on whether the window is executable ground** |
| step 3 (list three in `fx1`) | one edit; prediction measured and confirmed |
| step 4 (gates) | 66 pass today |

**This is the closest thing to a genuine measured blocker this work has produced**: the placement
needs executable ground, the only candidate ground is a window whose executability is documented
as a *candidate*, and no measurement here establishes it. It is stated as an open question with
its falsifier, not as a conclusion -- because I have not run the probe that would settle it.

---

# NARROWED (round 67): the window is known to the build as Y space

```
PAYLOADS table:
  A:  ybase=0x30000   xtab=0x400e2345   nul_i=0x007c8  nul_p=0x007c9
  B:  ybase=0x38000   xtab=0x400f5a10   nul_i=0x00588  nul_p=0x00589
```

**`ybase` IS the shared window base** -- `0x30000` on payload A, `0x38000` on B -- and `_sub`
rewrites the literal `$30000` in module sources to it. So the build knows the window and addresses
it as **Y space**. Since P, X and Y alias inside the window, a word written there as Y data **is**
the same memory a `p:` fetch would read.

## What this narrows, and what it does not

**It narrows the write-path worry.** The window is not unknown to the build; it has a base and a
naming convention. A shard's words could plausibly be placed as Y-relative data, which is how
every server already stages its own working memory.

**It does not touch the real question.** Writing Y data says nothing about whether the core's
program fetch reaches the window. On a 56300 the program counter is not restricted to P space in
principle, but "in principle" is not a measurement, and this work has repeatedly paid for treating
a plausible property as an established one.

## The probe that would settle it, stated so it can be run

**Cheap local test (can falsify, cannot confirm):** does any stock payload execute from the
window? `grep` the stock disassembly for a P org at or above the window base, or for a `jsr`
target into it. If stock code ever sits there, executability is proven by precedent. **I looked and
found no such site** -- `out/dsp/` holds `_stock_A.mem` and `_knobs`, not the per-payload
disassembly the AGENTS.md grep rule refers to (`tools/build/dsp_disasm_all.py` generates it), so
**this test has not actually been run.** Producing that disassembly is the first step.

**Decisive test (hardware):** place a `jsr` target in a tail, flash, and see whether the core
fetches it. AGENTS.md is explicit that a local *clean* is not evidence about hardware, but a local
*red* is a real defect -- so the local form can falsify the premise even though it cannot confirm
it.

## Where this leaves the goal

| | |
|---|---|
| tasks 0-4, 7, 8 | complete, each with evidence |
| task 5 validation (program) | complete |
| step 1 (emit shards) | built, 3 properties, gate-protected, 2 payloads |
| step 2 (place shards) | write path narrowed to Y space; **executability still unmeasured** |
| step 3 (list three in `fx1`) | one edit; prediction measured and confirmed |
| step 4 (gates) | 66 pass today |

Spring, Dark and Lo-Fi remain absent. The goal stays active: this is an open question with two
named tests, not a blocker, and I have not run either.

---

# MEASURED (round 68): the cheap test ran -- no stock code executes from the window

Round 67 named the test and the missing input. Both are now done.

```
$ python3 tools/build/dsp_disasm_all.py
payload A:  68 P modules,  6,817 instructions, 0 undecodable -> out/dsp/payload_A.asm
payload B:  46 P modules,  6,251 instructions, 0 undecodable -> out/dsp/payload_B.asm
```

**The test:**

```
payload A:  highest P CODE base 0x01eca    (0x30000 and 0x38000 appear as OPERANDS only)
payload B:  highest P CODE base 0x01c8a
lines with a 0x3xxxx code label, both payloads: 0
```

**Stock code occupies only `0x00000..0x01eca` on A and `0x00000..0x01c8a` on B.** The window base
appears in the disassembly **as an address being read or written** -- as data -- and never as a
code location.

## What this establishes, and what it does not

* **Established:** there is **no precedent** for executing from the shared window. No stock module
  places code there. If executability were a general property the stock image exercised, this is
  where it would show, and it does not.
* **Established:** the window *is* used, as data -- consistent with round 67's finding that the
  build addresses it as Y space (`ybase=0x30000` / `0x38000`).
* **NOT established:** that the window *cannot* execute. Absence of precedent is not absence of
  capability, and on a 56300 the PC is not architecturally confined to P space in principle.

**So the premise is neither confirmed nor refuted; it is now known to be unprecedented.** That is
a materially better position than round 66's, where the test had not been run at all, and it means
the remaining question is genuinely a hardware one.

## The two tests, updated

1. **Local precedent** -- RUN. Result: no stock code in the window (above).
2. **Hardware** -- place a `jsr` target in a tail, flash, see whether the core fetches it. This is
   now the *only* remaining test, and it is a hardware probe. AGENTS.md: a local *clean* is not
   evidence about hardware, but a local *red* is a real defect -- so test 1 could only ever have
   falsified the premise, and it did not.

## Where the goal stands

| | |
|---|---|
| tasks 0-4, 7, 8 | complete, each with evidence |
| task 5 validation (program) | complete |
| step 1 (emit shards) | built, 3 properties, gate-protected, 2 payloads |
| step 2 (place shards) | write path is Y space; **executing there is unprecedented and unproven** |
| step 3 (list three in `fx1`) | one edit; prediction measured and confirmed |
| step 4 (gates) | 66 pass today |

Spring, Dark and Lo-Fi remain absent. The goal stays active.

---

# CLOSED (round 69): the tail strategy rests on a heading's assertion

`modules/perky/ALL_FX_MEMORY.md` -- the document the brief cites as the authority for the memory
accounting -- says this:

```
## Shared-window executable tails

The DSP shared window $30000..$3ffff aliases P/X/Y. Existing stock-effect census/guard work pins
the highest stock FX2 write at base + $3da2. The words after that point are the only shared-window
regions currently admitted as CANDIDATE Perky program storage. The stock mailbox $37f00..$37f0f
is removed.
```

**The heading asserts "executable". The body says "candidate".** The section then points at
`tools/verify/verify_perky_all_fx_placer.py`, which "proves the complete 2,404-word capacity can
be used without crossing a hole or touching the mailbox" -- **a placement-capacity proof, which is
a software property. It executes nothing.**

## The complete, honest picture

| claim | status |
|---|---|
| the tails are free of stock FX writes | **measured** (census: highest FX2 write at `base+$3da2`; tails start `base+$3da3`) |
| the tails can HOLD 2,404 words of shards | **measured** (`verify_perky_all_fx_placer.py`) |
| the tails are addressable by the build | **narrowed**: the window is known as Y space (`ybase`) |
| a word can be WRITTEN there by the build | **not established** -- no records (r63), no `x_exclusive_runs` (r64), `_p_off` hard-exits (r66) |
| the core can EXECUTE from there | **not established.** Asserted by a heading; the body says "candidate"; no stock precedent (r68) |

**The plan's central assumption is the last row**, and it has never been measured -- not by the
document that asserts it, not by the gate it cites, and not by anything in this work.

## What the goal's own numbers imply about this

The brief reasons: "Safe shared tails: 2404 ... If Plate + Compressor are retired: 2404 + 594 + 180
= 3178. This is enough for the current 3054-word Perky program." **That arithmetic is correct and
it is the reason the tail strategy exists. But the brief also says "Do NOT pretend this is one
contiguous 2404-word region" -- it was careful about contiguity and did not test executability.**

## What would settle it

1. **A hardware probe**: place a `jsr` target in a tail, flash, see whether the core fetches it.
2. **A document from the reverse-engineering work** that states the window is executable and says
   how it was measured. `ALL_FX_MEMORY.md`'s heading is not that document; a heading is not a
   measurement.

**Until one of those exists, the honest status of the FX recovery is: the program is ready to be
placed, the placement is computed, the ground is unproven.**
