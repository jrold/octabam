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
