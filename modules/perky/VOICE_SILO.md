# PERKY voice silo — T1..T4, one PĒRKONS family per track

## Why

The drum has **four voices** and each voice owns **three algorithms**.  The port
now keeps that shape instead of offering one flat machine list to every track.
That buys three things:

1. **A bounded frame cost.**  A patch cannot stack arbitrary engines; the
   worst case is one algorithm per family, which is computable and gateable.
   Siloing does not make a single engine cheaper — it makes the ceiling
   knowable.
2. **Instruction-cache locality.**  A track only ever executes its own
   family's code, not any of the ~135 KB of ColdFire text.
3. **Patch portability.**  A PĒRKONS kit's voices map onto the four tracks
   algorithm-for-algorithm, and the panel semantics match the hardware.

## The layout

| OT track | voice | algorithms (hardware order) | shipped |
|---|---|---|---|
| T1 | V1 | Fold Drum 1 / Wavetable V1 / Simple Drum | **Fold Drum 1** |
| T2 | V2 | Fold Drum 2 / Wavetable V2 / Complex Drum | **Fold Drum 2** |
| T3 | V3 | Resonant Drums / Slap / Karplus | **Resonant Drums, Karplus** |
| T4 | V4 | Noise Hat / Noise Tone / Acoustic Hats | **Noise Hat, Noise Tone** |

Only the implemented algorithms are listed, compacted into a contiguous knob
range — the ALGO control on each track has exactly as many positions as that
family has shipped engines.  The table lives in `cf_perky4.h`
(`pk4_family_engines` / `pk4_family_len`) and is the single source of truth for
the driver, the host harnesses and this document's gate.

## How it works

* The staged SRC byte for ALGO is a **family-local knob position**, not a global
  engine id.  `pk_render` maps it through `pk4_voice_engine()` in exactly one
  place, so a p-locked or stale byte (for example a track that moves under a
  lock written for another family) can never select an algorithm the hardware
  would not offer that voice.
* `pk_final_page(track)` publishes the family length as the ALGO maximum, and
  `pk_ui_tick` republishes it for the stock "current track" byte, so the SRC
  SETUP list is per-track.
* P-locking is unchanged: the byte staged per step is the local position, so
  locks behave exactly like the knob.

## Adding the missing engines

Each addition is: put the engine in its family slot in `pk4_family_engines`,
bump `pk4_family_len`, and satisfy the engine gates.  **The local indices after
the insertion shift**, so a project saved with an older image can change which
algorithm a slot selects — the page clamp keeps the value in range, and the
release note has to say so.

Order by what each family is missing:

1. `Slap` (V3) and `Acoustic Hats` (V4) complete two families to their full
   three algorithms.
2. `Simple Drum` (V1) and `Complex Drum` (V2) give T1/T2 a second machine.
3. `Wavetable V1` / `Wavetable V2` need the wavetable asset codec ported to
   ColdFire as well, so they are the largest of the six.

## What this does not fix

Frame cost.  The four family-first engines (Fold 1, Fold 2, Resonant, Noise Hat)
model at 342.3 us of the 362.8 us frame; the same build with Karplus and
Noise/Tone on T3/T4 models at 257.5 us.  The silo itself costs nothing
measurable — the same engine mix measures 257.5 us with and without it — so the
remaining work is per-engine optimisation, not the layout.
