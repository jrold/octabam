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

⚠️ A short run says more than it should. `PRESETS MKII/PROJECT 261010` with
three Perky machines fits for the first ~1,500 frames (152.8 us/frame, 0 late
edges) and then does not: the song only becomes fully busy later.

| frames | 0 Perky | 3 Perky | late edges (3 Perky) |
|---|---|---|---|
| 1,500 | 116.3 us | 152.8 us | 0 |
| 4,000 | 120.5 us | 210.8 us | n/a |
| 12,000 | 123.6 us | 243.4 us | 9,888 of 12,000 |

The 4,000-frame row is the handoff's own table on the current image
(120.5 / 146.1 / 185.9 / 210.8 for 0/1/2/3 machines, against
120.5 / 151.2 / 195.7 / 221.3 before). So the two levers are worth about 5 us
a voice at that point in the song, not enough on their own.

Hold the deadline to the hardware-relevant threshold instead of frame/2: the
frame handler fits while the model average stays under 362.8/1.7 = 213.4 us.
The reported project needs 243.4 -> 213.4, i.e. about a quarter off its Perky
work (119.8 us). The gate's frame/2 = 181.4 needs ~2.9x.

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

The same arithmetic already fails the handoff's own table one voice earlier:
120.5 / 151.2 / 195.7 / 221.3 us for 0/1/2/3 machines means a *second* Perky
voice overruns 181.4, let alone a fourth. A four-voice fixture at frame/2 is
asking for roughly 13 us of model time per voice.

## The model over-prices this code's multiplies

The vendored core prices instructions from the MCF5206E user manual
(`vendor/mc68k/Musashi/m68kcfcycles.h`), which has no EMAC: `MUL.L` is the
"upper bound" 18 cycles and `MUL.W` is 9. The MCF5445x this image runs on has
an EMAC and executes `MULS.L`/`MULU.L` in about three. The engine inner loops
are multiply-heavy — the snare alone carries 39 `muls.l` sites — so the
model's absolute frame cost overstates the synthesised path specifically.

Measured on the fixture: a dependent multiply chain with a loop-variant
multiplier and trip count (so the optimiser can neither fold nor delete it)
added 9.0 us/frame for ~223,000 instructions, i.e. ~8.5 model cycles per
added instruction against 1.11 for the image as a whole.

Counted in the source, `pk_cf_slap_render` runs 22 multiplies per sample
(2 filter stages x 3, envelope, output scale, the five-tap delay's 10, and its
3 mixing multiplies) out of ~623 model cycles per sample, so **~64% of the
engine the reported project leans on hardest is `MUL.L` at the 5206E price**.
The snare is ~14 per sample.

That also means the x1.7 hardware factor is being applied to the same
multiplies twice. The factor was calibrated on the *stock* image, whose frame
handler is EMAC-heavy (`msacl`) -- and the model charges A-line EMAC opcodes
nothing -- so 1.7 already absorbs the stock image's unpriced multiply work.
Multiplying our engines' 18-cycle `MULS.L` figure by the same 1.7 counts that
work a second time. On the part both forms run on the EMAC at ~3 cycles.

So the honest reading is: **the model says the PERKY path is roughly twice as
expensive as the part will make it**, and a `cfmeter` reading from a Perky
build is what settles the real margin -- the "the size of the overrun could
still move" caveat the handoff raises. What cannot be settled locally is
whether the real margin is enough for three machines; that needs the unit.

⚠️ The engines deliberately do **not** use the A-line EMAC multiply form to
exploit this. The v4e layer charges A-line opcodes ~nothing, so rewriting
`pk_cf_mul_lo_u32` as `mac.l` + `movclr.l` would move the gate, but it would
also be *slower* on the part than one `muls.l` (six instructions against
three cycles). Trading a real instruction for a model artifact is not an
optimisation.

Numbers in this file are the vendored core's cycle model. The project's own
`cfmeter` factor (x1.7) still applies on top.

## Third-party review, five items — reviewed, measured, answered

A review proposed five optimisations. All five were checked against the code
and the shipped image; four were implemented. The four-voice fixture moved
266.1 -> 261.8 us/frame (the budget gate's own run; the staged comparison used
for the per-item numbers ends at 262.4), and every bit-exactness gate still passes (24/25; the
budget gate is the one that does not). The measurements matter more than the
list, so each verdict carries its number.

1. **Resonant snare: "pounds the ARM state object every sample" — IMPLEMENTED,
   small win.** The snare does touch the object ~50 times a sample (four
   decays x five fields, three resonators x nine, envelope, noise) and most of
   that is invariants. It is now block-cached: `res_env_load/step/store`,
   `res_dec_load/step/store`, `res_core_load/step/store` and
   `res_noise_load/step/store` run the whole 16-sample render in locals and
   commit once, exactly the shape cf_noise_hat already used. Measured: **-1.5
   us/frame (0.6%)**, not the expected fifth of the engine. The reason is the
   register file: the working set is ~50 fields against 8 data registers, so
   GCC spills and the object traffic is merely exchanged for stack traffic.
   The object accesses were already two instructions each after the BYTEREV
   work; what is left is arithmetic. The image grew 6 KB.
2. **Wavetable: `tab16` byte pairs, four `pk_cf_wt_wave()` a sample —
   IMPLEMENTED.** `tab16` now goes through `pk_cf_ld16`, and the four wave
   views are resolved once and kept until the object's own address changes
   (the bank stride is 0x1000, so each call was otherwise four comparisons
   plus a bank index). `tab16` was also switched in the other seven engines.
   The rest of the review's list — phase, current/next wave, pitch-envelope
   amount, mix — is genuinely per-sample mutable state, and hoisting it into
   locals hits the same register-file wall as item 1.
3. **Fold2: `wave()` scans four descriptors inside the loop, p1/p2 recomputed
   — IMPLEMENTED.** The descriptor scan is now cached per oscillator
   (`fold_wave_cache`) and p1/p2, the fold amount and the mute byte are read
   once per block. Note the oscillator *phase* cannot be hoisted: it changes
   every sample by construction.
4. **Acoustic Hats soft-float: `pk_cf_clz32()` is a shift loop, use FF1 —
   IMPLEMENTED.** `ff1 %dn` is one ISA_C instruction (the opcode the emulator
   already implements for the stock image, and the manual prices it at one
   cycle). It is a one-operand, in-place instruction, and it sets N/Z from the
   source, so the asm declares a `cc` clobber — unlike the sibling BYTEREV,
   which leaves the codes alone. The two subnormal normalisation loops in
   `pk_cf_f32_add` were folded into the same helper. Measured: **-0.9
   us/frame**, smaller than hoped because the loop rarely ran far (the
   captured filter values normalise in a few steps).
5. **`pk_cf_mul_hi_u32()`: four multiplies, investigate the EMAC —
   REVIEWED, NO CHANGE.** The four multiplies are real but they are already
   `MULU.W`, not `MULU.L`: GCC recognises the masked 16-bit operands and emits
   the 9-cycle form (verified in the generated assembly). Four 16x16 partial
   products is the minimum for an exact high half — a 32x32 `MULU.L` yields
   only the low half. The EMAC cannot do it either: `MAC.L` accumulates into a
   **48-bit** accumulator, so a 64-bit product's top 16 bits are gone; taking
   the high half needs bits 63:32.
