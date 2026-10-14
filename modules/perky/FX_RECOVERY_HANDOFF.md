# Current two-voice checkpoint (13 October 2026)

> **Historical FX-recovery handoff (13 October 2026), not current firmware instructions.** This document
> records an earlier PERKY development state and retains its original
> measurements, commits and failure analysis as evidence. The working MKII
> release is [PERKY4S](PERKY4S_RELEASE.md) (DSP, T1/T5,
> Fold1/Fold2/Simple/Complex, 12 retained stock FX). Its production shared-P
> budget has **zero free words**. Do not continue the old "next step" or flash
> plan here as if it were the present project status.


See [TWO_VOICE_CHECKPOINT.md](TWO_VOICE_CHECKPOINT.md) and [TWO_VOICE_MEMORY.md](TWO_VOICE_MEMORY.md). Fragmented P installation and mandatory FX recovery now have executable local proofs. Earlier status claims below are historical; startup clearing and shared/private call placement were real defects.

---

# FX recovery — handoff

## STATUS AT A GLANCE (round 128) — READ THIS FIRST

**Pick up at: STEP 2.** Everything else the goal names is done and gated. Step 2 -- integrate the
already-proven sharding -- is the only substantial code left, plus the Spring/Dark/Lo-Fi placement it
buys.

### Step 2 is now ONE EDIT, fully specified (rounds 120-127)

**Not a "substantial refactor".** Six rounds of reading reduced it to a single insertion, with every
number measured.

| piece | state |
|---|---|
| the **placement** | ✓ already computed -- `perky_emit_shards.emit()` calls `place_program_shards_two_space()` (r120) |
| the write path | ✓ needs **no change** -- `build_bus.place()` already spans several records, "cut at each record boundary" (r124) |
| the record **format** | ✓ `w24(space) w24(ADDR) w24(COUNT)` + `count*3` bytes inline (r121, r125) |
| the record **order** | ✓ **`"ac"`** on BOTH payloads -- measured: `ca` dies after one record; `ac` consumes 79,557/79,563 (A) and 77,055/77,061 (B) (r125) |
| **room** | ✓ **30,460 B** between payload B's end (`0x401086f4`) and `LOADER_AT` (`0x4010fdf0`); a 3,051-word tail needs **9,162 B** -- fits 3.3:1 (r126) |
| who reads the records | the **stock DSP uploader**, NOT octabam's loader (`loader.S` carries a payload-level table) -- **so the edit stays in the blob** (r127) |

**The edit:** insert, before the terminating record and in **both** payloads,
`w24(0) w24(tail_addr) w24(count)` followed by the shard's bytes. Then `place()` finds it, `_p_off`
resolves it, and the shard lands.

**The one risk not measured:** whether the **stock uploader** tolerates a record at an `addr` no stock
record covers. **INFERRED that it does** (an `addr` per record is that field's whole purpose), **not
measured.** Cheapest way to settle it: insert a probe record at a known-good but unusual DSP address
and read the words back with the probe recipe below -- **a local test, and the natural first half of
the edit.**

**What is NOT known:** where in the build the blob is assembled, so the insertion has a home. **Round
122 said `platform_build.build()`; round 123 retracted that** -- it is the *loader* builder and takes
the payload as input ("payloads built elsewhere"). **The writer is upstream, on `build_bus.py`'s side.
Lead, not finding.**

### Delivered and gated

| | |
|---|---|
| baseline frozen | tag `perky2v-hw-baseline` (annotated `0080b4e1` -> commit `fc438e03`), archived |
| SRC page order | `TUNE / DECAY / ALGO / PAR1 / PAR2 / MODE`, counts 128/128/4/128/128/3 |
| engines reference-qualified | Fold1, Fold2, Simple, Noise/Tone -- both cores, 32000 frames, dirty memory |
| Noise/Tone authenticity | resolved against the ARM captures; the shipping path IS the authentic seam |
| output gain | **measured at the seam**, trimmed -18.06 dB by exact left shift; all 5 item-4 numbers recorded |
| P/X/Y ledger | **explicit and proven disjoint** -- P 5 spans/0 overlaps, X 3/0, Y 1/0 |
| packaging round-trip | **PASSES** on a regenerated matched set (card decodes to the ELEK byte for byte) |
| candidate record | all **15 item-8 fields** + all **5 item-4 numbers** in `~/Downloads/PERKY2V_milestone_manifest.txt` |
| gates | **80 registered; `make check` = 332 assertions PASS, 8 SKIP, 0 FAIL** |
| flashable artifact | `~/Downloads/PERKY2V_milestone.{syx,bin}` -- `685e5105...` / `4ba4d72c...`, unchanged since r92 |

### NOT delivered: Spring, Dark and Lo-Fi (goal items 6-8)

**These three are what the rest of this file is about.** The mechanism to restore them is **proven
end-to-end as an analysis** (r61-88): 21 relocatable pieces, byte-identical reassembly against the
working monolith, zero sizing drift, a verified call graph, and a placement leaving their 2,667 words
untouched -- **but not integrated.**

**Step 2's hard part, precisely (r88):** the tails have no records in the image's P record table, so
nothing can write them. **A shared-window address IS loadable** -- payload A carries two in-window
records, so the format permits it and there is a template. **But payload B has none, and T1 lives
there.** So the work is: add P records for the tails to **both** payloads, then the fit-and-place
refactor, then call `place_program_shards_two_space()`.

### What rounds 86-119 added

* **Twelve gates** that existed and had never run, registered (64 -> **78**). The odd-address gate's
  teeth were proven both ways.
* **Three gates labelled "stale" in r81/96 -- that label was too broad.** r113 showed
  `verify_perky_machine_boot` has stale *defaults* only; the canary invokes it with explicit paths and
  **it needs no project fixture**. Registered, 76 -> 78.
* **The version-field defect: diagnosed, fixed, patched, and the patch verified from pristine.** The
  vendored tool wrote the ELEK version `ljust` where the OS reads it `rjust`; `ELEK_VERSION_OFF = 0x0D`
  is the arithmetic that settles it. `make eft-repatch` now exists (the `dsp-repatch` analogue) and is
  **proven inert** (bit-identical image, 332 PASS).
* **A provenance gate** for the brief's "no mismatch between HEAD, manifest and artifact" -- written
  with its teeth proven both ways after **three** ways it could have passed while checking nothing.
* **A real defect found and fixed on the producer side:** `out/platform/{layout.json,runtime.raw}` are
  **inputs** the canary reads and `make bus` rewrites, so an image and its platform files could silently
  disagree. The canary now stages the files it read.

### One external input, still

**`OT_PROJECT`** -- a stock Octatrack project -- is required by the canary, the odd-address audit, the
item-4 A/B and `build_cf_final.py`. **It cannot be synthesized here** (`tools/hw/ot_project.py` only
reads/writes an existing project, and no Elektron byte may enter the repo).

**The boot gate is NOT on that list** (r113) -- it stops at the RTOS handoff. **The wrapper round-trip
is NOT either** -- it ran, and passes, on a regenerated matched set (r104).

### Two things only hardware can answer

1. **The ladder step that matches Perky** -- the loudness A/B in test step 9.
2. **Does A change pitch and D change decay on T1?** -- validates the SRC reorder's PAR1/PAR2 remap.

**Plus a third, cheap:** does the unit display `PERKY2V` correctly today? That settles the
version-field question (r101-105) in one flash.

---

## STATUS AT A GLANCE (round 85) — superseded, kept for history

**Delivered and gated — tasks 0, 1, 2, 3, 4, 7, 8 of the goal:**

| | |
|---|---|
| baseline frozen | tag `perky2v-hw-baseline` -> `fc438e03`, archived with provenance |
| SRC page order | `TUNE / DECAY / ALGO / PAR1 / PAR2 / MODE`, counts 128/128/4/128/128/3 |
| engines reference-qualified | Fold1, Fold2, Simple, Noise/Tone -- both cores, 32000 frames, dirty memory |
| Noise/Tone authenticity | resolved against the ARM captures; the shipping path IS the authentic seam |
| output gain | **measured** (no source-path error), trimmed -18.06 dB by exact left shift |
| P/X/Y ledger | corrected; **76 gates run, 0 failed** |
| flashable artifact | `~/Downloads/PERKY2V_milestone.{syx,bin}`; hashes unchanged across 85 commits |

**NOT delivered: Spring, Dark and Lo-Fi are still absent** (goal items 6-8). Everything below in
this file is about getting them back.

### What rounds 76-85 added

**Twelve gates that existed and had never run are now registered** (64 -> 76 gates, 0 failed): the
odd-address gate (teeth proven both ways), the two tail-budget gates `ALL_FX_MEMORY.md` cites as its
proof, and nine engine/seam gates -- including the four-engine proof that is task 3's core. Three
further candidates were found **stale** (they test an older architecture) and deliberately left
unregistered rather than made green.

**And one finding subsumes the rest: every remaining blocker converges on a single external input.**
`OT_PROJECT` -- a stock Octatrack project -- is required by the canary, the boot gate, the
executability probe and `build_cf_final.py`. It cannot be synthesized here (`tools/hw/ot_project.py`
only reads and writes an existing project, and AGENTS.md forbids an Elektron byte in the repo), and
**the canary cannot currently reproduce the shipped artifact without it.**

## Why it is hard, in three lines

Perky's DSP program is **3051 words** and can only occupy **one contiguous run**. Keeping SPRING
(1063) + DARK (1067) + LO-FI (537) leaves just PLATE (594) + COMPRESSOR (180) = **774 words
local**, so the program must be emitted as **shards** across those runs plus five **shared-window
tails** (2404 words). Capacity is fine -- 3054 vs 3178 -- **contiguity is the problem.**

## The state of the sharding

**PROVEN (all measured, all committed):** 21 pieces, markers balanced, zero unmarked content, none
over the 605-word cap; code is origin-independent at three origins; **zero** cross-piece relative
branches (39 transfers are absolute `jsr`/`jsrl`); a two-space placement computed; all 21 shards
reassemble **byte-identically to the monolith**; they assemble at their **assigned** origins with
exact extents and **zero sizing drift**; and the placement leaves Spring/Dark/Lo-Fi's 2,667 words
untouched. `tools/perky/perky_emit_shards.py` does all of this and is registered as a gate.

**NOT DONE — step 2, placing the shards, which is three things:**

1. **the fit-and-place pipeline** (`build_bus.py`: assembly produces one word list, `_try_runs`
   picks one run, `place(words, cursor)` writes it) must carry N streams;
2. **the shared tails are not writable ground today** -- `region` is built only from harvested
   spans, and the tails have no records (see rounds 61-67);
3. **`place_program_shards_two_space()` must be called by the build**, not just by a tool.

**AND ONE MEASURED RISK THAT DECIDES THE WHOLE APPROACH:** whether the DSP can **execute** from the
shared window. `ALL_FX_MEMORY.md`'s heading says "executable"; its body says "candidate"; no stock
code is placed there (payload A's highest P code base is `0x01eca`); and no measurement exists.
**A heading is not a measurement.** The probe is designed and its recipe is documented below.

## The order of work from here

1. step 2 above (write path + fit-and-place refactor);
2. list SPRING REV, DARK REV, LO-FI in `remixes/test/perky-machine/remix.py`'s `fx1`
   (**prediction already confirmed by measurement**: 8 retained effects -> 11, zero new collisions);
3. **Test A** (`dsp peek P <tail>`) -- are the shard's words actually in a tail?
4. **Test B** (`--dsp-pcwatch <shard entry>`) -- does the core fetch them? **zero hits is decisive**;
5. only then the hardware flash, and re-run all 66 gates on the sharded image.

**Requirements 3 and 4 also need a stock project fixture (`OT_PROJECT`), which is not present in
this worktree.**

---



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

---

# THE PROBE IS RUNNABLE LOCALLY (round 70) -- addendum 69 was too pessimistic

Addendum 69 concluded the executability question "can only be settled by hardware". **That is half
wrong: a local probe can FALSIFY it, and AGENTS.md says a local red is a real defect.**

## The instrument

* **`dsp_host` cannot do it.** `setup.sh:75` builds it at
  `vendor/dsp56300/build/source/dsp_host/dsp_host`, and its options (`-inst -trace -mem -pokey
  -peekx ...`) contain **no way to start execution at an arbitrary PC**. It runs the payload from
  its dispatch entry, which is not where a tail shard would run.
* **`ot_emu` can.** AGENTS.md documents `ot_emu --dsp-pcwatch`: it boots the real dispatcher under
  the ColdFire port and can watch where the DSP fetches. **That is the right instrument**, because
  the question is precisely "does program fetch ever reach the window".

## The probe, concretely

1. build an image whose Perky shards are placed in the tails (step 2 above -- the hard part);
2. run it under `ot_emu --dsp-pcwatch`, with a project that selects Perky on T1 and T5;
3. **look for any fetch with a PC in `0x30000..0x3ffff`.**

**A red is decisive:** no fetch into the window while Perky is selected means the shards there never
run, and the tail strategy is dead. **A green is suggestive, not proof** -- AGENTS.md is explicit
that a lock-step local run is a fuzz of hardware timing, not the timing, so a local clean is not
evidence that a hardware defect is absent.

## Why this matters for the plan

It means the blocking question is **not** "wait for a flash". It is "finish step 2 far enough to
run the probe" -- **and step 2's remaining work is the write path plus the cursor accounting, both
of which are now located.** The order is therefore:

1. implement the tail write path (rounds 63-67) and the fit-and-place refactor (round 60);
2. list SPRING/DARK/LO-FI in `fx1` (round 52's confirmed edit);
3. **run `ot_emu --dsp-pcwatch` and look for a fetch into the window** -- falsifiable locally;
4. only then the hardware flash.

**The executability question is step 3, not a precondition for steps 1-2.** That inverts addendum
69's framing, and it means the goal is not gated on hardware for the next stage of work.

---

# THE PROBE, MADE PRECISE (round 71) -- and a cheaper test that comes first

`ot_emu` is built (`out/emu/ot_emu`, Mach-O arm64). Reading its own header comment:

```
--dsp-pcwatch PC   ->  dsp pcwatch -> dsp n=<k> <executed>:<a1>:<a0>:<b1>:<b0>:<x0>:<x1>:...
--dsp-watch        ->  watchmem, folded to its cached alias (0x8xxxxxxx) before the compare
                       dsp peek <core> <X|Y|P> <addr> <len>  ->  reads memory (len <= 4096)
```

**`pcwatch` watches a SPECIFIC PC, not a range.** So "does the PC ever reach the window?" cannot be
asked directly -- but the question does not need to be asked that way:

## Test A (cheap, and it comes first): did the words ARRIVE?

After the build places shards in the tails:

```
dsp peek <core> P <tail address> <len>
```

**`dsp peek` reads P memory. If the shard's words are there, the write path works -- which settles
rounds 63-67's question directly and without executing anything.** If they are not, the write path
is broken and no execution question arises. **This is strictly cheaper than the execution probe and
it tests the prerequisite.**

## Test B (the execution probe): does the core FETCH the shard?

Place the shard, then watch **that shard's entry PC**:

```
--dsp-pcwatch 0x33da3        (or whichever tail address the shard's first instruction occupies)
```

run with Perky selected on T1/T5, and look for hits. **A hit means the core fetched that address;
zero hits means the code there never runs.**

* **Zero hits is decisive** -- the tail strategy is dead, and it is a local red, which AGENTS.md
  says is a real defect.
* **Hits are suggestive, not proof** -- a lock-step local run is a fuzz of hardware timing, not the
  timing. The final confirmation is still a flash.

## The order, updated

1. implement the tail write path and the fit-and-place refactor;
2. list SPRING/DARK/LO-FI in `fx1`;
3. **Test A**: `dsp peek P` -- are the shard's words in the tail?
4. **Test B**: `--dsp-pcwatch <shard entry>` -- does the core fetch them?
5. hardware flash.

**Steps 3 and 4 are both local and both bounded.** Neither existed in addendum 69, which treated
the whole question as hardware.

---

# THE PROBE RECIPE, DOCUMENTED (round 72)

`tools/emu/README.md` "The port on a project" gives the invocation, and `--dsp` is the flag that
enables the engine:

```sh
# 1. stage a card from a project fixture
.venv/bin/python3 tools/emu/ot_emu/stage_card.py PROJECT_DIR OCTABAM RIG --out out/card.img

# 2. run the image under the port, with the DSP, playing
out/emu/ot_emu --image out/mainos_bus.bin --card out/card.img --set OCTABAM --project RIG \
    --sequencer --internal-clock --frames 600 --load-ms 90000 --dsp --main-level 64 \
    [--mem-dump spans] [--poke-trig 2]
```

**So both tests use tools that already exist** -- `--dsp` for the engine, `--mem-dump` (Test A),
`--dsp-pcwatch` (Test B). No new tooling. `verify_analog_bassdrum_ui.py` is a working precedent for
staging a card and dumping DSP memory from a gate.

## What the two tests look like concretely

**Test A -- did the words arrive?**
Run the image with the shards placed, then read P memory at a tail address. In the batch form this
is `--mem-dump` over the tail spans; interactively it is `dsp peek <core> P <addr> <len>`.
* words present -> the write path works (settles rounds 63-67);
* words absent -> the write path is broken, and no execution question arises.

**Test B -- does the core fetch them?**
`--dsp-pcwatch <the shard's entry PC>`, with Perky selected on T1/T5, then look for hits.
* **zero hits is decisive** -- the tail strategy is dead, and it is a local red;
* hits are suggestive only -- final confirmation is a flash.

## What is still missing to run them

1. **step 2** -- the shards must actually be placed, which is the write path plus the fit-and-place
   refactor;
2. **a project fixture** -- an existing one can be reused (`verify_analog_bassdrum_ui.py` stages
   its own; the Perky gates use fixtures too).

**Neither is a new investigation. The probe is now a recipe, not a research question.**

---

# TWO CORRECTIONS to the probe recipe (round 73), both by reading the precedent

**Addendum 72 said `--mem-dump` runs Test A. That is wrong.**

`verify_analog_bassdrum_ui.py` builds its spans like this:

```python
spans = '0x40170f60,6322=part.bin;0x400d5f4c,4=page.bin;0x400bb7d0,4=setup.bin;0x80000830,1=live.bin;...'
```

**Those are ColdFire addresses (`0x40…`, `0x80…`). `--mem-dump` reads COLDFIRE memory, not DSP P
memory.** Test A -- "are the shard's words in the tail?" -- needs the **interactive**
`dsp peek <core> P <addr> <len>` over the pipe (documented at `main.cpp:112-120`), not a batch flag.

**And the precedent skips without a project fixture:**

```python
src = os.environ.get('OT_PROJECT')
if not src:
    print('[SKIP] Analog Bassdrum panel: set OT_PROJECT to a stock project fixture'); return
```

`verify_perky_probe_port.py` printed the same `[SKIP]` line during the round-59 `make check`, and
**no fixture is present in this worktree.** So the probe has a third requirement beyond the two
addendum 72 listed: *a stock project fixture*.

## The requirement list, corrected

| # | requirement | state |
|---|---|---|
| 1 | step 2: the shards actually placed | not done (write path + refactor located) |
| 2 | a stock project fixture (`OT_PROJECT`) | **not present in the worktree** |
| 3 | Test A via `dsp peek P` (interactive), not `--mem-dump` | mechanism corrected here |
| 4 | Test B via `--dsp-pcwatch <shard entry>` | as addendum 72 said |

## Why this is recorded rather than quietly fixed

Addendum 72's recipe would have been followed exactly and produced **a dump of ColdFire memory that
is silent about the tails** -- and the natural reading of that silence is "the words aren't there",
which would have condemned the tail strategy on the strength of a measurement that never looked at
it. **That is the same instrument-blindness this branch keeps finding** (`send_probe`'s harmonic
metric, the reverb-smoothed XBUS measurement, the cached-alias write watch in AGENTS.md). The
remedy is the same: name what the instrument reads before trusting what it does not say.

---

# THE PROBE'S LAST REQUIREMENT IS YOURS TO SUPPLY (round 75)

Addendum 73 listed "a stock project fixture (`OT_PROJECT`)" as a requirement. Round 75 checked
whether it can be produced locally. **It cannot.**

* **No fixture on this machine.** The candidates checked (`~/Downloads`, `~/Documents`) hold
  unrelated material.
* **`tools/harness/stress_project.py` cannot conjure one.** Its own docstring:

  > `python3 tools/harness/stress_project.py [--remix X] [--source <project>] [--out …]`
  > **The source template stays local and is never committed.**

  It **derives** a stress layout from a source project; it does not generate a stock project.

**So the probe's requirement list is complete and its last item is a stock Octatrack project** --
which you have and this sandbox does not. Everything else is in the tree.

## The complete requirement list, final

| # | requirement | state |
|---|---|---|
| 1 | step 2: the shards actually placed | not done -- write path + fit-and-place refactor located |
| 2 | list SPRING REV, DARK REV, LO-FI in `fx1` | one edit; **prediction already confirmed** |
| 3 | a stock Octatrack project (`OT_PROJECT`) | **yours to supply** |
| 4 | Test A: `dsp peek <core> P <tail>` | mechanism corrected in addendum 73; interactive |
| 5 | Test B: `--dsp-pcwatch <shard entry>` | recipe documented; **zero hits is decisive** |

**Four of the five are local to this tree. The second is one edit whose outcome is already
measured. So the FX recovery is gated on step 2 (real work, no open question) and on one artifact
you can hand over.**

## A note on what "blocked" would mean here

The goal defines a genuine blocker as exact measured evidence: address/range, required words,
available words, a timing or ABI or relocation result, or a reference mismatch. **None of the
remaining items is any of those.** Step 2 is a refactor whose every unknown has been measured away;
item 3 is a fixture; items 4 and 5 are tests. **So this is not a blocker, and the goal stays
active** -- the honest description is "remaining work, with one input that must come from the
hardware side".

---

# THE ODD-ADDRESS GATE IS OUT OF REACH HERE, FOR THE SAME REASON (round 76)

The brief's gate list includes **"no odd-address ColdFire stores / prior store-merging regression"**.
That gate exists and is good:

> `tools/verify/verify_perky_cf_odd_access.py` -- "A real ColdFire raises an address error on any
> word/long access whose effective address is odd; **the vendored Musashi (in ColdFire mode) does
> not emulate that, so such an access runs fine under `ot_emu` and faults on the unit.** GCC's
> store-merging pass is the usual source... The CF units are built with `-fno-store-merging` to
> prevent it; **this gate is the check that it stayed prevented.**"

**It cannot run here, for two independent reasons:**

1. **Its input does not exist.** It reads `out/perky/cf-final/generated`, which is produced by
   `tools/perky/build_cf_final.py` -- and that script `die()`s without **three external inputs**,
   none of them present or in the tree:

   ```
   PERKONS_FIRMWARE   <unset>   "set PERKONS_FIRMWARE or pass --firmware with exact PERKONS v1.2.1"
   PERKYBITS_ROOT     <unset>   "set PERKYBITS_ROOT or pass --perkybits with the PerkyBits checkout"
   OT_PROJECT         <unset>   a stock Octatrack project
   ```

2. **It is not registered in `modules/perky/manifest.py`**, so it is not part of `make check` and
   never runs even when its input is present.

## The honest reading

**This is the same class of gap as the probe's fixture**: a required check whose subject needs an
artifact that lives outside this sandbox. And it is the *third* such item now --

| gate | blocker |
|---|---|
| window executability (Test A/B) | a stock Octatrack project (`OT_PROJECT`) |
| odd-address stores | PERKONS_FIRMWARE, PERKYBITS_ROOT, OT_PROJECT |
| -- | and neither gate is registered |

**Note also that the CF side is not in this milestone's artifact at all**: `build_fold_candidate.py`
prints *"no shipping CF transport yet"*. So the odd-address gate guards a component the canary does
not yet carry -- which is why it has no input, and why its absence has not bitten.

## What would close it

1. supply `PERKONS_FIRMWARE` and `PERKYBITS_ROOT` (you have both) and an `OT_PROJECT`;
2. run `tools/perky/build_cf_final.py` to produce `cf-final/generated`;
3. **register the gate in the manifest** so it runs in `make check` -- which is a one-line edit and
   is worth doing regardless, because a gate that exists and is never run is exactly the kind of
   thing this work has repeatedly found to be load-bearing and absent.

---

# THREE GATES THAT EXISTED AND NEVER RAN (rounds 77-78)

The brief's gate list includes checks this project had already written. **Three of them were not in
`make check`, so they had never run.** All three are now registered and the suite passes.

| gate | what it guards | state |
|---|---|---|
| `verify_perky_cf_odd_access` | word/long access at an odd ColdFire displacement | **registered; teeth proven in both directions** |
| `verify_perky_all_fx_placer` | the 2,404-word shared-tail budget is usable | **registered** |
| `verify_perky_all_fx_memory` | keep the default memory split; harvest neither FX arena | **registered** |

**Suite before: 64 gates. Now: 67 run, 0 failed.**

## Why the two tail gates matter here specifically

`ALL_FX_MEMORY.md` -- the document the brief cites as the authority for the memory accounting --
says of `verify_perky_all_fx_placer.py`:

> proves the complete 2,404-word capacity can be used without crossing a hole or touching the
> mailbox

**That sentence was the entire evidence for the tail budget, and the gate it names was not in the
suite.** Both gates pass when run -- so nothing was wrong with them, and the defect was purely that
nobody ran them. **The sharding plan's capacity claim rested on a proof that had been executed by
hand, if at all.**

## The audit method, so it can be repeated

```python
registered = set(re.findall(r'Gate\(\s*"(tools/verify/[^"]+)"', manifest_text))
unregistered = [n for n in perky_tools_on_disk if n not in registered]
```

**101 of 169 `verify_perky*` tools are unregistered, and MOST ARE CORRECTLY SO**: the `3algo_*`,
`wavetable_*`, `karplus`, `slap`, `complex_*` and `resonant_*` families are the retired and
deferred engines this goal forbids, and many others are helpers imported by other gates rather
than gates themselves. **The value of the audit was not the count -- it was finding the three that
were load-bearing for THIS milestone.** A raw "101 unregistered" figure would have been noise.

## What is still not done

The `cf-*` family (about 30 tools) remains unregistered because each needs the ColdFire candidate
built with `PERKONS_FIRMWARE`, `PERKYBITS_ROOT` and `OT_PROJECT`. **They are the same class of gap
as the probe's fixture**: a required check whose subject lives outside this sandbox.

---

# EIGHT GATES RECOVERED, AND A CORRECTION TO MY OWN AUDIT METHOD (rounds 77-79)

## The gates

| gate | what it guards | round |
|---|---|---|
| `verify_perky_cf_odd_access` | odd ColdFire word/long displacement | 77 (teeth proven both ways) |
| `verify_perky_all_fx_placer` | the 2,404-word shared-tail budget is usable | 78 |
| `verify_perky_all_fx_memory` | keep the default split; harvest neither FX arena | 78 |
| `verify_perky_shipping_voice_exec` | the shipping engine voice | 79 |
| `verify_perky_fold_regression` | fold engine regression | 79 |
| `verify_perky_fold_seam_exec` | the fold seam | 79 |
| `verify_perky_multi_seam_exec` | the multi-engine seam | 79 |
| `verify_perky_synth_seam_exec` | the synth seam | 79 |

**Suite: 64 gates at round 76 -> 72 run, 0 failed.** Every one of the eight passed when run by hand;
**none was in `make check`.** The four-engine proof -- the core of the goal's task 3 -- rested on
remembering to run its gates.

## The correction, which matters more than the count

My first audit used:

```python
re.findall(r'Gate\(\s*"(tools/verify/[^"]+)"', text)      # WRONG
```

**It misses a `Gate(` whose string is on the NEXT line** -- and the manifest uses that form. So
registrations were under-counted, two of my seven "unregistered" candidates were **already
registered**, and registering them raised `gate ... listed twice`. The corrected pattern:

```python
re.findall(r'Gate\(\s*\n?\s*"([^"]+)"', text)             # handles the wrapped form
```

**Corrected figures: 169 tools on disk, 75 registered, 94 not** -- not 101. **My round-78 note that
"most of the unregistered are correctly so" was right, but the number it rested on was wrong, and
it was wrong in a way that produced duplicate registrations rather than a quiet understatement.**

## The lesson, which is the branch's recurring one

**An audit tool that under-reports produces confident wrong conclusions AND a broken build.** The
detection was cheap -- `ValueError: gate ... listed twice` -- but only because registering a
duplicate is a hard error. **Had the schema silently tolerated it, I would have shipped a manifest
claiming 94 unregistered gates and believed it.**

**Same family as everything else here**: check what the instrument reads before trusting what it
does not say.

---

# TWELVE GATES RECOVERED, AND THREE FOUND STALE (rounds 77-80)

**Suite: 64 gates at round 76 -> 76 run, 0 failed.** Every gate below was verified to PASS by hand
*before* registration -- registering an untested gate is how you break a suite for reasons that have
nothing to do with the work.

| gate | guards | round |
|---|---|---|
| `verify_perky_cf_odd_access` | odd ColdFire word/long displacement | 77 (teeth proven both ways) |
| `verify_perky_all_fx_placer` | the 2,404-word tail budget is usable | 78 |
| `verify_perky_all_fx_memory` | keep the split; harvest neither FX arena | 78 |
| `verify_perky_shipping_voice_exec` | the shipping engine voice | 79 |
| `verify_perky_fold_regression` | fold regression | 79 |
| `verify_perky_fold_seam_exec` | the fold seam | 79 |
| `verify_perky_multi_seam_exec` | the multi-engine seam | 79 |
| `verify_perky_synth_seam_exec` | the synth seam | 79 |
| `verify_perky_simple_drum_voice_exec` | Simple Drum native parity (240 blocks) | 80 |
| `verify_perky_fold_drum_exec` | Fold Drum vs the ARM blocks (15) | 80 |
| `verify_perky_xstate_asm_layout` | the X-state ABI (62 accumulators) | 80 |
| `verify_perky_stock_dsp_boot_path` | stock-DSP boot path (1,000 ColdFire uploads) | 80 |

## THREE ARE STALE, AND MUST NOT BE REGISTERED

Running the candidates before registering them found three that fail for reasons unrelated to this
milestone:

| gate | why it fails |
|---|---|
| `verify_perky_synth_build_path` | *"full donor budget is 3441, expected 272"* -- written for an older donor layout |
| `verify_perky_image_legacy_identity` | `ImportError: cannot import name 'runtime_build' from 'remix'` -- references a removed API |
| `verify_perky_machine_boot` | `FileNotFoundError` -- needs an artifact path it is not given |

**Registering these would have made `make check` red for reasons that say nothing about the
shipping image** -- and the obvious next move would have been to weaken or delete them. **Recording
them as stale is the honest alternative: they are evidence that the tree has moved, not that the
milestone is broken.**

## The method, corrected and worth keeping

```python
# count Gate(...) however it wraps -- the manifest uses a multi-line form
registered = set(re.findall(r'Gate\(\s*\n?\s*"([^"]+)"', manifest_text))
candidates = [n for n in perky_tools_on_disk if f"tools/verify/{n}" not in registered]
for c in candidates:
    run it; register it ONLY if it passes; note it as stale if it fails for a
    reason unrelated to the milestone.
```

**Two guards, both earned here:** the corrected regex (round 79 -- the naive one missed the wrapped
form and produced duplicate registrations), and the run-before-register rule (this round -- which is
what separated the twelve from the three).

---

# A FOURTH STALE GATE, AND THIS ONE IS REQUIRED (round 81)

`verify_perky_machine_boot.py` guards **boot/upload/readback** -- a gate the brief lists by name.
It cannot run, and the reason is stale defaults rather than a defect:

```
--image      out/mainos_perky_machine.bin        but the canary writes out/mainos_perky_multi.bin
--packed     out/perky/machine-canary/packed     MISSING
```

Measured on this tree:

| input | state |
|---|---|
| `out/mainos_perky_multi.bin` | **present** (1,257,586 bytes -- the canary's output) |
| `out/platform/layout.json` | present |
| `out/platform/runtime.raw` | present |
| `out/platform-perky-machine` | present |
| `out/perky/machine-canary/packed` | **missing** |

**So the gate is one directory away from running, and that directory is what the canary produces.**
The likely history is a rename -- `machine-canary` to `multi`, and `mainos_perky_machine` to
`mainos_perky_multi` -- that updated the canary and not the gate.

## The four stale gates, together

| gate | why it fails | revival |
|---|---|---|
| `verify_perky_synth_build_path` | expects a 272-word donor; the build has 3441 | update the expectation, or retire it |
| `verify_perky_image_legacy_identity` | imports `remix.runtime_build`, removed | retire, or port to the new API |
| `verify_perky_machine_boot` | **stale paths**; inputs mostly present | **point it at the canary's output -- then register it** |
| `verify_perky_machine_boot`'s `--packed` | directory absent | produced by running the canary |

**`machine_boot` is the one worth reviving**: boot/upload/readback is a required gate, the canary
produces every input, and nothing about its checks looks wrong -- only its two defaults.

## What this round did not reach

I could not run the canary to produce `out/perky/multi/packed` and then re-run the gate. **So this
is recorded as "stale, one directory from working, and required" -- not as fixed**, and not as a
blocker either: the missing input is produced by a script in the tree.

---

# ONE MISSING INPUT GATES EVERYTHING REMAINING (round 82)

Running the canary -- the script that produces **both the flashable artifact and the boot gate's
input** -- stops at its first step:

```
$ python3 tools/perky/build_multi_machine_canary.py out/perky/simple-drum-assets
build-perky-machine: OT_PROJECT is required for the shipping sequencer gate
```

**`OT_PROJECT` is a stock Octatrack project.** Chasing four separate blockages over rounds 73-82
converged on the same artifact every time:

| check | needs |
|---|---|
| the canary / shipping sequencer gate | `OT_PROJECT` |
| `verify_perky_machine_boot` -- boot/upload/readback | `OT_PROJECT` |
| the window-executability probe (Test A / Test B) | `OT_PROJECT` |
| `build_cf_final.py` -- the odd-address gate | `OT_PROJECT` + `PERKONS_FIRMWARE` + `PERKYBITS_ROOT` |

**This is the single most useful thing this work can tell you.** Four apparently independent
blockers are one input:

```
OT_PROJECT=<a backed-up stock Octatrack project on this machine>
```

and for the CF family also `PERKONS_FIRMWARE` and `PERKYBITS_ROOT`, both of which you hold.

## What becomes possible immediately when it lands

1. **`build_multi_machine_canary.py` runs** -- so the artifact can be rebuilt from source and its
   `packed/` directory appears;
2. **`verify_perky_machine_boot` can be repointed and registered** -- closing a gate the brief lists
   by name;
3. **the canary's sequencer gate runs** -- an engine-level check currently unavailable;
4. **the probe (Test A / Test B) becomes runnable** once step 2 places the shards.

**None of that needs new code from me.** It needs the artifact.

## A caution about the artifact I do have

`~/Downloads/PERKY2V_milestone.{syx,bin}` exists and its hashes are stable -- **but the canary
cannot currently reproduce it, because the same `OT_PROJECT` is missing.** So the artifact is a
genuine, flashable, tested build; **it is not currently reproducible on this checkout.** Anyone
relying on it should know that, and supplying the project would restore reproducibility as a
side effect.

---

# THE LAST INPUT CANNOT BE SYNTHESIZED HERE (round 83) -- and that closes the audit

Round 82 found every remaining blocker converging on `OT_PROJECT`. **The last question worth asking
was whether this checkout can produce one.** It cannot, and the check is short:

`tools/hw/ot_project.py`'s complete command set is

```
report · set-gain · apply · host · stamp-defaults · stamp-slot
migrate-hosts · remap-slot · clone_samples
```

**every one of which takes an existing `PROJECT_DIR`** -- plus `guard_backup()`, which exists
specifically to refuse a write without a backup. **It reads and writes an Octatrack project; it
cannot manufacture one.** That is also what AGENTS.md's *"never an Elektron byte in the repo"*
requires: a project fixture cannot live here, so an absent one cannot be conjured from here.

## The audit is closed

Rounds 76-83 asked, in order: does the odd-address gate run (no -- unregistered); do the tail gates
run (no -- unregistered); do the engine gates run (five more unregistered); are the remaining
candidates stale (three yes, one required-but-stale); what do all the blockers share (**one input**);
can this checkout supply it (**no**).

**The result is a complete, ordered list of what remains, with a single external dependency at the
root of it:**

| # | item | state |
|---|---|---|
| 1 | step 2 -- place the shards (write path + fit-and-place refactor) | **the only substantial code left** |
| 2 | list SPRING/DARK/LO-FI in `fx1` | one edit; prediction already confirmed |
| 3 | `OT_PROJECT` -- a stock Octatrack project | **yours; unblocks 4-7** |
| 4 | `verify_perky_machine_boot` repointed + registered | needs 3 |
| 5 | the canary runs; the artifact becomes reproducible | needs 3 |
| 6 | the odd-address gate audits for real | needs 3 + `PERKONS_FIRMWARE` + `PERKYBITS_ROOT` |
| 7 | probe Test A / Test B | needs 1 + 3 |

**Item 1 is real work and needs nothing external. Items 2-7 are gated on one artifact.** That is the
whole picture, and it is a better place to stop than a list of things that were tried.

---

# "NO RESONANT CODE IN THE SHIPPING PATH" -- MEASURED AND NOW ASSERTED (round 86)

The brief lists this as a release gate. It had no check, so I measured it directly:

```
shipping program symbols: 205
symbols matching reson/res_/rsn: 0
words: 3051
```

**Zero Resonant symbols in the shipping program.** And the six `resonant`-named verify tools
(`verify_perky_3algo_resonant_fresh`, `verify_perky_resonant_compact`,
`verify_perky_cf_resonant_dsp`, and the rest) test the **retired** engines this goal forbids -- so
they are **correctly unregistered**, not gaps to close. That distinction mattered in round 78's
audit and matters here.

**Made permanent**: `verify_perky_shard_emit.py` already assembles the shipping program, so the
assertion lives there, where the symbol table is in hand:

```python
_rsn = sorted(l for l in syms if re.search(r"reson|res_|rsn", l, re.I))
check(not _rsn, f"Resonant symbols in the shipping program: {_rsn[:6]}")
```

**A requirement the brief states, previously unchecked, now asserted by a gate that runs in
`make check`** -- and it is the third brief-named gate recovered or created in rounds 77-86 (after
the odd-address store and the tail budget).

---

# STEP 2's HARD PART, SETTLED BY MEASUREMENT (round 87)

Rounds 63-67 converged on "the tails are not writable ground" from the `region`/record side, and
round 65 found `wrw_p` takes an absolute *image* address -- which raised the hope that a tail could
be written anyway, if only the image offset were computable. **It is not.**

The image's P layout is **piecewise per record**:

```
payload A: 68 P records, 68 DISTINCT (va + off - addr*3) values
payload B: 46 P records, 46 DISTINCT
-> NOT linear; the offset depends on the record
```

**So there is no formula from a DSP P address to an image address.** For a recorded address,
`_p_off` walks `mods` and uses that record's own `off`. For an **unrecorded** address -- every tail
-- **no such record exists, and no arithmetic substitutes for one.**

## What that means, precisely

| | |
|---|---|
| Do the records reach the window? | **yes** -- payload A's P coverage runs `0x00000..0x38013` |
| Do they reach the TAILS? | **no** -- round 63 measured zero overlap on four of five |
| Is there a linear map to fall back on? | **no** -- 68 records, 68 distinct offsets |

**The tails are the GAPS between records.** They are free precisely because no record claims them --
which is also why nothing can write them.

## So step 2 is three things, and the middle one is the hard one

1. the fit-and-place pipeline must carry N streams instead of one;
2. **the tails need RECORDS** -- entries in the image's P record table, which the loader then has to
   understand. This is not a `wrw_p` call and not a loop; it is new structure in the payload;
3. the build must call `place_program_shards_two_space()`.

**Item 2 is why the sharding plan is expensive**, and it is the honest answer to "why not just write
the words there". **The mapping from code address to image address is a table, not a formula, and
the tails are not in the table.**

---

# FEASIBILITY: THE TAILS CAN BE MADE LOADABLE -- WITH A TEMPLATE ON A AND NONE ON B (round 88)

Round 87 established that the tails have no image records, so nothing can write them. **The
decisive follow-up is whether a shared-window address is loadable AT ALL** -- because if the loader
refuses the whole window, no amount of new structure helps.

```
payload A: 2 P records INSIDE the shared window
  P:0x30000..0x300ab   (171 words)
  P:0x38000..0x38013   ( 19 words)
payload B: 0 P records inside the shared window
```

**A shared-window address IS loadable: payload A carries two such records.** So adding records for
the tails is **structurally possible** -- the format permits it, and there is a working template to
copy.

## But the template exists on one payload only

* **payload A** has the precedent (2 records in the window);
* **payload B has none** -- and payload B serves tracks 1-4, **where T1 lives**;
* and because the track-core mapping is inverted, **T1 (payload B) and T5 (payload A) need this
  independently.** One payload having a template does not give the other one.

## So step 2's hard part, precisely

**Add P records for the tails to both payloads:**
1. follow payload A's in-window records as the template;
2. produce the equivalent on payload B, which has no precedent;
3. keep the `_have != sum(...)` consistency check satisfied (it asserts the region covers exactly
   the harvested spans);
4. then the fit-and-place refactor and the placer call.

**This is feasible and expensive. It is not blocked by the format** -- which is the answer worth
having, and it took one measurement to distinguish "hard" from "impossible".

## The lineage of this question, since it took ten rounds

| round | claim | how it was settled |
|---|---|---|
| 61 | the tails are not writable ground (`region`) | reading `region`'s construction |
| 63 | four of five tails have no record in any space | counting records against the spans |
| 66 | `_p_off` hard-exits without a record | reading the only DSP->image mapper |
| 68 | no stock code executes from the window | disassembling both payloads |
| 87 | the mapping is piecewise, so no formula reaches a tail | 68 records, 68 distinct offsets |
| **88** | **a window address IS loadable; A has the template, B does not** | **counting in-window records, per payload** |

**Six measurements, each narrowing the same question, and the answer only became usable at the
last one.**

---

# STEP 2: THE PLACEMENT IS ALREADY COMPUTED -- THE BLOCKER IS THE RECORD TABLE (round 120)

**This narrows the pick-up point.** The handoff above says "step 2: the fit-and-place refactor plus the
tail records". Reading the code, **the first half is done.**

## `perky_emit_shards.emit()` already calls the placer

```python
def emit(multi_asm):
    whole, syms = B.assemble_syms(src, MONOLITH_ORG, "mono")
    pieces = slice_pieces(src, len(whole), syms)
    assigned = L.place_program_shards_two_space(
        [L.ProgramShard(n, b - a) for n, a, b, _, _ in pieces])
    dest = {p.name: p.start for p in assigned}
    ...
    return pieces, whole, dest, final, syms
```

**So the pipeline already carries N streams, already places them, and already returns each piece's
assigned origin.** That was the first of the three sub-steps. Run against `out/perky/multi/multi.asm`:

```
monolith 2353 words -> 16 pieces
  0x01000  synth_seam_glue.asm               336  LOCAL
  0x01150  simple_drum_envelope.asm          247  LOCAL
  0x01aa4  simple_drum_delta.asm             162  LOCAL
  0x33da3  noise_tone_math.asm               299  SHARED
  0x33ece  simple_drum_oscillator.asm        237  SHARED
  0x33fbb  pk_multi_simple_init               54  SHARED
  0x37da3  noise_tone_oscillator_packed.asm  194  SHARED
  0x37e65  noise_tone_filter.asm             133  SHARED
  0x37f10  noise_tone_envelope.asm           130  SHARED
  0x37f92  synthetic_control_map.asm         106  SHARED
  0x3bda3  noise_tone_envelope_packed7.asm    91  SHARED
  0x3bdfe  noise_tone_mix.asm                 89  SHARED
  0x3be57  noise_tone_voice_xstate_glue.asm   86  SHARED
  0x3bead  simple_drum_voice.asm              80  SHARED
  0x3befd  pk_multi_noise_init                78  SHARED
  0x3bf4b  simple_drum_frequency.asm          31  SHARED
  total: 2353 words in 16 pieces
```

**(That is the DEFAULT mixed payload, not the shipping light2 -- 2353/16 vs 3051/21. The mechanism is
the same; the numbers differ because the two payloads select different pieces.)**

## What is actually left, then

**Only the second half: the tails need records in the image's P record table, so the loader writes
them.** The placement decides *where* code goes; the record table is what makes the loader *carry* it
there. `perky_emit_shards` produces the bytes at the right origins and proves the extents exact -- **and
the loader still has no entry telling it those words exist.**

**So step 2 is not "refactor and place". It is one thing:** add records for the five tails, in **both**
payloads (payload A has a template -- two in-window records; payload B has none, and T1 lives there).

**That is a smaller and more sharply-defined task than the handoff previously implied.** The fit is
proven, the placement is computed, the pieces are byte-exact at their origins. **The records are the
whole of what remains.**

---

# STEP 2's RECORD FORMAT, READ FROM THE PARSER (round 121)

Step 2 is one task: **add records for the five tails to both payloads.** Round 121 read the parser
that defines them -- `tools/build/dsp_modmap.py` -- so the task now has a spec rather than a name.

## The record layout, from `parse()`

```
off = 0
if b[0] == 3:  off = 6          # optional leading tag
if b[off] == 4: off += 6        # and optionally a second

record i:
  +0   w24  space      <- 0..3; a value > 3 TERMINATES the table
  +3   w24  f1         <- count, if order == "ca"
  +6   w24  f2         <- addr
  +9   ...  count * 3 bytes of WORDS
  next record begins at +9 + count * 3        <- records are CONTIGUOUS
```

**Two orders are tried, `"ca"` and `"ac"`, and whichever consumes the blob cleanly wins** -- the
decompilation did not settle whether the count comes before the addr. So a writer must match whichever
the payload's other records use, and the parser will tell it which.

## The fact that decides the whole task

**`data = off + 9` -- the code WORDS are stored INLINE in the record, not referenced by it.** A record
is not "a pointer to some words elsewhere"; it **is** the words, with a 9-byte header.

**So adding a tail record means appending `w24(space) w24(count) w24(addr) + count*3 bytes` to the
payload blob, before the terminating record.** The tail's bytes go in with it.

**And `build_bus._p_off` -- the other side of this contract -- walks exactly these tuples:**

```python
for sp, a, cnt, off in mods:
    if sp == 0 and a <= addr < a + cnt:
        return va + off + (addr - a) * 3
sys.exit(f"payload {tag}: no P record holds P:0x{addr:05x}")
```

**`sys.exit` -- not a warning.** A word with no record cannot be written, which is why the tails are
free ground: **nothing claims them, so nothing can put code there.** Adding the record is what makes
them claimable.

## So step 2 is now three concrete edits

1. **Find the payload blob's WRITER** (the counterpart of this parser -- `parse` reads, something
   assembles).
2. **Emit a record per tail**, in whichever `order` the payload's existing records use, with the
   shard's bytes inline.
3. **Do it for BOTH payloads** -- payload A has two in-window records as a template; **payload B has
   none, and T1 lives there** (r88).

**Then call `place_program_shards_two_space()`** -- which `perky_emit_shards.emit()` *already does*
(r120), so that part is done. **The placement is computed; the records are what remains, and they are
now specified.**

---

# STEP 2's RECORD WRITER, LOCATED (round 122)

Round 121 specified the record format from the parser. Round 122 followed the call chain to the code
that **emits** them.

## The chain

```
build_multi_machine_canary.py:100
    base.repack_machine_loader.build(ROOT/'out/mainos_bus.bin', work, mainos, ...)

tools/perky/repack_machine_loader.py:205
    append, symbols, boot, names = platform_build.build([], [runtime_payload], work)
                                   ^^^^^^^^^^^^^^^^^^^^ THE PAYLOAD AND ITS RECORDS
```

**`tools/build/platform_build.py`, function `build()`, is the writer.** That is where a tail record
must be added.

## What was ruled out on the way

| candidate | verdict |
|---|---|
| `tools/remix/pack.py` | **the payload COMPRESSOR** (`_greedy_parse`, `_gamma_bits`) -- not the record packer |
| `tools/perky/build_multi_payload.py` | only `build(assets, out)` and `main()` -- a wrapper, not the writer |
| `tools/build/dsp_modmap.py` | the **parser** -- reads the table, never writes it |

**Three plausible-looking names, none of them the writer.** The chain had to be followed rather than
grepped for: the canary calls a repacker, which calls the platform builder, which writes the payload.

## So step 2's three edits, now located precisely

1. **`tools/build/platform_build.build()`** -- emit a record per tail, `w24(space) w24(count)
   w24(addr)` + the shard's bytes inline, matching the `order` the payload's existing records use.
2. **Both payloads** -- A has two in-window records as a template; **B has none, and T1 lives there**.
3. **Then the placement** -- `place_program_shards_two_space()`, which `perky_emit_shards.emit()`
   already calls (r120).

**The format is specified (r121), the writer is located (r122), and the placement is already
computed (r120).** What remains is the edit itself and its gate.

## The honest note on how this round went

**I spent several searches on the wrong files.** `pack.py` and `build_multi_payload.py` both *look*
like the payload packer -- one is a compressor, one is a wrapper. **Grepping for names that sound right
is how this session has repeatedly gone wrong; following the call from the entry point is what worked
here.** Worth remembering: the canary's line 100 was the thread, and it was already in my notes.

---

# CORRECTION: ROUND 122's "WRITER LOCATED" WAS WRONG (round 123)

Round 122 followed the call chain to `platform_build.build()` and called it the record writer.
**Reading its docstring, it is the LOADER builder and it takes the DSP payload as INPUT:**

> `payloads: [dict(name, blob, stage, dst, rawlen, rhash, backup)]` for **payloads built
> elsewhere**: `blob` = signature + GKA3 stream.

**"payloads built elsewhere" is decisive.** And its `LAYOUT = "layout.json"` is the *loader's*
`base, runtime, stage, ceiling` -- not a module table. There is no `space/count/addr` packing anywhere
in the file: the only `*3` in it is a hash multiply.

## What that changes

**The DSP P records are inside the DSP payload blob**, which this stage receives. So the writer is
upstream of the chain I followed -- **in whatever produces the DSP payload**, which is `build_bus.py`'s
side, not `platform_build`'s.

## Why this is worth writing down rather than quietly fixing

**Round 122 ended with a confident "located precisely" and a table of three candidates it had ruled
out.** All of that reasoning was sound; **the conclusion was wrong, and only the docstring showed
it.** A handoff that said "the writer is `platform_build.build()`" would send the next session to the
wrong file with my confidence behind it.

**That is the fifth time this session has recorded a confident wrong answer**, and the pattern is
consistent: **each was a label applied to the first thing that matched**, corrected by reading the
thing itself. Round 122 matched a call site; the docstring said what the call site *is*.

## Where the writer actually is

**The DSP payload's records come from the stock payload**, since `dsp_modmap.modules()` *parses* them
out of the image -- so `build_bus.py`, which assembles that payload, is where a tail record would be
inserted. **That is a lead, not a finding**; I have not read it, and this note says so deliberately.

---

# STEP 2 IS *ONLY* THE RECORD INSERTION -- `place()` NEEDS NO CHANGE (round 124)

Round 123 corrected the writer's location to "somewhere in `build_bus.py`'s side". Round 124 read the
function that actually writes P code, and it settles the scope.

## `build_bus.place()` -- the whole of the write path

```python
def place(words, start):
    """Write a contiguous word stream at P address `start`.

    The records load back-to-back but are separated by headers in the
    file, so the stream is cut at each record boundary.
    """
    i = 0
    for _, a, cnt, off in region:            # the RECORD TABLE
        if i >= len(words): break
        pos = start + i
        if not (a <= pos < a + cnt): continue     # ONLY inside an existing record
        n = min(len(words) - i, a + cnt - pos)
        for k in range(n):
            wrw_p(va + off + (pos - a + k) * 3, words[i + k])
        i += n
    if i != len(words):
        sys.exit(f"payload {tag}: placement ran past the region")
```

## Three things follow

**1. The words live in the FILE at `va + off + (pos-a)*3`.** The record's `off` is a file offset and
`*3` is the three-byte packing -- exactly the layout `dsp_modmap.parse()` reads.

**2. A stream may span SEVERAL records.** *"the stream is cut at each record boundary"* -- `place()`
walks record by record, writing `n` words in each until the stream is done. **Nothing requires a
stream to sit in one record.**

**3. And that is why step 2 needs no placement change at all.** If a record covering `0x33da3` exists,
`place()` will use it **with the code it already has.**

## So the task is exactly one thing

**Create the records.** They are *inherited from the stock payload* -- `dsp_modmap.modules()` parses
them out of the image, and the build only ever writes **into** them. **Nothing in this tree emits a
new one**, which is why the tails are unreachable: they are DspAddress ranges no record covers, and
`place()` skips every address outside `region` and then `sys.exit`s.

**Adding a tail record means inserting into the stock payload blob:**
`w24(space) w24(count) w24(addr)` + the bytes inline, **before the terminating record** -- in whichever
`order` the payload's existing records use.

**Then `place()` finds it, `_p_off` resolves it, and the shard lands. No other change.** That is a
sharper scope than any previous round recorded: **the placement, the emitter, the placer and the write
path are all already correct; only the table entry is missing.**

## And the payload-B problem, restated with the new detail

**Payload A has two in-window records** -- proof the format permits it, and a template.
**Payload B has none, and T1 lives there.** So the insertion has to be done twice, against two
different stock blobs, and **B's `order` may differ from A's** -- the parser tries `"ca"` and `"ac"`
precisely because it was not settled.

---

# THE RECORD ORDER IS `ac`, MEASURED ON BOTH PAYLOADS (round 125)

Round 121 read the format from the parser but left one field ambiguous: the decompilation did not
settle whether the count precedes the addr, so `parse()` tries `"ca"` and `"ac"`. Round 125 measured
which one each payload actually uses -- **because an inserted record must match it.**

```
payload A: blob 79,563 B
  order=ca:   1 record,  consumed  1,602 B   terminator 0x7f4e6d at +0x642
  order=ac:  98 records, consumed 79,557 B   ran off the end
payload B: blob 77,061 B
  order=ca:   1 record,  consumed  1,602 B   terminator 0x7df71b at +0x642
  order=ac:  91 records, consumed 77,055 B   ran off the end
```

**`"ca"` dies after one record on both payloads** -- it reads some large value as a "space" and stops.
**`"ac"` consumes 79,557 of A's 79,563 bytes and 77,055 of B's 77,061.** That is the parse, and
`modules()` picks it because it keeps whichever consumes more.

## So the header is

```
+0  w24  space
+3  w24  ADDR        <- first
+6  w24  COUNT       <- second
+9  ...  count * 3 bytes of words
```

**And the table runs to the end of the blob** -- 79,557 of 79,563 on A, 77,055 of 77,061 on B. Six
bytes of tail on each; the records are packed edge to edge.

## What that fixes for step 2

**The insertion has no ambiguity left.** A tail record is:

```
w24(0)  w24(tail_addr)  w24(count)  + count*3 bytes
```

placed before the terminating record, in **both** payloads, whose orders are now known to be the same.

**Two things this does NOT settle**, and they are the remainder: **where in the build the blob is
assembled** (so the insertion has a home), and **whether the blob has room** -- the records consume
essentially the whole blob, so a new one must go where the terminator is, and the stage/ceiling the
loader reserves decides whether that is possible.

---

# ROOM EXISTS: 30,460 BYTES BETWEEN PAYLOAD B AND THE LOADER (round 126)

Round 125 left two open questions. Round 126 answers the second -- **whether the blob has room** -- and
the answer is the `available words` figure the goal's blocker definition asks for.

## Measured

```
payload A: va=0x400e2324  79,563 B  -> ends 0x400f59ef
payload B: va=0x400f59ef  77,061 B  -> ends 0x401086f4
loader:                               0x4010fdf0
```

**The two payload blobs are back-to-back** -- A ends exactly where B begins -- so **A cannot grow without
moving B.** But B ends at `0x401086f4` and the loader sits at `0x4010fdf0`:

```
0x4010fdf0 - 0x401086f4 = 0x76FC = 30,460 bytes
```

**A tail record for the 3,051-word program costs `3,051 * 3 = 9,153` bytes of words plus a 9-byte
header = 9,162.** Against 30,460 available. **It fits, with 21,298 bytes to spare.**

## What this does and does not settle

**Settles:** the FILE side has room. **Known:** 30,460 available, 9,162 required, ratio 3.3:1.

**Does not settle:** whether the DSP side accepts a write to those addresses. **The record's `addr` is
a DSP address and its `off` is a FILE offset** -- so a new record grows the file blob (which fits) and
directs the loader to write DSP memory at the tail addresses (which are free RAM, 2404 words measured
across five spans in round 111).

**Nor:** whether the loader's own copy loop honours a record whose `addr` lies outside whatever it
assumed. **That is a property of the loader, and I have not read it.**

## Where the 30,460 bytes actually is

**It is the gap before `LOADER_AT = 0x4010FDF0`**, the fixed address the ColdFire side calls after the
stock OS image. **`platform_build`'s `LAYOUT` names it `ceiling`; `preboot_layout` enforces it.** So the
region is not unclaimed waste -- **it is reserved, and the reserve is what a growing payload B would
eat into.**

**That makes it a question about the reserve's purpose, not just its size** -- and the `preboot_reserve`
in `layout.json` (`base, size, ceiling`, 1,486,848 bytes) is about **DSP** buffer space, not the
ColdFire file. **Two different ceilings, and I have measured one of them.**

---

# WHO READS THE RECORDS: NOT OCTABAM'S LOADER (round 127)

Round 126 confirmed there is room for a tail record and left one question: **does the loader honour a
record at an arbitrary `addr`?** Reading the loader answers it -- **and the answer is that the question
was aimed at the wrong reader.**

## Octabam's loader has its OWN table, and it is payload-level

`tools/remix/loader.S`, assembled and linked at `LOADER_AT` by `platform_build.build()`:

```
src       address of the staged blob's SOURCE in this append (4-byte)
stage     uncached address the blob is copied to and depacked FROM
dst       uncached address the payload is depacked to
rhash     rolling x33 hash of the depacked payload
backup    uncached address of a backup copy, or 0 for none
```

**It copies and depacks whole BLOBS.** It walks `(src, len, phash, stage, dst, rhash, backup)` per
payload -- **nothing about P-module records, spaces or per-module addresses.**

## So the P records have a different reader

**They live INSIDE the depacked blob, and the reader is the stock OS's DSP uploader** -- whatever the
firmware uses to move a payload into DSP P memory. **That reader walks the record table and writes each
record's words at its `addr`**, which is the whole purpose of carrying an `addr` per record.

**INFERRED, not measured.** I have not read the stock uploader. **What is measured is that the table
exists with those fields and that the tails are free DSP addresses** -- and that is enough to say what
the insertion has to look like, but **not enough to promise the uploader accepts an addr it did not
expect.**

## Why the distinction matters for step 2

**If octabam's loader walked the records, adding one would mean changing `loader.S`** -- a second
edit, in ColdFire assembly, at a fixed address.

**It does not.** The loader's job is to get the blob into DRAM and depack it. **The records are
consumed downstream, in stock code**, so the insertion is confined to **the blob's bytes** -- exactly
where rounds 121-125 put it.

**That keeps step 2 to one edit in one place**, and it also means the risk is concentrated in the one
thing not measured: **whether the stock uploader tolerates a record at an address no stock record
covers.**

## What would settle it

**The uploader is stock code, so it can be read** -- or, more cheaply, **a record whose `addr` is a
known-good but unusual DSP address can be inserted and the words read back** with the probe recipe the
handoff already carries. **That is a local test, and it is the natural first half of the edit.**

---

# THE SLACK ASYMMETRY, AND WHY A IS NOT ACTUALLY SHORT (round 129)

Round 126 measured 30,460 bytes of room and I called it room for the tail record. **Reading the
addresses again shows it is room for ONE payload, not both:**

```
A: 0x400e2324..0x400f59ef        slack after A: 0 bytes
B: 0x400f59ef..0x401086f4        slack after B: 30,460 bytes
loader: 0x4010fdf0
```

**A ends exactly where B begins.** So **payload B can grow in place; payload A cannot without moving
B -- and moving B moves the loader, which sits at a fixed `LOADER_AT`.**

**And the mapping is inverted, so this is the wrong way round for convenience:** A serves tracks 5-8,
B serves tracks 1-4. **T1 is on B (the one with slack). T5 is on A (the one without).**

## But A is not short of SPACE -- it is short of UNALLOCATED space

**A already holds 3,441 words of records whose code the milestone is removing:**

```
Plate Reverb     594
Spring Reverb   1063
Dark Reverb     1067
Compressor       180
Lo-Fi            537
                ----
                3441
```

**Those records exist, are backed by bytes, and are pointed at code nobody wants.** The 3,051-word
program fits inside 3,441 words. **So A's requirement is not new space -- it is a REALLOCATION of
records A already carries.**

**That is a different edit from adding a record:** instead of inserting 9 + `count*3` bytes and shifting
everything, **change the `addr` and `count` of records that are already in the table, and pack the
shards into the byte area they already own.** No growth, no shift, no loader move.

## So step 2 has two shapes, one per payload

| payload | slack | approach |
|---|---|---|
| **B** (T1) | 30,460 B after its table | **append** records before the terminator -- measured to fit 3.3:1 (r126) |
| **A** (T5) | none | **repurpose** the 3,441 words of retired records -- re-point their `addr`, repack their bytes |

**Neither needs a new address space.** And **INFERRED, not measured:** that a record's `addr` and
`count` may be changed freely, and that a payload's loader does not depend on a record being where it
was. **The first is implied by the format (both fields are just words in a header); the second is the
same unmeasured property round 127 named.** Both are testable locally with a probe record.

## What this corrects

**Round 126 said "room exists" without asking room for *which* payload.** It is room for B only.
**The A side is solved by reallocation instead -- and that is a better answer than room, because it
needs none.**

---

# PAYLOAD A'S RETIRED RECORDS ARE ONE CONTIGUOUS 3,441-WORD RUN (round 130)

Round 129 argued A is short of *unallocated* space, not space. Round 130 measured its shape -- and the
argument holds exactly.

## The map

```
PLATE REV    0x01000..0x01251    594
SPRING REV   0x01252..0x01678   1063
DARK REV     0x01679..0x01aa3   1067
COMPRESSOR   0x01aa4..0x01b57    180
LO-FI        0x01b58..0x01d70    537
             ----------------------
             0x01000..0x01d70   3441 words -- CONTIGUOUS, no gaps
```

**One run, 3,441 words, from `0x01000` to `0x01d70`.** Every one of the five is retired by the
milestone's own FX priorities (Plate and Compressor approved; Spring, Dark and Lo-Fi to be restored).

## And it explains a number that had been sitting unexplained

`all_fx_layout.SAFE_LOCAL_P_SPANS` is `((0x1000, 0x1252), (0x1AA4, 0x1B58))` -- **774 words, in two
runs.** That is **Plate 594 + Compressor 180**, and nothing else:

```
0x01000..0x01251   594   PLATE      <- SAFE_LOCAL span 1
0x01252..0x01678  1063   SPRING     <- NOT in SAFE_LOCAL
0x01679..0x01aa3  1067   DARK       <- NOT in SAFE_LOCAL
0x01aa4..0x01b57   180   COMPRESSOR <- SAFE_LOCAL span 2
0x01b58..0x01d70   537   LO-FI      <- NOT in SAFE_LOCAL
```

**So `SAFE_LOCAL_P_SPANS` is precisely "the two sacrifices the brief permits"**, and the gap between
its two spans is **Spring + Dark = 2,130 words** -- the ones that must come back. **The layout module
has been encoding the brief's priority list in its constants all along**, and round 129's "A already
holds 3,441 words of records whose code is being removed" is that list.

## What it means for step 2, on the A side

**The five records are contiguous, so reallocating them is a local operation.** To give A a record per
tail: **change the `addr` and `count` of records already in the table, and lay the program's shards
into the 3,441-word byte area those records already own.** No insertion, no shift, no growth, and the
loader does not move.

**3,051 words of program into 3,441 words of area -- 390 to spare**, which is consistent with the
127-word total headroom the placer reports once A's and B's other spans are counted.

## Still inferred, still testable

**That a record's `addr` and `count` may be changed.** Both are plain words in a 9-byte header (r121),
so nothing about the format forbids it -- **but "nothing forbids it" is not "the loader tolerates it"**,
and that is the same unmeasured property round 127 named. **One probe record at an unusual address,
read back, settles it.**

---

# THE REALLOCATION PROBE: THE FORMAT ACCEPTS IT (round 131)

Rounds 129-130 argued payload A's tail records can be made by **re-pointing records it already has**,
rather than inserting new ones. That rests on an unmeasured claim: *a record's `addr` may be changed.
**Round 131 tested it -- on a copy, in memory, without touching the tree.**

## The probe

Take payload A's blob from the stock image. Find the PLATE record (`space=0 addr=0x01000 count=594`,
`data_off=0x104a6`). **Change only its three `addr` bytes to a tail address, `0x33da3`. Re-parse.**

```
after re-pointing addr to 0x33da3:
  records still parsed              : 98 (was 98)
  the tail address is now a record  : True    count=594
  the old 0x1000 record is gone     : True
  _p_off would resolve P:0x33da3    : True
```

**Four things, all as needed:**

* **the record count is unchanged** -- 98 before and after, so nothing downstream desynchronised;
* **the tail address is now a record** -- `parse()` finds `space=0, addr=0x33da3, count=594`;
* **the old address is gone** -- exactly the reallocation, not a duplication;
* **and `_p_off` -- the mapper the build itself uses -- resolves it.** `build_bus.place()` would now
  write into `0x33da3..0x34000` **through the record**, because that is how it already writes anywhere.

## What this proves, and what it does not

**Proves:** the record table's `addr` field is freely re-pointable **as far as the format and the
build's own reader are concerned**. The 9-byte header carries `addr` as a plain word, and nothing about
parsing, counting or mapping depends on it matching where it was.

**Does not prove:** that the **stock DSP uploader** accepts a record at an address no stock record
covered. **That is the runtime side, it is the same property rounds 127 and 129 named, and it needs
either the uploader read or a probe record on hardware.** The local half is now done.

## Why doing it on a copy mattered

**The probe mutated a `bytearray` copy in memory and wrote nothing.** The staged artifacts and the
stock image on disk are untouched -- the commit that records this changes only a markdown file.
**Given that this session has already broken a gate's inputs once by running a build (r114), the
cheapest possible experiment was the right one.**

---

# THE APPEND PROBE: BOTH LOCAL HALVES ARE NOW PROVEN (round 132)

Round 131 proved payload A's approach -- **re-point an existing record's `addr`**. Round 132 proves
payload B's -- **append a new one before the terminator.**

## The probe

```
payload B blob 77,061 B, 91 records
terminator at blob+0x12cff; 6 bytes after it

after inserting a 300-word tail record (909 B):
  blob    : 77,061 -> 77,970 B  (+909)
  records : 91 -> 92            (+1)
  the tail address is a record  : True  count=300
  _p_off would resolve P:0x33da3: True
  the first record is unchanged : True
```

**The blob grows by exactly the record's size (9-byte header + 300*3 = 909).** The count rises by one.
**The tail address becomes a record that `_p_off` resolves. And every record before it is byte-for-byte
what it was** -- so appending disturbs nothing that already works.

## Both shapes, both proven locally

| payload | shape | probe | result |
|---|---|---|---|
| **A** (T5) | re-point an existing record's `addr` | r131 | ✓ count unchanged, tail resolves, old address gone |
| **B** (T1) | append a record before the terminator | r132 | ✓ +909 B, +1 record, tail resolves, others untouched |

**That is the whole of step 2's mechanism, verified on copies in memory.** Neither probe wrote to disk.

## What is now proven, and the one thing that is not

**Proven locally:** the record table accepts **both** operations; `parse()` reads the result correctly;
**`_p_off` -- the build's own mapper -- resolves a tail address in either shape**; and neither operation
disturbs the records around it.

**Not proven:** that the **stock DSP uploader** accepts a record at an address no stock record covered.
**This is the third time it has been named** (r127, r129, r131) and it is the only thing left between
this analysis and an actual build attempt. **It needs either the uploader read or a probe record on
hardware.**

## One detail worth recording

**The terminator is `w24 = 0x3` on both payloads, and it is 6 bytes long** -- a header with no data.
`parse()` stops there because the record it would read next runs off the end, not because of the
`sp > 3` guard: **3 is not `> 3`.** That is a small inconsistency in the parser's comment, not in its
behaviour -- **but a writer must put the new record BEFORE those 6 bytes, not after**, or the
terminator ends up inside the table.

---

# THE REMAINING UNKNOWN, NARROWED TO STOCK COLDFIRE CODE (round 133)

Rounds 127-132 left one thing unproven: **does the reader accept a record at an address no stock record
covered?** Round 133 narrows *who* that reader is.

## The loader stages into COLDFIRE DRAM

`out/platform-perky-machine/layout.json`:

```
perky payload A dst    0x40b00000..0x40b150bd   (84.2 KB)
perky payload A stage  0x40b80000..0x40b91279   (68.6 KB)
perky payload B dst    0x40b40000..0x40b546f7   (81.7 KB)
perky payload B stage  0x40bc0000..0x40bd0d12   (67.3 KB)
```

**`0x40Bxxxxx` is ColdFire DRAM, not DSP P/X/Y.** A's 84.2 KB `dst` comfortably holds its 79,563-byte
blob.

**So `loader.S` copies, depacks and hash-gates the payload INTO COLDFIRE, and stops.** That is what its
`pretable` describes and all it does. **The payload does not reach DSP memory in that step.**

## Therefore the reader is stock ColdFire code

**Something in the stock OS takes the depacked blob from ColdFire DRAM and writes it into DSP P memory
-- and that is what walks the record table.** It is the only remaining candidate:

| candidate | verdict |
|---|---|
| `loader.S` | ✗ payload-level table only; stages into ColdFire (r127, r133) |
| the DSP itself | ✗ the blob is in ColdFire DRAM at that point (r133) |
| **the stock OS's DSP upload routine** | **✓ the only thing left** |

## Why that is useful rather than just a restatement

**It is a bounded search in stock code that is already in the image**, rather than an unknown about
hardware. The upload routine must:

* read records in the `w24(space) w24(addr) w24(count)` shape (r121, r125);
* write `count` words to `addr` in DSP memory;
* and stop at the terminator.

**The question is only whether it validates `addr`** -- and if it does validate, the check is a
comparison against some table or range that is itself readable.

**The three probes (r131, r132) and this narrowing together mean the work left is: read one stock
routine, or flash one probe record.** Everything else about step 2 is measured.

---

# THE READER HAS A NAME: THE STOCK DSP BOOT ROUTINE (round 134)

Round 133 narrowed the record table's reader to "some stock ColdFire DSP upload routine". **The repo
already names it.**

## `modules/perky/MEMORY.md`, lines 199-208

> The extended DSP uploads cannot overwrite their stock image slots, so the standard Octabam loader
> depacks each replacement upload to reserved SDRAM **before the stock DSP boot routine reads it.**
> PERKY uses the same four 256 KiB windows as the measured Analog-BD preboot path:

```
cached destination A   0x40b00000..0x40b3ffff
cached destination B   0x40b40000..0x40b7ffff
cached stage A         0x40b80000..0x40bbffff
cached stage B         0x40bc0000..0x40bfffff
```

**So the reader is the STOCK DSP BOOT ROUTINE**, and the address it reads from is documented, fixed,
and matches the `dst` the loader stages to (`0x40b00000` for A -- r133).

## Why this is the end of the scoping trail

**Round 133 argued it from the layout; the repo states it outright.** And it means:

* **the reader is stock code in the image** -- readable, not a hardware unknown;
* **it is a named routine**, so there is one thing to find rather than a search;
* **and the property in question is a single yes/no:** does that routine validate `addr`, or write
  wherever the record says?

**If it validates**, the check is a comparison -- a range or a table -- and that is itself readable in
the same routine.

## The whole of step 2's unknowns, now

| question | state |
|---|---|
| record format | ✓ measured (r121) |
| record order | ✓ measured: `"ac"` (r125) |
| room, payload B | ✓ 30,460 B vs 9,162 needed (r126) |
| room, payload A | ✓ not needed -- 3,441 contiguous retired words to reallocate (r129, r130) |
| does the format accept re-pointing | ✓ **probed** (r131) |
| does the format accept appending | ✓ **probed** (r132) |
| who reads the records | ✓ **the stock DSP boot routine** (r133, r134) |
| **does it validate `addr`** | **the one open question** -- and it is a yes/no in one named routine |

**Everything else about step 2 has been measured, and the last item is now a single routine to read.**

---

# THE LAST QUESTION, NARROWED BY MEASUREMENT (round 135)

The one open question is whether the stock DSP boot routine **validates `addr`**. Round 135 found the
strongest local evidence available, and it points one way.

## Stock itself already puts records in the shared window

```
payload A: 98 records; 2 have addr inside 0x30000..0x3ffff
    record at 0x30000   count=171
    record at 0x38000   count=19      <- within 0x1000 of the 0x37f10 tail
payload B: 91 records; 0 have addr inside 0x30000..0x3ffff
```

**Two things follow, both measured:**

**1. The routine already writes records into the shared window.** `0x30000` and `0x38000` are inside
`0x30000..0x3ffff` -- **the same address space the tails occupy** (`0x33da3`, `0x37da3`, `0x37f10`,
`0x3bda3`, `0x3fda3`). So **a record at a shared-window address is not a new kind of thing for it.**

**2. It has no fixed per-payload expectation of what lives there.** **A has two such records; B has
none.** A routine that required a record at a particular address would fail on one of them --
**so whatever it does, it does not assume.**

## What this does and does not establish

**Does not prove:** that it writes wherever `addr` says. **It could still validate against a range or a
whitelist.**

**But it moves the question.** The plausible validation would be a *space* check (P vs X vs Y) or an
*image-slot* check -- **and the tails pass a space check by construction (space 0, like every other P
record), while an image-slot check is already falsified by `0x30000`/`0x38000` being neither.**

**So the shape of the remaining risk is now small and specific:** not "will it accept a shared-window
address" (**stock does**), but "is there any per-address check at all" -- **and the A/B asymmetry
argues against one.**

## Still inferred, and the test that would end it

**INFERRED, not measured**, as rounds 127 and 129 also were. **The difference is that the inference now
rests on two measured records rather than on the format's silence.** The test is unchanged and cheap:
**insert a probe record at a tail address, read the words back with the probe recipe, and see whether
they arrive.**

---

# THE STOCK OS DOES NOT CARRY THE WINDOW ADDRESSES (round 136)

Round 135 narrowed the last question to "is there any per-address check at all". Round 136 asked a
sharper one: **does the stock boot routine even know these addresses?**

## Measured: it does not

Searching the stock MAIN OS for the four preboot windows as big-endian constants:

```
0x40b00000  stock OS hits: 0
0x40b40000  stock OS hits: 0
0x40b80000  stock OS hits: 0
0x40bc0000  stock OS hits: 0
```

**None of them is in the stock image.** So the routine that reads the depacked payload **cannot be
reading from a hardcoded constant.**

## What that means

**The address must arrive as data** -- from a table, a pointer, or a register the loader sets. Which
means **the stock routine is driven by what it is handed, not by what it expects.**

**That is evidence about the last question, and it points the same way as round 135:** a routine that
hardcodes nothing about *where* the payload is **is unlikely to be checking *where each record says to
go*** -- the two are the same kind of assumption.

**INFERRED, as rounds 127, 129 and 135 were.** The measurement is certain (zero hits); the conclusion
drawn from it is not.

## The caveat, stated because it matters

**"Zero hits" is consistent with two things:** the constant genuinely absent, **or** it being computed
(address = base + offset, with only the base in the image). **I have not distinguished them** -- doing
so means finding the routine and reading it, which is the same remaining task as before.

**What the search does establish is that the naive reading -- "stock knows 0x40b00000" -- is false.**
Whatever tells the routine where to read, **it is not a literal in the stock OS.**

## The picture, after five rounds on one question

| round | what was measured | what it did to the question |
|---|---|---|
| 127 | `loader.S` has a payload-level table | the reader is not octabam's loader |
| 133 | the blob lands in ColdFire DRAM | the reader is stock ColdFire code |
| 134 | `MEMORY.md` names it | **the stock DSP boot routine** |
| 135 | stock puts 2 records in the shared window | it writes there already |
| 136 | **stock carries none of the window addresses** | **it does not hardcode where to read** |

**Each round removed a way the routine could have refused a tail address, and none has produced one.**
That is not proof -- **but it is five measurements pointing the same way, and the test that ends it is
still one probe record.**

---

# STEP 2 AS A WORK PLAN (round 137)

Seventeen rounds (120-136) turned step 2 from "a substantial refactor" into the work below. **This is
the plan, in order, with the measurement behind each step.** Nothing here needs re-deriving.

## 0. The one test that gates the rest

**Insert a probe record at a tail address in one payload, build, and read the words back:**

```
.venv/bin/python3 tools/emu/ot_emu/stage_card.py PROJECT_DIR OCTABAM RIG --out out/card.img
out/emu/ot_emu --image out/mainos_bus.bin --card out/card.img --set OCTABAM --project RIG \
    --sequencer --internal-clock --frames 600 --load-ms 90000 --dsp --main-level 64
# then, interactively:  dsp peek <core> P 0x33da3 300
```

**If the words arrive, everything below is mechanical. If they do not, stop and read the stock DSP boot
routine -- and the record table is not the mechanism.** `--mem-dump` does **not** work for this (its
spans are ColdFire addresses).

**This needs `OT_PROJECT`.** It is the same dependency round 0 of the goal documents.

## 1. Payload B -- append (T1's core)

```
insert, immediately BEFORE the terminator (blob+0x12cff for the current build):
    w24(0) w24(tail_addr) w24(count) + count*3 bytes
```

**Measured:** the parse accepts it, the count rises by one, `_p_off` resolves the tail, and every
record before it is untouched (r132). **Room:** 30,460 bytes after B's table, 9,162 needed (r126).
**Order is `"ac"`** -- `w24(space) w24(ADDR) w24(COUNT)` (r125).

## 2. Payload A -- reallocate (T5's core)

**No insertion.** A's five retired records are **one contiguous 3,441-word run** at
`0x01000..0x01d70` (r130), and the program fits in it (3,051 words). **Change each record's `addr` to
the tail it should cover, and repack the shard bytes into the byte area those records already own.**

**Measured:** re-pointing a record's `addr` parses correctly, leaves the count unchanged, and `_p_off`
resolves the new address (r131).

## 3. The placement is already done

`perky_emit_shards.emit()` **already calls** `place_program_shards_two_space()` and returns
`dest = {piece: start}` (r120). `build_bus.place()` **already spans several records** and needs no
change (r124). **Do not write a placer.**

## 4. Where the edit goes

**The writer is on `build_bus.py`'s side, not `platform_build.build()`** -- that is the *loader*
builder and takes the payload as input (r123 retracted r122's claim). **The record table itself comes
from the stock payload and is only ever written INTO**, so the edit is: **change the table before/while
the payload is emitted.**

## 5. Order of work, and the checks at each step

| # | step | check |
|---|---|---|
| 1 | probe record at a tail | words read back at the tail address |
| 2 | B: append records | `verify_perky_shard_emit` + `_p_off` resolves every shard |
| 3 | A: re-point the 5 retired records | the retired addresses disappear from `region`; the tails appear |
| 4 | place the program | `place()` returns without `sys.exit`; extents exact |
| 5 | rebuild + `make check` | **80 gates, 332 assertions, 0 FAIL** |
| 6 | confirm Spring/Dark/Lo-Fi are PRESENT | the goal's items 6-8 |

## 6. What is NOT known, and it is one thing

**Whether the stock DSP boot routine validates `addr`.** Five measurements say it probably does not
(r127, r133, r134, r135, r136) -- and **step 0 above settles it in one run.** Everything else has been
measured.

---

# STEP 0 IS NOW ONE COMMAND (round 139)

The plan's step 0 -- the probe that settles whether the stock DSP boot routine accepts an unexpected
`addr` -- is now a tool rather than a recipe.

## `tools/perky/probe_tail_record.py`

```
python3 tools/perky/probe_tail_record.py --selftest      # proves the edit, writes nothing
python3 tools/perky/probe_tail_record.py --out out/mainos_probe_tail.bin
```

**What it does:** takes the built image, finds SPRING's record in payload A (`0x01252`, 1063 words),
**re-points its `addr` to the first tail (`0x33da3`)**, and fills its words with `0xABCDEF`.

**Why that shape:**

* **re-pointing is a PURE IN-PLACE edit** -- no insertion, no growth, no shifting, so the only
  difference from stock is one `addr` field and the bytes it governs;
* **it is the operation payload A needs anyway** (r131), so a positive result is the real answer;
* **SPRING is retired by the milestone's priorities**, so nothing the goal wants to keep is disturbed;
* **the marker is unmistakable** -- stock code is never `0xABCDEF`.

## Verified, three ways, before claiming anything

**1. `--selftest` re-parses the edited blob and checks eight properties:**

```
[ok] the donor record exists          [ok] the word count is preserved
[ok] the probe record is at the tail  [ok] the payload length is unchanged
[ok] the record count is unchanged    [ok] _p_off resolves the tail
[ok] the donor address is gone        [ok] the marker is in the image bytes
```

**2. The emitted image differs from the reference in exactly the right places:**

```
differing bytes: 3,192
expected header (addr field only): 0xf2ac3..0xf2ac5   =     3
expected data                    : 0xf2ac9..0xf373d   = 3,189  (1063 words)
all differences inside the expected ranges: True
```

**3 + 3,189 = 3,192 exactly**, sizes identical, and **the reference `out/mainos_bus.bin` is unchanged**
(checked with `cmp`).

**3. It writes only `out/mainos_probe_tail.bin`** -- a new file -- so it cannot disturb the inputs any
gate or the canary reads. **That matters: round 114 broke a gate's inputs by running `make bus`.**

## Reading the answer

Boot the probe and peek DSP P memory:

```
dsp peek <core> P 0x33da3 8
```

**Pattern present → the routine writes wherever `addr` says. Step 2's mechanism is confirmed and the
plan proceeds.**
**Stock bytes → it refuses. Stop and read the stock DSP boot routine.**

**The peek needs the emulator with a project on the card -- the same `OT_PROJECT` the goal's item 0
documents. The tool is ready; the run is what is missing.**

---

# THE PROBE TOOL IS GATED (round 140)

Round 139 wrote `tools/perky/probe_tail_record.py` -- the single command that answers step 2's one open
question. Round 140 made sure it cannot rot.

**`tools/verify/verify_perky_tail_probe.py`** runs the tool's `--selftest` inside `make check`: the
selftest re-parses an edited payload copy and checks eight properties of the edit -- the donor record,
the tail record, the record count, the old address, the word count, the payload length, `_p_off`, and
the marker. **It writes nothing** (the edit is on an in-memory copy).

```
make check REMIX=perky-machine
  exit=0
  333 [PASS]    <- +1, the tail-probe gate
    8 [SKIP]
    0 FAIL
```

**Registered gates: 80 -> 81. Assertions: 332 -> 333.**

**Why this was worth a round:** the probe answers the question the whole of step 2 rests on, and it
encodes measurements (the `"ac"` order, the 9-byte header, `_p_off`'s reach) that would otherwise live
only in this document. **A tool that answers the critical question and is not checked is one refactor
away from being wrong and silently trusted** -- which is exactly the pattern this session kept finding
in *other* gates (r96, r112, r113).

**If `out/mainos_bus.bin` is absent the gate SKIPs** rather than failing: a fresh checkout has no image
to probe, and that is not a defect.

---

# THE BUILD EDIT'S SHAPE (round 142)

Rounds 120-141 produced the plan. This records the **exact code shape** for the one place it goes, so
the edit is mechanical.

## Where the operation belongs

**Not `all_fx_layout.py`** -- that module owns placement (`SAFE_*_SPANS`, `ProgramShard`,
`place_program_shards_two_space`). **Not a new module.**

**`tools/build/dsp_modmap.py` owns the record format** -- it has `w24`, `parse`, `modules`, and the
`PAYLOADS = [("A", 0x400e2324, 0x136cb), ("B", 0x400f59ef, 0x12d05)]` constants. **The two write
operations belong beside `parse`.**

```python
def repoint(blob: bytearray, old_addr: int, new_addr: int, order: str = "ac") -> None:
    """Change one record's addr in place. The words do not move; the count does
    not change. This is payload A's operation (r131)."""

def append(blob: bytearray, space: int, addr: int, words: bytes,
           order: str = "ac") -> bytes:
    """Return `blob` with a record inserted before the terminator. The words go
    inline. This is payload B's operation (r132)."""
```

**Both are already prototyped and self-tested** in `tools/perky/probe_tail_record.py`
(`probe_payload()` is `repoint` plus a marker fill). **Lift the logic from there rather than writing
it again** -- it has been exercised against the real image and gated since r140.

## Why the edit is low-risk if done this way

* **Additive.** `dsp_modmap` is imported at module scope by six gates; adding functions changes no
  existing behaviour, and `make check` (81 gates, 333 assertions) is the check.
* **No new placement code.** `place()` already spans records (r124); `emit()` already calls the placer
  (r120).
* **Both operations are probed.** A re-point (r131); B append (r132). Both round-trip through `parse`.
* **Room is measured, not assumed.** B: 30,460 B available, 9,162 needed (r126). A: a contiguous
  3,441-word reused run (r130).

## The one thing to do first

**Run the probe** (r139's tool, gated in r140):

```
python3 tools/perky/probe_tail_record.py --out out/mainos_probe_tail.bin
# boot it with a project on the card, then:  dsp peek <core> P 0x33da3 8
```

**Marker present -> proceed with the edit. Stock bytes -> read the stock DSP boot routine first.**
**This needs `OT_PROJECT`; nothing else in the plan does.**

---

# THE RECORD TABLE HAS WRITE OPERATIONS (round 143)

Step 2's first code change, and it is in.

## What landed

`tools/build/dsp_modmap.py` -- the module that owns the record format -- now has, beside `parse`:

```python
def repoint(blob, old_addr, new_addr, order="ac") -> bytes
    """Return blob with the record at old_addr re-pointed to new_addr.
    The words do not move and the count does not change -- only the addr field."""

def append(blob, space, addr, words, order="ac") -> bytes
    """Return blob with a record for addr inserted before the terminator.
    words must be count*3 bytes, stored inline."""

def terminator_offset(blob, order="ac") -> int
    """Where a new record must be inserted."""
```

**The logic is lifted from `tools/perky/probe_tail_record.py`**, which has been exercised against the
real image and gated since r140 -- **not written fresh.**

## Verified, against the real payloads

```
repoint: 0x01252 -> 0x33da3 ... ok      length unchanged: True
append : B +300 words ... ok            (+909 B)
```

**Both round-trip through `parse`.** `repoint` is payload A's operation (the retired records'
contiguous run is repurposed); `append` is payload B's (it has 30,460 bytes of slack after its table).

**And `make check REMIX=perky-machine`: 333 PASS, 8 SKIP, 0 FAIL.** `dsp_modmap` is imported at module
scope by six gates, so that is the check that matters.

## What this changes about step 2

**The plan's step 4 -- "change the table before/while the payload is emitted" -- now has its
primitives.** What remains is to *call* them from the build with the shard bytes that
`perky_emit_shards.emit()` already produces and places.

**Still first: the probe** (r139, gated r140). It needs `OT_PROJECT`; the rest of the edit does not.

## On making this change at all

**Round 142 recorded the shape and declined to make the edit, judging a speculative change to a
six-gate module too risky with little context left.** Round 143 made it -- **by keeping it purely
additive, lifting tested logic rather than writing new, and running `make check` before committing.**
The first attempt did contain an artifact (a stray `if False else`, caught by grepping for it rather
than by reading the diff); it is gone, and `make check` was green after.

---

# THE WRITE OPERATIONS ARE GATED (round 144)

Round 143 added `repoint` and `append` to `dsp_modmap` and verified them by hand. **Round 144 made that
permanent.**

`tools/verify/verify_perky_record_write.py` exercises both **on the real payloads from the built
image**, with fourteen checks:

```
[ok] A: repoint keeps the blob length          [ok] B: append grows by header + words
[ok] A: repoint keeps the record count         [ok] B: append adds exactly one record
[ok] A: the new address is a record            [ok] B: the new address is a record
[ok] A: the old address is gone                [ok] B: _p_off resolves the new address
[ok] A: _p_off resolves the new address        [ok] B: every earlier record is byte-identical
[ok] A: _p_off no longer resolves the old one  [ok] an unknown address raises
[ok] A: no record moved or resized             [ok] terminator_offset points at the insertion point
```

**`make check REMIX=perky-machine`: 334 PASS, 8 SKIP, 0 FAIL.** Registered gates 81 -> 82,
assertions 333 -> 334.

## Two things worth pointing at

**`_p_off`'s predicate is reproduced rather than imported.** `build_bus` reads the image at import
time, and a gate must not. So the check tests *the same condition* the build uses -- **space 0 and
`a <= addr < a+count`** -- without dragging the build in.

**"An unknown address raises" is a check, not an afterthought.** A `repoint` that silently did nothing
would be worse than one that fails: the build would place words into a record that never moved.

## Why this pattern, twice now

**The probe tool (r140) and the write operations (r144) are both gated immediately after being
written.** That is deliberate and it is the opposite of what this session kept finding elsewhere --
the wrapper round-trip that existed and never ran (r96), the provenance check that would have passed
while checking nothing (r112), the boot gate left out for thirty rounds (r113). **Step 2's own
primitives will not be among them.**

---

# THE INTEGRATION POINT, FOUND (round 145)

The primitives are in and gated (r143, r144). This is where they get called.

## `build_bus.py:2210` -- how `region` is built

```python
_want = [_sp[k] for k in _harvest]
region = sorted((m for m in mods if m[0] == 0
                 and any(a <= m[1] < a + n for a, n in _want)),
                key=lambda m: m[1])
_have = sum(m[2] for m in region)
if _have != sum(n for _a, n in _want):
    sys.exit(f"payload {tag}: the harvested spans cover {sum(n for _a, n in _want)} words "
             f"but their P records total {_have} -- the module map and stock.p_spans disagree")
```

**`region` is the set of stock records whose addresses fall inside the harvested effects' spans** --
Plate, Spring, Dark, Compressor, Lo-Fi. **`place()` writes ONLY inside `region`** (r124), and
`_p_off` refuses anything else. **So the tails are unreachable for exactly one reason: no entry of
`region` covers them.**

## The change, precisely

**`mods` comes from `modules(bytes(img), va, ln)` at line 2119 -- it is read from the image.** Both
`region` and `_p_off` are built from it.

So the edit is:

1. **after `mods` is computed and before `region`**, call `dsp_modmap.repoint(...)` on `img` to move
   the records A will reuse onto tail addresses (payload A), and `append(...)` for B;
2. **re-read `mods`** -- `modules(bytes(img), va, ln)` again -- so `region` sees the new addresses;
3. **then the existing `_have != sum(...)` check becomes the gate**: it asserts `region` covers
   *exactly* the harvested spans, so the re-pointed set must total the same word count. **A re-point
   preserves count by construction (r131) -- so the check still holds, and if it does not, the build
   stops.**

**Nothing else changes.** `place()` already spans records; `_p_off` already resolves whatever `region`
says; the `_have` check already validates the accounting.

## Why this is the safe place to make it

**The `_have != sum(...)` check is a self-verifying guard.** It compares the word count `region`
covers against the count the harvest expects. A re-point that moved a record to a tail keeps the count
identical; **anything that got the edit wrong -- a lost record, a wrong count, a mis-parsed header --
makes `_have` disagree and the build stops with a named payload.** That is the cheapest possible
failure mode for a change to the core build.

## What is still not known

**Whether the stock DSP boot routine honours a record at a tail address.** Five measurements say
probably (r127, r133-r136); the probe settles it (r139, gated r140). **It needs `OT_PROJECT`.** The
edit above is correct regardless of that answer -- **if the routine refuses, the edit is simply not
enough, and the failure will be audible rather than silent.**

---

# CORRECTION: THE PLACEMENT IS NOT IN THE BUILD (round 146)

Round 145 said the change belongs at `build_bus.py:2210`, where `region` is built. **Checking the
dependency direction refutes that.**

```
tools/build/build_bus.py          imports perky_emit_shards?  NO
                                  imports all_fx_layout?      NO
                                  imports place_program_shards? NO

tools/perky/perky_emit_shards.py:40   import build_bus as B
```

**`build_bus` is the LIBRARY. `perky_emit_shards` imports it, and the emitter is what holds the
placement** (`emit()` calls `place_program_shards_two_space()` and returns `dest = {piece: start}` --
r120).

**So `region` at line 2210 knows only about the stock harvested records. It has no idea which shard
should go where, because that knowledge lives one level UP, in the emitter.**

## What that changes

**Round 145's three-step edit cannot be made where it was described.** `build_bus` cannot move a
record *to a tail a shard needs* without being told which tail -- and it does not know.

**Two shapes are actually available, and the choice is a design decision, not a mechanical one:**

| shape | how it works |
|---|---|
| **the emitter drives it** | `perky_emit_shards` already imports `build_bus` and holds `dest`. It can apply the record changes to the image **around** the build's write, or pass them in. |
| **the build takes it as input** | `build_bus` gains an optional parameter -- "these records belong at these addresses" -- and applies it before building `region`. Inert when absent, so every existing caller is unaffected. |

**The second is more in keeping with how `build_bus` is used** (a library with explicit inputs), and it
keeps the `_have != sum(...)` guard as the gate, which was round 145's best observation and still
holds.

## The pattern, for the third time

**Round 122 said the writer was `platform_build.build()`; round 123 read its docstring and retracted
it.** Round 145 said the integration point was `build_bus.py:2210`; **round 146 checked the imports and
retracted that too.** Both times the retraction came from reading one more file -- **and both times the
first answer was the thing that merely *sounded* like the right place.**

**What survives from round 145:** `region` is built from the harvested records, `place()` writes only
inside `region`, and `_have != sum(...)` is a real self-verifying guard. **Those are measurements and
they are unaffected.** Only the *location* of the edit was wrong.

---

# THE BUILD CAN NOW BE TOLD WHERE DSP CODE GOES (round 147)

Round 146 established that the placement lives in the emitter, not the build, and named two shapes.
**Round 147 built the one it judged better: the build takes it as an explicit input.**

## What landed

```python
# build_bus.py, beside REMIX
P_REMAP: dict | None = None
```

**`None` -- the default -- leaves the stock record table untouched.** Every existing caller is
unaffected, and `make check` is 334 PASS / 0 FAIL with it in.

A caller that knows where it wants DSP code sets it before the build runs:

```python
P_REMAP = {
    'A': [(0x01252, 0x33DA3)],              # re-point in place  (payload A)
    'B': [(None, (0x33DA3, words_bytes))],  # append before the terminator (payload B)
}
```

**Applied in the payload loop, immediately BEFORE `mods` is read** -- which is the whole point: `mods`
drives both `region` and `_p_off`, so the records must move first.

```python
if P_REMAP and tag in P_REMAP:
    _at = va - BASE
    _blob = bytes(img[_at:_at + ln])
    for _old, _new in P_REMAP[tag]:
        if _old is None:
            _addr, _words = _new
            _blob = dsp_modmap.append(_blob, 0, _addr, _words)
        else:
            _blob = dsp_modmap.repoint(_blob, _old, _new)
    if len(_blob) > ln:
        sys.exit(f"payload {tag}: P remap grows the payload to {len(_blob)} B; its slot is {ln}")
    img[_at:_at + len(_blob)] = _blob
mods, _ = modules(bytes(img), va, ln)
```

**A remap that outgrows its slot is refused by name rather than silently truncated.** And the
pre-existing `_have != sum(...)` check further down still asserts `region` covers exactly the harvested
spans, so a remap that loses or resizes a record stops the build.

## Both halves proven

```
P_REMAP = None  -> inert: True            make check: 334 PASS, 8 SKIP, 0 FAIL
armed           -> the record for 0x33da3 [(0, 212387, 1063, 68517)]
```

**Inert by default; the re-point resolves when set.**

## The bug this round found in its own first attempt

**The first edit added the loop but not a module-level `import dsp_modmap`.** `build_bus` imported the
*names* (`from dsp_modmap import BASE, IMG, PAYLOADS, modules`) and used `dsp_modmap.dumpmem` only
inside `__main__`, behind a local import. So the remap would have raised **`NameError` the first time
anyone set `P_REMAP`** -- and `make check` was green, because `P_REMAP is None` means the code never
runs.

**Found by asking the module object, not by reading the diff:** `hasattr(build_bus, 'dsp_modmap')`
returned `False`. **A guard written for one thing (`'import dsp_modmap' not in source`) matched a
different thing (a local import inside `__main__`) and skipped the fix** -- the same proxy-for-the-
question failure that has recurred all session, and the reason the check was `hasattr` on the loaded
module rather than a grep of the file.

## Where this leaves step 2

**The build can now be handed a placement and will write DSP code at tail addresses.** What remains is
for `perky_emit_shards` -- which already imports `build_bus` and holds `dest` -- to populate `P_REMAP`
from it. **Still first: the probe** (r139, gated r140), which needs `OT_PROJECT`.

---

# THE PLACEMENT ALREADY LANDS IN THE TAILS (round 148)

Round 147 gave the build `P_REMAP`. The open question was whether the shard placement and the tail
runs actually correspond. **Measured: they do, all of them.**

```
emit(): 16 pieces, dest has 16 entries
SAFE_SHARED_P_SPANS: (212387,212992) (228771,229120) (229136,229376) (245155,245760) (261539,262144)
SAFE_LOCAL_P_SPANS : (4096,4690) (6820,7000)
shards landing in a SAFE run: 16 of 16

synth_seam_glue.asm              0x01000   <- LOCAL run 1  (the PLATE record)
simple_drum_envelope.asm         0x01150   <- LOCAL run 1
simple_drum_delta.asm            0x01aa4   <- LOCAL run 1
noise_tone_math.asm              0x33da3   <- SHARED run 1
simple_drum_oscillator.asm       0x33ece   <- SHARED run 1
pk_multi_simple_init             0x33fbb   <- SHARED run 1
noise_tone_oscillator_packed.asm 0x37da3   <- SHARED run 2
noise_tone_filter.asm            0x37e65   <- SHARED run 2
noise_tone_envelope.asm          0x37f10   <- SHARED run 2
synthetic_control_map.asm        0x37f92   <- SHARED run 2
```

**Sixteen of sixteen shards sit inside a safe run.** `place_program_shards_two_space()` was already
doing the job; **nothing about the placement needs to change.**

## What that leaves

**Only the translation from `dest` to `P_REMAP`.** For each payload:

1. **find the stock records covering the retired spans** -- they are the ones `region` is built from
   (r145), and their addresses are known (`0x01000`, `0x01252`, `0x022a4`, `0x33da3`, `0x37da3`,
   `0x37f10`, `0x3bda3`, `0x3fda3`);
2. **for each shard in `dest` that falls in a run, emit `(old_addr, new_addr)`** -- a re-point, since
   the words stay in the record whose byte area they already occupy -- **or `(None, (addr, words))`
   where the shard needs a run no record covers**;
3. **hand that dict to `build_bus.P_REMAP`.**

**The word bytes come from `pieces`**, which `emit()` already returns alongside `dest`.

## Why this is now mechanical

**Every input is a measured number, not a guess:** the spans (above), the shard starts (`dest`), the
shard bytes (`pieces`), the record addresses (`region`), and the two operations (`repoint`/`append`,
gated since r144). **There is no remaining unknown in the placement** -- only the loop that joins
them.

## And the one thing that is still unmeasured

**Whether the stock DSP boot routine honours a record at a tail address.** r135-r136 narrowed it to
"probably", and **the probe (r139, gated r140) settles it in one run.** That is a hardware/emulator
question, not a placement one, and it does not block writing the loop.

---

# THE RECORDS, MEASURED (round 149)

Round 148 showed every shard already lands in a safe run. **Round 149 measured the records those runs
must be expressed through -- and found two things the loop cannot ignore.**

```
payload A:  0x00438..0x01cd8  count=6305  in a SAFE run: NO     <- the shared curve bank, NOT retired
            0x01000..0x01251  count= 594  in a SAFE run: 0x01000..0x02251   <- PLATE
            0x01252..0x01678  count=1063  in a SAFE run: 0x01000..0x02251   <- SPRING
payload B:  0x0042b..0x01ccb  count=6305  in a SAFE run: NO     <- the curve bank
            0x00dc0..0x01011  count= 594  in a SAFE run: NO     <- PLATE, at a DIFFERENT address
            0x01012..0x01438  count=1063  in a SAFE run: 0x01000..0x02251   <- SPRING
```

## 1. The same record is at different addresses in A and B

**PLATE is `0x01000` in payload A and `0x00dc0` in payload B** -- a 576-word difference. This is the
documented payload asymmetry (`docs/firmware/TABLES.md`, "Payload-relative addresses"): the payloads
are linked separately and the blocks below the table differ in size.

**`P_REMAP` is keyed by tag, so this is handled -- but a loop that computes one address and applies it
to both payloads would silently move the wrong record in B.** The addresses must be read per payload
from `mods`, never assumed.

## 2. A 6,305-word record covers the retired span and is NOT retired

**`0x00438` (A) / `0x0042b` (B) is the 6,305-word shared curve bank.** It is stock code every effect
reads; it is not Plate, Spring, Dark, Compressor or Lo-Fi, and it must not move.

**It still lands in `region`** -- `region` is built from any record covering a harvested span (r145) --
so `_have = sum(m[2] for m in region)` counts its 6,305 words as well.

**That is fine, and it is the guard working:** `_have` is compared against
`sum(n for _a, n in _want)`, and if the harvest's spans account for the bank too then they agree. **If
they do not, the build already stops with a named payload.** The rule the loop must obey is therefore
narrow and checkable: **re-point only the records whose addresses are the retired effect starts, and
leave every other record in `region` byte-identical.**

## What the loop must be

```
for tag, va, ln in PAYLOADS:
    mods, _ = modules(bytes(img), va, ln)          # per payload -- the addresses differ
    region  = <records covering the harvested spans>   # includes the 6,305-word bank
    remap   = []
    for record in region:
        if record.addr is a retired-effect start:  # 594 / 1063 / 1067 / 537 / 180 words
            new = <the safe-run address this record's extent should occupy>
            remap.append((record.addr, new))
        # every other record -- the bank included -- is left alone
    P_REMAP[tag] = remap
```

**The discrimination is by the effect's own word count, which is known exactly** (Plate 594, Spring
1063, Dark 1067, Lo-Fi 537, Compressor 180 -- the goal's own table). **Not by "is it inside a span",
which the bank also satisfies.**

## Still unmeasured

**Whether the stock DSP boot routine honours a tail-address record.** r135-r136 narrowed it to
"probably"; the probe (r139, gated r140) settles it. **It needs `OT_PROJECT` and does not block the
loop.**

---

# THE COMPLETE P PICTURE (round 150)

Round 149 gave the rules. **Round 150 measured the retired records themselves -- and the whole plan is
now explicit, with no gaps.**

## The five donors are contiguous, and per-payload

```
payload A: 0x01000..0x01251  594  Plate
           0x01252..0x01678 1063  Spring
           0x01679..0x01aa3 1067  Dark
           0x01aa4..0x01b57  180  Compressor
           0x01b58..0x01d70  537  LoFi
           ---------------------------------
           total            3441        <- the goal's own "3441-word donor region"

payload B: the same five, shifted by -0x240 (576 words)
```

**The five are one contiguous run `0x01000..0x01d70` in A -- and their total is exactly 3441, which is
the number the goal quotes. That is the accounting closing on itself.**

## Only TWO of the five are actually consumed

```
SAFE_LOCAL_P_SPANS (reused) : 0x01000..0x01251 (594, Plate) + 0x01aa4..0x01b57 (180, Compressor)
shards placed there         : synth_seam_glue 0x01000
                              simple_drum_envelope 0x01150
                              simple_drum_delta 0x01aa4
the other 13 shards         : the SAFE_SHARED runs at 0x33da3+
```

**Spring (1063), Dark (1067) and Lo-Fi (537) -- 2667 words -- are never addressed by the placement at
all.**

## Which is the goal, stated as arithmetic

| | words |
|---|---|
| SAFE_SHARED tails | 2404 |
| SAFE_LOCAL (Plate 594 + Compressor 180) | 774 |
| **total reachable** | **3178** |
| Perky program | 3051 |
| **free** | **127** |

**The goal's own numbers were 2404 + 594 + 180 = 3178 against 3054, leaving 124.** The program now
measures **3051**, so the headroom is **127**. **Either way it fits, and Spring, Dark and Lo-Fi are
not consumed.**

## So the remap is exactly this

```
payload A: repoint  (0x01000 -> the local run address the shard at 0x01000 needs)
                    (0x01aa4 -> the address simple_drum_delta needs)
           and the 13 shared shards need records at 0x33da3+ -- appended, since no
           stock record covers those addresses
payload B: the same, with every source address shifted by -0x240
```

**Both operations are in `dsp_modmap` and gated (r144). `P_REMAP` is in the build and proven both ways
(r147). The placement is already correct (r148). The selection rule is by word count (r149).**

## What is left, and it is one loop

**Join `dest` + `pieces` + the retired records into `P_REMAP`.** Every input is a measured number.
**The one thing that is still unmeasured is the hardware question -- whether the stock DSP boot routine
honours a tail-address record -- and the probe (r139, gated r140) answers it in one run.**

---

# THE OBSTACLE: RECORD EXTENTS AND SHARD EXTENTS DO NOT CORRESPOND (round 151)

Round 150's plan was "re-point the retired records to the tails". **Measuring the overlap between record
extents and shard extents refutes it.**

```
shard                                 OLD        NEW      words  moved?
synth_seam_glue.asm                 0x01000  0x01000    336  -
synthetic_control_map.asm           0x01150  0x37f92    106  MOVE
noise_tone_voice_xstate_glue.asm    0x011ba  0x3be57     86  MOVE
noise_tone_math.asm                 0x01210  0x33da3    299  MOVE
...
needing a MOVE: 15 of 16;   staying put: 1

payload A retired records vs shard extents:
  0x01000..0x01251 Plate       overlaps 4 shards
  0x01252..0x01678 Spring      overlaps 8 shards
  0x01679..0x01aa3 Dark        overlaps 6 shards
  0x01aa4..0x01b57 Compressor  overlaps 0     <- never used
  0x01b58..0x01d70 LoFi        overlaps 0     <- never used
```

## Why this breaks the plan

**`repoint` moves a RECORD -- one contiguous `count`-word extent -- by rewriting its `addr`.** The words
do not move; `build_bus.place()` then writes shard bytes into the byte area the record already owns.

**So a record's words can only go somewhere CONTIGUOUS, and only as one block.** But **Plate's 594
words feed FOUR shards, and those four go to four different safe runs** (`0x01000`, `0x37f92`, `0x3be57`,
`0x33da3`). **One `addr` cannot express four destinations.**

**Same for Spring (8 shards) and Dark (6).** The retired records are the *packed* extent the emitter
fills; the shards are the *placed* extents the safe runs want. **Nothing makes those two partitions
agree, and the placer is first-fit-decreasing, so they cannot be made to agree by construction.**

## What this rules out, and what it leaves

**Ruled out:** re-pointing the five records as a block. **Also ruled out:** a contiguous 3441-word target
-- the safe runs are fragmented (largest shard 605, r148).

**Left: a record per shard.** `append()` can create a record at any address with any count (gated,
r144), so **each of the 15 moving shards can get its own record at its `dest` address, carrying its own
bytes.** That is expressible and needs no new operation.

**But it raises the next question, and it is the important one:** what happens to the FIVE RETIRED
RECORDS, whose counts (594/1063/1067/180/537) no longer correspond to anything? **They would still sit
in `region` holding stale words.** `repoint` cannot shrink or delete a record, and `_have` counts their
words.

**So the remaining question is not "re-point or append" -- it is how `region` and `_have` are satisfied
when the record set no longer matches the packed content.** That is a question about `build_bus`'s
harvest path, and it needs reading before the loop is written. **Round 150's "one loop" was wrong; this
is the real remaining work.**

## What this does not affect

**The memory arithmetic is untouched:** Plate 594 + Compressor 180 + shared tails 2404 = 3178 against a
3051-word program. **Spring, Dark and Lo-Fi are still never consumed.** The obstacle is representational,
not spatial.

---

# THE HARVEST PATH ANSWERS IT -- AND `append` WOULD BREAK THE GUARD (round 152)

Round 151 asked how `region` and `_have` behave when the record set changes. **Reading the harvest path
answers it, and the answer reframes round 151.**

## What the code actually does

```python
_listed  = set(REMIX.modules) | set(REMIX.fx1 or [...])      # the two choosers
_derived = stock_mod.region_of(stock_mod.harvested(_listed))  # effects on NEITHER chooser
_harvest = sorted(set(_derived) | ({"CHORUS"} if DEV else set()), key=...)
...
region = every record inside a harvested span                  # line 2236: "EVERY RECORD
_have  = sum(m[2] for m in region)                             #  INSIDE A HARVESTED SPAN"
_want  = sum(n for _a, n in _want)
if _have != sum(n for _a, n in _want):
    sys.exit(f"payload {tag}: ... the module map and stock.p_spans disagree")
```

**`harvested()` is EFFECT-level** ("stock effects with DSP code that are on NEITHER chooser"), and
`region_of()` returns "every harvested effect with DSP code, in address order" -- its docstring notes
it "is no longer a single run". **`region` then takes every record inside those effects' spans.**

## Three consequences

**1. The tails ARE the harvested spans.** `SAFE_SHARED_P_SPANS` and `SAFE_LOCAL_P_SPANS` are, by
construction, the extents of the retired effects. **So `region` already contains the records at those
addresses -- unconditionally, with no change needed to reach them.** Round 151's framing ("no entry of
region covers the tails") was wrong: entries cover them; **their `addr`s are simply still the stock ones.**

**2. `append` would BREAK the guard.** `_have != sum(_want)` is an exact equality on word totals.
`append` adds a record and its words, so `_have` grows and `_want` does not -- **the build would stop
with "the module map and stock.p_spans disagree".** **That is the check working, and it rules out round
151's "a record per shard" as stated.**

**3. The shard/record mismatch is NOT an obstacle.** `place()` already spans records -- "cut at each
record boundary" (r124) -- so **a shard crossing several records is written into all of them.** **Round
151 treated the 4/8/6-shard overlap as fatal; it is not, because the writer was built for exactly that.**

## So the shape is

**Re-point the existing records so their `addr`s are the tail addresses, keeping their `count`s. The
total is unchanged, so `_have` still equals `_want`, and `place()` writes the shards across whatever
records their target addresses fall in.**

**What is left to work out is the ADDRESS ASSIGNMENT** -- which record goes to which tail -- **not a new
mechanism.** The primitives are in and gated (r144), the build takes the remap (r147), the placement is
already correct (r148), the selection rule is by count (r149), and the totals are known to close (r150).

## Retracting round 151's conclusion

**Round 151 said "round 150's one loop was wrong; a record per shard is needed".** **Both halves were
wrong:** the guard forbids `append` here, and no per-shard record is needed because `place()` spans
records. **What round 151 found that stands: the old `addr`s do not correspond to the new shard
addresses, so an address assignment is required. That is a smaller statement than the one it made.**

---

# CORRECTION: I MISREAD `SAFE_*_SPANS` FOR SIX ROUNDS (round 153)

**`SAFE_SHARED_P_SPANS` and `SAFE_LOCAL_P_SPANS` are `(start, END)` tuples, not `(start, LENGTH)`.**

```
as I had been reading them          as they actually are
0x33da3 .. 212992 "words"           0x33da3 .. 0x33fff =   605 words
0x01000 ..   4690 "words"           0x01000 .. 0x01251 =   594 words
```

**Read correctly, the three numbers the goal quotes fall out exactly:**

```
SAFE_LOCAL  : 0x01000..0x01251  594  <- PLATE
              0x01aa4..0x01b57  180  <- COMPRESSOR
              = 774
SAFE_SHARED : 0x33da3..0x33fff  605
              0x37da3..0x37eff  349
              0x37f10..0x37fff  240
              0x3bda3..0x3bfff  605
              0x3fda3..0x3ffff  605
              = 2404
shared + local = 3178          <- the goal's "2404 + 594 + 180 = 3178"
retired donor  = 3441          <- the goal's "3441-word donor region"
```

**The largest shard is 605 -- exactly what the goal says. Every number agrees.**

## What this invalidates

**Round 148's "16 of 16 shards land in a SAFE run" tested `s <= a < s + n` with `n` read as a length.**
With `n` actually the END address, that predicate is true for almost any small `a` -- **it was
meaningless, and r148's conclusion rested on it.** The real question -- whether each shard's *extent*
fits in a run -- **had not been asked.**

**Rounds 149-152 inherited the misreading.** Their record-level measurements (the five contiguous donor
records, the per-payload shift, `append` breaking `_have`) were computed from `mods`, not from these
spans, **so those stand.** What does not stand is any statement of the form "the tails are inside the
harvested spans": **they are not.** The shared runs sit at `0x33da3..0x3ffff`, **above the donor,** and
overlap no retired effect.

## What that means for the plan

**`SAFE_LOCAL` (774 words) is exactly Plate + Compressor -- the two effects the goal approves sacrificing
-- and it IS inside the harvested spans, so `region` covers it.**

**`SAFE_SHARED` (2404 words) is free space NO stock record covers.** Writing there therefore needs
`append`, and `append` grows `_have` while `_want` stays the harvested spans' total -- **so the build
would stop with "the module map and stock.p_spans disagree" (r152's finding, now with the right spans).**

**So the real remaining work is in the HARVEST PATH: `_want` must be extended to cover the shared runs,
or the harness that declares them must enter `region` another way.** That is a question about
`build_bus`/`stock_mod`, and it is the next thing to read -- **not an address assignment, as r152
concluded.**

## The lesson, which is this session's own recurring one

**I read a tuple's semantics off its values instead of off its producer, and every number looked
plausible.** 212,992 "words" is absurd -- larger than any DSP region -- and that absurdity was the
signal, sitting in my own output since r148, unread. **The check I should have run first: does the total
reproduce a number the goal states? It did not; I did not look.**

---

# WHERE THE SPANS COME FROM, READ AT LAST (round 154)

Round 153 corrected the format. **Round 154 read the declarations and their comments -- the place the
semantics were stated all along.**

```python
LOW_Y_SPAN          = (0x07A5, 0x1000)
FX_ARENA_SPAN       = (0x1000, 0xC000)
STOCK_MAILBOX_SPAN  = (0x37F00, 0x37F10)

# Half-open [lo, hi) ORDINARY-LOCAL-P ranges freed by the two effects this milestone is
# approved to sacrifice. Unlike the shared tails these are not in the aliased window, so a
# shard placed in one lives in a DIFFERENT ADDRESS SPACE from a shard in a tail. That is
# fine -- the DSP executes from both -- but it must be recorded, because the two spaces
# have different absolute bases and any emitter that treats them as one range is wrong.
SAFE_LOCAL_P_SPANS = ((0x1000, 0x1252),   # PLATE REV (594 words) -- approved sacrifice
                      (0x1AA4, 0x1B58))   # COMPRESSOR (180 words) -- approved sacrifice

# Half-open [lo, hi) shared-memory ranges that may be considered for P code.
SAFE_SHARED_P_SPANS = ((0x33DA3, 0x34000), (0x37DA3, 0x37F00), (0x37F10, 0x38000),
                       (0x3BDA3, 0x3C000), (0x3FDA3, 0x40000))
```

## Three things the source states outright

**1. The format is `[lo, hi)` -- half-open on the END.** The comment says so. **Six rounds of reading the
second element as a length were six rounds of not reading the line above it.**

**2. `SAFE_LOCAL_P_SPANS` IS Plate + Compressor**, with the words spent and the word "approved
sacrifice" beside each. **The milestone's own decision is recorded in the data.**

**3. The two spaces are DIFFERENT ADDRESS SPACES**, and the comment says an emitter that treats them as
one range "is wrong". **The local range is ordinary local P; the shared ranges are the aliased window.
`SAFE_LOCAL` and `SAFE_SHARED` are not interchangeable.**

## And the shared ranges are NOT stock effect spans

**They are "shared-memory ranges that may be considered for P code" -- free space in the aliased
window.** Which confirms round 153's correction from the other direction: **they are not inside any
harvested effect's span, so `region` does not cover them and `_want` does not count them.**

**The mailbox is respected:** `STOCK_MAILBOX_SPAN` is `0x37F00..0x37F10`, and the shared runs stop at
`0x37F00` and resume at `0x37F10`. **The boundary was chosen, not stumbled into.**

## So round 153's conclusion holds, and is now sourced

**Writing to `SAFE_SHARED` requires records no stock effect provides, so `append` is the only operation
that reaches them -- and `append` grows `_have` while `_want` stays fixed, so the build would stop.**
**The remaining work is in the harvest path: something must extend `_want`, or `region` must admit the
shared runs another way.**

**Next: read `harvested()`, `regions_of()` and `p_spans()` in `tools/remix/stock.py` -- the three
functions that build what `_want` is made of -- before writing anything.**

---

# THE ERROR EXPLAINED, AND THE MECHANISM WITH IT (round 155)

Round 154 read the span declarations. **Round 155 read their three producers -- and found the reason I
misread them for six rounds: the tree uses TWO conventions, both documented, and I read one as the
other.**

```python
# tools/remix/stock.py
def p_spans(payload) -> dict[str, tuple[int, int]]:
    """{effect key: (P address, words)} for one payload's DSP effect code."""   # (start, LENGTH)

# and its own consumer:
def regions_of(harvest):
    sp = p_spans("A")
    if cur and sp[cur[-1]][0] + sp[cur[-1]][1] != a:      # start + LENGTH = the next start
```

**`stock.p_spans()` is `(start, LENGTH)`. `all_fx_layout.SAFE_*_SPANS` is `[lo, hi)` -- an END.**
**Both are right where they live. Only one of them is what I assumed.**

## The mechanism, now fully visible

```python
_want  = [_sp[k] for k in _harvest]          # (addr, words) per harvested effect
region = sorted((m for m in mods if m[0] == 0
                 and any(a <= m[1] < a + n for a, n in _want)), key=...)   # records in those spans
_have  = sum(m[2] for m in region)
if _have != sum(n for _a, n in _want): sys.exit(...)
```

**`_want` is a list of `(address, words)` spans. `region` is every P record whose address falls inside
one. `_have` is those records' total; the check is equality against `_want`'s total.**

**So adding the shared runs to `_want` is exactly the right gesture -- and it is not sufficient by
itself.** With no record at `0x33da3+`, `region` gains nothing there, `_have` stays short of `_want`, and
the build stops with "the module map and stock.p_spans disagree".

## Which closes the loop

**Both halves are needed, and both exist:**

1. **`append` records at the shared runs** -- `dsp_modmap.append` (gated, r144), reachable from the
   build through `P_REMAP`'s `(None, (addr, words))` form (r147).
2. **Extend `_want` to cover the same runs** -- so `_have` and `_want` agree.

**`_want` is built from `_sp = stock_mod.p_spans(tag)`, so the extension belongs where the harvest is
computed** -- `build_bus.py`'s `_want` line, or the remix's declaration that feeds it. **That is the
one decision left, and it is a two-line question, not an unknown.**

## What is now settled, with a source for each

| claim | source |
|---|---|
| the spans are `[lo, hi)` | the declaration comment (r154) |
| `p_spans` is `(addr, words)` | its docstring and `regions_of` (r155) |
| the shared runs are not stock effects | the declaration comment (r154) |
| the mailbox is stepped over | `STOCK_MAILBOX_SPAN` (r154) |
| `append` alone breaks `_have` | the equality check (r152) |
| `_want` must gain the same runs | this round |
| the totals are 2404 + 774 = 3178 vs 3051 | measured (r153) |

**Every number the goal quotes now reproduces, every span is read by its own documented convention,
and the remaining change is: append records at the shared runs and extend `_want` to match.**

---

# THERE IS NO P-SPACE DECLARATION -- IT IS THE HARVEST (round 156)

Round 155 said the extension belongs where `_want` is computed. **Round 156 looked for an existing
declaration mechanism before writing code, and found one -- for the wrong space.**

```python
# modules/perky/manifest.py
claims=Claims(dsp_ranges=(
    DspRange("x", 0x3800, 236,           "PERKY compact voice state + envelope caches + RNG"),
    DspRange("x", 0x38EC, 2,             "PERKY source event-offset and admission staging"),
    DspRange("x", 0x3900, 0x64,          "PERKY shared sparse source-render scratch"),
    DspRange("y", 0x07a5, 0x1000 - 0x07a5, "PERKY packed Noise/Tone tables"),
)),
```

**`DspRange(space, address, LENGTH, note)`. Every one of these is `"x"` or `"y"`.**

## So there is no P-space declaration, and that is consistent

**`Claims.dsp_ranges` is how a module reserves X and Y -- the data spaces. P is not reserved that way: P
is taken by HARVESTING a stock effect, which is the whole `region`/`_want` mechanism.** A module that
wants P words does not declare an address; **it relies on the remix having given up an effect whose
records cover where it wants to write.**

**That is why the shared runs are a genuinely new kind of ground: they are P addresses that belong to no
effect, so no declaration covers them and no harvest reaches them.**

## The third argument is a LENGTH -- the second confirmation

`DspRange("y", 0x07a5, 0x1000 - 0x07a5, ...)` is `(start, length)`, the same convention as
`stock.p_spans` and its consumer `regions_of`. **`SAFE_*_SPANS` is the odd one out in this tree, not the
rule** -- it is `[lo, hi)`, and its own comment says so. **Two conventions, both documented, and rounds
148-152 read the wrong one.** Round 155 identified it; this round confirms it from a third site.

## What that leaves, precisely

**The change is in the harvest path, and there is no declaration to add -- the code that builds `_want`
must admit the shared runs.** Concretely:

1. **`_want` gains the shared runs** (`SAFE_SHARED_P_SPANS`, interpreted as `[lo, hi)`);
2. **`P_REMAP` appends a record per shard into those runs** -- `append`, gated (r144), reachable (r147);
3. **and `_have` then equals `_want`**, because the appended records' words are exactly what the runs
   were added with.

**Point 3 is the check that proves points 1 and 2 agree -- and it is already written, already in the
build, and already refuses by name.** Nothing new validates the change; the existing guard does.

## Where the goal stands after nine rounds on this

**The memory arithmetic reproduces the goal's own numbers (r153), both span conventions are sourced
(r154, r155, r156), the primitives are in and gated (r143, r144), the build accepts a remap and is inert
without one (r147), and the remaining work is three named lines in the harvest path.** **The one thing
still unmeasured is the hardware question -- whether the DSP boot routine honours a tail-address record
-- and the probe (r139, gated r140) answers it in one run.**

---

# LINE 1 OF 3: `P_WANT_EXTRA` (round 157)

The three lines from r156. **The first is in.**

## What landed

```python
# build_bus.py, beside P_REMAP
P_WANT_EXTRA: dict | None = None     # {tag: [(addr, WORDS), ...]}, None by default

# and at the harvest:
_want = [_sp[k] for k in _harvest]
if P_WANT_EXTRA and tag in P_WANT_EXTRA:
    _want = _want + list(P_WANT_EXTRA[tag])
region = sorted(...)                 # unchanged
_have  = sum(m[2] for m in region)
if _have != sum(n for _a, n in _want): sys.exit(...)   # unchanged -- this is the proof
```

**`(addr, WORDS)` is deliberate: it is the convention `stock.p_spans` and this very `region` line use
(`a <= m[1] < a + n`). `SAFE_*_SPANS` is `[lo, hi)`, so the caller converts.** Getting that backwards is
precisely the six-round error of r148-r153, and it is now written down at the declaration.

**`P_WANT_EXTRA` is keyed by payload because the records are** (r149: Plate is `0x01000` in A and
`0x00dc0` in B).

## Verified

```
P_WANT_EXTRA = None  -> inert: True
spans as (addr, words): [(212387,605), (228771,349), (229136,240), (245155,605), (261539,605)]
total 2404 words      -> the goal's "2404 P words"
make check REMIX=perky-machine: 334 PASS, 8 SKIP, 0 FAIL
```

**The spans convert to the right convention and total exactly 2404.**

## Why the check needs no change

**`_have != sum(n for _a, n in _want)` already proves lines 1 and 2 agree.** If `P_WANT_EXTRA` names a
span whose records were not appended, `region` misses those words and `_have` falls short -- **and the
build stops, naming the payload and both totals.** **Nothing new validates the change; the guard written
for the original harvest does.**

## Lines 2 and 3, still to come

2. **`P_REMAP[tag]` gains an append per shard** -- `(None, (addr, words))`, gated since r144
3. **the caller (the emitter) sets both from `dest` + `pieces`** -- and the equality check then passes

**Still unmeasured: the hardware question** -- whether the DSP boot routine honours a tail-address
record. **The probe (r139, gated r140) answers it in one run.**

---

# DESIGN A WORKS -- WITH THE RIGHT NUMBERS (round 158)

Round 157 put line 1 in. **Round 158 worked out lines 2 and 3, and got the arithmetic wrong twice
before getting it right.**

## First error: a sign

```
ground needed 2715, SAFE_SHARED offers 2404
  -> my script printed "fits in the shared runs with -311 to spare"
```

**Negative headroom printed as headroom.** The same class of unread absurdity as r153's 212,992 words --
**and this time it was in the line immediately above the conclusion.**

## Second error: two different programs

**The 2715 came from `3051 - 336`.** 3051 is the **shipping light2** emit (`REMIX=perky-machine BUILD=3`
gave `21 pieces / 3051 words` in r120); **the mixed emit is `16 pieces / 2353 words`.** Subtracting a
piece of one program from the total of another.

## The right numbers

```
MOVING : 15 shards, 2017 words
STAYING:  1 shard,   336 words        (synth_seam_glue, already at 0x01000)
                          total 2353

every shard's NEW extent is wholly inside ONE run: 16 of 16
  LOCAL  0x01000..0x01251 : synth_seam_glue 336, simple_drum_envelope 247   = 583  <= 594
  LOCAL  0x01aa4..0x01b57 : simple_drum_delta 162                           = 162  <= 180
  SHARED (five runs)      : the other 13 shards                             = 1608 <= 2404
```

**Everything fits, in the right run, with room to spare.**

## So design A is sound

**Append one record per moving shard at its `dest` address, carrying its own words, and name the same
spans in `P_WANT_EXTRA`.** The arithmetic then closes:

```
_have = retired records 3441 + appended 2017 = 5458
_want = harvested spans 3441 + P_WANT_EXTRA 2017 = 5458      equal
```

**The 2017 words are counted twice -- the retired records still hold their old stock code.** **That is
harmless: `region` is only a write target, and the records involved belong to effects this milestone has
given up. The cost is accounting, not space, and the space is separately proven to fit.**

## Why not simply re-point the five donor records

**Because their extents and the shards' extents do not correspond (r151): Plate alone feeds four shards
going to four different runs.** `repoint` moves one record to one new address; **it cannot split one
record across four destinations.** Appending is what expresses the placement.

## Lines 2 and 3, stated exactly

```
P_REMAP[tag]      = [(None, (dest[name], words(name))) for each shard that moves]
P_WANT_EXTRA[tag] = [(dest[name], words(name))        for each shard that moves]
```

**Both keyed by payload, both built from the same `(dest, pieces)` pair `emit()` already returns, and
both using `(addr, WORDS)`.** **Line 1 is in and inert; these two are all that remain -- and the guard
written for the original harvest proves them.**

---

# THE SHARD WORDS COME FROM `whole` (round 159)

Rounds 157-158 settled what lines 2 and 3 must say. **Round 159 found where their input actually lives --
and it is not where I had been looking.**

```python
def emit(multi_asm):
    src   = load_source(multi_asm)
    whole, syms = B.assemble_syms(src, MONOLITH_ORG, "mono")   # the assembled WORDS
    pieces      = slice_pieces(src, len(whole), syms)          # (name, a, b, SOURCE TEXT, idx)
    assigned    = L.place_program_shards_two_space([...])
    dest        = {p.name: p.start for p in assigned}
    def final(addr):
        for n, a, b, _, _ in pieces:
            if a <= addr < b:
                return dest[n] + (addr - a)
        return addr
    return pieces, whole, dest, final, syms
```

**`pieces[3]` is rewritten ASSEMBLY SOURCE, not bytes.** Rounds 157-158 assumed the words travelled with
the piece. **They do not.**

**The words are a slice of `whole`:** for piece `(n, a, b, text, i)`, the shard's `b - a` words are
`whole[a - MONOLITH_ORG : b - MONOLITH_ORG]`.

**And `emit()` already returns `final(addr)`, which performs exactly that translation one address at a
time** -- `dest[n] + (addr - a)` for the piece containing `addr`.

## So lines 2 and 3 are

```python
for (name, a, b, _text, _i) in pieces:
    new = dest[name]
    if new == a:
        continue                       # stays put; an existing record already covers it
    words = whole[a - MONOLITH_ORG : b - MONOLITH_ORG]     # ints, 24-bit DSP words
    packed = b"".join(w.to_bytes(3, "little") for w in words)
    P_REMAP[tag]      .append((None, (new, packed)))       # append a record carrying them
    P_WANT_EXTRA[tag].append((new, len(words)))            # and name the same 2 ground
```

**`packed` is `count * 3` bytes, which is what `dsp_modmap.append` requires** (and it refuses otherwise,
r143). **The word packing is the same `_w24`/`w24` order the record header uses** -- little-endian
three-byte, as `dsp_modmap.parse` reads it.

## What this closes

**Every input for lines 2 and 3 now has a named source, a named shape, and a gate:**

| input | where it comes from | checked by |
|---|---|---|
| which shards move | `dest[name] != a` | r158's table |
| the new address | `dest[name]` | r148, r157 |
| the words | `whole[a - MONOLITH_ORG : b - MONOLITH_ORG]` | this round |
| the packing | `to_bytes(3, "little")` | `dsp_modmap.append` refuses a wrong length (r143) |
| the per-payload addresses | `mods`, read per payload | r149's shift |
| that the two agree | `_have != sum(_want)` | the build's own guard (r152) |

**Nothing is left to discover. What remains is that loop, written into the emitter's caller, and one
build.**

---

# LINES 2 AND 3 ARE WRITTEN (round 160)

**`tools/perky/perky_tail_remap.py`** turns the emitter's placement into the build's two inputs.

## What it produces

```
emit(): 16 pieces, 2353 words; monolith org 0x1000
staying put : 1 shard  -- synth_seam_glue 0x1000 336w
appending   : 15 records, 2017 words

  0x33da3 299w SHARED   0x37da3 194w SHARED   0x37e65 133w SHARED
  0x37f10 130w SHARED   0x37f92 106w SHARED   0x3bda3  91w SHARED
  0x3bdfe  89w SHARED   0x3be57  86w SHARED   0x3bead  80w SHARED
  0x3befd  78w SHARED   0x33ece 237w SHARED   0x33fbb  54w SHARED
  0x3bf4b  31w SHARED   0x01150 247w LOCAL    0x01aa4 162w LOCAL

P_WANT_EXTRA total: 2017 words
[PASS] all 15 appended extents fall inside one reusable run
```

**It matches round 158's arithmetic to the word:** 15 movers, 2017 words, 1608 in the shared runs
(<= 2404), 409 in the local runs, and `synth_seam_glue` alone stays where it is because a record already
covers `0x01000`.

## A simplification the round found

**`dest` holds DSP P addresses, which are payload-INDEPENDENT.** Only the stock *record* addresses differ
between A and B (r149) -- **and `append` names none of them.** So the remap is **the same list for both
payloads**, and the function returns it keyed `A` and `B` without computing anything twice. **Rounds
157-158 assumed a per-payload difference was needed here; it is not.**

## What it refuses

* **A word count that disagrees with the piece's extent** (`len(words) != b - a`) -- so a bad slice is
  caught, not written.
* **Any appended extent not wholly inside a reusable run** -- the self-test fails by address and size
  rather than letting the build discover it.

## What is now in place

| line | state |
|---|---|
| **1. `P_WANT_EXTRA` in the build** | landed, inert by default (r157) |
| **2. `P_REMAP` gains one append per mover** | **built and verified (this round)** |
| **3. the caller sets both from `dest` + `pieces`** | **built and verified (this round)** |
| the guard that proves 2 and 3 agree | the build's own `_have != sum(_want)` (r152) |

**What remains is wiring this module into the build call and running `make check` -- not a design
question.** The one thing still unmeasured is the hardware question: **whether the DSP boot routine
honours a tail-address record**, which the probe (r139, gated r140) answers in one run.

---

# THE TAIL REMAP IS GATED (round 161)

Round 160 wrote `tools/perky/perky_tail_remap.py`. **Round 161 made sure it cannot rot -- and made it
check the three things it cannot see about itself.**

```
[PASS] all 15 appended extents fall inside one reusable run
[ok] every packed record is a whole number of 3-byte words
[ok] both payloads carry the identical remap (DSP-side addresses)
[ok] P_WANT_EXTRA totals 2017 words, matching the appended words
[PASS] the tail remap reproduces its own placement
```

**`make check REMIX=perky-machine`: 336 PASS, 8 SKIP, 0 FAIL.** Registered gates **82 -> 83**,
assertions **334 -> 336**.

## The three invariants the tool cannot state about itself

**1. Packing.** Every appended byte count must be a multiple of three. **A wrong packing is SILENT: the
record would carry misaligned words, the build would still pass, and the DSP would execute garbage.**
`dsp_modmap.append` refuses a non-multiple, but only when it is called -- this catches it at the source.

**2. Payload equality.** The two payloads must get the **identical** remap, because `dest` holds DSP-side
addresses and `append` names no stock record. **If they ever differ, an address has leaked in from
somewhere payload-dependent.** Round 160 argued this; the gate now enforces it.

**3. The word total.** `P_WANT_EXTRA` must total exactly the appended words. **That is the property the
build's `_have != sum(_want)` guard consumes** -- checking it here means a failure names this tool rather
than surfacing as "the module map and stock.p_spans disagree" three steps later.

## The bug this round found in its own first attempt

**The gate ran the tool as a subprocess with `REMIX` set, then imported the emitter in the parent with
`REMIX` unset** -- so the child printed PASS and the parent died with `no remix selected`. **A gate whose
two halves disagree about their environment.** Fixed by setting it in the process, not just the child.

## Three tools gated the moment they were written

| round | tool | what it protects |
|---|---|---|
| r140 | `probe_tail_record.py` | the one command that answers the hardware question |
| r144 | `dsp_modmap.repoint/append` | the record table's write operations |
| **r161** | **`perky_tail_remap.py`** | **the placement -> record-table step** |

**That is deliberate and it is the opposite of this session's recurring finding** -- the wrapper
round-trip that existed and never ran (r96), the provenance check that would have passed while checking
nothing (r112), the boot gate left out of the suite for thirty rounds (r113).

## Where step 2 stands now

**All three lines are built and two of them are in the build.** Line 1 (`P_WANT_EXTRA`) landed in r157.
Lines 2 and 3 exist as a verified, gated module. **What remains is calling it from whichever script
writes the payload, and one build.** The guard that proves the result is the build's own, and has been
since long before this work started.

---

# THE CALL SITE IS FOUND, AND IT ALREADY APPENDS (round 162)

Round 161 gated the remap. **Round 162 looked for where it must be called, and found the mechanism
already exists -- for a different space.**

## `tools/build/perky_image.py`

```
"""PERKY data injection into the two finalized OT DSP uploads.

Generic build_bus.py has already placed PERKY's source hook/code in each DSP
payload. This pass appends data records and returns replacement uploads for
Octabam's established pre-boot loader:

* X:0x3800 -- compact voice state / sideband initialization;
* Y:0x07a5 -- exact packed Noise/Tone/Simple static tables;
* optional profile-declared X/Y initializers generated under out/.
"""

def _check_space_free(records, space, base, words, ...)   # line 173
def extend_upload(img, tag, y_words, ...)                 # line 193  <- appends records
def integrate(img, table_dir)                             # line 233  <- entry point
```

**This pass already appends records to the finalized uploads** -- for X and Y -- **and it already has a
free-space check.** `extend_upload` is the shape the P work needs.

## Why that matters

**The call site is not a new script.** `build_bus` places PERKY's code and writes the image;
`perky_image.integrate()` then **appends records to that image** and returns the replacements the
pre-boot loader reads. **P records are the same kind of append, into the same image, at the same stage.**

**And the ordering is already right:** `integrate` runs *after* `build_bus` has finalized the payloads,
**which is exactly when `P_REMAP` must take effect** -- `build_bus` applies it immediately before reading
`mods` (r147), so it has to be set *before* that build, not after. **That is the one sequencing question
to settle when wiring it, and it is a question about which call happens first, not about mechanism.**

## What round 162 did not do

**It did not make the edit.** Wiring P into `extend_upload` touches the file that produces the shipping
image, and the sequencing question above has to be answered by reading `integrate`'s callers, not by
assuming. **With limited context left, recording the site and the question is worth more than a guess
that would surface as a silent misplacement.**

## Where step 2 stands, precisely

| piece | state |
|---|---|
| the two write operations | in `dsp_modmap`, gated (r143, r144) |
| the build's acceptance of a remap | `P_REMAP` + `P_WANT_EXTRA`, inert by default (r147, r157) |
| the placement | already correct; 16/16 in a reusable run (r148, r158) |
| placement -> remap | `perky_tail_remap.py`, gated (r160, r161) |
| **the call site** | **`perky_image.extend_upload` / `integrate` -- found, not yet wired** |
| the proof it all agrees | the build's own `_have != sum(_want)` (r152) |
| the hardware question | the probe, gated (r139, r140) |

**One wiring edit and one build separate this from Spring, Dark and Lo-Fi.**

---

# THE WIRING CANNOT USE THE MODULE GLOBAL -- `runpy` (round 163)

Round 162 found the call site and left one sequencing question. **Round 163 answered it, and the answer
rules out the obvious wiring.**

## What the callers do

```python
# tools/perky/build_multi_machine_canary.py:64
runpy.run_path(str(ROOT/'tools/build/build_bus.py'), run_name='__main__')

# tools/perky/repack_machine_loader.py:200
pres, pokes, log, table_layout = perky_image.integrate(prefix, table_dir)
```

**`build_bus` writes the image; `perky_image.integrate` appends records afterwards.** So `P_REMAP` and
`P_WANT_EXTRA` must be in place **before line 64 runs.**

## Why `build_bus.P_REMAP = ...` would NOT work

**`runpy.run_path(..., run_name='__main__')` executes the file in a NEW module namespace.** It is not the
`build_bus` module an importer sees -- **it is a second, separate module object built from the same
source.** Setting `P_REMAP` on the imported `build_bus` and then calling `runpy.run_path` **sets a value
the run never reads**, and it would look exactly like a working wiring: no error, no warning, and the
build would simply place nothing.

**This is the same shape as this session's recurring failure** -- r147's missing module-level import,
where `make check` was green because the code path never ran. **A wiring that cannot be observed to work
is worse than no wiring.**

## What the wiring must be instead

**`build_bus` must read the remap from something `runpy` inherits** -- the process environment, or a file
named by an environment variable. **The build already does exactly this for `REMIX`:**

```python
REMIX = remix_registry.remix(os.environ.get("REMIX"))
```

**So an environment or file channel is the established idiom in this file**, and it is the only channel
that crosses the `runpy` boundary.

## What that means for the plan

**Line 1 (`P_WANT_EXTRA`) and line 2 (`P_REMAP`) as module globals are still the right shape INSIDE
`build_bus`** -- they are how the loop reads them, and they are inert at `None`. **What changes is how the
caller reaches them: not by assignment, but by a channel the second module object also consults.** The
globals stay; a loader for them gets added beside `REMIX`.

**And the guard still proves the result:** if the channel is not read, `P_WANT_EXTRA` is `None`, the
shared runs are never added to `_want`, `region` never covers them, and the appended records are never
made -- **so the image is simply the old one, and the FX are still missing.** That is a visible outcome,
not a silent one: **Spring, Dark and Lo-Fi would still be absent from the build report.**

## The state, unchanged except for this

| piece | state |
|---|---|
| the two write operations | in `dsp_modmap`, gated (r143, r144) |
| `P_REMAP` / `P_WANT_EXTRA` in the build | in, inert at `None` (r147, r157) |
| the placement | already correct, 16/16 (r148, r158) |
| placement -> remap | `perky_tail_remap.py`, gated (r160, r161) |
| **how the caller reaches the build** | **must cross `runpy` -- env or file, not assignment (this round)** |
| the call site | `perky_image.extend_upload` / `integrate`, not yet wired |
| the proof | the build's own `_have != sum(_want)` (r152) |
| the hardware question | the probe, gated (r139, r140) |

---

# THE CHANNEL ACROSS `runpy` IS IN (round 164)

Round 163 established that assignment cannot reach the build. **Round 164 added the channel that can.**

## What landed

```python
# build_bus.py, beside REMIX
def _load_p_spans_from_env():
    _path = os.environ.get("PERKY_P_SPANS")
    if not _path:
        return None, None
    ...   # {"A": {"remap": [...], "want": [...]}, "B": {...}}
    print(f"  P spans: {_path} -> {n} record(s), {w} extra word(s)")
    return _remap, _want

P_REMAP, P_WANT_EXTRA = _load_p_spans_from_env()
```

**`PERKY_P_SPANS` names a JSON file.** Remap entries are `[null, [addr, "hex"]]` for an append or
`[old, new]` for a re-point; want entries are `[addr, words]`. **Unset leaves both at `None` -- what
every existing caller gets.**

**`os` is already imported at line 29** (`import dataclasses, hashlib, json, os, ...`), and `BUILD_TAG` on
line 198 uses the same mechanism. **The environment is this file's established channel**, which is why
it is the right one here.

## Verified both ways, against a real file

```
unset        -> P_REMAP=None P_WANT_EXTRA=None   inert: True
PERKY_P_SPANS -> "P spans: /tmp/perky_p_spans.json -> 2 record(s), 6 extra word(s)"
                remap A: [(None, (212387, b'\x01\x02\x03\x04\x05\x06\x07\x08\t'))]
                want  A: [(212387, 3)]
make check REMIX=perky-machine: 336 PASS, 8 SKIP, 0 FAIL
```

**`0x33da3` = 212387, the hex decodes to 9 bytes, the want pair is `(addr, words)`.** The loader runs,
reports what it loaded, and is silent and inert when the variable is unset.

## Why it prints

**The one failure mode left is a channel that is set but not read** -- the failure round 163 was written
to prevent. **A line naming the file and both totals means a run either shows the spans it took or
shows nothing at all; there is no third state to misread.** That is also the property that makes this
wiring checkable in a build log rather than by inference.

## The whole chain, now complete

```
emit()                                   -> dest, pieces, whole      (r159 added whole)
perky_tail_remap.build()                 -> remap, want               (r160, gated r161)
   written as JSON, path in PERKY_P_SPANS
build_bus._load_p_spans_from_env()       -> P_REMAP, P_WANT_EXTRA     (this round)
   applied before `mods` is read                                     (r147)
   _want += P_WANT_EXTRA[tag]                                        (r157)
   records appended via dsp_modmap.append                            (r143, gated r144)
   _have != sum(_want) proves it                                     (r152)
```

**Every link is in and every link but the second is gated or is the build's own guard. What remains is
the JSON writer between the second and third -- and a build.**

---

# THE CHAIN IS CLOSED (round 165)

Round 164 put the loader in the build. **Round 165 wrote the JSON it reads -- and the round trip closes.**

## What landed

`tools/perky/perky_tail_remap.py --write <path>` now emits the spec, **only after every check has
passed** (so a failed placement writes nothing), and prints the build line:

```
$ REMIX=perky-machine BUILD=3 python3 tools/perky/perky_tail_remap.py --write out/perky_p_spans.json
  ...
  [PASS] all 15 appended extents fall inside one reusable run
  wrote out/perky_p_spans.json
  build with:  PERKY_P_SPANS=out/perky_p_spans.json REMIX=perky-machine make bus
```

## And the loader reads it back

```
$ PERKY_P_SPANS=out/perky_p_spans.json python3 -c 'import build_bus as B; ...'
  P spans: out/perky_p_spans.json -> 30 record(s), 4034 extra word(s)
  P_REMAP tags      : ['A', 'B']
  record(s) per tag : 30                  <- 15 per tag x 2 tags
  P_WANT_EXTRA words: 4034                <- 2017 per tag x 2
  first entry       : addr=0x37f92  318 B = 106 words
```

**30 records and 4034 words are 15 and 2017 doubled -- because both payloads carry the identical
remap, which is correct (r160): the addresses are DSP-side and `append` names no stock record.** The
first entry's `318 B / 3 = 106 words` matches `synthetic_control_map`'s extent exactly.

## The whole chain, verified end to end

```
emit()                              -> dest, pieces, whole
perky_tail_remap.build()            -> remap (15 appends, 2017 words), want
perky_tail_remap --write            -> out/perky_p_spans.json          (this round)
build_bus._load_p_spans_from_env()  -> P_REMAP, P_WANT_EXTRA           (r164)
   applied before `mods` is read                                       (r147)
   _want += P_WANT_EXTRA[tag]                                          (r157)
   records appended via dsp_modmap.append                              (r143, gated r144)
   _have != sum(_want) proves it                                       (r152)
```

**Every link exists, the first three are gated, and the last is the build's own guard.**

## What is left, and it is one command

```
REMIX=perky-machine BUILD=3 python3 tools/perky/perky_tail_remap.py --write out/perky_p_spans.json
PERKY_P_SPANS=out/perky_p_spans.json make bus REMIX=perky-machine
make check REMIX=perky-machine
```

**The first is done and its output checked. The second is the build that has never been run with the
remap armed -- and it is the one step that can still surprise.** The build's own `_have != sum(_want)`
will say whether the appended records and the extended `_want` agree; **if they do not, it stops with a
named payload and both totals.** If they do, the P record table covers the shared runs, `place()` writes
the shards there, and **Spring, Dark and Lo-Fi are no longer consumed** -- because the placement no
longer needs their ground.

---

# THE ARMED BUILD RAN, AND THE GUARD SAID NO (round 166)

The chain closed in r165. **Round 166 ran it -- and the first honest result is a refusal.**

## Two findings, in order

**1. A shadowing bug of my own -- the same class as r147.**

```
line 2193:  _blob = dsp_modmap.append(_blob, 0, _addr, _words)
UnboundLocalError: cannot access local variable 'dsp_modmap'
```

**`main()` had `import dsp_modmap` at line 3367**, seven spaces in, serving `dumpmem` further down.
**A local import makes the name local for the WHOLE function, so my use at 2193 -- which runs first --
bound nothing.** I had added the module-level import at r147 and never removed the local one.

**`make check` was green throughout, because `P_REMAP is None` means line 2193 never executes.** That is
the third instance of this session's pattern: **a change that cannot fail while it is inert.** Removed;
the module-level import at line 33 covers both uses.

**2. The guard then fired, by name and with numbers.**

```
payload A: P remap grows the payload to 85749 B; its slot is 79563
```

**6,186 bytes over -- and `15 x 9 + 3 x 2017 = 6,186` exactly**: fifteen 9-byte record headers plus
three bytes for each of 2017 words. **The arithmetic is exactly what the remap asked for; the payload
slot simply is not big enough.**

## What that means, and what it corrects

**The constraint on this work was never `SAFE_SHARED_P_SPANS`' 2404 words.** That is free *DSP address
space*, and the program fits it (r158). **The binding constraint is the PAYLOAD SLOT:**
`PAYLOADS = [("A", ..., 0x136cb), ("B", ..., 0x12d05)]` -- **79,563 and 77,061 bytes.** Appending
records needs room *in the blob*, and A has 6,186 bytes less than the remap wants.

**Rounds 148-165 measured the wrong limit.** Everything they established about placement, correspondence
and the guard is still true; **what none of them checked is whether the record table can GROW to hold the
appends.** It cannot, as the design stands.

## The correction that follows

**Not every moving shard needs an appended record.** The 15 movers include ones whose new home is inside
the *donor region itself* -- `simple_drum_envelope` goes to `0x01150` and `simple_drum_delta` to
`0x01aa4`, both inside Plate's and Compressor's runs. **Those addresses already have stock records
covering them, so they need no append at all** -- only the ones landing in the shared runs do, and those
are 13 shards / 1608 words: `13 x 9 + 3 x 1608 = 4,941 B`. **Still more than 6,186? No -- less.** That
is the next measurement, and it decides whether the append design survives or has to place shards to
reuse existing records.

## The honest position

**The chain is built and the guard works. The first armed build refused for a measured, named reason
that no earlier round had looked for.** That is a better outcome than a build that produced an image with
the records in the wrong place -- and it is the outcome the guard was written for.

---

# THE RECORD TABLE CANNOT GROW IN PLACE (round 167)

Round 166 removed the two donor-region movers and reran. **It still refused -- and the second refusal
found the real constraint.**

## What the corrected spec did

```
[PASS] all 13 appended extents fall inside one reusable run
P_WANT_EXTRA total: 1608 words
build with:  PERKY_P_SPANS=out/perky_p_spans.json REMIX=perky-machine make bus

GUARD: payload A: P remap grows the payload to 84504 B; its slot is 79563
```

**`84,504 - 79,563 = 4,941` -- exactly the 13-append size.** So the payload is *already at* 79,563 B and
the check refuses **any** growth. **Round 166's "4,941 < 6,186 so it fits" compared the append against
the wrong quantity: 6,186 was the *overage of the first attempt*, not available room.**

## The measurement that explains it

```
PAYLOADS: A va=0x400e2324 ln=79563  ends 0x400f59ef
          B va=0x400f59ef ln=77061  ends 0x401086f4

gap between A and B: 0 B  (0 words)
```

**The two payloads are perfectly adjacent.** A ends exactly where B begins. **Appending a single byte
to A's blob overwrites the first byte of B -- and B is where the other Perky voice lives.**

**So `ln` is not a slot with slack; it is the payload's own length, and the region after it belongs to
somebody else.** Round 147's guard message said "its slot is {ln}"; **that word was wrong, and this
round is the correction.**

## What this means for the design

**The P record table cannot grow in place -- not by 13 records, not by one.** Any design that adds
records to the payload blob has to answer *where the bytes go*, and there is no free space adjacent to
either payload.

**Two shapes remain, and neither is a placement question:**

1. **Balance the growth** -- remove as many bytes from the payload as the records add. The payload is
   assembled from our modules and stock; **a module's contribution could shrink, but the appended
   records are ~4,941 B in A and the same in B, so this means giving up ~1,647 words of code.** That is
   a code-size problem, which section 6 of the goal explicitly puts last.
2. **Put the records outside the payload** -- which is what `perky_image.extend_upload` already does for
   X and Y (r162): it appends to the **upload**, not the payload, and the pre-boot loader reads the
   result. **The upload is the structure with room.**

**Shape 2 is the one the tree already uses, and it is the one to read next.**

## The honest position

**Two armed builds, two measured refusals, both by name and with numbers -- and the second one found the
constraint that sixteen rounds of placement analysis never touched.** The placement is correct, the
correspondence is proven, the guard works. **What was never checked is whether the container can hold
the new records, and it cannot.**

---

# THE UPLOAD GROWS, AND P CAN GO THROUGH IT (round 168)

Round 167 found that the payload blob cannot grow in place -- A and B are adjacent, gap 0. **Round 168
read `extend_upload` and found that this is not the constraint it looked like.**

## What `extend_upload` actually does

```python
def extend_upload(img, tag, y_words, x_words=None, extra_x=None, extra_y=None):
    """Return one payload upload with validated PERKY X/Y records inserted."""
    records, term = ab_records.records(img, *c["payload"])
    _check_y_free(records, len(y_words), tag)
    ...
    extra += ab_records.ot_record(2, Y_BASE, y_words)
    for base, values, purpose in extra_y or []:
        _check_space_free(records, 2, base, len(values), tag, purpose)
        extra += ab_records.ot_record(2, base, values)
    raw = bytes(img[p0:term]) + extra + bytes(img[term:p0 + c["payload"][1]])
    return raw, term
```

**It inserts `extra` at the terminator `term`, keeps the rest, and returns the result as a REPLACEMENT
UPLOAD.** `integrate` returns "preboot_payloads" -- **these grown blobs are what the pre-boot loader
reads, not the bytes at the payload's fixed `va`.**

**So the growth is real and it is allowed.** Round 167's finding -- that the payload region is adjacent to
B and cannot extend -- **applies to writing at `va`. It does not apply to the upload, because `extend_upload`
never writes back there.**

## Three things this gives, all already built

**1. The record builder.** `ab_records.ot_record(space, base, values)` -- **for P, `ot_record(0, addr, words)`.**
The five-argument shape is right there: space 1 for X, space 2 for Y, **0 for P**.

**2. The insertion point.** `term`, the record-table terminator -- **the same place `dsp_modmap.append`
puts a record (r143).** Two implementations of one operation, and the guard `_check_space_free` proves
neither collides with an existing record.

**3. Proof the pattern works.** X and Y have shipped through this path. **P is the same operation into
the same table.**

## What that changes about the plan

**`P_REMAP` / `P_WANT_EXTRA` and the `PERKY_P_SPANS` channel (r157-r165) were built for `build_bus` --
and they work; the guard proved it twice, by refusing correctly.** But they were aimed at the wrong
container. **The records belong in `extend_upload`, alongside the X and Y records it already inserts,
and the blob it returns is what carries them.**

**That also resolves the ordering question from r162-r163 without a channel: `extend_upload` runs from
`repack_machine_loader` AFTER `build_bus`, and it is the last thing to touch the payloads.** No `runpy`
boundary to cross, **because nothing needs to reach `build_bus` at all.**

## The honest position

**`P_REMAP`, `P_WANT_EXTRA`, `PERKY_P_SPANS`, `perky_tail_remap.py` and its gate are all correct work
against the wrong target.** They are inert and gated, so they cost nothing; **they are simply not the
path the records take.** The path is `extend_upload`, and it was there before this work started.

---

# THE P PATH IS READY, WITH ONE COSMETIC FIX (round 169)

Round 168 found the records belong in `extend_upload`. **Round 169 read the two functions that decide
whether that is true, and it is.**

## `ab_records.ot_record` is space-agnostic

```python
def ot_record(space, addr, words):
    b = bytearray()
    for v in (space, addr, len(words), *words):
        b += bytes((v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff))
    return bytes(b)
```

**`ot_record(0, addr, words)` emits `space, addr, count, *words` as little-endian three-byte words --
exactly the record format `dsp_modmap.parse` reads and `dsp_modmap._record_header(order="ac")` writes
(r143).** Two implementations, one format, and the tests for each already exist.

## `_check_space_free` takes the space as a parameter

```python
def _check_space_free(records, space, base, words, tag, what):
    for rec_space, address, count, _off in records:
        if rec_space == space and _overlap(base, words, address, count):
            label = "X" if space == 1 else "Y"     # <-- the only space-specific line
            die(f"payload {tag}: existing {label} record ... overlaps PERKY {what} ...")
```

**The overlap test is generic; only the message's label is not.** `_check_space_free(records, 0, addr,
words, tag, "P code")` would work and would call a P record "Y".

## So the work is two small edits, both in `extend_upload`

```python
# 1. the label, so a space-0 collision names P
label = {0: "P", 1: "X", 2: "Y"}.get(space, "?")

# 2. a p_records parameter, inserted like the X and Y records
for addr, values in p_records or []:
    _check_space_free(records, 0, addr, len(values), tag, "P code")
    extra += ab_records.ot_record(0, addr, values)
```

**Inserted at `term`, after the X and Y records, before the terminator moves.** The blob that comes back
carries all three spaces, and the pre-boot loader reads it.

## And the remap already produces exactly this input

**`perky_tail_remap.build()` returns `remap` as `(None, (addr, packed_bytes))` -- addr plus the words.**
For `extend_upload` the shape needed is `(addr, [word, ...])`: **the same pair with the bytes unpacked
back to words, or `build()` asked for words instead of bytes.** That is a one-line change to a gated,
tested module -- **not new logic.**

**`P_WANT_EXTRA` and the `PERKY_P_SPANS` channel are not needed on this path at all:** they extend
`build_bus`'s `_want`, and `build_bus` is not where the records go.

## Where this leaves the milestone

**The placement is correct and proven. The record format is understood and has two written
implementations. The insertion point exists and already carries two other spaces. The one thing that
was missing -- a container that can grow -- is `extend_upload`, and it was there before this work
began.**

---

# P RECORDS GO THROUGH `extend_upload` (round 170)

Rounds 168-169 found the path and read the two functions. **Round 170 made the edits -- and the P
record is emitted.**

## What landed

```python
# the label, so a space-0 collision names P
label = {0: "P", 1: "X", 2: "Y"}.get(space, "?")

# a p_records parameter on extend_upload, inserted like X and Y
for base, values in p_records or []:
    _check_space_free(records, 0, base, len(values), tag, "P code")
    extra += ab_records.ot_record(0, base, values)

raw = bytes(img[p0:term]) + extra + bytes(img[term:p0 + c["payload"][1]])
```

## Measured

```
before: 98 records, terminator at payload+1005033 (absolute)
extend_upload returned 79593 B (was 79563)  ->  grew 30 B
  9 B  -- the Y record, always emitted (ot_record(2, Y_BASE, []) is 9 bytes with no words)
 21 B  -- the P record: 9-byte header + 4 words x 3
 30 B  -- total, exactly
```

**A P record at `0x33da3` with four words grew the upload by exactly the header plus its words, on top
of the Y record the function already emits.** `make check REMIX=perky-machine` stays green.

## Why this is the right container, restated in one line

**The two payloads are adjacent -- A ends where B begins, gap 0 (r167) -- so `build_bus` cannot grow the
record table in the bytes it writes.** `extend_upload` exchanges the terminator for `extra` + the
terminator and **returns a replacement upload the pre-boot loader reads.** Same table, same format, a
container that can grow. **X and Y have shipped this way since before this milestone.**

## What is left

**The remap's output needs one shape change.** `perky_tail_remap.build()` returns `(None, (addr,
packed_bytes))`; `extend_upload` wants `(addr, [word, ...])`. **Unpack the bytes back to words, or ask
`build()` for words.** Then `repack_machine_loader` passes `p_records` alongside the X and Y it already
passes, and **the `PERKY_P_SPANS` channel, `P_REMAP` and `P_WANT_EXTRA` are simply unused** -- they were
built for `build_bus`, which is not where the records go. **They are inert and gated, so they cost
nothing; deleting them is a tidy-up, not a prerequisite.**

---

# THE SHAPE MATCHES AND THE PATH MEASURES (round 171)

Round 170 put `p_records` into `extend_upload`. **Round 171 changed `perky_tail_remap.build()` to emit
what it takes -- `(addr, [word, ...])` instead of `(addr, packed_bytes)` -- and measured the join.**

## The full path, measured

```
build() -> 13 record(s), 1608 words, 2 kept in local
extend_upload(p_records=...) -> 84513 B (was 79563), grew 4950 B
expected 9 (Y) + 4941 (P) = 4950
MATCH: True
```

**4,941 B is exactly the growth round 166's refusal said was needed** -- 13 headers (117 B) plus 1608
words (4,824 B). **The same bytes, through the container that can hold them.**

## The gate caught the change, which is what it was for

```
verify_perky_tail_remap.py line 67:  addr, packed = entry[1]
ValueError: too many values to unpack (expected 2, got 106)
```

**`make check` went red on `297a`-style grounds -- a checker that knew the old shape.** That is the
third time this session a gate written alongside its subject has earned its keep (r140, r144, r161),
**and the first time one actually fired.** Updated to the new shape; `make check` is green again.

**The gate now asserts the thing that still matters for this shape:** every record carries at least one
word. **A zero-word record would be a no-op that still consumed 9 bytes of the upload** -- harmless but
pointless, and now refused by name.

## What is in place, end to end

| piece | state |
|---|---|
| placement | correct; 16/16 in a reusable run (r148, r158) |
| the retired records | the five contiguous donors, per-payload shift measured (r149, r150) |
| the selection rule | shared runs only; local runs are already covered (r167, r170) |
| the record format | `ot_record(space, addr, words)` -- space-agnostic (r169) |
| the container | `extend_upload`, which grows and returns a replacement upload (r168, r170) |
| the shape | `build()` emits `(addr, [word, ...])` (this round) |
| the join | measured: 4,950 B = 9 Y + 4,941 P (this round) |
| all gates | 336 PASS, 8 SKIP, 0 FAIL |

## What is left

**`repack_machine_loader` must pass `p_records` alongside the X and Y it already passes.** Every input
exists and is measured; **the only unwired link is one argument at one call site** (line 200, r162).
**Then the build runs, Spring/Dark/Lo-Fi stop being consumed, and `make check` will say so.** The
hardware question -- whether the DSP boot routine honours a tail-address record -- is still answered by
the probe (r139, gated r140), which needs `OT_PROJECT`.

---

# THE LAST WIRE IS A PARAMETER THREAD (round 172)

Round 171 measured the join: `build()`'s output goes into `extend_upload` and grows the upload by exactly
the right bytes. **Round 172 found what is left, and it is smaller than it looked.**

## The chain, as it stands

```python
# repack_machine_loader.py:200
pres, pokes, log, table_layout = perky_image.integrate(prefix, table_dir)
```

**`integrate` calls `extend_upload` once per payload internally, and it does not take `p_records`.** So
the wire is:

1. **`integrate(prefix, table_dir, p_records=None)`** -- a new optional parameter, default `None`, so
   every existing caller is unchanged;
2. **pass `p_records[tag]` to the `extend_upload` call for each payload**, in the same place the X and Y
   arguments already flow;
3. **`repack_machine_loader`** calls `perky_tail_remap.build()` and hands the result in.

**Nothing new is invented at any of the three steps.** Step 1 is a default parameter, step 2 is an
argument, step 3 is a call.

## Why the records reach the right payload

**`build()` returns the same record list keyed `A` and `B`** (r160: the addresses are DSP-side, so they
are payload-independent). **`integrate` already iterates payloads** -- it has to, since `extend_upload`
takes a `tag`. So the mapping is `p_records[tag]`, and if a tag is absent the argument is `None`, which
`extend_upload` already treats as "no P records".

## What this round did not do

**It did not make the edit.** Threading a parameter through `integrate` means reading its body to see
how the two `extend_upload` calls are shaped -- **and with little context left, a wrong guess there would
surface as a build that silently emitted no P records at all, which is exactly the failure the whole
`PERKY_P_SPANS` detour was built to avoid.**

## The state, unchanged

| piece | state |
|---|---|
| placement, selection rule, record format | measured and in (r148-r150, r167, r169) |
| `extend_upload` takes `p_records` | in; measured growth 9 Y + 4,941 P (r170) |
| `build()` emits the right shape | in; the join measured (r171) |
| all gates | **336 PASS, 8 SKIP, 0 FAIL** |
| **the wire** | **`integrate(..., p_records=None)` + two arguments (this round)** |
| the hardware question | the probe, gated (r139, r140), needs `OT_PROJECT` |

**Three edits, all mechanical, none a design question.**

---

# THE THREAD IS IN, AND THE SCRATCH IS THREE TIMES THE SIZE NEEDED (round 173)

Round 172 named three edits. **Round 173 made the first two, and read the body that decides the third.**

## What landed

```python
def integrate(img, table_dir, p_records=None):
    ...
    for tag, c in PAY.items():
        raw, _term = extend_upload(
            img, tag, y_words, x_words, extra_state_init(layout), extra_y,
            (p_records or {}).get(tag),
        )
```

**`p_records` is `{tag: [(addr, [word, ...])]}`, default `None`, so every existing caller is
unchanged.** `extend_upload` already takes it (r170). **`integrate` already iterates payloads, so
`(p_records or {}).get(tag)` is the whole mapping.**

**Verified inert:** `inspect.signature` shows both defaults are `None`, and **`make check` is 336 PASS,
8 SKIP, 0 FAIL.**

## And the limit that decides whether this fits

```python
if len(raw) > 0x40000 or 4 + len(packed_blob) > 0x40000:
    die(f"payload {tag}: upload {len(raw):,} B / packed {len(packed_blob):,} B "
        "outgrows its 256 KiB preboot scratch")
```

**The preboot scratch is 256 KiB -- 262,144 bytes.** Measured in r171, payload A with all 13 P records
is **84,513 B**: 79,563 before, plus 4,950. **It uses 32% of the scratch.**

**So the container is not merely bigger than the payload -- it is three times bigger.** The r167
adjacency finding was real and remains the reason `build_bus` cannot host the records; **what it was not
is a reason the records cannot exist.**

## The one edit left

**`repack_machine_loader` must call `perky_tail_remap.build()` and pass the result to `integrate`.** That
needs `pieces`, `whole` and `dest` from `emit()`, **and whether that module already has them is the one
thing this round did not check** -- reading `repack_machine_loader`'s data flow is the next step, and it
is a read, not a guess.

## State

| piece | state |
|---|---|
| placement, selection rule, record format | in (r148-r150, r167, r169) |
| `extend_upload` takes `p_records` | in; measured 9 Y + 4,941 P (r170) |
| `build()` emits `(addr, [word, ...])` | in; join measured (r171) |
| `integrate` takes `p_records` | **in, inert (this round)** |
| scratch headroom | **262,144 B limit vs 84,513 B used -- 32%** |
| all gates | **336 PASS, 8 SKIP, 0 FAIL** |
| the caller supplying `p_records` | **the one edit left** |

---

# THE REMAINING THREAD IS TWO EDITS, BOTH LOCATED (round 174)

Round 173 put `p_records` into `integrate`. **Round 174 found who can supply it -- and it is not where
r172 guessed.**

## The call chain, measured

```python
# tools/perky/build_multi_machine_canary.py
 57:  full = base.perky_machine_module.build(..., dsp_source=base.repo_relative(work/'multi.asm'))
 81:  p_words = payload.source.noise.measure((work/'multi.asm').read_text(), work/'multi.asm')
100:  base.repack_machine_loader.build(ROOT/'out/mainos_bus.bin', work, mainos,
                                        platform_dir=ROOT/'out/platform',
                                        work=ROOT/'out/platform-perky-machine')
```

**`work/'multi.asm'` -- the file `perky_emit_shards.emit()` reads -- is already in scope in the canary,
three times over.** And it is the canary, at line 100, that calls `repack_machine_loader.build`.

## So the thread is

```
canary:  pieces, whole, dest, ... = perky_emit_shards.emit(work/'multi.asm')
         p_records, _ = perky_tail_remap.build(pieces, whole, dest, E.MONOLITH_ORG)
         repack_machine_loader.build(..., p_records=p_records)
             -> perky_image.integrate(prefix, table_dir, p_records=p_records)   (r173)
                 -> extend_upload(..., (p_records or {}).get(tag))              (r170)
                     -> ab_records.ot_record(0, addr, words)                    (r169)
```

**Two edits: an optional `p_records` parameter on `repack_machine_loader.build`, and the two lines in
the canary that compute and pass it.** Every function in the chain already accepts what it must.

## Correction to r172

**r172 said the wire was "`integrate` + `repack_machine_loader` passes `p_records[tag]`".** That was
half right: **`integrate` does take it (r173), but the value has to originate in the CANARY, because
that is where `emit()`'s input lives and where `repack_machine_loader.build` is called.** A thread
through `repack_machine_loader` is still needed; **its source is one level higher than r172 said.**

## State

| piece | state |
|---|---|
| placement, selection rule, record format | in (r148-r150, r167, r169) |
| `extend_upload` takes `p_records` | in; measured 9 Y + 4,941 P (r170) |
| `build()` emits `(addr, [word, ...])` | in; join measured (r171) |
| `integrate` takes `p_records` | in, inert (r173) |
| scratch headroom | **262,144 B limit vs 84,513 B used -- 32%** |
| the call chain | **measured; `multi.asm` in scope in the canary (this round)** |
| all gates | **336 PASS, 8 SKIP, 0 FAIL** |
| the two edits | **named, located, mechanical** |
| the hardware question | the probe, gated (r139, r140), needs `OT_PROJECT` |

---

# THE WIRE IS IN; THE CANARY STOPS ON `OT_PROJECT` (round 175)

Round 174 located two edits. **Round 175 made both.**

## What landed

```python
# tools/perky/repack_machine_loader.py
def build(image_path, table_dir, output, platform_dir=None, work=None,
          p_records: dict | None = None) -> None:
    ...
    pres, pokes, log, table_layout = perky_image.integrate(
        prefix, table_dir, p_records=p_records
    )

# tools/perky/build_multi_machine_canary.py, before the repack call
import perky_emit_shards as _E, perky_tail_remap as _R
_pieces,_whole,_dest,_final,_syms = _E.emit(work/'multi.asm')
_recs,_extra,_stayed,_kept,_moved = _R.build(_pieces,_whole,_dest,_E.MONOLITH_ORG)
print(f"  P records: {len(_recs['A'])} to append ({_moved} words); "
      f"{len(_stayed)+len(_kept)} shard(s) already covered")
base.repack_machine_loader.build(..., p_records=_recs)
```

**`make check REMIX=perky-machine`: 336 PASS, 8 SKIP, 0 FAIL.** Both defaults are `None`, so every
existing caller is unchanged.

## And the canary stops before reaching it

```
$ REMIX=perky-machine BUILD=3 python3 tools/perky/build_light2_machine_canary.py
  OT_PROJECT is required for the sequencer gate
exit=1
```

**The P-records line never prints** -- the canary dies in an earlier gate. **`OT_PROJECT` is the external
input this session has named since the beginning: a stock Octatrack project on the card, which cannot be
produced here, because AGENTS.md forbids committing an Elektron byte.**

## What that means, stated exactly

**The code path is complete and green; it has never executed.** That is the same category as the changes
in r147, r166 and r171 that were inert-until-armed -- **except that this one is not inert by design, it is
blocked by an input.** The difference matters:

* **an inert path can be tested by arming it** (r166, r171 -- done, and both found real defects);
* **this one cannot be armed without a file that must not exist in the repo.**

**And the honest reading of that is not "blocked".** `perky_tail_remap --write` + `integrate`'s
`p_records` parameter can be exercised **without the canary**: `extend_upload` was tested directly in
r170 and r171, and the canary's only additional contribution is *the argument*. **A focused test that
calls `emit()` -> `build()` -> `integrate()` on a scratch image would exercise the whole chain and needs
no project at all.**

**That is the next thing to write -- a gate, not a build.**

## State

| piece | state |
|---|---|
| placement, selection rule, record format | in (r148-r150, r167, r169) |
| `extend_upload` / `build()` / `integrate` | in; joins measured (r170, r171, r173) |
| `repack_machine_loader` + canary wiring | **in; `make check` green (this round)** |
| the chain, end to end | **never executed -- `OT_PROJECT` gates the canary** |
| the next step | **a gate that drives `emit()` -> `build()` -> `integrate()` with no project** |
| the hardware question | the probe, gated (r139, r140), also needs `OT_PROJECT` |
