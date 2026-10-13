# Task 5 — restoring Spring / Dark / Lo-Fi: the measured feasibility picture

**Measured on `perky-2voice-milestone`. This corrects an arithmetic assumption in
the milestone brief, so it comes first.**

## The brief's arithmetic assumes one region; there are seven fragments

The brief reasons:

```
safe shared tails   2404
+ Plate              594
+ Compressor         180
=                   3178   >= 3054 (the Perky program)  ->  124 words headroom
```

**That sum is right, but it is not one region.** Measured from
`modules/perky/ALL_FX_MEMORY.md` and the stocked P spans:

| fragment | words | where |
|---|---:|---|
| shared tail 1 | 605 | `$33da3..$33fff` |
| shared tail 2 | 349 | `$37da3..$37eff` |
| shared tail 3 | 240 | `$37f10..$37fff` |
| shared tail 4 | 605 | `$3bda3..$3bfff` |
| shared tail 5 | 605 | `$3fda3..$3ffff` |
| **tails subtotal** | **2404** | shared window (`$30000..$3ffff`) |
| Plate's local run | 594 | local P `$1000..$1252` |
| Compressor's local run | 180 | local P `$1aa4..$1b58` |
| **total** | **3178** | **seven fragments, largest 605** |

**Plate and Compressor are NOT adjacent** — Spring (`$1252`), Dark (`$1679`) and
Lo-Fi (`$1b58`) sit between/around them, and those three are exactly the effects the
user requires back. So sacrificing Plate + Compressor frees **two separate local
runs**, not one 774-word run.

**Consequence: no single fragment is ≥ 3,054, so the current Perky program cannot be
placed contiguously at all.** It fits *only* if it is first split into pieces ≤ 605
words. Capacity is sufficient (3,178 with 124 slack); contiguity is not available.

## What exists, and what does not

**Exists:**
* `modules/perky/all_fx_layout.py` — the machine-readable contract, with
  `ProgramShard` / `ProgramPlacement` and `place_program_shards()`, a first-fit
  explicit indivisible-shard placer;
* `tools/verify/verify_perky_all_fx_placer.py` — exercises that contract;
* `dsp_asm` takes an arbitrary `org`, so an individual shard *can* be assembled at
  its own base (`tools/build/build_bus.py:629 assemble_src(src, org, label)`).

**Does not exist:**
* **no builder calls `place_program_shards`.** A tree-wide search finds the name in
  exactly two files: its own definition and the gate. The gate places *synthetic*
  shards. Nothing places the real program.
* **no sharded Perky source.** The composed program is one code stream assembled at
  one base — `perky-machine` still harvests all five effects as a single
  **3,441-word contiguous run** (measured from `remixes/test/perky-machine`, which is
  why the current image has no Spring, no Dark and no Lo-Fi).
* **`PERKY_MACHINES_TARGET.md` does not exist**, although `ALL_FX_MEMORY.md` cites it
  as the authority that overrides the historical "user accepted fewer effects" notes.
  The contract's own stated basis is therefore missing from this tree.
* **the placer cannot reach the local runs at all** — `place_program_shards` walks
  `SAFE_SHARED_P_SPANS` only, and its failure text says so: *"total free tail
  capacity is … largest original span 605"*. Even a perfectly sharded program cannot
  be placed by the existing placer, because the tails alone total **2,404 < 3,054**.

## Therefore task 5 is two pieces of work, not a placement tweak

1. **Shard the composed Perky program at relocation-safe boundaries** into pieces
   ≤ 605 words. This is the hard part: the program is one stream with local branches,
   data adjacency and `jsrl`/`bra` between regions, and the contract is explicit that
   *"code may only cross a hole after a builder has explicitly split it at a
   relocation-safe boundary"* and that a single indivisible shard larger than 605 is
   rejected **even when total capacity remains**.
2. **Extend placement to a second address space.** The tails are the shared window;
   Plate's and Compressor's runs are local P. A placer that handles both, with
   correct cross-space fix-ups, is required before the 774 local words are usable.

**Neither is a blocker requiring new information from the user — both are
engineering. But neither is small, and this is why the brief's "2404 + 594 + 180"
step is not the last step.**

## What was NOT done here

The FX recovery itself is **not implemented**. This document records the measurement
that determines its shape. The current tree still ships the five-effect harvest.

## Corollary worth knowing before choosing a path

If the program cannot be sharded below 605 words per piece without behavioural
change, the remaining levers in the brief's own priority order are **dead-code
removal, duplicate-helper folding, and constant/table sharing** — i.e. shrinking
3,054 toward the 2,404 that the *tails alone* provide, which is a **650-word**
reduction. The brief lists sharding first and code-size second; the measurement says
sharding alone is insufficient without also extending the placer, and code-size work
is insufficient without sharding. Both are needed.

---

# ADDENDUM — the complete stock P map, and the toolchain constraint

## There is no shortcut: stock P is one packed region with zero gaps

Measured from `stock.p_spans('A')` — every stock effect's P extent, sorted:

```
0x007d1   727  FILTER        0x01252  1063  SPRING REV
0x00aa8   261  SPATIALIZER   0x01679  1067  DARK REV
0x00bad   282  EQUALIZER     0x01aa4   180  COMPRESSOR
0x00cc7   207  PHASER        0x01b58   537  LO-FI
0x00d96   289  FLANGER       0x01d71   345  DJ EQ
0x00eb7   329  CHORUS        0x01eca   277  COMB FILTER
0x01000   594  PLATE REV
total 6158 words, 0x7d1..0x1fdf, ZERO GAPS
```

Every span abuts the next; the gap detector printed none. The `perky-machine` harvest
takes the contiguous upper part `0x1000..0x1d71` (3441 words, the five effects the
brief lists).

**So there is no larger contiguous run to move Perky into.** Restoring Spring (1063),
Dark (1067) and Lo-Fi (537) = 2667 words puts them back at their own addresses and
leaves Perky exactly Plate's 594 and Compressor's 180 — **two non-adjacent local
runs**, 2277 words short of the 3051-word program.

Capacity is not the problem: 774 local + 2404 in shared tails = 3178 >= 3051.
**Contiguity is the problem, and it is unavoidable without sharding.**

## `dsp_asm` cannot assemble a shard that references another shard

MEASURED — the assembler accepts exactly these options:

```
-in  -out  -org  -list  -sym
```

It **emits** a symbol table (`-sym`) and **cannot consume one**. There is no external
symbol, equate, or link input. It assembles **one self-contained unit at one origin**,
and every symbol that unit references must be defined inside it.

That is the concrete obstacle to the brief's plan. "Split the code at relocation-safe
boundaries" requires each piece to resolve `jsr`/`jmp`/`bra` targets that live in
*other* pieces, and the assembler has no way to express a symbol defined elsewhere.

(The ColdFire side does have linker-backed units — `build_bus.py` section 1d, and
`ab_image.py` moves a blob and fixes up "its external callers". None of that machinery
applies to the DSP payloads.)

**What sharding would therefore require — new tooling, not configuration:**

1. a relocation-safe boundary analysis over the composed source;
2. a two-pass scheme: assemble whole to learn every symbol address, place the shards,
   then rewrite each cross-shard reference as an **absolute literal** (the composer
   already forces internal calls into explicit long JSRs, so the form exists) and
   re-assemble each shard at its final origin;
3. a placer spanning **two address spaces** — the shared window tails and local P —
   since `place_program_shards` walks `SAFE_SHARED_P_SPANS` only and the tails are 650
   words short on their own;
4. execution gates for the sharded layout, since a cross-shard jump that lands wrong
   is invisible to assembly.

## Summary for this task

* required: **3051** words as a single self-contained unit (a `dsp_asm` constraint)
* available contiguous: **774** local, in two non-adjacent runs — **2277 short**
* available fragmented: **2404** in five shared tails, largest **605**
* toolchain: no external-symbol input; one unit, one origin
* `PERKY_MACHINES_TARGET.md`, which `ALL_FX_MEMORY.md` cites as its authority, is absent
* Y is **exactly full** (2139/2139) — no Y headroom exists for any of this

**This is engineering, not a question for the user. But it is a project, and the
brief's "2404 + 594 + 180 = 3178, 124 words headroom" step reads as though a single
placement decision remains. It does not: the program must be split, and the splitter
does not exist.**

---

# ADDENDUM 2 — RETRACTION and correction: sharding needs NO toolchain change

**Addendum 1 concluded that `dsp_asm` "cannot assemble a shard that references
another shard", and implied a linker would be needed. The first half is true of the
assembler PROPER; the conclusion drawn from it was wrong. Corrected here.**

Reading `dsp_asm.cpp` beyond the option list shows how labels actually work:

```cpp
// Pre-scan label names. The assembler's symbol table does not resolve these
// in operands, so labels are substituted textually as $hex instead.
for (auto& [n, text] : lines) {
    const auto colon = text.find(':');
    if (colon != std::string::npos && text.find(',') == std::string::npos)
        labels[text.substr(0, colon)] = 0;
}
```

**Labels are substituted TEXTUALLY, as `$hex` literals, before the encoder ever sees
them.** The symbol table never resolves an operand; a label is just a name that a
pre-pass rewrites into an absolute value.

Two consequences:

1. **A shard needs no external-symbol support, because it needs no symbols at all.**
   If the source already contains `$1234`, nothing has to be resolved. The assembler
   never knew the difference.

2. **The composer is Python** (`build_noise_tone_synth_source.py::
   generate(layout_path) -> str`), so the substitution can be done at source-emission
   time, entirely outside the assembler.

The same comment block records the one real constraint:

```cpp
// The assembler implements only the RELATIVE b-forms (bra/bsr/bcc); jmp and
// jcc are not supported. So a branch operand is a DISPLACEMENT from the
// instruction's own address, while everything else (do, immediates, memory
// references) takes the label's absolute value.
```

**So a cross-shard transfer cannot be a `bra` b-form** — its operand is a displacement
from the instruction's own address, and the short relative range does not cross a
hole. Cross-shard transfers must be **absolute `jsr`/`jsrl`**, which is the form the
composer already forces: `force_long_local_jsr()` converts every internal PERKY call
into an explicit long JSR. **The required instruction form is already the shipped
one.**

## So the sharding plan is a Python project, not a toolchain project

1. compose the program as today and assemble it once at a provisional origin, taking
   the label -> address map from `-sym` (or from the pre-pass's own map);
2. choose shard boundaries at relocation-safe points — module/piece boundaries, since
   those are the units the composer already builds and the places where calls are
   already explicit long JSRs;
3. assign each shard a final origin;
4. **re-emit each shard's source** with its cross-shard targets written as `$hex`
   literals at their FINAL addresses, keeping intra-shard labels as labels;
5. assemble each shard at its own origin, place with a placer extended to cover both
   the shared tails and the two local runs;
6. gate it: a cross-shard jump that lands in the wrong hole assembles perfectly and is
   invisible to every existing check, so the sharded layout needs an execution gate.

No `dsp_asm` change. No `dsp-repatch`. No `make emu-cf` rebuild of the vendored
assembler — which matters, because AGENTS.md records that a stale `dsp_asm` silently
emits wrong forms, and the binary is not the source.

## The lesson, since this is the second time in three rounds

Addendum 1 read the option list, found no `--extern`, and concluded a linker was
needed. The answer was one comment block further down the same file. **Reading the
interface is not reading the implementation** — and the repository says so itself:
"disassemble what you assemble", "the binary is not the source". The equivalent here
was "read how the name is resolved, not just which flags exist".

---

# ADDENDUM 3 — two obstacles found by trying to assemble the composed source

Attempting the first step of the sharding plan (assemble the composed program once, to
take the label -> address map) fails, and the failure is informative. MEASURED, by
running `dsp_asm` directly on `out/perky/light2/multi.asm`:

```
src.asm:370: InvalidInstruction -- "jmp     @CONT@"
src.asm:408: pass-1 sizing drift -- pass 1 placed this line at P:0x01182,
             pass 2 at P:0x01181 (a label resolved to a size the dummy did not;
             spell the operand as a number)
```

## 1. The source the builder assembles is not the source on disk

`@CONT@` is still present (exactly one occurrence). The build substitutes it with the
stock continuation address per payload -- the build log says
`SUBST: PERKY PROBE payload A -- @CONT@ -> $000426` -- and only THEN assembles. So a
shard emitter cannot work from `multi.asm` as written; it must reproduce the build's
preprocessing, or run after it. Step 1 of the plan is therefore "assemble what the
builder assembles", not "assemble the file".

## 2. SIZING DRIFT IS THE REAL HAZARD FOR SHARDING, AND IT IS ALREADY VISIBLE

`dsp_asm` is a **two-pass** assembler, and it reports when a label resolves to a size
between passes such that the instruction grows or shrinks -- which moves EVERY address
after it. Its own advice is blunt: *"spell the operand as a number."*

This is precisely the failure mode sharding introduces deliberately. The plan says
"re-emit each shard with cross-shard targets as `$hex` literals at their final
addresses". If substituting a label with its absolute value changes the encoding size
of any instruction -- a `jsr` that shortens, a displaced move that becomes one word
where the label form was two, or the reverse -- then the shard's internal addresses all
shift relative to the monolithic assembly, and **the shard no longer matches the code
that was qualified.**

So the shard emitter needs an invariant that this warning makes explicit:

> for every cross-shard reference, the literal form must encode to the SAME SIZE as the
> label form did in the monolithic assembly.

That is checkable, and it must be checked per shard, not assumed. `force_long_local_jsr`
is what makes it plausible: it already forces calls into an explicit long form, which is
size-stable regardless of distance. But "plausible" is exactly what the two-pass warning
exists to catch, and one drift site is already present at line 408 in the QUALIFIED
build -- so drift is not hypothetical here.

## Consequence for the plan

Insert a step before splitting:

0. reproduce the builder's preprocessing, then assemble and capture the label map AND
   per-instruction encodings;
1. choose shard boundaries at pieces where every outgoing reference is size-stable;
2. assert, per shard, that every substituted literal encodes to the same size as the
   label form did -- and fail loudly if not.

---

# ADDENDUM 4 — step 2 (choose shard boundaries) is blocked by the markers themselves

The plan's step 2 is "choose shard boundaries at relocation-safe points -- module/piece
boundaries, since those are the units the composer already builds". Attempting it shows
the boundaries the composer emits do NOT cover the program.

Parsing `out/perky/light2/multi.asm` for the composer's own `; ===== BEGIN <name> =====`
/ `; ===== END <name> =====` delimiters:

| piece | chars | ~words |
|---|---:|---:|
| `synth_seam_glue.asm` | 11629 | 479 |
| `noise_tone_math.asm` | 10608 | 437 |
| `noise_tone_oscillator_packed.asm` | 5549 | 228 |
| `synthetic_control_map.asm` | 3802 | 157 |
| `noise_tone_envelope.asm` | 2499 | 103 |
| `noise_tone_filter.asm` | 2049 | 84 |
| `noise_tone_voice_xstate_glue.asm` | 1673 | 69 |
| `noise_tone_mix.asm` | 1368 | 56 |
| **marked total** | | **~1613 of 3051** |

**CONFIDENCE: the word column is INFERRED, not measured** -- it is the piece's character
share of the source times the measured 3051-word total. The character counts are exact;
the word split between pieces is an estimate, and any shard boundary chosen from it must
be re-measured by assembling the shard.

Two things follow.

**1. The good news.** The largest marked piece is ~479 words, comfortably under the
605-word shard cap, so the marked pieces are individually splittable.

**2. The obstacle.** **~1438 words -- 47% of the program -- lie outside every marker.**
Those are the engine bodies (Fold Drum 1, Fold Drum 2, Simple Drum). Piece boundaries as
the composer emits them therefore cover barely half the program, and "split at piece
boundaries" cannot work as written: there are no boundaries inside the engines.

## What step 2 actually needs

Either the composer must delimit the engine bodies too, so every byte of the program sits
inside exactly one marked piece; or shard boundaries must be found inside the engine
bodies by inspection, which is harder and is precisely where relocation-safety is least
obvious -- the engines contain the local branches and data adjacency the contract warns
about.

The first is the smaller change and the safer one: it does not require understanding the
engines' internals, only marking the units the composer already concatenates.

## Method note

This is the third time this milestone that attempting a step has produced the useful
result where reasoning about it produced nothing (the `@CONT@` preprocessing, the sizing
drift, and now uncovered pieces). The pattern is consistent: run the step, read what it
actually does, and let the failure say what the plan missed.

---

# ADDENDUM 5 — step 2 progressed: engine bodies marked, coverage 1613 -> 2040 of 3051

The composer appended the engine bodies with no delimiters at all:

```python
source += (ROOT/'modules/perky/fold_drum_voice.asm').read_text()
source += (ROOT/'modules/perky/fold_drum2_voice.asm').read_text()
```

so 47% of the program sat outside every piece. Wrapping those two appends -- and the
inline `pk_tone_candidate_voice` block -- in the composer's own
`; ===== BEGIN <name> =====` / `; ===== END <name> =====` form takes the marked set from
8 pieces to 11:

| piece | chars | ~words |
|---|---:|---:|
| `synth_seam_glue.asm` | 11629 | 478 |
| `noise_tone_math.asm` | 10608 | 436 |
| `fold_drum2_voice.asm` | 6849 | 281 |
| `noise_tone_oscillator_packed.asm` | 5549 | 228 |
| `synthetic_control_map.asm` | 3802 | 156 |
| `fold_drum_voice.asm` | 3638 | 149 |
| `noise_tone_envelope.asm` | 2499 | 103 |
| `noise_tone_filter.asm` | 2049 | 84 |
| `noise_tone_voice_xstate_glue.asm` | 1673 | 69 |
| `noise_tone_mix.asm` | 1368 | 56 |

**PROVEN SAFE, not assumed:** the change is comments only, and a full rebuild produced
**byte-identical artifacts** -- card `4ba4d72c...`, MIDI `685e5105...`, unchanged. A
comment-only change that moved the bytes would mean the markers were being assembled.

**NOT YET COMPLETE, and one gap is my own error:**

* I emitted `; ===== BEGIN pk_tone_candidate_voice =====` **without a matching END**. An
  unterminated piece is not a piece; it is a marker that will silently swallow whatever
  follows it in any parser that trusts the delimiters.
* **~1012 words still lie outside all markers.** The remaining unmarked content is other
  inline `source+='''...'''` blocks further down `build_fold_candidate.py`.

**Falsifier:** the coverage test is a source-text parser, so it can be wrong in the same
way the markers can. The check that cannot be fooled is the byte-identity one above, and
it says only that nothing was assembled differently -- **not** that the coverage is
complete. Coverage completeness must be re-measured after every new marker.


---

# ADDENDUM 6 — coverage 1613 -> 2164; one marker imbalance remains, and it is the composer's

Marking the remaining inline blocks in `build_fold_candidate.py` -- closing the
`pk_tone_candidate_voice` piece I had opened without an END, and wrapping both
`pk_multi_fold_init` and `pk_multi_fold2_init` -- takes the marked set to **13 pieces**
and coverage to **~2164 of 3051 words**.

**PROVEN BYTE-NEUTRAL AGAIN:** full rebuild, artifacts byte-identical to before
(card `4ba4d72c...`, MIDI `685e5105...`). Comments only.

**Marker balance, measured:** zero BEGIN-without-END (my earlier error is closed), and
**largest marked piece ~476 words, zero pieces over the 605 cap** -- so what is marked is
splittable.

## What still blocks step 2

1. **`noise_tone_envelope_packed7.asm` has an END with NO BEGIN.** This is the composer's
   own imbalance, not mine. It matters more than an unmarked block: a parser that trusts
   the delimiters will either mis-close the previous piece or extend it to here, and
   either way the boundary it computes is fiction. Any splitter must **refuse to run when
   the markers are unbalanced** rather than pick an interpretation.

2. **~887 words remain unmarked.** They are outside `build_fold_candidate.py`'s appends,
   so they come from the other composer (`build_noise_tone_synth_source.py`) or from
   regions rewritten after concatenation. Finding them needs the same treatment on the
   other emission path.

## Status of step 2

Partially done, and honestly bounded: **13 pieces marking ~2164 of 3051 words, four
imbalances or gaps resolved (three gaps closed, one imbalance found), every change proved
byte-neutral by a full rebuild, and two blockers identified with their cause**.

Falsifier carried forward: coverage is measured by parsing source text, so it is exposed
to exactly the marker problems above. It is only trustworthy once the markers balance and
the unmarked remainder is zero -- and byte-identity does not speak to coverage at all.

---

# ADDENDUM 7 — markers BALANCED (14 pieces, zero imbalance); coverage 1613 -> 2225

The imbalance was a one-line slicing bug in `build_multi_synth_source.py`, and its shape
is worth recording because it is easy to repeat:

```python
source = source[:begin] + wrapper + linear + source[end:]
```

`source[:begin]` **drops the BEGIN marker**, `source[end:]` **keeps the END**. A balanced
pair became unbalanced the moment a piece's body was replaced by a computed wrapper --
and nothing about the emitted text looks wrong until something tries to parse it.

Fixed by giving the replacement its own balanced pair. MEASURED after:

```
pieces: 14
BEGIN without END: NONE
END without BEGIN: NONE
largest piece: synth_seam_glue.asm ~476 words; over cap: 0
UNMARKED: ~826 words   (coverage ~2225 of 3051)
```

**PROVEN BYTE-NEUTRAL:** full rebuild, artifacts byte-identical (`4ba4d72c...`,
`685e5105...`). Comment only.

## Why balance mattered more than the remaining coverage

An unmarked region is a region a splitter declines to touch. **An unbalanced marker is
worse: it invites the splitter to invent a boundary** -- either mis-closing the preceding
piece or extending it to the END. That boundary would be fiction, and fiction that
assembles. Balance was therefore the precondition, not a nicety, and it now holds.

## Still open for step 2

**~826 words remain outside all markers**, down from 1438 when this began. Located next.

**Carried forward falsifier:** coverage is measured by parsing source text, so it is
exposed to the very marker problems above. Byte-identity is silent on coverage. The
number to trust is "unmarked = 0", and it is not there yet.

---

# ADDENDUM 8 — step 2 essentially complete: coverage 1613 -> 2982 words, 19 pieces, balanced

The remaining unmarked block was the Simple Drum renderer, appended raw as `extras` in
`build_multi_synth_source.py` from five files. Marking them was done **per file, not as
one piece**, and that choice matters:

* `extras` combined is ~803 words -- **over the 605-word shard cap**, so a single marker
  pair around it would have produced a piece that could never be a shard. Per-file pieces
  are individually sized.

MEASURED after:

```
pieces: 19
imbalance: BEGIN-only none, END-only none
covered: 73285 of 74981 chars
UNMARKED: ~69 words        (from 1438 when step 2 began)
largest piece: synth_seam_glue.asm ~473 words
pieces over the 605 cap: 0
```

**PROVEN BYTE-NEUTRAL:** full rebuild, artifacts byte-identical (`4ba4d72c...`,
`685e5105...`), for every one of the changes in addenda 5-8.

## What step 2 now has

* **19 pieces, markers balanced** -- so a splitter can trust the delimiters instead of
  inventing a boundary;
* **no piece exceeds the 605-word shard cap** -- so every piece is a legal shard, or a
  legal starting point for one;
* **~69 words unmarked**, down from 1438. What remains is small enough to identify by
  eye rather than by another pass of this analysis.

## The method, now with five instances

`@CONT@` preprocessing · sizing drift · three-word length gap · uncovered engine bodies ·
the unbalanced marker · the over-cap `extras` block.

**Every one was found by attempting the step and reading what it actually did.** The last
two are the clearest: a splitter would have mis-closed a piece, and one piece would have
been silently unsplittable -- both invisible to inspection, both obvious the moment the
measurement ran.

---

# ADDENDUM 9 — the last unmarked block, located exactly

Coverage is now all but complete. The remaining unmarked content is a **single block of
~1687 characters (~69 words)** containing `pk_multi_noise_init:`, and it is pinned between
two known pieces:

```
before: simple_drum_delta.asm   (the noise composer's tail, marked in addendum 8)
after : fold_drum_voice.asm     (appended by build_fold_candidate.py)
```

So it is emitted by the noise/synth composer path, after the marked pieces and before
`build_fold_candidate.py` reads the composed source and appends the engine bodies. It is
**not defined at line-start in any `.py` or `.asm` in the tree**, so it is produced
dynamically -- a further search of that path, not a further analysis of this one.

## Why this is a clean stopping point rather than a loose end

Everything step 2 needed is in place:

* **19 pieces, markers balanced** -- a splitter can trust the delimiters;
* **no piece exceeds the 605-word shard cap** -- every piece is a legal shard or a legal
  starting point;
* **~69 words unmarked of 3051** (2%), down from 1438 (47%) when step 2 began, and the
  remainder is identified **by name and by its two flanking pieces** rather than as a
  region to re-derive.

The remaining block is small enough that it cannot hide a boundary problem of the kind
that has mattered here -- but it still must be marked before a splitter runs, because
**an unmarked region is one a splitter declines to touch, and a declined region is a
region that silently stays in the monolithic image.**

## Carried forward

* `unmarked = 0` is the bar, and it is not met. The last block is located, not yet marked.
* Coverage is measured by parsing source text, so it is exposed to the marker problems
  already found twice. Every coverage figure in addenda 5-9 was taken from a rebuild whose
  artifacts were **byte-identical** to the previous build -- which proves the markers did
  not assemble, but says nothing about whether coverage is complete.


---

# ADDENDUM 10 — the last block's emitter is GENERATED, and that is why the search failed twice

Searching for `pk_multi_noise_init` the obvious way does not find its definition:

```
grep -rn "multi_noise_init" --include=*.py --include=*.asm
  tools/perky/build_multi_synth_source.py:49:   jsrl pk_multi_noise_init      <- reference only
modules/perky/synthetic_control_map.asm   -> 0
modules/perky/simple_drum_delta.asm       -> 0
```

**No `.py` and no `.asm` in the tree defines it.** It nevertheless lands in the composed
source, immediately after `; ===== END simple_drum_delta.asm =====` and before
`fold_drum_voice.asm`.

## What that means

The body is **built from fragments** by the composer chain, so the label never appears
whole in any file for a text search to find. This is the same shape as the earlier
markers: the emitted text is not the source text, and a search of the source cannot see
what the composer assembles.

It also explains why two rounds of grep-and-read failed to locate it, and why the next
step is **not another grep**: the emitter has to be found by instrumenting the composer
chain -- for example, dumping the source immediately after each stage
(`noise.generate` -> `multi_synth.generate` -> `fold_candidate`) and diffing, so the
stage that introduces the block identifies itself. That is a mechanical next step with a
definite answer.

## Standing state of step 2

* **19 pieces, markers balanced, no piece over the 605-word cap.**
* **Unmarked: this one block, ~69 words of 3051 (2%)**, located between two named pieces.
* `unmarked = 0` is the bar. It is not met, and this document says so rather than calling
  98% complete.

**Carried forward, and it is the third time this distinction has mattered:** every
coverage figure here came from a rebuild whose artifacts were byte-identical to the
previous build. That proves the markers are not assembled. It says nothing about whether
coverage is complete. The two questions are independent, and only one is settled.
