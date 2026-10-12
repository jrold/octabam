# The PK_LADDER bisection — flash sheet

**A diagnostic ladder for a machine that wedges.** On the unit, assigning a Perky
machine through the UI stops the sequencer advancing and produces no sound. A wedged
machine cannot report anything, so CF METER is the wrong instrument: its
ColdFire-side slots freeze with the CPU, and if the DSP wedges its track-8 audio
stops, so you get silence rather than a period. It also costs a flash and a power
cycle and measures **one** image — it can never say which increment caused the fault.

**The ladder works the other way round: start from a configuration that RUNS, and add
functionality until it stops.** Every rung is the **same panel-selectable module**, so
the workflow is identical at every rung and the only variable is DSP behaviour.

## The five rungs

| rung | what is present | what it isolates |
|---|---|---|
| **1** | the source hook, **never admits**; the stock source renderer runs | **the seam itself** — the `jsr` at the site, the displaced-instruction replay, the not-admitted `rts` |
| **2** | + admission, record read, state load, **silence**; no per-sample work | **the admission and the state load** |
| **3** | + the **Fold** renderer | **the Fold renderer** |
| **4** | + **Bass** | **the Bass renderer** |
| **5** | + **Snare** — the shipping machine | (known to fail) |

## Procedure

Flash **rung 1 first**, then run the ordinary workflow on the unit:

1. boot with no Perky machine on the target track;
2. select T1;
3. assign PERKY through the UI (double-tap the track key, `LEFT`, `down` ×5, `YES`);
4. return to Tracks;
5. enter trigs in grid-record;
6. press PLAY.

Then read the first rung that **fails**, where "fails" means either symptom: the
transport stops advancing, or the track produces no sound.

| first failing rung | conclusion |
|---|---|
| **1** | the **hook mechanism** is at fault. Nothing downstream matters — the entire DSP-side machine can be left alone until the seam is understood. |
| **2** | the **admission or the state load**. The seam is sound; the renderer is not implicated. |
| **3** | the **Fold renderer** — and only Fold; Bass and Snare have never run. |
| **4** | the **Bass renderer**. |
| **5** | the **Snare renderer** — the last increment is the fault, and everything below it is exonerated in a single pass. |
| **none** | every rung runs. The fault is not in the DSP-side machine at all, and the next suspect is the ColdFire-side per-event work or the record contents. |

**Rung 1 is the safest first flash**: it carries the hook with no renderer, so if it
runs, the seam is exonerated in one flash and rung 2 is already the next question.

## A SECOND AXIS, because the DSP ladder alone is ambiguous

**The DSP rungs all leave the ColdFire running its entire per-event work** — the
resonant law on every event, the trigger, and the 88- or 101-word state handed to the
transport. So a rung-1 stall could not distinguish the seam from the ColdFire's
per-event cost, and the failure register's own measurement points at the ColdFire
("the ColdFire outruns its frame").

`PK_CF_MINIMAL=1` removes that work: the resonant condition is false, a resonant
engine falls through to the zeroed-controls branch, and **the record goes out with
`n = 0`** — the "no state" case the DSP already handles. The seam, the record and the
DSP machine are all untouched; only the per-event ColdFire arithmetic is gone.

Verified by the record itself, not by reading the source:

| build | `record[10]` |
|---|---|
| shipping | **count = 88, engine = 10** |
| `PK_CF_MINIMAL=1` | **count = 0, engine = 0** |

and the shipping build is byte-identical (`c389cfab`), so the switch is inert at its
default.

**Read it as a pair.** Flash `CFMIN` first: if the transport still stalls with **no
ColdFire per-event work and no state delivered**, then the fault is in the seam, the
record traffic, or the admission itself — not in the arithmetic the register blames.
If `CFMIN` runs and `LADDER5` stalls, the per-event ColdFire work is the fault and the
whole DSP-side ladder is exonerated in one flash.

| flash | what it removes |
|---|---|
| **CFMIN** | every per-event ColdFire resonant operation; the record carries no state |
| LADDER1 | the DSP machine entirely (the hook is present, never admits) |

## Artifacts

```
out/OCTATRACK_OCTABAM79X_LADDER1.bin   eb543833681101e4309d4b3667a33d49c0b66a8873d387491a1f19413e61edbc
out/OCTATRACK_OCTABAM79X_LADDER2.bin   e052366e63c6a2f97c06e4a68db84c42ddd35f78dd24154f578a36e1a2cd56d3
out/OCTATRACK_OCTABAM79X_LADDER3.bin   3e4c7ad6651bcab23db68cf436259a9526afcb34e662adab57a6d6369f826757
out/OCTATRACK_OCTABAM79X_LADDER4.bin   d254c06e6ed765128d39ab89278344ea0045565fe61adadc7877a6c1d9b15af6
out/OCTATRACK_OCTABAM79X_LADDER5.bin   581ed2ce6957bd8245c8a5c4659638862dc22fa9a7db49b180d628558fc72680
```

```
out/OCTATRACK_OCTABAM79X_CFMIN.bin    e334a5bdbeec456400bd5c1fbcd19419e02ba19e50be977f90d0feb97f0a5f02
```

`.syx` beside each. **LADDER5 is the shipping build**, so flashing it is no worse
than what is already on the unit. All five are checksum-verified, and **no two are
the same image**.

## Rebuilding a rung

```
PK_LADDER=<1..5> python3 tools/perky/emit_3algo_manifest.py
OCTABAM_NO_CACHE=1 make bus REMIX=perky-dsp-3algo
```

Two traps, both of which cost an hour when the ladder was built:

* **`PK_LADDER` must be set when REGENERATING, not when building.** The build reads
  `modules/perky/machine_3algo.asm` from disk; `compose()` only reaches it through
  `emit_3algo_manifest.py`. Setting the variable on `make bus` alone produces five
  byte-identical images.
* **`out/cache/` does not key on the environment**, so a rung built without
  `OCTABAM_NO_CACHE=1` comes back as the previous rung's image.

`tools/verify/verify_perky_3algo_ladder.py` regenerates all five and reads the
instructions back, so a rung that silently stopped disabling its renderer fails the
suite rather than moving the boundary.

## What the ladder cannot see

**Whether a rung wedges.** That is the measurement it exists to make, and it needs
the unit. Locally the emulator runs every rung — including rung 1, which cannot run
the renderer at all — with byte-identical DSP audio, because a lock-step machine
cannot be late. That is why the bisection is a flash sheet and not a gate.

## Before building a third axis: `pk_tick_hook` is measured and cheap

The obvious third suspect is the 19 ColdFire UI detours, and the biggest of those by
**frequency** is `pk_tick_hook`, which runs on **every UI tick**. Its target
`pk_ui_tick` compiles to **65 instructions** -- a bank-range check and a
`pk_track_page` lookup -- and `pk_resonant_prime` is **absent**, confirming the
control-settle hoist added in an earlier round really was reverted.

**So the per-tick cost is trivial**: a UI tick at roughly 50 Hz against an audio frame
at 2,750 Hz. That does not prove the detours are innocent, but it **removes the only
one of them that runs continuously** -- the one that could plausibly stall a transport
-- and leaves the assignment-time detours, a weaker suspect than the per-event work
`CFMIN` already targets.

**Flash `CFMIN` and `LADDER1` before building any detour variant.** They answer more
per flash, and they are already built, verified and packaged above.
