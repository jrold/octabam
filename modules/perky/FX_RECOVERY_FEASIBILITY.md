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
