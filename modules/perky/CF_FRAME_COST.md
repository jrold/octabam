# PERKY ColdFire frame cost — optimisation checkpoints, 10 October 2026

The unit's failure mode ("PERKY: briefly sounds, then the sequencer stalls")
is the ColdFire frame handler overrunning its 362.8 us frame. The two levers
below were applied to the shipping PERKY CF image on `perky-machines`; every
other qualification gate still passes bit-exactly.

## What was measured, and where the cost really is

`tools/harness/perky_cf/price_project.py` and the `--profile` buckets agree
that the **steady-state render** is the cost, not the event frame:

| variant of the user-path fixture (T1 Wavetable, T2 Fold2, T3 Resonant
snare, T4 Acoustic Hats) | model us/frame |
|---|---|
| all four voices active | 314.0 (was) |
| four voices, one trig per bar instead of four | 310.7 |
| four voices, every trig erased (voices never start) | 117.4 |
| four Perky tracks signed but rendering silence (`PK4_FLOOR_EXPERIMENT`) | 134.8 |

Erasing trigs removes the *render* (an untriggered track is never called by
the stock source packer), not a per-event cost; cutting the trig rate 4x
changes nothing. `--profile` attributed a third of the frame to four
`pk_cf_*_render` inner loops.

## Lever 1 — get the one-time work out of the audio callback

`pk4_init` clears the whole 119 KB engine. It ran on the first render, i.e.
inside the frame handler, and cost about 4 ms of ColdFire time — ten times
the frame — which is exactly the firmware's own stall guard
(`0x4000aae0 tstl 0x46104d4e / beq / halt`).

* `control_cf_final.c` now primes it from `pk_ui_tick`, copying the existing
  boot-time PCM-decode pattern (`pk_final_ensure_pcm`); the audio path keeps
  the same one-cookie guard.
* `pk4_init` clears the engine a long at a time (the object is 4-byte aligned
  and a whole number of longs long), instead of a byte store loop.

Result on the project the user reported: `PRESETS MKII/PROJECT 261010`, three
Perky machines — the deadline model went from **OVER (375.1 us late)** to
**fits, 0 late edges over 1,500 frames** (152.8 us/frame average).

## Lever 2 — word/long state access

Every engine object is the little-endian byte image of an ARM object and the
ColdFire is big-endian, so the byte-wise `r16/r32/w16/w32` helpers cost 4-11
instructions each. `cf_math.h` now provides `pk_cf_ld16/ld32/st16/st32`: one
`move.l` plus the ColdFire V4e `byterev` instruction (0x02c0) for a long, and
the portable byte ladder on the little-endian host build. All twelve engines
use them.

* Host gates (x86) are unchanged and still bit-exact against the fixtures.
* The ColdFire source records are byte-identical to the pre-change image
  (`--block-dump` comparison, all eight tracks), which is the cross-check that
  the byte swap is right.
* `verify_perky_cf_odd_access.py` still audits the emitted displacements (the
  inline asm keeps them visible) and passes.

Result: the four-voice user-path fixture went **314.0 -> 264.7 us/frame**
(-16%) and the reported project 159.3 -> 152.8 us/frame.

## What is still out of reach, and why

`verify_perky_cf_realtime_budget.py` runs the four-voice fixture against a
budget of frame/2 = 181.4 us. The floor measurement above says the fixture
costs **134.8 us with the engines contributing nothing at all**, so the four
renderers would have to fit in 46.6 us — about 194 ColdFire cycles per sample
per voice — where they currently need roughly 136 us. The stock firmware
alone is ~71% of that budget, and its own hot loop (the frame handler's DSP
exchange, `0x400036xx`) is ~10,000 cycles/frame in both the zero-Perkys and
the four-Perkys runs. Closing the remaining gap is not a renderer tweak:

* the per-sample state traffic is already one load/store per field;
* the loop bodies are straight-line arithmetic that must stay bit-exact;
* the only remaining structural lever is to move synthesis off the 266 MHz
  ColdFire frame entirely (the DSPs have a 23,040 cycle/16 samples voice
  budget), which is a different architecture, not an optimisation.

Numbers in this file are the vendored core's cycle model. The project's own
`cfmeter` factor (x1.7) still applies on top.
