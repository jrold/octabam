# Perky Machines — all-stock-FX memory contract

This document is the physical-memory contract for the locked Perky Machines
target in `PERKY_MACHINES_TARGET.md`. It supersedes older PERKY4/HW4 notes that
allowed stock effects to be harvested or retired.

## Non-negotiable rule

Both Octatrack FX slots and every stock effect remain available. Final Perky
code/data may not claim any word needed by the stock FX allocator or stock
runtime mailbox/staging regions.

## Facts pinned against pristine OS 1.40C

`tools/verify/verify_perky_all_fx_memory.py` reads the decoded pristine MAIN OS
and refuses drift from these facts on either DSP core:

- stock P high water: core A `$1fdf`, core B `$1d9f`;
- common private low-Y gap: `$07a5..$0fff`, **2,139 words**;
- stock local FX arena: `$1000..$bfff`, **45,056 words/core**;
- FX1 allocator: four × `$0c00` words;
- local FX2 allocator: two × `$4000` words;
- two additional FX2 slots/core live in the aliased shared window.

The tempting 16K-P / 40K-Y DSP memory split is therefore rejected. It would end
local Y at `$9fff`, leaving only 36,864 words above `$1000`; stock FX require
45,056. The shortfall is **8,192 words**, exactly half an FX2 slot.

## Shared-window executable tails

The DSP shared window `$30000..$3ffff` aliases P/X/Y. Existing stock-effect
census/guard work pins the highest stock FX2 write at `base + $3da2`. The words
after that point are the only shared-window regions currently admitted as
candidate Perky program storage. The stock mailbox `$37f00..$37f0f` is removed.

| P range | Words |
| --- | ---: |
| `$33da3..$33fff` | 605 |
| `$37da3..$37eff` | 349 |
| `$37f10..$37fff` | 240 |
| `$3bda3..$3bfff` | 605 |
| `$3fda3..$3ffff` | 605 |
| **Total** | **2,404** |

`modules/perky/all_fx_layout.py` is the machine-readable contract for these
regions. `tools/verify/verify_perky_all_fx_placer.py` proves the complete 2,404
word capacity can be used without crossing a hole or touching the mailbox. A
single indivisible shard larger than 605 words is rejected even when total free
capacity remains, so builders must split code only at explicitly relocation-safe
boundaries.

## Consequences for the final architecture

1. Keep the stock DSP memory split. Do **not** trade stock Y for more local P.
2. Do **not** use the old HW4 FX1 donor/reclaimed-Y layout in a final build.
3. Use `$07a5..$0fff` only for data that fits the measured 2,139-word private-Y
   budget.
4. Treat the five shared-P tails as a **2,404-word program shard budget**, not a
   monolithic code region.
5. Large PĒRKONS assets (full Wavetable and Acoustic Hats sample banks) cannot be
   permanently resident in the stock FX arenas. They require a stock-preserving
   backing/cache/streaming strategy or a smaller exact representation proven by
   a realtime gate.
6. All-family P fit must be measured on the **deduplicated composed source**, not
   by summing standalone renderer sizes. Common arithmetic/render helpers are
   already known to overlap heavily.

## Required gates before physical firmware

A candidate is not an all-FX Perky Machines build unless at minimum:

- `verify_perky_all_fx_memory.py` passes against pristine 1.40C MAIN OS;
- `verify_perky_all_fx_placer.py` passes;
- every emitted P/X/Y extent is checked against this contract;
- the final DSP composition passes the realtime two-voices-per-core budget;
- no stock FX dispatch entry, allocator base, or effect buffer is retired;
- the packaged image passes normal Octabam image-integrity gates.

Older documents that say the user accepted fewer stock effects are historical
and are overridden by `PERKY_MACHINES_TARGET.md` and this contract.
