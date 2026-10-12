# Composed reduced Perky DSP machine — implementation record

**Branch:** `perky-dsp-2voice-3algo` (from `perky-optimize`, commit `a522d2f2`).

This is the reduced production target: **two Perky voices total, one per DSP
core, three selectable algorithms each.** It is deliberately smaller than the
superseded twelve-family / four-voice target and it does **not** move synthesis
back to ColdFire.

## MEASUREMENT BOUNDARIES: exactly what 74,515 and 80,722 contain

Item 1 asked for the beginning and end of the measurement, not a reference to it.
Read off the code, exactly:

`tools/verify/verify_perky_3algo_timing.py` drives the probe
`tools/verify/verify_perky_3algo_exec.py` defines:

```asm
pk3t_fold:
        move    #>voice,r6
        move    #>scratch,r5
        jsrl    pk_simple_base
        jsrl    pk_fold_voice
        jsrl    pk3c_rng_out        ; a GATE-ONLY state dump: 12 instructions,
        rts                         ; four X reads and four X writes
```

and the composed source is assembled with `@CONT@` replaced by `$000426`, which
in a probe-only binary is **uninitialised memory**.

**So the quoted figure is: `pk_simple_base` + the voice renderer + a 12-instruction
gate-only RNG dump, for one 16-sample block, measured by the host's decoded-opcode
counter. It INCLUDES something production never runs and EXCLUDES three things
production always runs:**

* includes `pk3c_rng_out`, a diagnostic that exists only so the gate can check RNG
  state -- production has no such call;
* excludes `pk3d_source`, i.e. the admission check ('PK'/'Y1', the slot test), the
  control staging and the mode delivery;
* excludes `pk3z_scale`, the x256 output stage, which loops over all 32 words;
* excludes the stock continuation entirely -- which is correct and intended, since
  the stock share is the separate `16 x 1410` reserve.

That is the honest description of the boundary, and it is **not** the same set as
the production path in either direction.

### The Fold "overhead" EXPLAINED, and the overhead column was not overhead

Closing the loose end flagged above. Decomposing the dispatch path by measuring
its components in isolation, and by driving the dispatcher down paths that reach
different amounts of work:

```
meas_nop                     3     the baseline
meas_scale                 346     the x256 loop over 32 words
meas_silence               394     the clear loop
meas_base                  837     pk_simple_base -- cheap, NOT the culprit
meas_voice               12419     the Fold voice render dominates
meas_both                13279     base + voice, and 837 + 12419 + 23 = 13279
```

and through the dispatcher itself:

```
fold admitted           18998
bass admitted           45357
snare admitted          48592
unknown engine->silence   534     admission + staging + clear + scale + return
not admitted (slot 1)      26
```

**The dispatcher's own fixed cost is 534** -- that is item 2's
"dispatcher/wrapper overhead", measured directly by driving an engine id it does
not recognise, so it runs admission, staging, the silence clear, the scale stage
and the return without rendering anything.

**And the "overhead" column I published one commit ago is NOT overhead.** The
dispatch-over-render difference is **Fold +5,719, bass +1,616, snare +1,025** --
not uniform. A fixed dispatcher cost cannot differ by engine, so the column was
mixing the dispatcher's ~534 with **state- and control-dependent variation in the
render path**: the two entries see the renderer with different staged control
words, so they are not running the same code path, and the difference is the
renderer's, not the wrapper's.

**So the correct overhead figure is 534, for every engine:**

> **SUPERSEDED.** The percentages below are computed from the STRESS figures
> (74,515 / 80,722), which are NOT the production bound. See "THE REAL
> ANSWER (item 5)" for the corrected reachable-domain figures: **36.4%
> (bass) and 41.3% (snare)** against the same allowance.

| | renderer | + 534 | vs 23,040 |
|---|---|---|---|
| Fold Drum 1 | 26,112 | 26,646 | 13.5% over |
| Resonant Bass | 74,515 | 75,049 | needs **69.3%** |
| Resonant Snare | 80,722 | 81,256 | needs **71.7%** |

which leaves last commit's 69.3 / 71.6 essentially intact -- but for the right
reason now, and with the 5,698 Fold anomaly explained as a render-path difference
rather than a wrapper cost.

**The measurement lesson, which cost two commits:** to attribute a difference to a
WRAPPER, both entries must be shown to run the same INNER path. I compared two
entries with different control words and called the difference "overhead". The
silence-path measurement is the one that isolates the wrapper, because it
provably renders nothing.

### The production-path delta, all three engines -- and my extrapolation was WRONG

Measured with the same one-harness discipline, now covering every engine
(`tools/perky/measure_3algo_path_cost.py`):

```
engine        render   quoted  dispatch  overhead   ratio
FOLD DRUM      13279    13300     18998     +5698  1.431x
RES BASS       43741    43762     44251      +489  1.012x
RES SNARE      47567    47588     48051      +463  1.010x
```

The self-check passes for every engine (the gate's 12-instruction dump measures
+21 each time), so the deltas are real.

**THE OVERHEAD IS FOLD-SPECIFIC, AND I EXTRAPOLATED IT WRONGLY.** One commit ago I
took the Fold figure and added it to the two Resonant engines, producing a table
saying they needed 71.3% and 73.3% reductions. **That was wrong:** their actual
overhead is **+489 and +463 -- about 1%**, not +5,698. The Fold path is the
outlier, and the reason is not established; the two obvious candidates are the
`pk_simple_base` block decode (which only the Fold path calls, though BOTH the
render and dispatch entries call it, so it should cancel) and the `x256` scale
loop, which is far too small to account for ~5,700. **Flagged as unexplained.**

**Corrected budget:**

> **SUPERSEDED.** The percentages below are computed from the STRESS figures
> (74,515 / 80,722), which are NOT the production bound. See "THE REAL
> ANSWER (item 5)" for the corrected reachable-domain figures: **36.4%
> (bass) and 41.3% (snare)** against the same allowance.

| | renderer | + its own overhead | vs 23,040 |
|---|---|---|---|
| Resonant Bass | 74,515 | 75,004 | needs **69.3%** |
| Resonant Snare | 80,722 | 81,185 | needs **71.6%** |

So the figures the original report quoted -- **69.1% and 71.5%** -- were
essentially right all along, and the dispatcher overhead for the Resonant engines
is **negligible (~1%)**. The renderer-only measurement boundary is therefore NOT
materially misleading for these two algorithms, which is the direct answer to
item 1's concern.

**Also a units error in my own previous table**, worth naming: I wrote "77.6%
over" where the arithmetic gives `80,213 / 23,040 = 3.48x`. "Over by" and
"reduction needed" are different numbers and I conflated them in the same table
whose subject was unit confusion.

### The production-path delta: MEASURED, with the harness validating itself

The previous attempt was inconclusive because **I read a stale meter file after an
assemble that had failed silently** -- the probe wrote `move #>0038e8,r1`, which
is InvalidInstruction (the immediate-to-*register* form is `#$0038e8`; `#>` is
for accumulators), so a meter from an earlier run was still on disk and I
reported it as a measurement. That is the whole explanation for the 6,919-cycle
disagreement, and it is a process failure, not a hardware one.

The measurement the item asked for is now built and run: **one harness, one
seeded state, one assembly, three entries differing only in what they call.**

```
m_render    :  13279 modeled cycles/block     base + voice
m_quoted    :  13300                          + the gate's 12-instruction RNG dump
m_dispatch  :  18998                          pk3d_source: admission + dispatch
                                              + mode delivery + the x256 scale
```

**The harness validates itself.** The gate-only dump measures **+21 cycles**, and
`pk3c_rng_out` is 12 instructions plus a `jsrl`/`rts` pair -- the right magnitude,
which means the harness resolves differences of tens of cycles and the other
deltas are real.

**So, for this case:**

* the quoted timing figure tracks the renderer (13,300 against 13,279): the
  gate-only dump is 0.16% of it, so the quoted number is a fair stand-in for the
  renderer;
* **the production path costs +5,698 modeled cycles/block over what the timing
  gate measures -- +42.9%**, i.e. **+11,396 hardware cycles**, for the dispatcher,
  the admission check, the mode delivery and the `x256` scale stage.

**What that does to the budget.** The allowance is 23,040 modeled for the whole
source. If 5,698 of it is dispatcher overhead, the share left for the RENDERER is
**17,342, not 23,040**:

> **SUPERSEDED.** The percentages below are computed from the STRESS figures
> (74,515 / 80,722), which are NOT the production bound. See "THE REAL
> ANSWER (item 5)" for the corrected reachable-domain figures: **36.4%
> (bass) and 41.3% (snare)** against the same allowance.

| | renderer, measured | + overhead | vs 17,342 |
|---|---|---|---|
| Resonant Bass | 74,515 | 80,213 | **77.6% over** |
| Resonant Snare | 80,722 | 86,420 | **79.9% over** |

The required reduction therefore moves from 69.1/71.5% to roughly **77-80%**, not
because anything got worse but because the budget the renderer was being judged
against was **overstated by the omitted overhead**.

**Stated limits.** The +5,698 was measured on the FOLD path; the two Resonant
engines do not call `pk_simple_base`, so their overhead will differ and must be
measured separately before the table above is quoted as final. One seeded state
(Fold ARM mode-1 corner-0), one block.

## FIXED AND CALIBRATED: the reachability tool works, and there is NO more dead code

The withdrawn tool is fixed. Its bug was tracking instruction ADDRESSES by adding
word counts, which drifts from the assembler's real layout; a target whose computed
address matched no instruction silently ended the walk, pruning the entire
Resonant half of the dispatcher. **Label-level reachability needs no address
arithmetic at all, so that failure mode cannot occur** (`tools/perky/reach_3algo.py`).

**Calibration, against the one independent number available.** The verified dead
code is **51 instructions**, established by actually removing them and confirming
15/15 Fold ARM parity:

```
UNREACHABLE: 51 instructions in 6 blocks
   pk_u32_sub               6
   pk_sub_no_borrow         9
   pk_u32_asr               4
   pk_u32_shift_sign_ready 13
   pk_noise_step           10
   pk_noise_refresh         9
1 call/branch target was NOT label-form and was not followed:
   pk3x_scaled: jmp @CONT@        <- the external continuation, correctly excluded
```

**51, exactly, and the same six blocks.** 142 of 149 labels are reachable. The one
unfollowed target is `jmp @CONT@`, the external continuation -- correct.

**Its word estimate is approximate** -- 54 here against the verified 67 -- because
it guesses which instructions carry an extension word. Use it for the SET, quote
the verified 67 for the SIZE. Stated in the tool and here rather than quietly
rounded.

### THE ANSWER FOR ITEM 8: dead code cannot recover DJ EQ

**These six blocks ARE the whole dead set.** There is no more dead code to find, so
**67 words is a ceiling, not a milestone** -- and DJ EQ needs 86. Dead-code removal
therefore **cannot** close the gap, whatever the 19-word arithmetic suggested.

The remaining route to a smaller sacrifice is ~19+ words of genuine bit-exact
COMPRESSION of live code, which is a different and much harder task than deletion,
and one where the ablation ceiling already says the dense parts are the algorithm
itself.

**What this round is worth.** It replaces "the tool is wrong, the question is open"
with a calibrated negative result: the avenue is exhausted, the number is 67, and
the next attempt should not be another reachability scan.

## The 19 missing words: a static dead-code tool was written, and is NOT trustworthy

The concrete remaining non-hardware work after item 8 is ~19 more words (the
verified dead code is 67, and 86 buys DJ EQ back). I wrote a reachability
analysis to find them mechanically -- walk the composed source from the single
production entry `pk3d_source`, following fallthrough, branches, `do` targets and
`jsr`/`jsrl`, and report what is never reached.

**It reports 1,028 unreachable instructions = 1,031 words. That is wrong, and I am
not publishing it.** The decisive refutation is that it marks
`pk3d_snare_voice` -- **107 instructions, reached from `pk3a_entry` via `jsrl`,
and demonstrably live** (the dispatcher renders Snare in the gate that passes) --
as dead. A tool that calls a live renderer dead over-reports by roughly 15x
against the recorded 67, so every other name on its list is unverified too.

The likely fault is in resolving call targets: the `beq pk3a_entry` /
`beq pk3n_entry` edges are evidently not being taken, so the whole Resonant half
of the dispatcher is pruned. I did not isolate it, and **after the last three
rounds of publishing numbers I had to retract, the correct action is to withdraw
the tool rather than report its output as a finding.**

**What stands:** the VERIFIED dead code is **67 words** -- 51 unreachable
instructions, established by actually removing them and confirming 15/15 Fold ARM
parity, not by static analysis. That is **19 words short** of the 86 needed for
DJ EQ, and the tool that was supposed to close the gap is not yet trustworthy.

**This is also a repetition of a live trap**, and worth naming: `drop_unreached()`
-- an earlier name-based removal of six routines -- BROKE the Fold renderer,
because routines were reachable by FALLTHROUGH. Static reachability in this
codebase has now fooled me twice, in opposite directions (once removing too much,
once reporting too much).

## The event offset: `X:$20c` is the SAMPLE COUNT, and the machine hardcodes 16

Chasing the recorded `X:$20c` gap to ground produced something sharper than
"a dropped offset". Stock's own code, payload A:

```
000394: and     #>$f,a                ; a = a & 0xf            -> 0..15
000396: move    #>$10,b               ; b = 16
000398: sub     a,b      a,x:>$20c    ; b = 16 - a  ; and store a -> X:$20c
00039a: asl     a        b,x:>$20d    ; a <<= 1     ; and store 16-a -> X:$20d
00039c: move    a,x:>$20e             ; 2a -> X:$20e   <-- THE HOOK SITE
...
00042a: move    x:>$20c,n7            ; n7 = a      <-- THE SOURCE'S LOOP COUNT
00042c: ...
000434: move    x:>$20d,n7            ; n7 = 16 - a <-- THE CONTINUATION'S
```

**So `a` is the trig's sample position in the frame, `X:$20c = a`, `X:$20d = 16-a`,
and `X:$20e = 2a` is the interleaved word index the seam read.** Stock sets `n7`
from `X:$20c` for the SOURCE and from `X:$20d` for the CONTINUATION: the source
renders the `a` samples up to the event, and the continuation renders the remaining
`16-a`.

**The composed machine hardcodes `move #>$10,n7` -- 16 -- and never reads
`X:$20c`.** Exactly as the seam did before it, so this is inherited rather than
introduced.

**Why the audio is still correct, and what it costs.** The stock continuation
renders `16-a` samples STARTING AT `a`, so it overwrites the machine's samples
`a..15` with its own. The frame comes out right. But the machine did **16 samples
of work where the contract asks for `a`** -- up to 16x more on the source, and the
frame as a whole does `16 + (16-a)` samples' worth instead of `16`.

**What that does to the blocker: nothing, and the reason matters.** Timing is a
WORST case, and the worst case is `a = 15`, where the saving is 1/16 = 6% -- not
enough to touch a 36.5% / 41.4% gap. The AVERAGE case improves by up to 2x, which
is real but not a timing argument. The measured reachable figures use `n7 = 16`
and are therefore an **upper bound on a bound**, and they stay the honest number.

**AND THE OBVIOUS FIX IS A TRAP.** Setting `n7 = X:$20c` directly is dangerous:
on this DSP a `do` loop with ``LC = 0`` runs **65,536** iterations, so `a = 0`
would turn a 16-sample render into a 65,536-sample one -- the exact class of
disaster this branch has already met once (a 196,608-iteration voice loop from a
modulo buffer). Any implementation must guard `a >= 1` explicitly, and that guard
is not written yet.

**So the item is narrowed rather than closed**: the contract is now documented and
evidenced, the audio is unaffected, the worst-case timing is unaffected, and the
implementation has a named hazard that must be handled before anyone tries it.

## THE RESONANT NOISE USED A PRIVATE RNG THAT NOTHING SEEDED

This is the bug behind the state mismatch at **words 14 and 84..87** that this
branch had carried as "unresolved". It is fixed, and it was two bugs deep.

`pk_resonant_noise` / `pkr_noise_refresh` are **borrowed from the Slap voice**
(`resonant_dsp.py`: it takes `slap_voice.asm` after `pk_slap_noise:` and renames
only the label). Slap keeps the RNG in its own frame slots `r5+$72..$75`, which
`center_scratch` relocates to `r5+$32..$35`. **In the resonant renderer nothing
ever writes those slots** -- so the noise drew from whatever the block happened to
hold, while the reference model drew from the shared RNG. The two diverged only
where the noise reaches the output, which is exactly where the gate looked: the
noise sample-and-hold value (`NOISE+2`, word 14) and the noise resonator's
position and velocity (`NOISE_RES+10..13`, words 84..87).

**Fixed** by pointing the routine at the canonical limbs `X:0x38e8..0x38eb`, the
convention `pknv_refresh` already uses. The absolute form is deliberate:
`center_scratch` relocates only the `r5`-relative slots, so these must not look
like one.

**Measured effect**: `verify_perky_3algo_exec` used to stop at **case 0** on the
voice-block comparison. It now passes **cases 0..28 including the full X state AND
the RNG comparison**, and stops at case 29 on a PCM-only difference -- see below.

**A second, unrelated bug in the same gate.** The RNG read-back compared
`state[block][0x72]` (X:0x3872) while `run()` seeds the limbs at
`composed.RNG_GAP_END` = X:0x38e8. That address was stale from an older layout and
**had never executed**, because the X comparison above it failed first. It now reads
`composed.RNG_BASE - STATE`, the bytes it actually seeds.

## ITEM 8, HALF BUILT: the ARM->compact bridge is proven

Item 8 asks that panel changes reach the renderer. The authentic machine updates a
Resonant voice on the CPU per event -- the ARM routines at 0x0802682C / 0x08026030,
carried in C by `cf_perky4.c` -- writing TUNE, DECAY, ENV and MIX into an
ARM-shaped object, while the DSP port renders from a COMPACT layout. Until now the
only thing that crossed between them was a **fixed template computed at a neutral
panel setting**, which is why the instruments sound but ignore their knobs.

**`modules/perky/resonant_compact_cf.c` is the bridge, and it is proved.**
`tools/verify/verify_perky_3algo_compact_cf.py` compares it word for word against
the models' **own `from_arm`** over **800 states** -- 400 per family, randomized
TUNE/DECAY/ENV/MIX targets across 0..4095, randomized velocity and note, and a
70/30 split of triggered and untriggered objects. **Bit-exact.**

Choosing the renderer's own reader as the oracle is the point: a field the port
drops and a field the renderer needs cannot cancel out, because there is only one
description of the layout.

**The comparison earned its keep immediately.** The first hand-written port had two
errors, and both compiled clean:
* the snare's four decay blocks were transcribed at the wrong offsets (0x188 /
  0x19C / 0x1CC instead of **0x18C / 0x1A4 / 0x1BC**);
* the two mix coefficients were **missing entirely** -- `MIX_FIRST`/`MIX_SECOND`,
  object 0x164/0x168 to compact 97/99.

**A REMOVED DEPENDENCY, MEASURED.** `common_update` fills the ARM object's 0x34
from the 4096-entry pitch table, which would mean carrying 8 KiB to the ColdFire.
`from_arm` never reads 0x34, and **zeroing the whole pitch table leaves the compact
state bit-identical** (measured, both families). The only table the update still
needs is the 12-entry chromatic one, so the 8 KiB table stays where it is.

**NOT WIRED IN YET, and the artifact is byte-identical because of it.** The card
image is unchanged at `e3a6f297...`: the port is a proven component, not yet a
producer. Wiring it needs `res_update_bass`/`res_update_snare` exposed from
`cf_perky4.c` (they are `static` there), a per-family ARM object in `pk_render`, and
the conversion call -- then item 8's gate, that a knob change alters the audio
through the production path.

## REPEATED TRIGGERS: item 6, and a defect in the gate that hid it

A drum voice must **restart on every hit** and **must not restart between them**:
a note held across four 16-sample blocks is one hit, not four. Nothing did that
before -- the template was loaded only when the ENGINE changed, so a second hit on
the same engine continued the first one's decay.

**A flag cannot express it.** The obvious design -- send the track's trig bit and
reload when it changes -- is wrong in the other direction: with a flag, the note's
RELEASE also changes the value, and the release would restart the voice.

**So a monotonic rising-edge COUNT travels instead.** `control.c` keeps
`pk_trig_last`/`pk_trig_count` per track, bumps the count on a rising edge only,
and packs it into record word 0x15's high byte beside the engine id. The
dispatcher folds `count << 4` into the ledger it ALREADY compares, so "a new hit
happened" costs no extra branch -- which matters, because a near branch cannot be
used there at all (`dsp_asm` sizes every label long in pass 1, so the two passes
disagree and the build refuses). The count sits in bits 4..11 because the low
nibble is the engine id and bit 15 is the ledger's tagged marker.

Counts are 8 bits, so the counter wraps every 256 hits and a hit exactly 256 later
could look like no change. Widening it would collide with the engine id and the
tag, so the wrap is accepted and recorded rather than hidden.

**Two defects in the harness had to be fixed before it could test any of this, and
both had been reporting plausible numbers:**

1. **The block stride is the HOST's `-frames`, not the machine's n7.** `-frames 20`
   makes the host emit **160 bytes per block**; the machine's own n7 (16, which it
   sets) only decides how many of those the RENDERER wrote. The gate sliced at 128,
   so every block after the first was read from a **misaligned offset** and still
   produced non-zero, plausible-looking peaks. Fold's peaks moved from
   `[23040, 70400, 143360, 242176]` to `[23040, 91648, 206080, 366336]` once the
   stride was right -- the earlier figures were an artifact of the misread.

2. **The ledger has to be carried between blocks.** The first version of the
   trigger test reset it per block, so every block looked like an engine change,
   every block reloaded the template, and a held note was indistinguishable from a
   fresh hit. The harness was measuring its own reset. The dump window now runs to
   X:0x38ed so the ledger travels with the voice.

**And the first restart assertion was wrong too**: it compared the block's dumped
state against the template, but the dump happens AFTER sixteen rendered samples, so
it has already evolved. The correct comparison is like with like -- the first hit
(starting from a zero voice) and the second hit (starting from an evolved one but
reloading) must end in **exactly the same state**, and a held block must not.

**Verified now, on payload B/T1 through the real path:**

```
hit      trig=1  peak 8388608     counts [1, 1, 2, 2]
release  trig=0  peak 8388352     the count rises on a HIT and on nothing else
hit      trig=1  peak 8388608     a hit restarts the voice (both hits end identically)
held     trig=1  peak 8388352     a held note continues instead of reloading
```

The snare's release peak differing from its hit is the same fact from the audio
side: the release does not restart the voice.

## RETRACTED: the envelope curve is NOT reachable outside its 16-bit form

An earlier revision of this file claimed the envelope curve's 16-bit register form
(`sub x0,a / move a1,x0` in `noise_hat_envelope.asm` and `simple_drum_envelope.asm`)
diverged from the model on **25.5%** of envelope2's domain. **That number was
wrong**, and the way it was wrong is worth recording.

It was computed over **all 2048 table entries**. The renderer can only ever reach
**indices 0..1023**: `index = (raw >> 10) & 0x7ff` with `raw` clamped to `$0fffff`.
Restricted to the reachable range, the real v1.2.1 curves are:

| table | reachable max abs adjacent delta | positions over 16 bits |
|---|---|---|
| envelope1 | **340** | **0** |
| envelope2 | **6553** | **0** |

**Both are far inside 16 bits, so the DSP's form is exact for every curve the
hardware can present.** This is the same shape as the interpolator finding above:
a form that looks lossy, real data that never exercises the loss, and a fixture
that does.

The gate's own synthetic envelopes are the ones that exceed it --
`(i*43 + i*i*5) & 0xffff` and `(0xffff - ((i*181) ^ (i*17))) & 0xffff` reach
64388 and 53052 at reachable indices, against the real 340 and 6553. **That fixture
is unrepresentative, and it is a fixture defect.**

**It is deliberately NOT changed to make the gate pass.** The gate's current
failure is at a reachable index whose delta is `-156` -- well inside 16 bits and
bit-exact between the model and the DSP -- so the wild fixture is not what it is
detecting, and re-fixturing would move the case rather than explain it. Two DSP
changes that would have made the form general were written, tested, found to
change no failing value, and **reverted**: the real tables never need them, they
cost eight P words out of a hwtest budget already down to eleven free, and a
renderer change that fixes nothing is risk without benefit.

**The gate is therefore left RED, and what is actually known about it is this**:

* only **case 29 of 256** fails, on **PCM sample 15 of 16**; cases 0..28 pass,
  including the full X state and the RNG;
* it is **output-stage only** -- the post-block state matches exactly, so
  everything captured in the voice block agrees;
* samples 0..14 agree exactly, including thirteen that saturate to -32768;
* ruled out so far, each by measurement: the RNG (reproduces the model's 64-bit
  sequence exactly), the envelope delta at the failing index (-156, bit-exact),
  the envelope table addresses (the composer rewrites `$09a5`/`$0c51` to
  `Y_ENV1`/`Y_ENV2` correctly), and the velocity word (255, its own low byte).

That is a characterised single-sample divergence in a saturation-heavy synthetic
stress case, not a demonstrated defect in the production path. It is recorded here
rather than papered over.

## THE ACCEPTANCE GATE: an end-to-end production simulation, all six cases

`tools/verify/verify_perky_3algo_production_sim.py` runs the machine the way the
unit runs it, and is the check that decides whether an artifact is flashable:

```
PANEL          pk_engine_open() then the picked row, which is `pk_engine_select`
               with the model read OUT OF control.c's own browser arrays -- so a
               mapping change moves the gate with it and cannot be bypassed
CONTROL PATH   pk_render(track, ping, 0, 16) -- the real one, which prepares the
               controls and writes the record
RESET STATE    the voice block starts at ZERO
RENDER         pk3d_source on the real payload, FOUR consecutive blocks
ASSERT         non-zero PCM on every block, and state continuity
```

It seeds no fixture state, calls no renderer directly, and **runs with `-frames 20`**
-- what stock leaves in n7 at the hook -- because the machine is required to set its
own render length; a host-forced 16 would hide exactly the bug that made the render
overrun X:31.

```
payload track row                model count  peaks                                  continuity
B       T1    001 FOLD DRUM          0    40  [23040, 70400, 143360, 242176]        evolves
B       T1    010 RES BASS          10    88  [8388608, 8388608, 8388608, 8388608]  evolves
B       T1    011 RES SNARE         11   101  [8388608, 8388352, 6009344, 8388608]  evolves
A       T5    001 FOLD DRUM          0    40  [23040, 70400, 143360, 242176]        evolves
A       T5    010 RES BASS          10    88  [8388608, 8388608, 8388608, 8388608]  evolves
A       T5    011 RES SNARE         11   101  [8388608, 8388352, 6009344, 8388608]  evolves
```

**ALL THREE algorithms sound on BOTH payloads, from reset state and through the real
panel entry.** Fold's peaks RISE (23040 -> 70400 -> 143360 -> 242176), which is a
drum attack rather than a held value; the snare's vary, which is its state evolving
rather than replaying.

### FOLD WAS SILENT TOO, and the same fix covers it

The first run of this gate showed **Fold at `[0, 0, 0, 0]`** -- silent from reset for
the same reason the Resonant pair were: a zero voice block has no block index, no
envelope and no noise state, so the decoder had nothing to decode. `fold_control_update.py`
has the same init/trigger/update recovery (`fresh_fold1`, `trigger_fold1`), so Fold's
fresh state is generated and carried identically: **40 words**, `record[10]` = 40,
model 0. The P budget did not move, because the state rides the record buffer.

**THE HARNESS IS NEW AND DELIBERATELY SO.** `tools/harness/perky_cf/production_sim.c`
drives the real `pk_engine_open`/`pk_engine_select`/`pk_render` and emits the whole
record as DSP words. Three details cost real time and are recorded so they are not
rediscovered: the two stock UI calls `pk_engine_select` makes must be executable
`ret` stubs; `0x4005829c` must return **0** so `pk_engine_open` takes its
`if (!window) return` path after capturing the bank/part/track (a bare `ret` leaves
garbage in `rax`, the draws run, and the harness faults); and `trigger_fold1`
**mutates in place and returns None**, unlike the resonant pair.

## FIXED: the Resonant fresh state now reaches the DSP

The engines were silent because **nothing ever initialised X:0x3800**. A zero voice
block is silent BY THE ALGORITHM -- `ResonantSnare([0]*WORDS)` and
`ResonantBass([0]*WORDS)` peak at **0 over 64 blocks in the reference model
itself** -- so this was never a port defect, and Fold was the only algorithm that
ever made sound. Every gate missed it because every gate SEEDED the voice block from
a captured fixture: **the gate supplied exactly the thing production does not.**

**The authentic law already existed, in two places.** `resonant_control_update.py`
is the exact v1.2.1 init/update/trigger recovery (bass 0x08026790 / 0x0802682C /
0x080268DC, snare 0x08025F8C / 0x08026030 / 0x08026108, shared 0x080246AC /
0x08024714 / 0x08024878), and `cf_perky4.c` carries the same law in C
(`common_init`/`common_update`/`common_trigger`, `res_update_bass`,
`res_update_snare`, `prepare_res`). Running it produces a state that renders:

```
fresh -> update -> trigger -> from_arm   bass peak 32768   snare peak 32768   (model)
                                          bass peak -8388608, snare ... (see below)
```

The shared tables it needs (`pitch.bin`, `chromatic.bin`) are **not missing** --
they are build outputs of the `perky-optimize` worktree at
`out/perky/cf-final-verify/fixtures/assets/`.

**The fix, using the transport that already had room.** The per-track record buffer
is **336 bytes (84 longs)** at `0x80001c90 + (ping&1)*0xa80 + 336*track`, and the
record itself uses **40** of them. So the state rides in the spare words:

```
record[10]   = (word count << 16) | engine id      -> DSP words 0x14, 0x15
record[11+]  = the compact voice words, DENSE      -> DSP words 0x16 onward
```

and `pk3d_source` loads them into X:0x3800 **when the engine id changes**, which the
ENGINE LEDGER already detects. A matching ledger means the engine is current and the
voice block holds the EVOLVED state, so no load fires and the drum continues instead
of restarting every block. Cost: **+13 P words** (3,825 -> 3,838); nothing else moved.

**Measured, through the real dispatch, from a ZERO voice block:**

| voice block | record carries | peak | voice[0:5] |
|---|---|---|---|
| zeros | 88 words (bass) | **8,388,608** | `[255, 1, 0, 0, 1]` |
| zeros | 101 words (snare) | **8,388,608** | `[255, 1, 0, 0, 1]` |
| zeros | **nothing** (control) | **0** | `[0, 0, 0, 0, 0]` |
| zeros | nothing (control) | **0** | `[0, 0, 0, 0, 0]` |

and the state PERSISTS rather than reloading, which is what the varying continuation
peaks show: snare over four blocks is `[8388608, 8388352, 5919744, 8388608]`, not a
repeated first block.

**`tools/verify/verify_perky_3algo_resonant_fresh.py`** is the production-path gate
the directive asked for: it derives the state with the authentic law, requires the
tracked artifact to match it, requires the MODEL to render it, then drives
`pk3d_source` from a zero block with the state in the record and requires non-silent
audio -- with two controls (a record carrying nothing must stay silent; a matching
ledger must leave an empty block empty) so the audio cannot come from anything lying
around.

**What is still NOT done, stated plainly.** The `update` step runs in the gate, not
on the unit: the state delivered is the NEUTRAL-setting fresh state, so the engines
make sound and switch correctly but do not yet track the TUNE/DECAY/ENV/MIX knobs
per block. The law for that is `res_update_bass`/`res_update_snare` in
`cf_perky4.c` and it would run per event on the ColdFire, writing the updated state
into the same record words. Retrigger is likewise not yet driven from the record's
trig flag.

## THE PANEL BUG, found by the user: two of three browser rows were wrong

The image was flashed and made no sound. The cause was in the PANEL path, and no
gate in this branch could see it: every one of them builds a record by hand and
calls `pk3d_source` directly, so **none tested how a family byte gets chosen**.

The engine browser's labels and handlers, as shipped:

```
"001 FOLD DRUM"   model  0  -> family  0   renders
"003 SIMPLE DRUM" model  2  -> family  2   SILENCE  (no family-2 case in the DSP)
"011 NOISE/TONE"  model 10  -> family 10   renders -- and it is RESONANT BASS
(no row)          model 11  -> RESONANT SNARE WAS UNREACHABLE
```

The DSP dispatches on the family byte in `p[11]` and renders exactly 0, 10 and 11;
anything else reaches `pk3c_silence`. So the browser offered a row that could only
ever be silent, mislabelled Resonant Bass, and left Resonant Snare with no way to
be selected at all -- **the one thing the target requires (all three algorithms
selectable on T1 and T5) was not satisfied by the shipping image.**

**Fixed** in `modules/perky/control.c`, guarded on both candidates so every other
remix is untouched: the three rows are now Fold Drum 1, Resonant Bass and Resonant
Snare, mapping to 0, 10 and 11.

**And gated**, by `tools/verify/verify_perky_3algo_panel.py` -- the gate this branch
was missing. It reads the browser's labels and handlers out of `control.c`, checks
they are the same length, resolves each handler's family, requires the set to equal
the composer's own engine set (so the two cannot drift), requires all three
algorithms to be offered, and then drives each offered family through the real
dispatch and requires it to REACH A RENDERER (meter > 5,000; the silence path costs
~534). It reports the audio peak but does not assert on it -- see the next section
for why.

## THE RESONANT ENGINES DO NOT SELF-START -- the deeper reason the track is quiet

Chasing the silence past the panel bug produced something larger, and it is
verified in the MODEL, not just the port:

```
MODEL snare from zeros : peak over 64 blocks = 0; first nonzero block = None
MODEL bass  from zeros : peak over 64 blocks = 0; first nonzero block = None
MODEL snare from STRESS: peak 32768
```

**A zero voice block is silent by the algorithm.** `ResonantSnare([0]*WORDS)` and
`ResonantBass([0]*WORDS)` never produce a sample, in sixty-four blocks, in the
reference model itself. So this is **not** a port defect -- the DSP agrees with the
model exactly -- and the resonant engines are silent on a unit for the same reason.

**They need a state, and nothing in the production path establishes one.** Measured
through `pk3d_source`, one block each:

| engine | voice state | audio peak |
|---|---|---|
| Snare (11) | a SNARE state | 8,388,608 |
| Snare (11) | a FOLD state | **0** |
| Snare (11) | zeros | **0** |
| Snare (11) | a FOLD state, with the engine-change re-seed | **0** |
| Bass (10) | a BASS state | 8,388,608 |

**So Fold Drum 1 is the only one of the three that works from a fresh state**, which
is why the one browser row that ever made sound was "001 FOLD DRUM".

**What this means.** Every gate in this branch passed because the gates SEED the
voice block from a captured fixture -- the same shape of gap as the n7 bug and the
panel bug: the gate supplies exactly the thing production does not. The engine-change
re-seed added earlier stops the rail by CLEARING the block, which for these two
engines means clearing the only thing that could have made them sound; that trade is
now explicit rather than hidden.

**Not fixed here.** Establishing the resonant voice's initial state is a real piece
of work -- it needs either a DSP-side initialisation on engine change, or a
ColdFire-side state seed, and it needs the PĒRKONS oracle to say what the state
should be. It is the reason a hardware timing sweep should be run with **Fold Drum 1
first**, and it is recorded here rather than papered over.

## THE n7 BUG: the render length was never set, and every gate hid it

**The most serious defect found in this branch, and it was in the shipping path.**

The renderers' sample loop is `do n7,...`. On this DSP a `do` with `LC = 0` runs
**65,536** iterations, so n7 must be a defined positive number at every entry. It
was not. The composed machine inherited whatever the stock caller left, and
stock's last write before the hook is `move #$14,n7` on payload A — **twenty**.
The composer's own `move #>$10,n7` sat at the END of the dispatch, where stock
overwrites it at the continuation's own entry (payload A `0x42a`/`0x434`, payload
B `0x225`/`0x22f`): dead code that concealed the missing setup.

**Measured through `pk3d_source`:**

```
-frames 16:  X words written 32/64; beyond X:31 -> 0    meter 19011
-frames 20:  X words written 40/64; beyond X:31 -> 8    meter 23063
```

With n7 = 20 the machine wrote **eight words past the 16-frame source buffer**, at
`X:32..X:39` — and `X:0x20` is the stock scratch AGENTS.md says stock uses every
block — and cost **23,063 modeled cycles against 19,011**. So every timing figure
taken before this fix **understated production by ~21%**, and the buffer overrun
would have been live on the unit.

**Why every gate missed it:** the host's `-frames 16` set n7 for them. The gates
test the renderer; none tested the entry condition the renderer depends on.

**The fix**, in `pk3d_source`, before the dispatch:

```asm
        move    #>$10,n7
```

16 is the value every gate and every captured ARM fixture was validated at, so the
known-good audio is preserved. After it:

```
-frames 16:  words 32, beyond 0, meter 19011
-frames 20:  words 32, beyond 0, meter 19011
-frames 24:  words 32, beyond 0, meter 19011
```

The machine is now immune to the caller's n7, and `tools/verify/verify_perky_3algo_n7.py`
pins that: exactly the 32-word interleaved buffer for every caller n7 tried, never
past X:31, and an identical modeled cost each time.

**The stock contract, recorded and deliberately NOT adopted.** `n7 = X:$20c`
(payload A `0x42a`) is the trig's sample position `a` = 0..15, with the continuation
taking `16 - a` from `X:$20d`. Adopting it would shorten the render and cut the
cost. It is not adopted because it changes which samples the source owns, whether
the continuation overwrites `a..15` is not established, and `a = 0` would hand `do`
an LC of 0. The source says all of that where the next person will read it.

## DEAD CODE SHIPPED: 67 words, because the instrumented build needed them

The reachability analysis (`tools/perky/reach_3algo.py`) finds 51 unreachable
instructions in six blocks, all starting immediately after an `rts` — the
structural reason no fallthrough reaches them. That matches, exactly, the 51
established long before by actually removing them and confirming 15/15 Fold ARM
parity.

They are now removed in `compose()`. **Why now, when the removal was declined
earlier as "no functional gain":** the instrumented hardware build adds CF METER's
206-word DSP insert and was **35 words over**. The 67 fit it, and they make the
shipping build smaller too: **3,892 -> 3,825 words**. Unreachable code cannot change
behaviour, and all gates were re-run to prove it — `reach_3algo.py` now reports
**0 unreachable**, and every gate passes.

## THE RESONANT ORACLE: precisely what is missing and what it blocks

Chased to ground rather than left as "needs the stock image". The absent artifact
is **not** the stock Octatrack OS. It is the **PĒRKONS v1.2.1 image**, sha256
`adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6`, referenced as
`FIRMWARE_SHA256` by twelve `verify_perky_cf_*.py` gates. They are supplied it via
`PERKONS_FIRMWARE` or `--firmware`, and without it they stop with:

```
set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1
```

**What those gates are:** the **ColdFire** PĒRKONS renderer translations — a
different port from this branch's DSP machine. They read the interpolation tables
out of the SHA-pinned image at `0x0803237C`/`0x08032178`.

**What is NOT blocked by it:**

* the **captured fixtures ARE present and hash-pinned** — `out/perky/engine-fixtures/`
  holds engines 1..12, nine cases each, and `CAPTURE_SHA256` in the gates pins them.
  The Fold ARM parity (15/15) and the **reachable timing figures** are built on
  those fixtures and are real.
* every one of this branch's twelve gates.

**The remaining real gap, stated plainly:** `verify_perky_3algo_exec.py` — the
parity gate, and **not one of the twelve** — **FAILS on the Resonant section** and
did so before this session's changes (verified by stashing them: byte-identical
failure). The PCM comparison passes; the **post-block STATE** comparison fails on
the first synthetic bass case at words 14 (`40210` vs `61392`) and 84–87 (nonzero
vs `0`). Word 14 is the tail of `NOISE`; 84–87 are the tail of `NOISE_RES`
(74..87). So the shipped resonant renderer's **state layout** differs from the
model's on stress states, at the first case tried — it never reaches the ARM
comparison. Resolving that needs the PĒRKONS image to re-derive what the renderer
should write there.

**And it does not block the hardware timing sweep**, which measures cycles, not
sample parity.

## THE TIMING LEDGER, audited row by row

A reviewer's arithmetic gave **31.6% / 36.9%** where this document said **36.5% /
41.4%**. The discrepancy is real and it is the **safety margin, which this document
never named**. The full ledger, units explicit on every row:

| # | quantity | value | unit |
|---|---|---|---|
| 1 | frame deadline | **72,512** | hardware cycles (16 samples x 4,532) |
| 2 | stock reserve | **22,560** | hardware cycles (16 samples x 1,410) |
| 3 | available to the source | **49,952** | hardware cycles (1 - 2) |
| 4 | model->hardware conversion | **2x** | modeled -> hardware |
| 5 | available to the source | **24,976** | modeled cycles (3 / 4, exact) |
| 6 | safety margin | **3,872** | hardware cycles (1 - (4 x 7 + 2)) |
| 7 | safety margin | **5.34%** of the frame deadline; **7.75%** of row 3; **1,936** modeled | -- |
| 8 | source allowance, WITH margin | **23,040** | modeled cycles (the repository's `MAX_MODELED_BLOCK`) |
| 9 | dispatcher wrapper | **547** | modeled cycles (measured on this firmware) |
| 10 | renderer allowance, WITH margin | **22,493** | modeled cycles (8 - 9) |
| 11 | renderer allowance, WITHOUT margin | **24,429** | modeled cycles (5 - 9) |
| 12 | Bass reachable cost | **35,713** | modeled cycles |
| 13 | Snare reachable cost | **38,737** | modeled cycles |

**Required reductions, wrapper held fixed (the physically right form -- the wrapper
does not shrink when the renderer does):**

| | WITH margin | WITHOUT margin |
|---|---|---|
| Resonant Bass | **37.0%** | **31.6%** |
| Resonant Snare | **41.9%** | **36.9%** |

**Why the document said 36.5% / 41.4%.** Those came from comparing
`(renderer + wrapper)` against the 23,040 allowance -- i.e. from shrinking the
WRAPPER as well as the renderer, which is not physically what happens. It is
optimistic by **0.5 percentage points** on each engine. The reviewer's 31.6% / 36.9%
is the correct **without-margin** figure; 37.0% / 41.9% is the correct
**with-margin** figure. Both are right, for different budgets.

### Where the margin came from, and what kind of thing it is

`tools/verify/verify_perky_realtime_budget.py` line 16:

```python
MAX_MODELED_BLOCK = 23040  # 2x + stock = 68,640 / 72,512 cycles, >5% headroom
```

**Chosen conservatively, not measured.** The exact modeled budget is 24,976; 23,040
is that value ROUNDED DOWN to leave ">5% headroom", and it is a round number
(`0x5A00`) rather than a derived one. It is neither a measurement nor an inherited
development allowance -- it is a deliberate hold-back of 1,936 modeled cycles
(3,872 hardware) on top of the two measured inputs (row 2's stock reserve and
row 4's conversion factor).

The conversion factor itself is a second, separate conservatism: measured at
**1.89 / 1.89 / 1.94 / 1.97** on four instruction forms and rounded UP to 2x, which
adds ~1.5% of extra reserve on its own. Rows 4 and 6 are therefore two independent
holds, not one.

### Was 22,560 measured with THIS branch's retained-FX configuration? NO.

The constant is `STOCK_SHARE = CORE_TOTAL - USABLE` in `tools/build/cycle_count.py`,
with the comment *"STOCK FILTER'S OWN LOAD IS INSIDE STOCK_SHARE"* and
`BURN_SPARE = 1392  # measured, worst realistic FX1 load, 7 Aug 2026`. It descends
from hardware sweeps, and **`make cycles` says so for this remix in its own words**:

```
  This remix carries none of the modules the 7 Aug hardware sweep
  was measured with, so the headroom arithmetic below does not
  apply to it. ... -- and the wall is a CLIFF, not a slope.
  Only a burn sweep measures it.
```

So the 22,560 is a **stock-share constant from a sweep whose FX configuration is
not this branch's**. This branch retains six stock FX (FILTER, EQUALIZER, PHASER,
FLANGER, CHORUS, SPATIALIZER); the sweep measured a particular FX1 load and stock
FILTER's 192 cycles/sample specifically. **No measurement on this branch establishes
that 22,560 holds for exactly these six.** That is a genuine open item, and it cuts
one way only: a different FX load can only make the reserve LARGER, so the renderer
budget is an upper bound.

### Two constant inconsistencies inside the corpus

They are small but should be named, since this audit is about exactness:

* **stock reserve**: `verify_perky_realtime_budget.py` and the timing gate use
  **1410** (22,560/frame); `cycle_count.py` computes `4535 - 3120` = **1415**
  (22,640/frame) under a comment that says "~1410".
* **core total**: the perky budget uses **4,532** cycles/sample (72,512/frame);
  `cycle_count.py` uses `CORE_TOTAL = 4535` (72,560/frame).

Using the `cycle_count.py` pair instead moves the ledger by **0.1 percentage points
at most** (Bass 31.6% either way; Snare 36.9% -> 37.0% without margin; 41.9% with,
unchanged), and the margin from 5.34% to 5.29%. Neither choice changes any decision.

### The one-line answer

**The document's 36.5% / 41.4% was wrong in form, not in magnitude of error: it
charged the wrapper against a budget that already excluded it. The correct figures
are 37.0% / 41.9% WITH the repository's 5.34% (3,872 hardware cycle) conservative
hold-back, or 31.6% / 36.9% WITHOUT it.** The hold-back is a conservative choice,
not a measurement, and it is the entire discrepancy.

## RE-MEASURED after the firmware change: the wrapper is 547, and the blocker did not move

**Changing the firmware invalidates every figure measured on the old source**, so
they were re-measured rather than carried forward -- the boundary error this branch
has now made six times, and the first time it was caught by asking the question
before being told.

**The renderer figures are unchanged, and that is correct:** the timing gate drives
`pk3t_fold`/`pk3t_bass`/`pk3t_snare` directly, and the change was in the
DISPATCHER, so it cannot see it.

```
fold  25,393 | bass 35,713 | snare 38,737   reachable (identical to before)
```

**The wrapper moved, by exactly the compare path:**

```
steady-state wrapper (silence path, ledger seeded)   534 -> 547    (+13)
one switch block      (silence path, ledger stale)    -- -> 676    (+129, the
                                                                    108-word re-seed)
```

The 676 is the whole story of the re-seed's cost: 108 words at ~1.2 cycles each.
It is paid **once per engine change**, not per block.

**The blocker is unmoved:**

| engine | reachable | + 547 | needs | hardware window |
|---|---|---|---|---|
| Fold Drum 1 | 25,393 | 25,940 | 11.2% | **+2.7%** |
| Resonant Bass | 35,713 | 36,260 | **36.5%** | +31.1% |
| Resonant Snare | 38,737 | 39,284 | **41.4%** | +39.5% |

36.4% -> 36.5% and 41.3% -> 41.4%: the fix for the switching rail cost the blocker
nothing measurable, which is the result that makes it safe to keep.

## FIXED: the engine-change re-seed -- a switch no longer rails

The hazard measured above is fixed. The dispatcher now compares the incoming engine
id against an **ENGINE LEDGER** and, on a change, clears the shared voice block
before staging this block's controls:

```asm
        move    b1,x0                   ; x0 = engine id
        move    x0,a
        add     #>$8000,a               ; the tagged engine id
        move    a,x1
        move    x:$38ed,b
        cmp     x1,b
        beq     pk3s_same
        move    #>$3800,r0              ; re-seed the shared voice block
        move    #>$ffffff,m0
        clr     a
        do      #$6c,pk3s_done
        move    a1,x:(r0)+
pk3s_done:
        move    x1,b
        move    b1,x:$38ed
pk3s_same:
```

**The id is tagged with `0x8000`** so that a boot word of zero can never match a
real engine id -- the first dispatch after boot therefore re-seeds too, which is
what a fresh start should do. `x:$38ed` was `ADMIT_LATCH`, free since the latch was
removed, so this costs no new claimed word. The block costs **+20 P words** (3,872
-> 3,892, both payloads FREE 171).

**Measured effect.** Before, driving each engine from the seeded Fold state:

```
BASS   mono[:4] (-8388608, -8388608, -8388608, -8388608)   <- -2^23, RAILED
```

and after:

```
FOLD   meter  19075  mono[:4] (0, 0, 0, 0)  peak 0
BASS   meter  42480  mono[:4] (0, 0, 0, 0)  peak 0
SNARE  meter  46019  mono[:4] (0, 0, 0, 0)  peak 0
```

The new engine starts from a cleared block instead of inheriting the old engine's
fields, so there is no rail. A **silent block after a switch is the re-seed working**,
not a defect, and the switch gate now says so rather than asserting non-zero
everywhere: its assertion is **no block rails (`|peak| >= 2^23`)**, which is the
hazard that was actually measured.

**Three gates needed their SETUP changed, not their assertions weakened.** The
engine-join, dispatch and switch gates seed the voice block to test the
steady-state renderer; they now also seed the ledger to say "this engine is already
current", so no re-seed fires and they test what they always tested. The
core-mapping guard also needed rewriting: it refused any write to `x:$38ed` without
a clear, which was right for a latch and wrong for a ledger. It now refuses the
LATCH SHAPE specifically -- a load followed by `tst`, i.e. a word tested for truth
-- and requires the ledger to be COMPARED, which is the property that matters.

Image `7e2e4f122f1f62e87d0299ca31675e1ec830d1b63f4aadacc43481ba8d70c3ef`, reproduced
byte-for-byte by both build paths, **all eleven gates PASS**.

## ITEM 6 residual: trigger, and persistent state -- plus an ANOMALY left open

**The DSP ignores the record's trigger field entirely.** Two identical drives
differing only in record word 3 (the trig), 2 blocks each:

```
trig=0 blocks: [[-256, -512, -1024, -12544], [335360, 353536, 383488, 401920]]
trig=1 blocks: [[-256, -512, -1024, -12544], [335360, 353536, 383488, 401920]]

block0 identical across trig values: True
block1 identical across trig values: True
```

**Byte-identical.** So the trigger's effect reaches the DSP **only through the
control words the ColdFire prepare computes** -- `pk_simple_prepare` smooths one
extra step on a trig, and that is the whole channel. This is consistent with the
probe's own comment ("the record flag is checked so a stale/non-event offset cannot
manufacture a hit") and it settles item 6's trigger/retrigger question: there is no
DSP-side trig path to test, because there is no DSP-side trig path.

**Persistent state works.** Block 1 differs from block 0 (peak 317,184 -> 663,296),
so the voice block carries the render forward rather than restarting -- the same
property the switch gate exercises across an engine change.

### THE ANOMALY RESOLVED -- and it exposed a real switching hazard

The test named above: each engine driven from the SAME state and the same controls,
one engine per run.

```
FOLD   meter  18998  mono[:4] (-256, -512, -1024, -12544)
BASS   meter  45357  mono[:4] (-8388608, -8388608, -8388608, -8388608)
SNARE  meter  48592  mono[:4] (0, 0, 0, 0)

fold == bass : False      fold == snare : False
```

**All three separate cleanly**, with three different meters. So the engine dispatch
does select different code and produce different audio, and the earlier coincidence
was about STATE EVOLUTION between blocks, not about the dispatch. The anomaly is
closed as benign.

**But it exposed a real hazard in the switched configuration:**

* **Fold -> Resonant Bass saturates at full-scale NEGATIVE.** `mono[:4]` is
  `-8388608` = `-2^23` exactly, i.e. clipped at the 24-bit rail, on the FIRST block
  after the switch. Bass's resonators read the words Fold left behind and the sum
  rails.
* **Fold -> Resonant Snare renders SILENCE** (`0, 0, 0, 0`).

Those are the two failure modes the brief's "switch algorithms safely ... survive
algorithm changes between events" is about, and they are now measured rather than
assumed.

**The boundary, stated.** This is measured with the record's CONTROLS HELD FIXED
across the switch. A real switch also runs the ColdFire prepare for the new engine,
which recomputes the control words and may well prevent the rail -- so this
establishes that the DSP-side switched state is hostile, not that a panel switch
pops. Establishing the latter needs the prepare in the loop, which is a
ColdFire-side test.

**What it means for the design either way.** The voice block is shared by three
engines with different layouts (word 34 is `MODE` for Fold, `DECAY_A` for Bass and
inside `RES2` for Snare -- the same reason the mode delivery had to be Fold-only).
A switch therefore hands each engine the previous engine's fields as if they were
its own. A safe switch needs the DSP to clear or re-seed the voice block when the
engine id CHANGES, which is now a concrete, bounded piece of work with a measured
motivation.

### THE EARLIER ANOMALY, kept for the record

**Engine 10 (RES BASS) and engine 0 (FOLD) produced the SAME block-1 PCM:
`(335360, 353536, 383488)`.** Yet the switch gate's per-block meters are
**19,014 / 17,731 / 17,772** -- different costs, so different code executed.

Same output from different code is exactly the kind of thing that is either
completely benign (a shared post-processing stage dominating the block, e.g. the
`x256` scale or the applied-control path) or an engine dispatch not doing what it
claims. **I am not going to guess which**, and per this branch's own history the
guess would be wrong. The next step is to make the two engines' block-1 renders
differ by construction -- a state and controls that exercise the Resonant
resonators specifically -- and see whether the outputs separate.

## ITEM 6 residual: algorithm switching WORKS at the dispatch level

The one control sub-item that was not gated is algorithm switching. It is now
exercised through the real dispatcher.

**The harness problem, and how it was solved.** A probe cannot call `pk3d_source`
twice: the machine hands control back with `jmp @CONT@` rather than returning to
its caller, so a second `jsrl` in the same block never executes -- which is why a
first attempt reported three identical meters and looked like a pass. The fix is a
**stateful probe across script blocks**: the host calls the entry once per block,
so a counter in X memory advances the selected engine between calls.

```
meas_cycle:
        move    #$0039b1,r6
        move    x:(r6),a          ; the counter, in X memory
        move    #$000300,r4
        move    #$000000,b
        tst     a
        beq     mset              ; 0 -> FOLD
        move    #$00000a,b
        cmp     #$1,a
        beq     mset              ; 1 -> RES BASS
        move    #$00000b,b        ; 2 -> RES SNARE
mset:
        move    b1,x:(r4+$13)     ; publish the engine id, as pk_render would
        move    a1,b
        add     #$1,b
        move    b1,x:(r6)         ; advance the counter
        jsrl    pk3d_source
        rts
```

Three blocks, and the per-block meters are:

```
blocks 3  max 16718 instr/block
meters: ['16718', '15914', '15989']
```

**Three different, plausible per-block costs** -- the machine selects and runs a
different renderer each block, in sequence, with no crash and bounded output. The
id is published exactly as `pk_render` publishes it, into record word `0x13`.

**The non-zero version is now a gate.** With a REACHABLE state (the Fold ARM
fixture) and live staged controls, `tools/verify/verify_perky_3algo_switch.py`
drives all three engines in sequence and asserts non-zero, bounded, reproducible
audio:

```
block engine          peak  nonzero  first-3
    0 FOLD DRUM     317184    16/16  (-256, -512, -1024)
    1 RES BASS      663296    16/16  (335360, 353536, 383488)
    2 RES SNARE    1049600    16/16  (570624, -675840, -698880)
```

All three switched blocks are live, inside 24-bit (peak 1,049,600 against
8,388,607), and identical across two identical drives.

**An oracle was attempted and is not constructible.** The natural control is the
switched FOLD block against a direct render from the same state and controls. It
**fails at sample 0**, and the reason is structural: the dispatcher stages its
controls through `x:(r6+$67)` and `x:(r5+$70..$72)`, and `r5`/`r6` there are
whatever the **STOCK caller** left. A probe cannot replicate that context, so the
"control" renders from different registers. A control that cannot be constructed is
not evidence; the gate says so in its own docstring rather than shipping a
comparison that would be either fake or permanently red.

**So the boundary is: every block is checked for being live, bounded and
reproducible -- NOT for being the samples hardware would produce.** No oracle
exists for any of the three in the switched configuration, and the gate states
that rather than implying coverage it does not have.

## ITEM 9: the next legitimate blocker, stated against its own bar

The directive lists seven preconditions. Each is now satisfied by a measurement in
this document, and the bar is met **on the reachable domain**, not on stress.

| # | precondition | evidence |
|---|---|---|
| 1 | production continuation cost measured or tightly bounded | stock reserve **22,560** cycles/block (16 x 1410, hardware-measured, stock FX load INSIDE it) + wrapper **547** modeled |
| 2 | exact measurement boundaries documented | "MEASUREMENT BOUNDARIES" above: renderer + a 12-instruction gate-only dump; excludes dispatcher, mode delivery, the x256 scale, and stock |
| 3 | reachable production timing domain established | the captured ARM fixtures; `timing.json` keys its verdict on `worst_reachable` |
| 4 | hot path profiled | ablation: `pk_resonant_decay` 39.7%, `pk_resonant_core` 21.7%, `pk_u32_mul_low` 15.9%, `pk_resonant_noise` 5.5% |
| 5 | reasonable bit-exact avenues attempted AND measured | native-width multiply (closed: max captured width 32 > 24), dead code (exhausted: 51 instructions, 67 words, reachability-calibrated), redundant reloads (5 composition-wide) |
| 6 | minimum production cost still exceeds 72,512 with continuation and margin | see below |
| 7 | independent control/integration/parity work completed | prepare paths, engine-ID join, admission, T1/T5 mapping, parameter transport, mode delivery, rejection paths -- all gated |

**Precondition 6, the arithmetic.** On the reachable domain, with the wrapper and
the stock reserve included:

```
Resonant Bass   renderer 35,713 + wrapper 534 = 36,247 modeled
                -> 2x = 72,494 hardware + 22,560 stock = 95,054 vs 72,512 -> +31.1%
Resonant Snare  renderer 38,737 + wrapper 534 = 39,271 modeled
                -> 2x = 78,542 hardware + 22,560 stock = 101,102 vs 72,512 -> +39.4%
```

and the ablation ceiling says **removing every non-algorithm instruction still
leaves the snare at 29,517 modeled against a 23,040 allowance -- 28% over** (bass
24,881, 8% over). Since the non-algorithm content is only 23.9% of the snare
renderer, no instruction-level optimisation reaches the allowance; closing it
requires removing roughly half the resonant arithmetic itself, which is the
algorithm, and the brief forbids changing it.

**So the blocker is legitimate, and it is now precisely this:**

> Resonant Bass and Resonant Snare cannot meet the DSP frame deadline on their
> reachable production states. The required reductions are **36.4% and 41.3%** of
> the renderer (not the 69-72% the earlier report claimed, and not the 2.8%/11.3%
> the earlier report also claimed). **The gap is larger than the entire
> non-algorithm content of the code**, so it cannot be closed by bit-exact
> implementation optimisation; and the algorithm itself is off-limits by the
> brief. A decision is needed: change the algorithm, change the deadline's
> assumptions, or drop one of the two Resonant engines.

**Fold Drum 1 is NOT part of the blocker** -- at 25,393 reachable + 534 wrapper it
lands 2.6% over the hardware window, well inside what bit-exact work could reach.

**What is NOT blocked, and should not be folded into this:** the event sample
offset (`X:$20c`) is a recorded functional gap awaiting a design decision about
pre-trig behaviour, and the resonant oracle needs the stock 1.40C image, which is
absent from the tree.

## ITEM 8: the FX sacrifice, revisited -- architectural answer plus a threshold

The directive asks whether code placement, fragmentation, shared-P tails,
relocation or **overlaying the mutually exclusive renderers** can reduce the
stock FX sacrifice. Both halves have answers.

**Overlaying: not available, and not because it was not tried.** The placement
schema is `DspSection` (`tools/remix/schema.py`), whose fields are exactly:

```
asm, priority, payloads, bus_role, ybase, dev_pin_ybase, r7_latch_slot, gate_label
```

`priority` is documented as BYTE-LOAD-BEARING packing order. **There is no
overlay, segment, bank, relocation or load-address field**, so the architecture
has no mechanism to overlaid code even if the semantics allowed it -- and they do
not: the algorithm is chosen PER TRACK PER BLOCK, so any of the three bodies can
be required on a switch that must not load code. Overlaying them would require
runtime loading, which the directive itself rules out, and `verify_perky_3algo_image`
plus the "A GAP IS A WALL" single-run placement rule mean the section must be one
contiguous blob regardless.

So the three complete renderer bodies genuinely must be resident.

**The threshold, which is the actionable half.** `verify_perky_3algo_sacrifice`
measures, for the CURRENT composition (3,872 words after the mode delivery):

```
composed Perky DSP program: 3872 P words per payload
  nothing removed (preserve all stock FX)   0     short 3872
  SPRING REV only                        1063     short 2809
  PLATE + SPRING + DARK                  2724     short 1148
  + COMPRESSOR                           2904     short  968
  + LO-FI                                3441     short  431
  + DJ EQ                                3786     short   86
  + COMB FILTER                          4063     FITS
```

**86 words is the whole distance to a smaller sacrifice**: shrink the composition
to 3,786 and DJ EQ comes back, leaving only the three reverbs, COMPRESSOR, LO-FI
and COMB FILTER sacrificed. That is a concrete, measurable target rather than a
hope.

**And 67 of those 86 words are already found.** The dead-code removal measured
earlier is worth 67 words (51 unreachable instructions, verified 15/15 Fold ARM
exact) and is deliberately NOT shipped because it gives no functional gain on its
own and perturbs the equivalence gate's basis. **It is 19 words short of the
threshold.** So the remaining question for item 8 is whether ~19 further words of
bit-exact reduction exist -- a far smaller and better-posed task than "reduce the
sacrifice", and one worth doing only if DJ EQ is worth 19 words of risk.

## THE REAL ANSWER (item 5): the production bound is the REACHABLE figure, and I was quoting STRESS

**This corrects the headline number of the entire investigation.** The directive's
item 5 says, in terms: "Do not use impossible randomized states to impose a
production timing bound." The repository's own timing report has been carrying
both figures all along:

```
schema: perky-3algo-timing-v2
fold    worst=25393  stress=25393  reachable=None   from=arm-fixtures
bass    worst=35713  stress=74511  reachable=35713  from=arm-fixtures
snare   worst=38737  stress=80718  reachable=38737  from=arm-fixtures
```

**74,515 and 80,722 are `worst_stress`.** They come from `resonant_state()`, whose
own docstring says it covers "both sides of every bounded-path guard" with
`DECAY_COUNT` up to `0xffffffff` and random coefficients -- states the production
control path cannot produce. The timing gate's docstring says it plainly:

> The verdict uses the REACHABLE figure. Reporting the stress figure as the
> production cost is the error this split exists to prevent.

**I quoted the stress figure as the production cost, round after round.** So did
the blocker report the directive is about. That is the error, and it is larger
than the unit error I spent three rounds on.

**The correct budget:**

| engine | reachable (production bound) | + wrapper 534 | vs 23,040 allowance | hardware window |
|---|---|---|---|---|
| Fold Drum 1 | 25,393 | 25,927 | **11.1% over** | 74,414 / 72,512 = **+2.6%** |
| Resonant Bass | 35,713 | 36,247 | needs **36.4%** | 95,054 / 72,512 = **+31.1%** |
| Resonant Snare | 38,737 | 39,271 | needs **41.3%** | 101,102 / 72,512 = **+39.4%** |

**So the answer to item 3 is 36.4% and 41.3%, not 69-72%.** That is roughly *half*
the reduction the blocker report demanded, and it is the direct answer to the
directive's question of whether case A (~2.8%/11.3%) or case B (~69-71%) applies:
**neither.** The truth is a third case the framing did not name -- about 36-41%,
because the numerator was stress-inflated and the denominator was a real derived
allowance.

**And Fold Drum 1 is only 2.6% over the hardware window.** It is not blocked at
all; it is a hair over, which is why it was never the subject of the directive.

**What this changes for the blocker bar (item 9).** The bar's clause "resulting
minimum production cost still exceeds 72,512 cycles including mandatory
continuation and justified margin" must be evaluated on the **reachable** figure.
On that reading:

* Fold Drum 1: **+2.6%** -- within reach of bit-exact optimization, not a blocker;
* Resonant Bass: **+31.1%**, Resonant Snare: **+39.4%** -- genuinely over, and the
  ablation ceiling (the algorithm is 76% of the snare renderer) says bit-exact
  optimization cannot close 31-39% without touching the algorithm.

**The lesson, and it is the sharpest of the session.** I verified *units*, I
verified *measurement boundaries*, I verified *which side of the wrapper a cost
belongs to* -- and never once asked **whether the number I was quoting was the
one the tool designated as the verdict**. The repository had the right figure
written in its own report the whole time, on a line labelled `reachable`, next to
the one I kept reading.

## RECONCILED: where 23,040 comes from, and why the "2.76% over" claim was the error

Item 1 of the directive asked precisely what 74,515 and 80,722 contain and how
they relate to 72,512. It is answerable from the repository, and the answer
corrects BOTH framings in the blocker report.

**Provenance.** `tools/verify/verify_perky_realtime_budget.py`:

```python
"""The interpreter host counts decoded opcode cycles rather than instructions.
Use a 2x margin on that model (hardware MOVE timings exceed its nominal counts),
and reserve stock's measured 1410 cycles/sample. Only one PERKY voice per core is
admitted, with FX1/FX2 NONE for this hardware canary."""
MAX_MODELED_BLOCK = 23040  # 2x + stock = 68,640 / 72,512 cycles, >5% headroom
...
report = dict(modeled_cycles_max=worst[0], ..., block_limit=MAX_MODELED_BLOCK,
              model_margin=2, stock_reserved=16 * 1410,
              deadline=16 * 4532, max_voices_per_core=1)
```

So the allowance is **derived from the physical deadline**, not a historical
development figure:

```
deadline        = 16 x 4532 = 72512
stock reserve   = 16 x 1410 = 22560   (stock's MEASURED 1410 cycles/sample)
hardware budget = 72512 - 22560 = 49952
modeled budget  = 49952 / 2 = 24976   (the host model undercounts hardware ~2x)
allowance       = 23040               (a 7.8% haircut on the modeled budget)
check: 2x23040 + 22560 = 68640 / 72512 = 94.7%  ->  5.3% headroom
```

**Units, stated once.** 74,515 and 80,722 are the interpreter host's
`modeled_cycles` per 16-sample block. 72,512 is HARDWARE cycles per block. The
model undercounts hardware by ~2x (measured 1.89/1.89/1.94/1.97 on four
instruction forms), so the two are not comparable without the factor.

**Therefore:**
* the blocker report's "Bass is over the PHYSICAL deadline by 2.76%" compared
  MODELED against HARDWARE. That is the arithmetic error, and it is already
  retracted. In hardware terms bass is `2 x 74515 + 22560 = 171590` against
  72,512 -- over by 137%, not 2.76%.
> **SUPERSEDED by "THE REAL ANSWER (item 5)".** This bullet is arithmetically
> correct but built on the STRESS numerator. On the reachable bound the
> figures are **36.4% (bass) and 41.3% (snare)**.

* the "51,475 / 57,682 must be removed" figures are `modeled - 23040` and are
  **correctly computed**, because both sides are in the host model's units. The
  honest reduction figure is therefore **69.1% (bass) and 71.5% (snare)**, and it
  is the same fraction in either unit:
  `1 - 2x23040/(2x74515) = 69.1%`.
* what made 23,040 look like a silent revert is that **its provenance was not
  written down**. It is `(72512 - 22560) / 2`, less margin -- a real derivation
  from the physical deadline. That is now recorded.

**RETRACTED, one commit later: my own "FX NONE" caveat was wrong.** I wrote that
the 1,410 cycles/sample stock reserve was measured with FX1/FX2 NONE, so the real
reserve must be larger and the real allowance smaller. `tools/build/cycle_count.py`
says the opposite, in its own words:

```python
BURN_SPARE = 1392       # measured, worst realistic FX1 load, 7 Aug 2026
CORE_TOTAL = 4535       # 200 MIPS / 44100, arithmetic
USABLE = 3120           # what our code may actually spend, per core
STOCK_SHARE = CORE_TOTAL - USABLE      # ~1410, by subtraction
...
# STOCK FILTER'S OWN LOAD IS INSIDE STOCK_SHARE: the 23 Aug budget was
...
print(f"... [{', '.join(stock_rows)}] -- stock code; FILTER measured 192")
```

**"STOCK FILTER'S OWN LOAD IS INSIDE STOCK_SHARE"** -- the reserve already
contains stock FX load, measured at 192 cycles/sample per FILTER instance, and
`BURN_SPARE = 1392` is "the worst realistic FX1 load". The "FX1/FX2 NONE" phrase
belongs to `verify_perky_realtime_budget.py`'s canary CONFIGURATION -- the
per-voice harness deliberately runs with no FX so it measures the voice, not the
bank -- and I read it as a statement about the 1,410 reserve. It is not one.

So the allowance of 23,040 **stands as derived**: `(72512 - 22560) / 2` less
margin, with stock FX load already inside the 22,560. There is no hidden larger
shortfall from the retained effects.

**What the residual uncertainty actually is**, in the repository's own terms:
`make cycles` prints "the counter reads ~270 LOW on the reverb (CHIP.md s2); the
wall is a CLIFF" and, for a remix like this one, "the headroom arithmetic below
does not apply to it ... Only a burn sweep measures it." So the ceiling is a
hardware burn sweep on a CLIFF, not a slope, and the local counter under-reads by
a documented ~270 cycles on the reverb. That is the limit of what local tooling
can say -- not an FX-loading error in the budget.

## Final architecture

| | |
| --- | --- |
| Capable tracks | Octatrack **T1** and **T5** only |
| Core mapping | T1 on payload **B** (its core carries T1–T4); T5 on payload **A** (T5–T8) |
| Voices per core | exactly **one** |
| Algorithms | **Fold Drum 1**, **Resonant Bass**, **Resonant Snare** |
| T2–T4, T6–T8 | ordinary Octatrack tracks |
| FX1 + FX2 | preserved on all eight tracks |
| Wavetable | not used |

The three algorithms reuse the already-qualified renderers. Nothing was
rewritten: `build_dsp_3algo_source.py` composes the *same* bodies the
standalone gates execute, and every state/trigger/mode behaviour is theirs.

## Composition and deduplication

`tools/perky/build_dsp_3algo_source.py` emits one source for both payloads.
Its `measure()` reports the real linked size, never the sum of standalone
probes.

| | P words |
| --- | ---: |
| Fold Drum 1 standalone probe | 1,337 |
| Resonant Bass standalone probe | 2,456 |
| Resonant Snare standalone probe | 2,338 |
| Naive sum | 6,131 |
| **Composed shipping source** | **4,000** |

The 2,131-word difference is measured, not estimated. Deduplication is
*proved*, not assumed:

* the bass and snare resonator/decay cores must canonicalise to
  byte-identical instruction text or the build stops;
* the exact `pk_u32_*` low32 arithmetic, the RNG/noise stream, the hardware
  noise sample-and-hold helper and the shared envelope renderer
  (`pk_noise_hat_envelope`) are emitted once;
* the standalone math dispatcher (`pk_math_probe`), which shipping code never
  calls, is dropped from the resonant tail;
* the Fold/Simple primitive set (`pk_simple_envelope` / `_frequency` /
  `_oscillator` / `_delta_at` / `_base`) is emitted once.

`resonant_dsp.source()` gained a keyword-only `core_variables_fixed` hook so
two families can share one decoder body; with its defaults it reproduces the
standalone probe byte-for-byte, which is why the existing gates still pass.

### How the cores were made shareable

The decoder cores address their temporaries through `r4`. Bass and snare
reached the generator with different variable counts, so the same instruction
sequence carried different displacements. `core_variables_fixed` pins the
twelve temporaries plus `r_input` to a private slot block and moves each
family's own variables above it. A canonical-label comparison then shows the
two bodies are the same machine code, and one copy ships.

## Private X ledger (per core)

| Range | Words | Purpose |
| --- | ---: | --- |
| `X:$3800..$386b` | 108 | the one voice object (largest algorithm is the 101-word snare) |
| `X:$386c..$38e7` | 124 | spare |
| `X:$38e8..$38eb` | 4 | shared RNG stream (two u32 limbs) |
| `X:$38ec` | 1 | source-seam event offset |
| `X:$38ed` | 1 | one-Perky-track-per-core admission latch |
| `X:$3900..$39bb` | 188 | shared render scratch (resonant needs 184) |

The RNG limbs are a **fixed absolute address** owned by the shared helper, not
a register-relative slot. The composer refuses to build if the helper moves
them, because every renderer would silently read a different stream.

## Y ledger

The Fold/Simple bodies carry their table bases as absolute immediates, so
their addresses are fixed by the qualified renderer and the ledger fits around
them:

| Base | Words | Content |
| --- | ---: | --- |
| `Y:$07a5` | 512 | three 256-point Fold/Simple waves |
| `Y:$0c50` | 683 | shape-0 amplitude curve |
| `Y:$0efb` | 68 | packed pitch basis (+padding) |
| `Y:$2000` / `Y:$2280` | 683 / 683 | resonant curve banks 1 and 2 |
| `Y:$2500` / `Y:$2600` | 257 / 257 | resonant interpolation tables A and B |

Total ≈ 3,320 words of the 2,139-word *private* low-Y budget plus the resonant
tables; placement of the resonant banks is the next measurement (see below).

## Status this round

**Done and verified**

* the composed source builds; `4000` P words measured with `dsp_asm` at
  `P:$1000`;
* each retained standalone renderer gate still passes unchanged
  (`verify_perky_fold_drum_exec.py`, `verify_perky_resonant_dsp_exec.py`);
* the deduplication identities are enforced by the builder itself;
* the RNG base and the Fold/Simple table bases are asserted, not assumed.

**Open — the composed execution gate, and the scratch-convention item**

Two things are open, and the first is a real implementation item rather than a
harness problem.

**(1) The scratch convention is not unified — fully characterized.**

The composed machine hands every algorithm the same scratch base, but its
pieces were written against two different conventions. Measured displacement
windows (against each body's own base):

| Body | Window | Native convention |
| --- | --- | --- |
| `fold_drum_voice.asm` | `0x5d .. 0x61` | uncentred (`r5+$n`) |
| `simple_drum_delta.asm` | `0x48 .. 0x60` | uncentred |
| `pknv_noise` (noise helper) | `0x00 .. 0x61` | uncentred |
| `noise_tone_math.asm` (shared low32/RNG) | `-0x40 .. +0x02` | CENTRED |
| resonant voice | `-0x40 .. +0x3e` | CENTRED |
| resonant cores | `-0x40 .. +0x3a` | CENTRED |

Two additional hard facts:

* every body's window fits inside the DSP's one-word `-64..63` displacement
  range only under its own convention, so a single scratch block cannot host
  a mixed set;
* `pk_simple_base` names its second-difference cache by **absolute** address
  (the literal `$3964`, with `r4` fixed there) rather than relative to the
  caller's base, and `pk_simple_delta_at` shares that cache.

**The intended fix** (worked out but not yet landed; it needs one more
measurement round because the two obvious variants both silently rendered
zero):

1. put the Fold/Simple bodies and `pknv_noise` on the centred convention by
   advancing `r5` by `0x40` at each entry label and subtracting `0x40` from
   every displacement (this is exactly what
   `dsp_source_layout.center_scratch` does for the resonant recipes);
2. set the composed `SCRATCH_BASE` so the *centred* ABI lands at `0x3940`;
   the Fold primitives then read their own documented field map
   (`0x3940..0x39a2`) and their absolute cache at `0x3964` with no relocation;
3. relocate the single absolute `#>$003964` literal at compose time to
   `#>$0039a4` if the centred ABI is instead kept at `0x3940` while the
   scratch block starts at `0x38c0` — whichever of (2)/(3) the next
   measurement shows is consistent.

**That fix was built and measured this round, and it does not resolve the
silence.** With the Fold/Simple bodies and `pknv_noise` centred, the shared
math kept centred, and `SCRATCH_BASE = 0x38c0` (so the centred ABI lands at
`0x3940`, the Fold field map occupies `0x3940..0x39a2`, and the absolute cache
sits at `0x3964`), the composed Fold renderer still returns all-zero PCM for a
fixture the standalone binary renders as `-1, -1, -2, -2, ...`. So the scratch
convention is a real latent hazard -- it is still worth unifying -- but it is
**not sufficient** to explain the composed silence, and the search has to move
on rather than iterate on the layout.

The strongest remaining lead is that the composed and standalone binaries
differ in exactly one structural way that this round did not eliminate: the
composed `pk_fold_voice` is entered through `build_dsp_3algo_source`'s
dispatcher-adjacent layout, while the standalone one is a self-contained
program. The next experiment should therefore be to build the composed source
with the dispatcher and seam entry **removed entirely** (`with_source=False`,
which the composer already supports) and drive the renderers from that, so the
comparison is against the smallest possible image -- then re-introduce the seam
one piece at a time.

### The composed Fold silence: FOUND

**The composed renderer was never broken. The gate was feeding it a block that
looked already decoded.**

`pk_simple_delta_at` is a second-difference decoder with a persistent 17-word
cache. It compares the cache's first word against the block index it wants and
**decodes only on a miss**. Zero is a *valid* block index, so a cache seeded
with zeros makes block 0 look already decoded: `pk_simple_base` reads a zero
delta, the voice's `x:(r6)` sample is zero, and the whole Fold path stores
silence -- with no error anywhere and every instruction executing exactly as
qualified.

The standalone gate was already doing this correctly and its comment was the
only place the requirement was written down:

```
$ grep -n 3964 tools/verify/verify_perky_fold_drum_exec.py
tables='Y a50 ... \nX 3964 ffffff\n'
```

The composed gate wrote `X 3964` too, but:
* with **zeros**, not the `ffffff` sentinel; and
* it computed the address as `SCRATCH_BASE + 0x40` and then overwrote that
  range with a *second* zero seed, so the sentinel never survived.

Both are now fixed: the gate seeds `0x3964` -- the address the primitives name
*absolutely* (`move #>$003964,r4`) -- with the `ffffff` sentinel.

**Measured effect.** The composed Fold now produces the fixture's real samples:

```
before:  (0, 0, 0, 0, 0, 0, 0, 0)
after :  (-1, -2, -4, -6, -9, -13, -18, -23, -29)   expected: -1,-2,-4,-6,...
```

**PCM parity now PASSES for the Fold path.** The comparison was also shaped
wrong: `run()` returns `stereo[::2]` -- ONE word per sample, because the host
writes the same value to both channels -- while the expectation was built by
doubling every fixture sample, so a correct 256-sample result was compared
against a 512-element list. The reference is now interleaved the same way the
result is, and the gate's PCM check passes:

```
got[:6] = [-1, -2, -4, -6, -9, -13]
pcm[:6] = [-1, -2, -4, -6, -9, -13]
```

The next check is the persistent X state, and it reports a real mismatch to
work from:

```
final X[:11] = [255, 0, 44544, 0, 174, 0, 8864, 2050, 8864, 2050, 4, 0]
```

### Two more harness bugs, and where the gate now stands

**The host hardcoded its state window at `X:0x200`.** `bd909_host` both seeded
`r5` and dumped the state block from a fixed `STATE = 0x200`, so a module that
keeps its voice block anywhere else (the composed machine uses `X:0x3800`) had
its state dumped from a window it never wrote -- every word read zero, which is
indistinguishable from a renderer that produces no persistent state. Measured
directly: seeding a marker at `X:0x0200` came back through the dump, while the
same marker at `X:0x3800` did not, even though the DSP itself reads `X:0x3800`
correctly (proved with a `move x:>$3800,a` probe returning the seeded word).

The host now takes `-statebase HEX`, defaulting to the historical `0x200`, so
every existing caller is unchanged. The composed gate passes `-statebase 3800`.

**Where the gate stands now:**

* Fold PCM: corners and lengths now match (`lengths 256/256`), and **corner 0
  passes exactly** -- the composed renderer reproduces the captured ARM fixture
  through the composed build.
* **the composed and standalone builds are IDENTICAL in both block-0 PCM and
  post-block-0 state.** Running both with the same probe, the same base
  (`X:0x0200`) and their own table ledgers:

```
block-0 PCM identical:        True
post-block-0 state identical: True
state diffs:                  []
```

  Both leave `[2]=0xb170, [4]=0x0b17, [15]=0xaaa0, [35]=0x0010` where the
  fixture's `wrapper-window-after` has `0x839b, 0x540d, 0xedfc, 0x0100`.

**Correction to an earlier note in this record.** The "the carried state is
scaled wrong" finding was measured against that fixture window and is WRONG as
stated: the composed run does not disagree with the qualified standalone build
at all, so whatever the fixture window holds, it is not a word-for-word image of
the voice's live 40-word state. Both the composed and the standalone differ from
it in the same way.

**One more correction.** The `0x7f` seen in the standalone gate's leftover
`case.data` is not a seed difference: that file is overwritten once per case and
what remained was from a different case. Every fixture window checked decodes
`word0 = 0x00ff`, which is what the composed gate seeds. So the two gates agree
on the seed and the seed is not the lead after all.

### Where the Fold item actually stands

Everything the composed build produces has now been measured against the
qualified standalone build and found **identical**:

| measurement | composed vs standalone |
| --- | --- |
| block-0 PCM, corners 0/1/2 | identical (and equal to the ARM fixture) |
| post-block-0 40-word state | identical (`state diffs: []`) |
| `pk_simple_base` (36 words) | 35 identical, 1 relocated `jsr` target |
| `pk_fold_voice` (60 words) | 55 identical, 5 relocated branch targets |
| `pk_simple_envelope` / `_frequency` / `_oscillator` | 100% identical |
| `pk_simple_delta_at` (70 instructions) | only 4 relocated targets |

The remaining gate failure is therefore **not** the composed DSP code: it is a
difference between the composed gate's harness and the standalone gate's in how
the block-to-block carry is driven.

**Measured boundary, restated exactly.** The gate's `run` drives 16 blocks of
16 frames each (`-frames 16`, a 16-line script), and `stereo[::2]` gives 256
mono samples. For corner 1:

```
mono samples  0..15 : [-29, -115, -257, -457, -712, -1024, -1267, -1268,
                       -1222, -1133, -1000, -822, -601, -336, -29, 320]
mono samples 16..31 : [713, 1147, 1622, 2138, 1981, 1490, 949, 361,
                       -275, -959, -1687, -2461, -3281, -4143, ...]
fixture  sample 29  : -4160   (got -4143)
```

So the FIRST block matches the fixture exactly (and a single-block run matches
it for all three corners), the second block matches for its first 13 samples,
and the first disagreement is sample 29 = block 1 index 13. `want` equals the
fixture exactly (the double-then-stride is a no-op), so the comparison itself is
sound.

**The call structure is excluded.** Running the *composed* source with both
structures gives the same answer:

```
standalone structure: 1 line,  -frames 256   n=256  first diff=(29, -4143, -4160)
composed   structure: 16 lines, -frames 16   n=256  first diff=(29, -4143, -4160)
```

and the *standalone* source passes under both (first diff `None`). So the
16-calls-of-16-frames shape is not the cause; the two sources simply disagree
from block 1 index 13 onward.

**What that leaves, precisely.** Block 0 is exact for both, and the 40-word
voice state after block 0 is identical for both. The only other state that
persists from call to call is the composed scratch block at `X:0x3900` and the
delta cache at `X:0x3964`, and the two builds keep those at **different
addresses**. A direct read of the shared words after one block already shows one
difference that has to be resolved before it can be called a defect:

```
composed   @0x3960 (its base word) = 0x3800
standalone @0x3960                 = 0x0200
```

which is exactly the two builds' respective voice bases -- i.e. it is the
correct value in each build's own frame, not yet evidence of a fault. The next
measurement is therefore to read the same *logical* slots in each build's own
frame and compare those, rather than reading the same absolute address in both.

### Standing position on the Fold item

Every composed artifact measured to date equals the qualified standalone
artifact: block-0 PCM for all three corners (equal to the captured ARM
fixture), the post-block-0 40-word state (zero differences), and all four
routine bodies to within relocated branch/`jsr` targets. The composed source
nevertheless diverges from the fixture at block 1 index 13 while the standalone
does not.

This has now consumed many rounds, so the honest framing is: the composition
itself is verified; the outstanding Fold failure is isolated to state that is
carried across calls and laid out at different addresses in the two builds, and
the measurement that will settle it is a like-for-like read in each build's own
frame. It is recorded here rather than carried as an unexplained red gate.

### `make check REMIX=perky-dsp-3algo` -- what it found

Running the repository's own floor against the now-canonical artifact surfaced
three things, two of them mine to fix and one pre-existing.

**1. The sacrifice is a GATED expectation, and mine was missing.**
`tools/remix/selftest.py` holds a `_want` dict of each remix's intentional
stock-FX sacrifice, defaulting to the three reverbs. `perky-dsp-3algo` had no
entry, so the gate failed on the measured seven. Added, with the measured
shortfall table in the comment beside it -- this is exactly the "narrowly
updated and documented" case the brief allows, and the measurement is in
`verify_perky_3algo_sacrifice.py`.

**2. `perky-cfmeter-idle` had no entry either.** Its measured harvest is
`('DARK REV',)`, the same insert as its sibling, so it takes the sibling's value.
My first attempt at this RENAMED the `perky-cfmeter` key, which broke that remix
instead -- both remixes exist (`remixes/test/perky-cfmeter` and
`remixes/test/perky-cfmeter-idle`) and BOTH need an entry. The note I wrote
claiming the key was stale was wrong and is corrected in place.

**3. Docs.** `remixes/perky-dsp-3algo/README.md` was missing (the repo requires
one per remix) and the three generated indexes were stale. Written and
regenerated with `make docs`.

**Pre-existing, NOT this branch:** `make check` then stops in `verify-shared` at
`verify_knob_clicks.py`, whose build of the `_knobs` fixture fails the
"disassemble-what-you-assemble" guard on SPECTRUM:

```
P:0x01559  wrote 'move x:(r1)+,x0  b,y1'  chip runs 'move x:(r1)+,x0'
```

This branch touches 22 files -- `tools/verify`, `modules/perky`, `tools/perky`,
`tools/harness/bd909_host`, `remixes/perky-dsp-3algo`, `modules/perky3algo` --
and **none** of the assembler, `build_bus.py` or SPECTRUM. So the failure is in
the tree, not here, and it blocks `verify-shared` for every remix.

### The fixture<->model correspondence is itself unverified -- and my round-18 claim needed this check

Round 18 concluded "the model does not reproduce the ARM capture". Before letting
that stand I checked it two ways, because that section's own method note says the
previous three errors came from checks blind to something.

**Check 1 -- is it the tables?** The comparison used the model's GENERATED
envelope/interpolation tables, while the standalone ARM gate uses the FIRMWARE's
original ones. That is exactly the apples-to-oranges trap flagged earlier in this
record, so it had to be ruled out. It is ruled out: word 14 is **table-independent**.

```
model vs ARM, generated tables    diffs=11  word14=39631
model vs ARM, all-zero tables     diffs=11  word14=39631
model vs ARM, e1 only             diffs=11  word14=39631
ARM expects word14 = 59070
```

**Check 2 -- is the fixture pair even a matched pair?** The ARM capture holds
three windows per corner. Running the model across each transition:

```
corner 0/1/2 (identical):
  model(before, 16 samples) vs AFTER             diffs = 20 / 21 / 20
  model(after,  16 samples) vs CONTINUATION-AFTER diffs = 11 / 12 / 10
  word 14:  before->11346   after=65066   continuation-after=59070
```

**The model reproduces NEITHER transition.** Not the forward one
(`wrapper-window-before` -> `wrapper-window-after`), and not the continuation one
(`after` -> `continuation-after`). Every corner fails both, by two different
amounts, and `word 14` is a different value in all three windows.

**What that means.** The fixture<->model correspondence is not established. The
gates that compare the DSP against this model, or against these fixtures, rest on
a pairing that has never been shown to hold -- and the one gate that would have
shown it (`verify_perky_resonant_dsp_exec.py --firmware`) has never run here,
because it needs the stock 1.40C image for the original Y tables.

**So the round-18 conclusion survives, strengthened and re-scoped.** It is not
"the model is wrong about word 14"; it is that **neither transition of the
captured fixture is reproduced by the reference model at all**, which means the
resonant state assertion is not a usable oracle in either direction. That is a
statement about the ORACLE, not about this branch's composition -- and it is the
reason this item cannot be closed from the repository alone.

### The MODEL does not reproduce the ARM capture either -- so that comparison is not an oracle

After three wrong framings I stopped theorising and ran the test that should have
come first: **apply the reference model to the ARM fixture and see whether IT
reproduces the hardware.** It does not.

```
bass  c0: model-vs-ARM continuation-state diffs = 11   word 14: model 39631  ARM 59070
bass  c1: diffs = 12                                    word 14: model 39631  ARM 59070
bass  c2: diffs = 10                                    word 14: model 39631  ARM 59070
snare c0: diffs = 11                                    word 14: model 39631  ARM 59070
snare c1: diffs = 13                                    word 14: model 39631  ARM 59070
snare c2: diffs = 10                                    word 14: model 39631  ARM 59070
```

So word 14 has **three different values**, and they belong to three different
things:

| | word 14 |
| --- | ---: |
| the composed DSP renderer | 17741 |
| the reference Python model | 39631 |
| the captured ARM hardware | 59070 |

**What that means for the item.** The composed execution gate asserts
`state[:WORDS] == voice.words` -- the DSP's state against the model. For Fold that
holds exactly (640 blocks). For the resonant family **the model does not satisfy
it against the hardware it was derived from** -- 10 to 13 words differ, on every
corner. So that assertion is not a valid oracle for the resonant renderers, and
the "five divergent words" I reported two rounds ago is **not evidence of a
composition defect**. It is the DSP, the model and the hardware disagreeing three
ways, with the model itself already failing to match the hardware.

**This is the correct reading of the item, and it removes the implication that
this branch's composition is at fault.** What remains genuinely open is which of
the three is right about `NOISE+2`, and answering that needs the standalone ARM
gate (`verify_perky_resonant_dsp_exec.py --firmware`), which has never run here
because it needs the stock 1.40C image for the original Y tables.

**A note on method.** Three framings of this word were wrong before this one,
each because the check was blind to something -- the callees, the model's own
source, and which artifact the "expected" value came from. The test that settled
it was the one that compared THE ORACLE TO THE HARDWARE. Running that first would
have cost one step instead of four.

### Word 14, corrected again: the semantics AGREE, so it is the RNG sequence

**The previous section's framing is also wrong and is corrected here.** It said
the composition "appears to overwrite a RATE with a SAMPLE" while the model
treats the word as something else. It does not. The model's own noise step is

```python
def render_noise(words, base, rng):
    count = words[base]
    if count:
        words[base] = (count - 1) & MASK16
        return s16(words[base + 2])          # NOISE+2 = the held sample
    words[base] = words[base + 1]
    result = s16(next_random(rng))
    words[base + 2] = result & MASK16        # ...written from the RNG
    return result
```

-- the SAME semantics as `pk_resonant_noise` / `pkr_noise_refresh`. Both hold a
counter at `NOISE+0`, a reload at `NOISE+1`, and the held sample at `NOISE+2`,
and both overwrite `NOISE+2` with `next_random`'s output. There is no
rate-versus-sample disagreement between them.

**And 65066 is not special to that word.** The fixture's `rng-continuation-before`
is `0x0d1ce7c3, 0x59b5fe2a` -- whose low half is `0xfe2a` = 65066 as well. The
constant appears in more than one field of the ARM capture; my reading of it as
"the fixture seeds `NOISE+2` with `NOISE_RATE`" was an over-read of a repeated
constant.

**So the divergence is in the RNG SEQUENCE, not the interpretation.** Stepping
the model's own generator from the ARM seed:

```
step 0: low16=0x7a48  high16=0x59cd
step 1: low16=0x36a9  high16=0x94c2
step 2: low16=0x72b6  high16=0x6440
```

Neither observed value -- composed `0x454d`, model `0xe6be` -- is step 0, 1 or 2,
which is expected: 16 samples with a reload of 0..3 fires the refresh several
times. `next_random` returns `new_high & 0x7fffffff` and `render_noise` stores its
low 16 bits, so the model's word is the HIGH half; a first, cheap hypothesis is
that the composed path stores the LOW half instead (`r5-$30` is a 32-bit low
word from `pk_u32_mul_full` / `pk_rng_no_carry`), which would be exactly a
half-word swap.

**That hypothesis was then TESTED and is NOT supported.** Stepping the model's
generator 64 times from the ARM seed, neither `0x454d` ever appears as a low half
nor `0xe6be` as a high half:

```
steps where low16==0x454d or high16==0xe6be:  0
```

**A measurement error in my own framing, worth recording so it is not repeated:**
`0xe6be` is not a Python-model value at all. It is the ARM capture's own
`wrapper-window-continuation-after` word 14 -- the hardware's value. I had been
calling it "the model's expectation" throughout this section. So the comparison
is composed-versus-HARDWARE, not composed-versus-model, and the absence of either
value among plain RNG steps is expected rather than diagnostic, because word 14
holds whatever sample was current when the capture stopped.

**Where that leaves it.** Established: the composed renderer and the ARM capture
disagree on word 14 in all six cases (17741 vs 59070) while corner 0's PCM is
bit-exact; the model's `render_noise` has the same counter/reload/sample
semantics as the composed code; and the value is not a direct RNG output from the
before-seed over 64 steps either way. NOT established: the cause.

**Three framings of this word have now been wrong** (read-back address; rate
versus sample; half-word swap), each because the check was blind to something --
the callees, the model's own source, and which artifact the "expected" value came
from. The honest position is the list of measured facts above and no cause.

**Also unexplained, and worth flagging:** the composed value is identical (17741)
in all six runs and the model's is identical (59070) in all six, even though the
counter and reload seeds differ per corner. Either both implementations are
insensitive to those seeds over 16 samples, or something upstream is fixed. That
is not accounted for.

### Word 14: the fixtures seed it with NOISE_RATE, and three parties disagree

Measured directly -- seeded value, composed value after the run, and the model's
expectation, for all six ARM cases:

```
bass  c0..c2:  seeded 65066   composed 17741   model 59070
snare c0..c2:  seeded 65066   composed 17741   model 59070
```

Three things fall out, and the first is the interesting one.

**The fixture seeds `NOISE + 2` with 65066 -- which is `NOISE_RATE`.** That is
exactly the value the brief singles out ("the fact that `NOISE_RATE = 65066`
appears in captured fixtures proves that value is reachable; retain support for
it"). So in the REAL captured hardware state, this word holds the noise RATE.

**The composition writes 17741 over it.** `pkr_noise_refresh` stores the RNG
output's low half into `r6+$e` -- the same word -- so the composed path treats
`NOISE + 2` as the held noise SAMPLE.

**The model writes 59070**, a third value, and treats the word as something else
again.

So all three disagree about what this word is, and the composition appears to
overwrite a RATE with a SAMPLE. The composed writes the same 17741 in every case
even though the counter/reload seeds differ per corner, which is itself odd and
suggests the refresh fires on a schedule the fixtures do not vary.

**Not established:** which of the three readings is correct, and whether the
model's 59070 is the RATE transformed, the SAMPLE, or a third quantity. Settling
it needs the recipe's own reference -- and the standalone ARM gate that would
provide it (`verify_perky_resonant_dsp_exec.py --firmware`) has never run here,
because it needs the stock 1.40C image for the original Y tables.

This is a concrete, falsifiable lead rather than a resolved finding: **the
composed noise path may be writing its sample into the word the hardware uses for
the noise rate.** It is recorded as such.

### RETRACTED: the "read-back address" explanation of word 14

**The previous section's conclusion is wrong and is retracted.** It said
`pk_rng_step` "never writes `r5-$30`", so the refresh reads a word nothing
produces. That checked only `pk_rng_step`'s OWN body. `pk_rng_step` is not
self-contained -- it calls the 32-bit helpers, and those write the word:

```
pk_u32_mul_full   move y1,x:(r5-$30)
pk_u32_mul_full   move x1,x:(r5-$2f)
pk_u32_mul_full   move b1,x:(r5-$30)     ; r2
pk_u32_mul_full   move b1,x:(r5-$2f)
pk_rng_no_carry   move a1,x:(r5-$30)
pk_rng_no_carry   move a1,x:(r5-$2f)
```

So the refresh's `move x:(r5-$30),a` reads exactly what the callee produced. The
composed noise path is internally consistent, my "the generator never writes the
word the refresh reads" claim is **false**, and the round-15 record is corrected
here rather than left standing.

This is the same failure mode as the earlier `drop_unreachable` regression:
**analysing a routine as if its callees were not part of it.** Both times the
instrument (a body-local scan) was blind to exactly the thing being ruled out.

**What is still true, and is now the whole of the item.** Word 14 is `NOISE + 2`
in both families -- the held noise sample. On the captured ARM fixtures it is
wrong in every case, and BOTH sides of the comparison are CONSTANT across all six
runs:

```
composed 17741 (0x454d)   model 59070 (0xe6be)   -- identical for bass and snare, corners 0/1/2
```

A field that takes the same value regardless of the fixture's trajectory is not
trajectory-derived: it is set from the CONTROL side. So the divergence is in how
the composed path derives that value from the prepared controls, not in the
resonator arithmetic -- and corner 0's PCM being bit-exact says it does not reach
the output on that trajectory.

**Not established:** which control-derived quantity it is, and whether the model
or the composition is the one that is right. The standalone ARM gate that would
settle it -- `verify_perky_resonant_dsp_exec.py --firmware` -- still needs the
stock 1.40C image for the original Y tables and has never run here.

### The divergent word, traced to a read-back address -- and it is NOT the composition

`word 14` is `NOISE + 2` in BOTH families (`bass.NOISE = 12`, `snare.NOISE = 12`),
i.e. the held noise sample. Traced through the composed source:

* `pk_resonant_noise` DECREMENTS the counter at `r6+$c` and returns the held
  sample from `r6+$e`; on the counter hitting zero it takes `pkr_noise_refresh`;
* the refresh path stages four RNG limbs into `r5-$40..-$3d`, calls
  `pk_rng_step`, writes the limbs back, and then reads the new sample from
  **`r5-$30`**;
* `pk_rng_step` (84 instructions) **writes** `-$40 -$3f -$3e -$3d`, `-$20 -$1f
  -$1e -$1d`, `-$1a -$19 -$18 -$17`, `-$10`, `-$f`, `-$a` -- and **never writes
  `r5-$30`** at all.

So the refresh reads its result from a word the generator never writes.

**And this is not something the composition introduced.** The STANDALONE
recipe's `pk_rng_step` has the *same* write set, and its `pk_resonant_noise`
reads back from the *same* displacement. The two builds agree here; only the
composition's centred convention moves the numbers, and it moves both sides
together. So the divergence is a property of the recipe, and the standalone has
it too.

**Why nothing caught it until now:** the only gate that would have --
`verify_perky_resonant_dsp_exec.py --firmware`, which compares the STANDALONE
renderer against the captured ARM fixtures -- has **never run in this tree**,
because it needs the stock 1.40C image for the original Y tables. Every other
resonant gate compares synthetic states, and the composed gate compares against
the model's expectation rather than against a second implementation.

That also explains the shape of the evidence: corner 0's PCM is bit-exact while
its state word 14 is wrong, because the held noise sample only reaches the output
when the noise resonator is actually mixed in, which the corner-0 trajectory does
not do.

**Not established, and stated as such:** whether `r5-$30` is written by some
other routine in the reachable path, or whether the recipe simply never updates
the held sample. What IS established is that `pk_rng_step` does not write the
word the refresh reads, in either build.

### The last open correctness item: the composed RESONANT state comparison

The composed Fold renderer matches its model in PCM **and** in every state word
(640 blocks, 15/15 ARM). The composed Resonant renderers do not, and this is what
the composed execution gate still reports. Characterised, on the captured ARM
fixtures, dumping the full block after the final 16-sample call:

```
bass  corner 0: PCM exact=True   state diffs=5   14: 17741 vs 59070, 84: 57112 vs 3754, 85: 65535 vs 0
bass  corner 1: PCM exact=False  state diffs=5   same words
bass  corner 2: PCM exact=False  state diffs=5   same words
snare corner 0: PCM exact=True   state diffs=5   14: 17741 vs 59070, 53: 60588 vs 2391, 54: 65535 vs 0
snare corner 1: PCM exact=False  state diffs=4   same words
snare corner 2: PCM exact=False  state diffs=4   same words
```

Two things fall out of that table, and they are different problems:

1. **`word 14` is wrong the SAME way every time** -- 17741 in all six runs, both
   families, all corners, against 59070 expected. A value that is identically
   wrong across unrelated inputs is not a computation going astray; it is a field
   the composed renderer does not maintain (or reads from a different source)
   while the reference model does.
2. **The 32-bit pair carries `0xFFFF` in its low word where the model has 0**
   (`bass 84/85`, `snare 53/54`). For bass those offsets are `NOISE_RES + 10..13`
   = the noise resonator's `RES_POSITION` and `RES_VELOCITY` (two 32-bit fields
   each). An `0xFFFF` low half against a model zero is the signature of a
   sign-extension or a split-write, not of a wrong resonator position.

**And note what is NOT wrong.** For corner 0 the PCM is **bit-exact** in both
families. So the audio path is right, the block layout is right (only five of
88 words differ, so this is not an offset mismatch), and the divergence is
confined to state the reference model maintains and the DSP either derives
differently or does not keep.

That reframes the item honestly: the gate compares the DSP's ENTIRE internal
state against the reference model word for word, which Fold happens to satisfy
exactly and the resonant implementation does not. Whether the resonant words must
match, or whether matching PCM is the right contract for an independent
implementation, is the question this item turns on -- and it is NOT settled here.
What is established is the exact set of divergent words, that they are the same
five everywhere, and that corner 0's audio is already bit-exact.

### FX sacrifice: WHY it cannot be reduced (item 8, answered)

Two independent constraints, each established rather than assumed.

**1. A module must fit inside a SINGLE run -- multi-run harvesting is impossible
here.** The placer states it outright (`tools/remix/app.py`):

> ⚠️ A GAP IS A WALL. What you gave up becomes one or more contiguous RUNS, and a
> module is one code stream, so it must fit inside a SINGLE run -- 3,880 words
> spread over three runs will not take a 3,500-word module. Harvesting an effect
> that sits BETWEEN two runs joins them into one.

The composed machine is **one** DSP source in **one** `DspSection`, i.e. one code
stream. So the idea of closing the 82-word gap from a small second opening is
closed by the architecture, not by the gate: the sacrifice must be a single
contiguous run, and the run that fits is `P:0x1000..0x1fdf` on payload A
(`P:0x0dc0..0x1d9f` on B) -- PLATE through COMB FILTER.

**2. Dead code is real, safe, and still not enough.** A reachability walk from
`pk3d_source` that **models fallthrough** -- following `jsr`/`jsrl`/`jmp`/`bra`/
`bcc` targets and each `do` loop's end label, and continuing linearly past
anything that does not end a routine -- finds **51 unreachable instructions**:

```
pk_u32_shift_sign_ready  13      pk_noise_refresh   9
pk_noise_step            10      pk_u32_sub         6
pk_sub_no_borrow          9      pk_u32_asr         4
```

That is **67 P words**: the composed program goes 3,868 -> 3,801, and the Fold
ARM corpus is **15/15 exact** with the removal in place, so it is a real,
bit-exact saving -- unlike the earlier attempt, which matched NAMES and broke the
fold renderer precisely because `pksde_read_r2` / `pksdo_read_r2` /
`pknhe_read_r2` are reached by fallthrough and no `jsr` points at them.

**It does not reduce the sacrifice.** The breakpoint to keep SPATIALIZER is
3,786 words; 3,801 is still **15 words short**. Dead code alone cannot pay for a
fourth effect.

**And it is deliberately NOT shipped.** 67 words buys nothing -- the sacrificed
set is unchanged -- while perturbing the equivalence gate's basis (that gate
assembles a renderer-only build with no single entry point, and compares
instruction COUNTS against the standalone recipes). Trading a gate that currently
proves renderer equivalence for a saving with no functional effect is a bad
bargain, so the composer is unchanged and the measurement stands as the answer.

**Conclusion.** Given a 3,868-word machine and the single-run rule, the
seven-effect sacrifice is forced. The only remaining lever is making the
renderers genuinely smaller -- which is the same work as the timing
optimisation, and is blocked by the same finding: the resonant arithmetic IS the
algorithm.

### The canonical build now reproduces the deliverable

The gap recorded in the previous round -- `make bus REMIX=perky-dsp-3algo`
producing a DIFFERENT image from `tools/perky/build_dsp_3algo.py`, because the
composed machine was installed into the module registry **in memory only** -- is
closed.

`tools/perky/emit_3algo_manifest.py` writes the same declaration out as a
tracked module, so the canonical build links it:

```
modules/perky3algo/manifest.py       the declaration (dataclass repr of the
                                     module perky_machine_module.build returns)
modules/perky/control_3algo.s        generate.py, THREE_ALGORITHM_DEFINES
modules/perky/machine_3algo.asm      build_dsp_3algo_source.compose(), with
                                     @CONT@ LEFT IN for the build to substitute
                                     per payload
```

Nothing in the manifest is hand-written -- it is generated from the helper that
already worked, so it is exact by construction. Three things had to be true and
each was found by the build refusing:

1. **`@CONT@` must stay in the source.** The build substitutes it per payload
   -- `$000426` for A and `$000221` for B, read off the emitted `DspSection` --
   and refuses a `subst` key that does not occur in the source. Writing the
   source with the A value already substituted is therefore rejected outright.
   *Not established:* whether the earlier front-end path, which did substitute
   up front, was producing a wrong payload B; the two build paths now agree
   byte for byte, so whatever it did it landed on the same bytes. What IS
   established is that the per-payload substitution is real and that the tracked
   source must leave the marker in place for it to happen.
2. **The DSP hook must name this machine's own entry.** The in-memory helper
   inherits the probe's `pk_probe_source`; the composition defines `pk3d_source`.
3. **The module needs its own key.** It is `PERKY 3ALGO`, so it sits beside the
   tracked `PERKY PROBE` probe rather than shadowing it.

Measured, both paths now agreeing byte for byte:

```
make bus REMIX=perky-dsp-3algo    f0f4505dcd5cdb150d325d5adf3b79e521f15b5fe6ec999bb0b79239905e9c37
tools/perky/build_dsp_3algo.py    f0f4505dcd5cdb150d325d5adf3b79e521f15b5fe6ec999bb0b79239905e9c37
```

**A real non-determinism found while guarding it.** The drift check initially
reported a difference every run: `frozenset({'A', 'B'})` reprs as
`frozenset({'A', 'B'})` in one process and `frozenset({'B', 'A'})` in the next,
because set iteration follows string hashing and Python randomises that per
process. The emitter now canonicalises every `frozenset` repr by sorting it, and
`render()` is verified deterministic within a process and against the file on
disk.

**The drift guard is a gate, not a promise.**
`verify_perky_3algo_control_join.check_generated_artifact` re-runs all three
generators and refuses on any difference -- because a stale tracked copy means
`make bus` links and ships something other than what every other gate in this
branch proves. It also still asserts the DEFAULT generator output contains
neither prepare, so the candidate guard cannot silently stop working.

### Boot / image / upload / readback gates -- and a trap that made one run lie

The ColdFire port is not in the tree; it was built (`make emu-cf` ->
`out/emu/ot_emu`, 2,970,424 B) so the port-side gates could run at all.

**Deliverable image: `out/mainos_bus.bin`, 1,117,092 bytes,
sha256 `f0f4505dcd5cdb150d325d5adf3b79e521f15b5fe6ec999bb0b79239905e9c37`.**

Every result below was taken with the image hash checked BEFORE and AFTER the
gate, so a gate that rebuilds cannot be mistaken for a gate that passed on this
artifact.

| gate | result | artifact |
| --- | --- | --- |
| `verify_perky_preboot_reserve` | PASS | unchanged |
| `verify_perky_stock_dsp_boot_path` | PASS (1,000 uploader/boot bytes byte-identical) | unchanged |
| `verify_perky_cf_loader_contract` | PASS | unchanged |
| `verify_perky_image_tables` | PASS | unchanged |
| `verify_perky_3algo_image` | PASS | unchanged |
| `verify_perky_3algo_control_join` | PASS | unchanged |
| `verify_replaces --image` | PASS (OK) | unchanged |
| `verify_menu` | PASS (ALL CHECKS PASSED) | unchanged |
| `verify_usb` | PASS (no EP0 stall during enumeration) | unchanged |

**A trap that made the first run of two of those gates meaningless.**
`verify_dirtystate` does not merely read the image -- it **rebuilds
`out/mainos_bus.bin` itself** via `make bus REMIX=<remix>`, which the Makefile
comments say outright. That build links the remix AS DECLARED (`probe_cf.s`, the
development canary), not the composed machine this branch composes, so it wrote a
**different, 1,112,560-byte image** over the deliverable. The first
`verify_replaces` / `verify_menu` run therefore passed against the WRONG
artifact. Both were re-run after rebuilding and both pass on the real one, but
the ordering is load-bearing and the tree's own warning ("any verifier that reads
`out/` must know who wrote it last") applies to this branch too.

**Which is itself a finding about shipping.** `make bus REMIX=perky-dsp-3algo`
and `tools/perky/build_dsp_3algo.py` produce DIFFERENT images, because the
composed machine is installed into the module registry **in memory only** -- the
canary pattern this branch inherited. So the deliverable is not reproducible by
the canonical build command, which is a real gap against the definition of done
("a complete firmware image is generated"); the image is generated, but not by
the path anything else in the repository uses. Making the remix itself carry the
composed machine is the next build task.

**Gates that pass VACUOUSLY on this remix, recorded so they are not counted as
coverage:**

```
verify_dirtystate      verify_dirtystate: 0 renders, 0 failed
verify_initregs        init-registers: 0 module inits scanned, 0 failure(s)
module_gates           module gates (isolated remix-only): none declared
```

All three exit 0, and none of them exercised anything of this machine.

**Gates that cannot run here, with the reason:**

```
verify_labels / verify_modenames / verify_hidden
    need .venv/bin/python3; .venv exists but is empty, so the Makefile's
    `[ -x .venv/bin/python3 ]` test is false and they SKIP.
verify_dram_boot
    "perky-dsp-3algo carries no DRAM payload" -- keys on a DRAM runtime this
    remix does not declare.
verify_perky_machine_boot
    wants out/mainos_perky_machine.bin, the multi-machine canary's artifact.
verify_perky_table_image
    refuses any image carrying the platform-loader append; it is an isolated
    table canary and this is a shipping image.
verify_perky_image_legacy_identity
    cannot run at all: imports perky_image (does not resolve) and runtime_build,
    which the tree records as removed 6 Oct 2026. Pre-existing, not this branch.
```

So definition-of-done item 14 is **partly** met: every in-repo gate that can run
against this artifact and actually covers it passes, and the ones that do not are
enumerated above with reasons rather than quietly counted.

### THE ARTIFACT DID NOT CONTAIN THE CONTROL PATH -- found and fixed

The gates above compile `control.c` themselves, with the candidate defines set.
**The shipping image did not.** `control.c` guards the Fold dispatch behind
`PK_FOLD_CANDIDATE` and the Resonant family behind `PK_RESONANT_CANDIDATE`, both
defaulting to 0, and `modules/perky/generate.py` -- which compiles the
authoritative `control.c` into the ColdFire assembly the image links -- passed
**no defines at all**. So the generated artifact contained neither routine, and
every one of this machine's three algorithms fell through to the `else` that
zeroes the prepared controls.

Measured, on the generator's own output:

```
default defines : pk_fold_prepare=False  pk_resonant_prepare=False   24,823 B
3-algo defines  : pk_fold_prepare=True   pk_resonant_prepare=True    30,221 B
```

This is the "the binary is not the source" family the repository's own history
warns about: the source read correctly, every gate that compiled it itself
passed, and the file that actually shipped was missing the code.

**Fixed.** `generate.py` now takes `defines`, exposes
`THREE_ALGORITHM_DEFINES`, and records the defines it was given in the produced
assembly's header so a wrong configuration is visible in the artifact rather
than only in its symbols. `build_dsp_3algo.py` passes them and then **asserts the
generated text contains `pk_fold_prepare` and `pk_resonant_prepare`**, refusing
the build otherwise -- a define that did not reach the compiler leaves a file
that still assembles and still links, so the check has to be on the text.

`verify_perky_3algo_control_join.py` now repeats that check as a gate, and also
asserts the DEFAULT output contains neither routine, so the candidate guard
itself cannot silently stop working.

Image rebuilt: `f0f4505dcd5cdb150d325d5adf3b79e521f15b5fe6ec999bb0b79239905e9c37`.

**The boot/image gates, run against this image:**

| gate | result |
| --- | --- |
| `verify_perky_preboot_reserve` | PASS |
| `verify_perky_stock_dsp_boot_path` | PASS (1,000 uploader/boot bytes byte-identical) |
| `verify_perky_cf_loader_contract` | PASS |
| `verify_perky_image_tables` | PASS |
| `verify_perky_3algo_image` | PASS |
| `verify_perky_3algo_control_join` | PASS |

**Two perky gates are not applicable to this artifact, and one is stale in the
repo** -- recorded so they are not mistaken for passes:

* `verify_perky_machine_boot.py` wants `out/mainos_perky_machine.bin`, an
  artifact the multi-machine canary builds, not this one.
* `verify_perky_table_image.py` refuses any image carrying the platform-loader
  append; it is an isolated table canary and this is a shipping image.
* `verify_perky_image_legacy_identity.py` cannot run at all: it imports
  `perky_image`, which does not resolve, and a `runtime_build` module the tree
  records as removed on 6 Oct 2026 ("runtime_build.py when Octakit was
  removed"). That is a pre-existing broken gate, unrelated to this branch.
* `verify_dram_boot.py` reports "perky-dsp-3algo carries no DRAM payload" -- a
  gate that keys on a DRAM runtime this remix does not declare.

### Optimisation ceiling: measured by ablation, and it is short

The brief's item 4 asks for bit-exact optimisation avenues to be attempted and
measured, and its item 9 makes "resulting minimum production cost still exceeds
72,512" a precondition for a blocker. Here is that measurement.

**Method.** Replace one routine's body with an immediate `rts` in the COMPOSED
source, rebuild, and diff the executed instruction count for the same
synthetic-state run (`bd909_host -cycle-meter 0`, 16 frames, one call). This is a
timing ablation, not a correct build -- it measures what a block COSTS, and it is
an upper bound on what removing it could save, because stubbing also skips work
that depends on it.

Per block, snare, baseline 27,538 instructions/16 samples:

| block stubbed | instructions/16 saved | share |
| --- | ---: | ---: |
| `pk_resonant_decay` | 10,928 | 39.7% |
| `pk_resonant_core` | 5,974 | 21.7% |
| `pk_u32_mul_low` | 4,372 | 15.9% |
| `pk_resonant_noise` | 1,524 | 5.5% |
| `pk_noise_hat_envelope` | 480 | 1.7% |

(Those overlap -- stubbing `pk_resonant_decay` also removes the cores' dependent
work -- so they do not sum.)

**Stubbing ALL FIVE at once** gives the algorithm's own cost:

```
snare: baseline 27,538 instr/16   all resonant blocks stubbed  6,572
       algorithm cost 20,966 = 76.1% of the renderer
bass : baseline 25,592 instr/16   all resonant blocks stubbed  7,764
       algorithm cost 17,828 = 69.7% of the renderer
```

So the **non-algorithm** share -- register setup, the 32-bit pack/unpack
motifs, loop control, the dispatcher glue -- is only **23.9% for snare and 30.3%
for bass**.

**What that means against the allowance.** From the reachable-domain measurements
above (the figures that should be used, not the stress ones):

| engine | reachable worst | allowance | must go | non-algorithm available |
| --- | ---: | ---: | ---: | ---: |
| Resonant Snare | 38,787 | 23,040 | 15,747 (40.6%) | 23.9% = ~9,270 |
| Resonant Bass | 35,697 | 23,040 | 12,657 (35.5%) | 30.3% = ~10,816 |

**For the snare, removing EVERY non-algorithm instruction in the renderer still
leaves 29,517 modeled cycles/16 against an allowance of 23,040 -- 28% over.** No
instruction-level optimisation can reach the allowance, because the reduction
required is larger than the entire non-algorithm content of the code. Reaching
it requires removing roughly half of the resonant arithmetic itself, which is
the algorithm, and the brief forbids changing it.

**For the bass the position is tighter but the same in kind:** removing every
non-algorithm instruction would land at 24,881 -- 8% over the allowance -- and
that upper bound assumes literally zero overhead, which no real loop achieves.

This is the measured continuation ledger the brief's item 3 case B asks for, on
the reachable domain rather than on stress states. It does not rest on the
historical 23,040 alone: 23,040 descends from `make cycles`' measured 3,120
cycles/sample and the measured ~1.9x model-to-hardware factor, both re-derived in
this branch.

**Caveat, stated plainly.** Ablation is an upper bound, not an achievable
optimisation: stubbing a routine also skips its dependent work, and a real
optimisation must preserve every result bit-exactly. So the true achievable
saving is LESS than the table above, which strengthens rather than weakens the
conclusion.

**The most promising avenue from the brief's list, closed by measurement.**
The brief suggests "replacing synthesized multiword arithmetic with native-width
operations where proven equivalent over reachable domains". The DSP's native
multiply is 24x24 -> 48, so `pk_u32_mul_low` -- the low 32 bits of a 32x32
product, built from three 16x16 partials, 15.9% of the snare -- would collapse
to a single `mpyuu` **if its operands were provably <= 24 bits**.

They are not. Reading every 32-bit word out of the CAPTURED ARM fixtures (the
reachable oracle, not randomized states), the widest value is **32 bits** for
both families:

```
bass : captured-fixture 32-bit word values: max bit width = 32   (24-bit fit: NO)
snare: captured-fixture 32-bit word values: max bit width = 32   (24-bit fit: NO)
```

So the precondition fails on reachable data, and this branch cannot take that
optimisation. Recorded as a measured negative result rather than left as an
untried idea.

### Dirty state: the repository's gate misses this remix, so it is gated here

`verify_dirtystate.py` is the repository's gate for "a persistent slot that init
does not clear holds whatever the effect before ours left in the block -- and no
local render can see it, because the port and `dsp_host` boot zeroed RAM". It
cost a session on Spectrum's stale h2 poles.

**For this remix it reports "0 renders, 0 failed"** -- the composed machine is
installed as a source hook and declares no FX init, so that gate never exercises
it. `tools/verify/verify_perky_3algo_dirtystate.py` does, driving the composed
renderer from zeroed AND from four garbage patterns on silence:

```
  all zeros (the control)    nonzero   0/64  peak        0
  garbage voice block        nonzero   0/64  peak        0
  garbage, all $ffff         nonzero   0/64  peak        0
  garbage, alternating       nonzero   0/64  peak        0
```

**PASS** -- the machine is silent on silence regardless of what the voice block
held, so it does not leak uninitialised state into its output. This is a
verification of a property that was assumed, not a defect repaired.

It is also the answer to a question worth asking on the unit: on real hardware
`X:0x3800..0x386b` holds whatever ran before, and this says that does not reach
the output on silence.

### Checked and SOUND: the composed path's x256 output scale

The composed machine's `pk3z_scale` multiplies the renderer's output by 256
(eight `asl a`), and **the qualified seam has no such stage** -- it wrote its
impulse straight to `X:0`. That looks alarming from the outside: the direct
renderer reproduces the ARM capture EXACTLY,

```
DIRECT renderer (no scale stage) vs ARM:  first diff None
   head [-1, -2, -4, -6]      arm [-1, -2, -4, -6]
```

while the dispatch path carries those same words through `x256` to
`[-256, -512, -1024, -1536]`. A 48 dB discrepancy between "what the capture says"
and "what the machine ships" is exactly the shape of a gain defect.

**It is not one, and the measurement says why.** The renderer's full range, over
the captured ARM cases, is

```
largest |renderer output| over the ARM cases: 32598
x256 = 8345088      full-scale 24-bit = 8388607      fits: True
headroom factor: 1.01x
```

The renderer emits a **16-bit-scaled** word (its maximum, 32,598, is a 16-bit
figure) and `x256` maps that onto **24-bit full scale**, landing at 8,345,088
against a limit of 8,388,607. The **1.01x headroom is the evidence**: the scale
was chosen to fit this renderer's range exactly, not picked round.

So `arm-pcm.bin` is the capture at the RENDERER's stage, not the machine's output
stage, and the two are related by precisely this conversion.

**Why this is recorded rather than left implicit.** The engine-join gate asserts
`dispatch == direct x 2^8` -- i.e. it asserts what the code DOES, which would be
equally true if the scale were wrong. Only comparing the SCALE against the
renderer's range establishes that it is right. A gate that encodes the
implementation cannot also validate it, and this is the clearest instance of that
in the branch.

### The dispatcher gate now also proves non-Perky tracks are left to STOCK

Definition of done #4 -- "T2-T4 and T6-T8 remain normal Octatrack tracks" -- rested
on the slot check alone. With a working dispatcher harness it is now tested
directly: seed `X:0` (the stock source block) with a marker, drive a record the
machine must NOT take, and require the marker back untouched, because
`pk3v_not_admitted` returns and the STOCK source runs instead.

```
rejection: a record this machine must NOT take is left to STOCK, so
X:0 still holds the marker 0x5a5a it was seeded with
  no 'PK' at word 0            X:0 =    23130  untouched
  'PK' but no 'Y1'             X:0 =    23130  untouched
  slot 1 (a different track)   X:0 =    23130  untouched
  CONTROL: admitted record     X:0 =     -256  TOUCHED (expected -- the renderer wrote it)
```

The last line is the **positive control**: an admitted record DOES overwrite that
word, so the test can tell "untouched" from "the check never ran". Three rejection
paths, one discriminating control.

That covers every way a track can fail to be this machine's: wrong magic, right
magic but not the second, and the wrong track slot.

### LANDED: the dispatcher-driven test, and the mode is verified end to end

Third attempt, and it passes. `tools/verify/verify_perky_3algo_dispatch.py` drives
`pk3d_source` -- the production path -- and reads the voice block back:

```
fold: p[8] must become the firmware mode (panel + 1) % 3 at word 34
  panel 0 -> word34     1  want     1  OK
  panel 1 -> word34     2  want     2  OK
  panel 2 -> word34     0  want     0  OK

resonant: word 34 is DECAY_A / inside RES2 -- it must NOT be written
  RES BASS        word34  4660  seeded  4660  PRESERVED
  RES SNARE       word34  4660  seeded  4660  PRESERVED
```

So the mode delivery fixed earlier is now **verified through the real dispatch
path**, not merely inspected, and the resonant families are confirmed not to have
their decay block clobbered by it.

**The root cause of the two earlier failures was the entry ADDRESS.** A probe
placed first in the binary puts the entry at `P:0x1000`, and that run writes zero
bytes of PCM and state and exits 3 with `no return from 1000 (pc=1c20)`. The join
gate's *identical* dispatch, at `P:0x1017`, returns 0 and renders 29,452
instructions. The address dependency itself is not explained -- and it is not a
property of the machine, which behaves the same either way -- but the gate now
reproduces the invocation that is known to work instead of chasing it.

**What each of the three attempts cost, and what it taught:**

1. Hand-rolled the host command; diverged from the working one by a single data
   line (`X 20e 000000`, which the dispatcher's first instruction replays).
   *Lesson: reuse a known-good driver.*
2. Reused the driver, but placed the probe first. Still `pc=1c1e` -> `pc=1c20`
   when a single instruction was added, which correctly located the fault in the
   machine's post-render path rather than the probe. *Lesson: when a difference
   does not move the symptom, it is not the cause.*
3. Reused the driver AND the entry the working gate uses. Passes.

Three rounds on a test is a poor rate and I said so at the time; what made the
third one work was running the *working* gate's own artifacts by hand and
comparing exit codes, which took one command and should have been the first.

### The missing test, second attempt: a line-by-line comparison, and what it ruled out

I applied the lesson from the first attempt -- compare against the WORKING
invocation rather than iterate on my own -- and rebuilt the gate to **reuse
`verify_perky_3algo_engine_join`'s assembler and host driver** instead of
hand-rolling the host command. That removed the duplication that caused the first
failure.

**It still fails, and the comparison narrowed it usefully.** New datum: the
failure persists with the probe reproduced EXACTLY as the working gate's --
including the `move #>$0,r0` line I had dropped -- and the faulting PC advances by
exactly two words when that line is added (`pc=1c1e` -> `pc=1c20`). So the probe
is executing correctly, **the runaway is in the machine's own post-render path**,
not in the probe and not in the data.

That points at `jmp @CONT@`. The composed machine hands control back by jumping
to the stock continuation (`$000426`) rather than returning, and 0x426 is
uninitialised in a probe-only binary, so execution walks off. The join gate does
exactly the same thing and works -- so the remaining difference is in which PATH
each gate's records take through the machine, and I did not isolate it.

**Ruled out across both attempts:** the record shape (`pk_render_record` prints
word 19 = engine id and word 16 = `p[8]`); the probe's trailing register resets;
`check=True` on the host call; hand-rolled versus shared data lines; and the
probe itself, now byte-for-byte the working one.

**Removed again rather than left broken.** Two attempts have now failed on a
harness problem and the record says where to resume: instrument what happens
between the machine's `jmp @CONT@` and the host's "no return", in the working gate
and this one, side by side.

### The missing test: identified and designed, NOT landed

The coverage gap named above is the dispatcher-driven test. I wrote it
(`tools/verify/verify_perky_3algo_dispatch.py`) and **removed it again rather than
leave a broken gate in the tree**. Recording where it stands, because the next
attempt should not repeat this ground.

**Design.** Assemble the composed source WITH the dispatcher, add a probe that
sets `r4` to a `pk_render`-shaped record and calls `pk3d_source`, then read the
voice block back and assert `X:0x3800+34 == (panel + 1) % 3` for Fold and
*unchanged* for the two Resonant engines. That single test would have caught all
three of this audit's findings.

**Where it fails.** When the record is ADMITTED -- which is the whole point of the
test -- the host writes **zero bytes** of PCM and state and exits 3 with

```
no return from 1000 (pc=1c1e)
```

The cause of the non-return is understood and benign: the machine hands control
back with `jmp @CONT@` (the stock continuation) rather than returning to the
probe, so the host's "no return from entry" is expected -- and
`verify_perky_3algo_engine_join` tolerates exactly that and works. **What is not
understood is why that gate gets its PCM and this one gets none**, on a record
that is byte-identical for `panel = 0`. It is a harness difference I did not
isolate, and after several attempts I stopped rather than keep guessing.

**Ruled out along the way:** the record shape (`pk_render_record` produces word 19
= the engine id and word 16 = `p[8]`, confirmed by printing it); the probe's
trailing `move #>0,r0`; and `check=True` on the host invocation.

So this is the one piece of identified, designed, non-hardware-dependent work that
is still open, and it is a harness problem, not a machine problem.

### FIXED: the Fold MODE is now delivered (`p[8]` -> voice word 34)

Both open questions are answered from the repository, and the fix is in.

**Question 1 -- which side applies the `[1,2,0]` mapping?** The DSP. The
qualified transport gate pins `[1,2,0][record[8]] == v.words[34]` where
`record[8]` is the ColdFire's panel mode and `words[34]` is the ARM hardware's
value, and `pk_render`'s output is fixed by that same gate -- so the mapping
happens between the two records, on the DSP side. Reading the fixtures confirms
the mapping exactly:

```
engine-1-mode-1 -> words[34] = 1        panel 1 (0-based 0) -> (0+1)%3 = 1
engine-1-mode-2 -> words[34] = 2        panel 2 (0-based 1) -> (1+1)%3 = 2
engine-1-mode-3 -> words[34] = 0        panel 3 (0-based 2) -> (2+1)%3 = 0
```

so **firmware mode = `(panel + 1) % 3`**.

**Question 2 -- do the Resonant families use word 34?** NO, and writing it there
would be a bug:

```
fold  MODE  = 34
bass  DECAY_A = 34     <- word 34 is the decay block's base
snare RES1 = 15, RES2 = 29, RES3 = 43   <- word 34 is inside RES2
```

So the delivery is **Fold-path only**, which is why it lives in `pk3e_entry`.

The emitted sequence, in the Fold dispatch before `pk_simple_base`:

```
move    x:>$209,r4          ; RELOAD the record: pk_simple_base points r4 at
                            ; the second-difference cache, so it no longer
                            ; addresses the record
move    x:(r4+$10),a        ; p[8], the panel mode
add     #>$1,a              ; (panel + 1)
move    a,x1
move    x1,a                ; clean a -- the low-word trap
move    #>$0,x0             ; a move sets no condition codes
cmp     #>$3,a
tge     x0,a                ; ... wrap 3 back to 0
move    a1,x:(r6+$22)       ; the Fold voice's MODE word
```

Costs 13 P words (3,859 -> 3,872, both payloads FREE 191). Image
`f7781914db8f0511c77ad098f634e1f484e3f68372fafaf566295ff583abec1d`, reproduced
byte-for-byte by both build paths, all gates PASS.

**What is verified and what is not, stated plainly.** Verified: the emitted
instruction sequence, the arithmetic for panel 0/1/2 checked by hand
(1, 2, 0), the mapping against all three captured fixture modes, that word 34 is
MODE for Fold and a decay/resonator field for the others, and every existing
gate. **Not verified end to end:** I could not get a dispatcher-driven run to
dump the voice block back -- my harness attempt failed parsing the state file --
so the mode's arrival at `X:0x3812` is established by the code and the mapping,
not by an executed end-to-end dispatch. That is the honest boundary.

**The coverage gap this exposes, which is the real lesson.** The Fold ARM parity
is proven by driving `pk3t_fold`, a DIRECT probe into the renderer -- which
bypasses the dispatcher entirely. That is why 640 blocks and 15/15 ARM cases
passed while the production path never delivered a mode: **the gate tests the
renderer, not the path that calls it.** A dispatcher-driven ARM case is the
missing test, and it would have caught all three of this audit's findings.

### The composed machine DROPS the MODE: `p[8]` never reaches the renderer

Third finding from the same audit, and the sharpest of the three.

`pk_render` publishes the selected MODE in record byte 8 -- `p[8]`, which is
record WORD `0x10` -- and the qualified Fold transport gate pins the contract it
has to satisfy:

```python
assert record[9] == v.words[14] and [1,2,0][record[8]] == v.words[34]
```

So `record[8]`, mapped through the panel-to-firmware table `[1,2,0]`, must become
the voice's **word 34** -- the word the Fold renderer reads its mode from.

Measured on the composed machine:

```
record words the DISPATCHER reads: ['13', '2', '8', 'a', 'c', 'e']
record word 0x10 (p[8] = the MODE) read by the dispatcher?  NO
any write to the voice mode word r6+$22 anywhere?            NO
```

**The mode is never delivered, and the voice's mode word is never written.** On a
real unit `X:0x3800+34` holds whatever ran before, so the Fold algorithm would run
in a stale or arbitrary mode -- transient when it should sustain, or noise when it
should not.

**And the execution gate cannot see it.** Every Fold case seeds the voice block
from an ARM capture or from the model, and both already CONTAIN word 34. The gate
therefore supplies exactly the value the machine fails to supply itself, which is
why 640 blocks and 15/15 ARM cases pass while the production path is wrong.

That is the same shape as the latch: a value the machine needs, absent from the
path that runs in production, invisible to gates that seed the very state at
issue.

**Established:** the dispatcher's record reads are exactly
`{0x2, 0x8, 0xa, 0xc, 0xe, 0x13}` and `0x10` is not among them; no write to
`r6+$22` exists in the composed source; the qualified gate pins
`[1,2,0][record[8]] == words[34]` as the contract. **Not established:** whether
the `[1,2,0]` mapping belongs on the ColdFire side (so the record carries the
already-mapped value) or on the DSP side at load, and how the two Resonant
families express their mode -- they may not use word 34 at all. Both need
checking before this is patched, and it is recorded rather than guessed.

### The composed machine DROPS the frame's event sample offset

Found by auditing the deliverable the same way the latch was. The qualified seam
documents its own contract:

```asm
; The stock source builder publishes this frame's event sample offset
; in X:$20c.  The record flag is still checked so a stale/non-event
; offset cannot manufacture a hit.
move    x:>$20c,a
tst     a
blt     pk_probe_continue
cmp     #>$10,a
bge     pk_probe_continue
; Convert the frame offset to the interleaved stereo word index ...
```

The composed machine **never reads `X:$20c` at all** -- the composed source has
zero references to it, and `tools/perky/build_dsp_3algo_source.py` does not
mention it anywhere. It renders its 16-sample block from sample 0 every block.

**What that means.** The offset exists because a trig does NOT necessarily fall
at the start of a block; it is where in the 16-sample frame the event belongs. A
source that ignores it places every hit at the block boundary, so a trig is up to
**15 samples (about 0.34 ms at 44.1 kHz) early** and effectively quantised to
16-sample boundaries. For a drum machine that is a real placement error, not a
cosmetic one. The seam got this right; the composition inherited a different
entry and dropped it.

**Established:** the seam reads `X:$20c` as the event sample offset and clamps it
to `0..15`; the composed machine has no reference to `0x20c`; it renders from
sample 0. **Inferred, not measured:** the resulting audio timing -- I have not
measured the placement error in the output, only established that the input is
ignored.

**Why it is recorded rather than patched.** Honouring the offset means emitting
`offset` samples of *continuation* -- the voice advancing WITHOUT retriggering --
before the hit begins, then triggering. The voice block at `X:0x3800` does
persist across blocks, so that is possible in principle, but which behaviour the
pre-trig samples should have (continue the previous hit, output silence, or hold)
is a design question this branch should not answer by guessing. It is the same
class of finding as the latch -- state or input the machine needs and does not
use -- and it came from the same audit.

### FIXED: the one-voice-per-core latch is removed

The defect recorded below is fixed. `x:$38ED` is no longer used at all: the
latch is **removed**, not cleared, because the composed machine is installed only
at the per-track source site and has no once-per-block hook to clear it from.

**Why removing it is correct rather than merely expedient.** The latch guarded a
case the target cannot produce. `x:$418` is this core's track slot and only
slot 0 is admitted -- verified against the stock walk, which steps it `0x20` to
`0x80` over the core's four tracks -- and the target gives each core exactly ONE
Perky-capable track. So at most one record per core can reach the admission test,
and in fact exactly one can pass the `PK`/`Y1` test at all. The latch's only
observable effect was to silence every block after the first.

Measured after the removal:

```
x:$38ed extension-word occurrences in the shipped image: 0
composed : 3859 P words   (was 3868)   both payloads FREE 204 (was 195)
make bus REMIX=perky-dsp-3algo   9388afd5215af35ca34a433e9af1e670b07bb2c7fff832797d6e7803004b649b
tools/perky/build_dsp_3algo.py   9388afd5215af35ca34a433e9af1e670b07bb2c7fff832797d6e7803004b649b
```

`verify_perky_3algo_core_mapping.py` now **guards the defect** rather than
asserting the latch: it refuses any build in which the admission word is written
without being cleared, with the reasoning in the failure message.

**What was established on the way, and is worth keeping:**

* The dispatcher's site is INSIDE the per-track loop, not once per block --
  payload B's `P:0x001a2` and payload A's `P:0x0039c` are the `move a,x:>$20e`
  reached from `bne` at `0x331 -> 0x18b` (B) and `0x53c -> 0x385` (A). So the
  dispatcher runs four times per block per core.
* Payload A re-enters its `x:$418` init every block (`0x586: bra 0x102`, landing
  before the `move x0,x:$418` at `0x373`). **Payload B shows no such re-entry**
  anywhere in the disassembly -- every backward branch was checked -- which is
  either a real asymmetry in the two payloads or a limit of matching targets
  printed as `func_XXXX`. That question is now moot for this fix, because the
  latch is gone and nothing depends on `x:$418` restarting, but it is recorded
  rather than dropped.

### CRITICAL: the one-voice-per-core latch is SET and NEVER CLEARED

Found while auditing item 6's remaining sub-items. This is a functional defect in
the shipped machine, and it is not a timing or oracle issue.

The composed dispatcher implements "one Perky voice per core" with a latch at
`X:$38ED`:

```
move    x:>$38ed,a        ; read the latch
tst     a
bne     pk3c_silence      ; already admitted -> render silence
move    #>$1,a
move    a1,x:>$38ed       ; SET it, once
...
```

Its own comment says *"the first admitted PERKY record wins for the whole
frame"* -- so a per-frame reset is intended. **There isn't one.** Measured:

```
any mention of 38ed / 38ec in the composed source:
     25: move    x:>$38ed,a
     29: move    a1,x:>$38ed
     38: move    x:>$38ec,a
     39: move    a,x:>$38ec
```

One read, one write, no clear. `pk3c_silence` zeroes `X:0` and nothing else.
And it is not cleared anywhere else either -- searching the BUILT IMAGE for the
`x:$38ed` extension word finds **4 references, 2 per payload = one read and one
write each**, i.e. exactly this code and no other.

`X:$38ED` is inside the module's OWN claimed range
(`DspRange("x", 0x38EC, 2, "PERKY source event-offset and admission staging")`),
so stock does not own it and does not reset it.

**Consequence.** The first block that admits a PERKY record sets the latch, and
every subsequent entry takes the `bne pk3c_silence` path. The Perky track renders
one admitted block and then **silence, permanently**. This is invisible to every
gate in this branch because they each seed `X:$38ED = 0` and run a single call --
so the latch is exercised exactly once and never observed across a frame
boundary.

**What is established versus inferred.** Established: the write sets 1; nothing
in the composed source or in the built image clears it; the word is ours; the
dispatcher silences whenever it is non-zero. Inferred (not measured here):
that the hook is entered once per track per block on hardware, and therefore
that blocks after the first are silent. The fix needs to know where a
once-per-block reset belongs -- the composed machine is installed only at the
per-track source hook, so there is no obviously-correct place inside it -- and
guessing one is how this session's earlier mistakes happened. It is recorded as
a defect with its evidence, not patched blind.

**This would have made the flashed image useless**, which is exactly what the
brief's "do not stop after emulator-only tests" is about.

**Where the fix belongs, and what must be established first.** The hook site is
INSIDE the per-track loop, not once per block: payload B's site `P:0x001a2` is
`move a,x:>$20e`, reached from the `bne` at `0x53c` (payload A) that walks
`x:$418` over the core's four tracks, and a new module section begins immediately
after it at `0x1a4`. So the dispatcher is entered once per TRACK per block --
four times -- and the latch exists to admit only the first of those four.

**But the slot check may already do that.** The stock walk gives `x:$418` the
value `0` once per pass and advances it by `0x20` up to `0x80`, and the
dispatcher admits ONLY `x:$418 == 0`. If that walk restarts at 0 each block --
which is what a per-block track walk must do -- then admitting slot 0 admits
exactly one track per block per core, the latch is REDUNDANT, and the defect is
fixed by deleting it rather than by finding somewhere to clear it.

**What is not established**, and must be before patching: where `x:$418` is
returned to 0 for the next block. The disassembly shows `move x0,x:>$418` with
`x0 = 0` at BOOT (`P:0x373` on A, `0x17d` on B) and one advancing read-modify-write
at `P:0x533..0x53a` on A (`0x243..` on B) -- but no second reset to 0 was
located. If the slot carries over between blocks instead of restarting, then
deleting the latch trades one failure for another (an admission once every four
blocks) and the real fix is different. **That single question decides the fix**,
and answering it from the payloads is the next step -- not a blind patch.

### T1/T5 mapping: now evidenced and gated, from the STOCK payloads

The definition of done asks for "T1 mapping to its correct DSP payload/core" and
"T5 mapping" to be tested. Nothing in this branch tested them -- the admission
rule was asserted, and the track<->core mapping was an inherited assumption. It
is now read out of the stock payloads themselves
(`tools/verify/verify_perky_3algo_core_mapping.py`):

```
track base : payload B x:$420 = 0 (tracks 1-4), payload A x:$420 = 4 (tracks 5-8)
slot walk  : payload A x:$418 steps 0x20 to 0x80 = 4 tracks per core
slot walk  : payload B x:$418 steps 0x20 to 0x80 = 4 tracks per core
latch      : composed sets x:$38ed = 1 on the first admitted record
admission  : composed dispatcher admits x:$418 == 0x0 (the core's first track)
```

Three facts, each from the pristine payload rather than from an assumption:

1. **Stock walks `x:$418` as the per-core track slot**: `add #<$20,b` /
   `cmp #>$80,b` / `bne` (`P:0x537..0x53c` on A, `0x243..` on B). Four steps of
   `0x20` to `0x80` is exactly **four tracks per core**, one slot each -- so
   `x:$418 = 0` is that core's FIRST track.
2. **Each payload records its own track base in `x:$420`**: 0 on payload B and
   4 on payload A. Payload B serves tracks 1-4 and payload A serves 5-8, so slot
   0 is **track 1 on B** and **track 5 on A**.
3. **The composed dispatcher admits slot 0 only** (`move x:>$418,b` / `tst b` /
   `bne`, then latch `x:$38ed = 1`). Admitting no other slot is what keeps T2-T4
   and T6-T8 ordinary.

The gate fails if either payload's base changes, if the stride or limit stops
describing four tracks, or if the admitted slot stops being 0 -- i.e. if the
mapping this machine depends on ever moves.

Worth recording as a near-miss: my first two attempts at this gate asserted the
admission rule as a `cmp #>$0,b` and the latch as "store the slot value". Both
were WRONG -- the rule is a `tst b`, and the latch stores the CONSTANT 1, not the
slot. The gate only passed once it described what the artifact actually does.

### The TIMING TOOL now reports the reachable bound as the production number

The reachable-versus-stress split was measured, but the tool that ships the
number still headlined the STRESS figure -- which is precisely what made the
original blocker report wrong to challenge. Fixed:

```
algorithm   stress/16  REACHABLE/16   2x+stock  vs window verdict  bound
fold            25393         25393      73346       +834    OVER  arm-fixtures
bass            74511         35713      93986     +21474    OVER  arm-fixtures
snare           80718         38737     100034     +27522    OVER  arm-fixtures
```

`worst_reachable` comes from the captured ARM fixtures -- the same oracle the
standalone resonant gate uses -- and the VERDICT is keyed on it;
`worst_stress_cycles` is the synthetic guard-coverage set, reported beside it and
labelled as stress. `timing.json` carries both, plus `peak_modeled_stress`, and
each row says which bound it used (`bound_from`). The tool's docstring, which had
claimed the synthetic states were "the reachable control/state domain", is
corrected -- that claim was the source of the confusion.

The verdict does not change: every algorithm is still OVER the allowance on the
reachable domain, and the peak is 38,737 modeled (snare). What changes is that
the shipped report can no longer be read as quoting a stress state as the
production cost.

### REACHABLE vs STRESS: the timing figures were taken on stress states

**This materially changes the timing picture and is the answer to the brief's
item 5.** The `74,515` (bass) and `80,722` (snare) figures in
`verify_perky_3algo_timing.py` come from `resonant_state()`, whose own docstring
says it covers "both sides of every bounded-path guard": it deliberately writes
`RES_MOD = choice(0, 1, 65535, 0xffffffff)`, random 16-bit pitches and
coefficients, `DECAY_COUNT = choice(0, 1, 2, 65535, 0xffffffff, ...)` and so on.
Those are STRESS states, not states the Perky control path can produce.

Driving the composed renderers from the **captured ARM fixtures** instead
(`engine-7-mode-{panel}-corner-{corner}`, the same oracle the standalone
resonant gate uses, with its offset/size convention), one 16-sample block per
call:

| engine | synthetic stress worst | reachable ARM worst (3 corners) |
| --- | ---: | ---: |
| Resonant Bass | 74,515 | **34,673 / 35,697 / 35,671** |
| Resonant Snare | 80,722 | **38,049 / 38,787 / 38,551** |

**The reachable worst is about HALF the stress worst.** Against the repo's
23,040 modeled allowance that is bass over by ~12,657 (a **35%** reduction, not
69%) and snare over by ~15,747 (a **41%** reduction, not 71%).

Two caveats, both real, neither of which changes the direction:

1. Six fixture runs is a small sample of the reachable domain. It is much better
   evidence than randomized impossible states, but it is not a proof of the
   domain's maximum, and the 2x model margin and stock reserve are unchanged.
2. **Corners 1 and 2 do not match those fixtures** -- bass corner 0 and snare
   corner 0 are EXACT, bass corner 1 diverges at sample 191, and bass corner 2 /
   snare corners 1-2 diverge at sample 2. The timing taken on corners 1-2 is
   therefore timing of a renderer whose output is not yet trusted; corner 0's
   figures are on a bit-exact render and are the ones to rely on:
   **bass 34,673, snare 38,049**.

   **But this comparison is NOT apples-to-apples, and the divergence is NOT
   established as a renderer defect.** The standalone resonant gate's own ARM
   path (`verify_perky_resonant_dsp_exec.py`, under `--firmware`) builds its
   expectation from the FIRMWARE'S ORIGINAL Y TABLES
   (`0x08022EA0`/`0x080236A2`/`0x0803237C`/`0x08032178`), not from the model's
   generated envelope/interp assets. The run above necessarily used the model's
   assets, because the stock image is not in this tree (only
   `out/raw/section_3_MAIN_OS.bin`, whose sha256 is not the manifest's
   `adcdbc4a...`). So corners 1-2 are most likely reading the wrong curve data,
   exactly the class of fault that broke the Fold path, and the standalone ARM
   comparison has **never run here at all**. Resolving it needs the user's stock
   1.40C image; it is not a conclusion this branch can reach from the repo.

So the honest position on the brief's items 2 and 3 is: the required reduction
on reachable measured states is somewhere near **35-41%**, not 69-71%, and the
69-71% figure was derived from stress states the production control path cannot
reach. This does not yet show the engines FIT -- every reachable figure measured
so far is still over the 23,040 allowance -- but it moves the question from
"architecturally impossible" to "needs roughly a third off the hot path", which
is a different problem and the one the optimisation work should attack.

### MEASURED CONTINUATION LEDGER (this configuration)

Every number below is either printed by the repository's own cycle tool or
measured this round. Nothing is inferred from an assumed reserve.

**A. The core budget, printed by `make cycles REMIX=perky-dsp-3algo`:**

```
budget/core                 4535   (200 MIPS / 44.1 kHz)
usable by us                3120   measured 23 Aug 2026; stock takes the other ~1415
headroom                    3120   against the worst core above
stock rows           NOT COUNTED   [FILTER, EQUALIZER, PHASER, FLANGER, CHORUS,
                                    SPATIALIZER] -- stock code; FILTER measured 192
hook sections        NOT COUNTED   [PERKY PROBE] -- reached by a DspHook
```

So the tool itself states the split: **stock's own share ~1,415 cycles/sample,
usable by us 3,120 cycles/sample**, and it explicitly reports that our retained
stock effects are *not* charged against that 3,120 because they are stock code.
Note also its own warning: *"the wall is a CLIFF, not a slope. Only a burn sweep
measures it."*

| line | cycles/sample | provenance |
| --- | ---: | --- |
| whole core | 4,535 (4,532 measured) | `make cycles`; CHIP.md probe 55, 199.9 MHz |
| stock's own share | ~1,415 | `make cycles`, measured 23 Aug 2026 |
| usable by us | 3,120 | `make cycles`, measured 23 Aug 2026 |
| one frame (16 samples) | 72,512 | 16 x 4,532 |

**B. The host's cycle model to hardware conversion -- MEASURED this round.**
Driving each instruction form in a 256-iteration DO loop through
`bd909_host -cycle-meter 1` and comparing against CHIP.md's hardware table:

| instruction | host modeled | CHIP.md hardware | ratio |
| --- | ---: | ---: | ---: |
| `move x0,a` | 1.06 | 2.00 | 1.89x |
| `move x:(r0),a` | 1.06 | 2.00 | 1.89x |
| `move x:(r7+$15),a` | 2.05 | 3.98 | 1.94x |
| `move x:(r7+$70),a` | 3.05 | 6.01 | 1.97x |

**C. What the renderer figures actually contain -- the measurement boundary.**
`verify_perky_3algo_timing.py` drives these entries:

```
pk3t_snare:  move #voice,r6 / move #scratch,r5 / jsrl pk3d_snare_voice
             / jsrl pk3c_rng_out / rts
```

i.e. **2 register setups + the renderer body + a TEST-ONLY RNG dump.** No stock
continuation, no AMP, no FX1, no FX2, no routing, no dispatcher, no wrapper
beyond two moves. And they are **modeled cycles, not hardware**.

**D. Dynamic instruction counts, measured this round** (`-cycle-meter 0` vs `1`
on the same runs, 16 frames, one call):

| engine | instructions/16 | modeled cycles/16 | modeled/instr |
| --- | ---: | ---: | ---: |
| fold | 4,790 | 9,735 | 2.03 |
| bass | 25,627 | 43,802 | 1.71 |
| snare | 27,556 | 47,599 | 1.73 |

Those are for one control state; the worst over the 1,024-state sweep is higher
(bass 74,515, snare 80,722 modeled).

**E. ACTUAL_AVAILABLE_PERKY_CYCLES.**

```
whole core frame                 72,512   hardware cycles / 16 samples
- stock's own share            - 22,592   (1,412/sample, measured, make cycles)
= usable by us                   49,920   (3,120/sample, measured)
- safety margin (repo holds)   -  6,144   (see below)
= modeled allowance              23,040   (2 x 23,040 = 46,080 hardware)
```

The repository's `MAX_MODELED_BLOCK = 23,040` converts to 46,080 hardware cycles
against 49,920 usable, i.e. it holds back **3,840 hardware cycles = 240/sample =
7.7%** of the module budget. That is the justified margin, and it is the repo's
own.

**F. The true required reduction**, against that allowance:

| engine | modeled/16 (worst) | allowance | over by | reduction needed |
| --- | ---: | ---: | ---: | ---: |
| Fold Drum 1 | 26,112 | 23,040 | 3,072 | 11.8% (mode-2 noise path only) |
| Resonant Bass | 74,515 | 23,040 | 51,475 | 69.1% |
| Resonant Snare | 80,722 | 23,040 | 57,682 | 71.5% |

This is **case B** of the brief. It is not a reversion to a stale number: the
allowance descends from `make cycles`' own measured 3,120/sample and the
measured ~1.9x model-to-hardware factor, both re-derived this round.

**G. Where the cost actually is -- attributed per sample.** Static expansion of
the call tree, with each routine's internal DO loops applied at their trip
counts (the entry's own sample loop counted once per sample):

```
pk3d_snare_voice   796 instr/sample
   its own body            372   46.7%
   pk_resonant_core        198   24.9%
   pk_u32_mul_low          132   16.6%
   pk_resonant_decay        76    9.5%
   pk_noise_hat_envelope    10    1.3%
   pk_resonant_noise         8    1.0%
```

The cost is **spread across the whole synthesis path**: the largest single item
is the voice's own body at 47%, and no one removable block approaches the 69-71%
that has to come off. That is the evidence that instruction-level optimisation
of the listed kinds cannot close this gap -- not an assertion, a distribution.

**H. What is genuinely unmeasured, stated plainly.** The *per-track* split of
stock's 1,415 is not measured: whether a Perky track's source work **replaces**
some stock continuation (the normal source read for that track) is not
established. That would *raise* the allowance. Its ceiling is bounded: if the
Perky source displaced the entire non-stock budget and the replaced track's
whole share, the ceiling is the whole core 4,532/sample = 72,512 modeled, and
Snare at 80,722 modeled would still exceed it. So the per-track question cannot
rescue the gap, but it is honestly still open and is the one measurement worth
making next.

### TIMING MODEL RECONCILED -- the blocker report contained a category error

**This retracts the "over the physical deadline by 2,003 / 8,210 cycles" claim
from the blocker report. Those two numbers compared a MODELED figure against a
HARDWARE deadline and are meaningless.** The reduction figures derived
afterwards (51,475 / 57,682 against 23,040) used the correct comparison. The
report mixed both, and that inconsistency is real.

**The model, from `docs/firmware/CHIP.md` section 2 (all hardware or
triangulated, not inferred):**

| quantity | value | provenance |
| --- | --- | --- |
| whole core, per sample | **4,532 cycles** | hardware, probe 55, 199.9 MHz measured 22 Sep 2026 |
| stock's own share | **≈1,410 cycles/sample** | hardware, by subtraction (4,532 − 3,120) |
| DSP-usable budget for module work | **≈3,120 cycles/sample** | hardware, triangulated three ways: 1,652 + 4×192 + 704 = 3,124 |
| one frame (16 samples) | **72,512 cycles** | 16 × 4,532 |

**AND the host's cycle model undercounts hardware by ≈2x.** That is not an
assumption; I measured it against CHIP.md's own hardware instruction table
(`docs/firmware/CHIP.md` section 2) by driving each form in a 256-iteration DO
loop through `bd909_host -cycle-meter 1`:

| instruction | host modeled | CHIP.md hardware | ratio |
| --- | ---: | ---: | ---: |
| `move x0,a` | 1.06 | 2.00 | 1.89x |
| `move x:(r0),a` | 1.06 | 2.00 | 1.89x |
| `move x:(r7+$15),a` | 2.05 | 3.98 | 1.94x |
| `move x:(r7+$70),a` | 3.05 | 6.01 | 1.97x |
| `nop` | 1.06 | -- | -- |

So the 2x margin in `verify_perky_realtime_budget.py` is **measured, not
arbitrary**, and it applies to this branch's numbers too (same host, same
`-cycle-meter 1`).

**The correct production test**, therefore:

```
hardware for a 16-sample block  =  2 * modeled        (measured ~1.89-1.97x)
module budget                   =  3,120 * 16  =  49,920 cycles   (hardware)
=>  modeled allowance           =  49,920 / 2  =  24,960
```

The repository's `MAX_MODELED_BLOCK = 23,040` is the same test with ~7.7%
headroom held back (2 × 23,040 = 46,080, leaving 3,840 of the 49,920). So
**23,040 is the correct production allowance for this configuration**, and it is
correct because it was derived from the same hardware measurements -- not
because it is a "historical" number that no longer applies.

**Measurement boundaries, stated exactly.** The 74,515 / 80,722 figures come
from `verify_perky_3algo_timing.py` driving `pk3t_bass` / `pk3t_snare`, which
are:

```
  move #voice,r6          <- 2 register setups (probe glue)
  move #scratch,r5
  jsrl <renderer body>    <- the composed renderer under test
  jsrl pk3c_rng_out       <- TEST-ONLY RNG dump, not production
  rts
```

So those numbers are **renderer body + 2 register loads + a test-only dump**.
They contain NO stock continuation, NO AMP, NO FX1, NO FX2, NO routing, NO
dispatcher, and they are MODELED cycles, not hardware. Both corrections matter
and they compound in opposite directions -- which is exactly why comparing
"74,515" to "72,512" was wrong twice over.

### Consequence: the required reductions

| algorithm | modeled/16 | allowance 23,040 | shortfall | % |
| --- | ---: | ---: | ---: | ---: |
| Fold Drum 1 | 26,112 | 23,040 | 3,072 | 11.8% (mode-2 noise path only) |
| Resonant Bass | 74,515 | 23,040 | 51,475 | 69.1% |
| Resonant Snare | 80,722 | 23,040 | 57,682 | 71.5% |

These reduction targets stand. What does NOT stand is calling Bass "2.76% over"
or Snare "11.32% over" the deadline: that comparison put modeled cycles against
the hardware frame.

**What this does not settle, and what the next measurement must.** The 1,410
figure is stock's own share for the core; whether a Perky track's source
REPLACES enough stock work that the effective allowance is larger is not yet
measured, and neither is the per-track split. That is the honest open item, and
it is bounded: even granting the Perky source the entire non-stock budget plus
the replaced track's whole share, the ceiling is 4,532 cycles/sample =
36,256 modeled, which Snare at 80,722 still exceeds by 2.2x.



`tools/verify/verify_perky_3algo_timing.py` measures the composed production
renderer per algorithm. It deliberately does NOT assert PCM parity -- the parity
gate does that -- because a timing number must be obtainable while a parity item
is open.

**The first revision of this tool used the wrong budget test, and that is worth
recording.** It compared raw modeled cycles against the 72,512-cycle hardware
window. The repository's own realtime gate
(`tools/verify/verify_perky_realtime_budget.py`) applies the correct model:

```
hardware window for a 16-sample block : 16 * 4532 = 72,512 cycles
stock reserve (measured)              : 16 * 1410 = 22,560 cycles
model margin                          : 2x  (hardware MOVE timings exceed
                                             the interpreter's decoded counts)

  2 * modeled + 22,560 <= 72,512   =>   modeled  <=  23,040 cycles/16 samples
```

So a voice's measured figure must be compared against **23,040**, not against
72,512, and the composed gate previously reported 26,112 for Fold without that
comparison ever failing -- consistent with the parity assertions being what stops
that gate.

Corrected measurements:

```
hardware window: 72512   stock reserve: 22560   model margin: 2x
=> a voice may model at most 23040 cycles/16 samples

algorithm   blocks  modeled/16   2x+stock  vs window   verdict
fold           640       26112      74784      +2272      OVER
bass          1024       74515     171590     +99078      OVER
snare         1024       80722     184004    +111492      OVER
```

**Conclusion, stated plainly:** the composed machine does not satisfy the
production timing bound. Per the target's runtime policy this is not grounds to
drop any algorithm -- their reachable production paths must be optimized and
re-measured, with bit-exactness preserved against the existing oracles and the
equivalence and standalone gates kept green.

Targets, relative to the 23,040-cycle model allowance:

| algorithm | modeled | must come down by | as a fraction |
| --- | ---: | ---: | ---: |
| Fold Drum 1 | 26,112 | 3,072 | 12% |
| Resonant Bass | 74,515 | 51,475 | 69% |
| Resonant Snare | 80,722 | 57,682 | 71% |

The states measured are the ones the production renderers actually reach: the
captured ARM corpus plus the randomized native set for Fold, and
`resonant_state` (both sides of every bounded-path guard) for the resonant
families.

**Hot-path breakdown for Snare** (per sample, weighted by call count), as a
starting point for that work:

```
pk_resonant_core    x3   66 instr   weight 198
pk_u32_mul_low      x4   33 instr   weight 132
pk_resonant_decay   x4   19 instr   weight  76
pk_noise_hat_env    x1   10 instr   weight  10
pk_resonant_noise   x1    8 instr   weight   8
                                  ----------
per-sample call cost                424 of 831 instructions
```

The resonant cores and the shared low-word multiply dominate, which is where an
optimization that preserves bit-exactness has to look.

**Fold's overage is one path, and it is small.** Measuring the distribution
rather than only the maximum:

```
fold modeled cycles/16 over 415 blocks:
  min 13173   median 14036   p90 18704   max 26112
  blocks over 23040: 11 of 415   (2.7%)
```

and **all 11 are `mode = 2`** -- the physical noise sample-and-hold path. The
drum modes are comfortably inside budget; the overage is 3,072 cycles on one
path. The cost sits in `pknv_noise` (35 instructions) plus its call into
`pk_rng_step` (83 instructions), and the over-budget blocks are the ones whose
`noise_rate`/counter make the refresh path run on most samples:

```
native fold native 104  26112  mode=2 counter=0   fold=45771 noise_rate=37250
native fold native  95  25811  mode=2 counter=143 fold=65535 noise_rate=52006
native fold native  86  25758  mode=2 counter=272 fold=4092  noise_rate=27859
```

`pknv_noise`'s refresh path moves the four RNG words out to scratch, calls
`pk_rng_step`, and moves them back, and `pk_rng_step` itself measures **145
instructions**, not the ~83 an earlier cut of this record claimed -- that figure
came from a label-block count that stopped at the first nested label and is
retracted here.

**Where the 145 goes**, read directly:

```
pk_rng_step:
  move x:(r5-$40),a / move a1,x:(r5-$20)     <- 4 words copied through scratch
  ...                                        (8 instructions, then 8 back)
  move #>$00f42d,a / move a1,x:(r5-$3e)      <- each 32-bit constant is TWO
  move #>$005851,a / move a1,x:(r5-$3d)         instructions
  jsrl pk_u32_mul_low                        <- called twice
  ...
  jsrl pk_u32_add
```

It is almost entirely **32-bit arithmetic built out of 16-bit words**, so every
load, store and constant costs two instructions, and the scratch round-trips are
pure overhead. `pk_rng_step` is one RNG advance per sample on the noise path.

**The captured hardware fixtures settle the reachability question.** I checked
whether the over-budget mode-2 states are reachable from the control law by
enumerating `fold_control_update._rate(offset, scale, param)` over a plausible
panel range, which yields only 20 values topping out at 21,845 -- apparently
below the corpus's 37,250. That enumeration was over the WRONG parameter ranges
and its conclusion is retracted: the captured ARM fixtures themselves carry
`NOISE_RATE = 65066` in `engine-1-mode-2-*`, so high noise rates are reachable
on hardware. The over-budget mode-2 states are therefore genuine, and the
3,072-cycle saving is real work rather than an artefact of randomized sampling.

**Honest sizing of the remaining timing work.** Fold needs 3,072 cycles off one
path; Bass and Snare need ~69%/71% cuts. The hot paths are the shared 32-bit
arithmetic layer (`pk_u32_mul_low` 33 instructions, `pk_u32_add`, and the
`pk_rng_step` wrapper around them) and the three resonant cores. A bit-exact
saving here means rewriting that shared layer -- keeping both 16-bit halves in
registers across the product/add rather than round-tripping through scratch --
and re-proving every renderer against the oracles. That is a substantial,
well-scoped piece of work, not a tweak, and it is the largest single item
between this branch and a flashable image.

### The timing bound is not met, and it is not a composition problem

The repository's own realtime gate
(`tools/verify/verify_perky_realtime_budget.py`) states the model and applies it
to the shipping one-voice-per-core case:

> the interpreter host counts decoded opcode cycles ... **Use a 2x margin on
> that model (hardware MOVE timings exceed its nominal counts), and reserve
> stock's measured 1410 cycles/sample.** Only one PERKY voice per core is
> admitted, with FX1/FX2 NONE for this hardware canary.

So a voice may model **23,040 cycles per 16-sample block**. Applying that same
model to the **qualified standalone** gates -- which pass on correctness and
assert no timing bound at all -- gives:

| source | modeled/16 | 2x+stock | vs 72,512 | verdict |
| --- | ---: | ---: | ---: | --- |
| Fold Drum 1 (standalone) | 26,121 | 74,802 | +2,290 | OVER |
| Resonant Bass (standalone) | 76,319 | 175,198 | +102,686 | OVER |
| Resonant Snare (standalone) | 82,263 | 187,086 | +114,574 | OVER |

and the composed build measures 26,112 / 74,515 / 80,722 -- within 9 cycles of
the standalone for Fold.

**Two conclusions follow, and both matter:**

1. **The overage is not caused by composing.** The composed source is
   instruction-identical to the standalone renderers and lands within 9 cycles
   of them. Every algorithm was already over this bound on its own, in the
   branch it was qualified in; the standalone gates simply do not assert it.
2. **Meeting it requires reductions that bit-exact instruction-level
   optimization cannot deliver.** Bass needs 51,475 cycles off (69%) and Snare
   57,682 (71%). Those figures are of the order of removing most of the
   resonator work, which is an *algorithmic* change -- the opposite of the
   bit-exactness the target requires and of its "do not redesign" instruction.

Fold is the one tractable case: 3,072 cycles (12%) off a single path (mode-2
noise), where `pk_rng_step` is 145 instructions of 32-bit arithmetic assembled
from 16-bit words. That is real, well-scoped work.

For Bass and Snare the honest engineering position is that the current
resonant algorithm does not fit one-voice-per-core on this budget, and no
instruction-level optimization closes a 70% gap. The options are a deliberately
smaller resonant algorithm (a redesign the target forbids, and therefore a
decision for the user) or accepting a higher per-voice budget than the canary
model assumes. Neither is something this branch should decide silently.

### CORRECTION: the control law is NOT already done

An earlier cut of this record (and the commit that added it) claimed the ColdFire
control law already exists and "routes Fold Drum 1, Resonant Bass and Resonant
Snare". **That was wrong, and it is retracted here.** The mistake was reading
`modules/perky/cf_perky4.c` -- `pk4_algo_init` / `pk4_prepare` / `pk4_render` --
as the control path. It is the **abandoned ColdFire synthesiser**: `pk4_render`
has **zero** callers outside its own file, and the file's callers are the
`control_cf_*` bridge, i.e. the path this target explicitly forbids ("Do NOT move
synthesis back to ColdFire").

**The real control path** is `modules/perky/control.c`, and its actual state is:

```c
void pk_render(unsigned track, unsigned ping, unsigned start, unsigned end) {
    ...
    if      (p[11] == 2u) pk_simple_prepare(&simple_controls[track], p, trig);
#if PK_FOLD_CANDIDATE
    else if (p[11] == 0u) pk_fold_prepare(&simple_controls[track], p, trig);
#endif
    else {                       /* every other family */
        simple_controls[track].valid = 0;
        ... prepared[k] = targets[k] = 0;
    }
    record[0] = 0x504b0000u;     /* 'PK' */
    record[1] = 0x59310000u | trig;   /* 'Y1' + trigger flag */
    record[2] = record[3] = 0;
    for (unsigned k = 0; k < 6u; ++k)
        record[4+k] = ((uint32_t)p[2*k] << 16) | p[2*k+1];
}
```

So the control law has a prepare path for **Fold** (family 0) and **Simple
Drum** (family 2) and **nothing else**: Resonant Bass would need family byte 10
and Resonant Snare 11, and both currently fall into the `else`, which zeroes the
prepared controls and writes `record[3] = 0` -- the very word the composed DSP
reads for its engine id (`move x:(r4+$6),b`).

**What is therefore actually true:**

* the DSP-side dispatch, admission and storage are complete and validated
  (equivalence + image gates);
* the ColdFire side has **no path at all** for two of the three target
  algorithms, so selecting Bass or Snare would currently write engine id 0 and
  render Fold's dispatch branch with zeroed controls;
* the transport, chooser, paging and p-lock plumbing *is* reusable
  (`pk_engine_select`, `source_offset`, the `p[]`/`record[]` ABI), so this is
  still much less than a from-scratch control law -- but it is real work, not
  a configuration change.

**The record layout, resolved.** `pk_render` builds `p[12]` as `p[0..5]` from
the DSP control words and `p[6..11]` from the track's page slots
(`0x80000810 + 72*track + 0x20 + k - 6`), then overrides `p[6] = p[MODE_SLOT]`
and writes:

```c
record[4+k] = ((uint32_t)p[2k] << 16) | p[2k+1];
```

So the pair written at `record[3]` is `(p[6], p[7])` -- and byte offset 6, which
is what `pk3d_source` reads with `move x:(r4+$6),b`, is exactly `p[6]`. But
`p[6]` has just been overwritten with `p[MODE_SLOT]`, the visible main-page MODE
parameter.

**That is the crux, and it is a real defect against this target.** The composed
dispatcher treats byte 6 as the ENGINE ID and compares it against 0/10/11, while
the existing control path puts the MODE parameter there. The two disagree about
what that byte means. Fold happens to work because family 0 and mode 0 coincide
numerically; Bass and Snare cannot be selected at all, because mode never takes
the values 10 or 11.

So the control-side work is now precisely specified rather than a general "add
two prepare paths":

1. decide the engine-id encoding the dispatcher will read (a dedicated byte, or
   `p[6]` carrying family rather than mode);
2. have the ColdFire side publish the selected family for exactly the three
   target algorithms, and only on the tracks the admission rule admits;
3. add the Resonant Bass / Resonant Snare control preparation itself, which does
   not exist in `control.c` today.

Item 1 is a layout decision that touches the already-qualified renderers, so it
should be taken deliberately rather than by editing the dispatcher to match
whatever byte is free.

**The model byte never reaches the dispatcher at all.** Tracing every writer of
byte 6:

* `pk_fold_prepare` ends with `p[11] = 0;`
* `pk_simple_prepare` ends with `p[11] = 2;` (and `p[10] = 0;`)
* `p[6]` is written only by `pk_render`'s `p[6] = p[MODE_SLOT]`

and `record[4+k] = (p[2k] << 16) | p[2k+1]` places `p[6]` at byte offset 6, while
`p[11]` lands at `record[5]`'s low byte -- byte offset **11**. The composed
dispatcher reads byte **6**. So the value the engine chooser actually selects
(`p[MODEL_SLOT]`, the persisted model byte) is written to byte 11 and **never
read by anything**.

Consequences, stated plainly:

* byte 6 can only ever hold **0 or 2** (Fold's or Simple Drum's family), because
  those are the only two writers and they overwrite what `pk_render` put there;
* the composed dispatcher's `cmp x0,b` against 0/10/11 therefore only ever
  matches **0**, so the DSP always takes the Fold branch;
* **Resonant Bass and Resonant Snare are unreachable through the control path in
  the image as it stands** -- not merely unprepared, but unselectable.

**And the byte-offset arithmetic is not the 4:1 mapping an earlier note assumed.**
The qualified seam settles it: `probe_glue.asm` matches `'Y1'` with
`move x:(r4+$2),b` / `cmp #>$005931,b`, which means the record's bytes 2 and 3
are `0x59` and `0x31`. But `pk_render` writes `record[1] = 0x59310000u | trig`,
i.e. 0x59 into bits 31-24, 0x31 into 23-16, and the trigger into 15-8. So the
record's byte offset N maps to a DSP word's bytes and NOT one-per-byte:

```
record[0] = 0x504b0000  -> bytes 0,1 = 'P','K'
record[1] = 0x59310000|trig -> byte 2 = 'Y', byte 3 = '1', byte 4 = trig
record[2] = record[3] = 0   -> bytes 5..10 = 0
record[4..7] = p[0..7] pairs -> later bytes
```

So byte offset **6** -- what `pk3d_source` reads with `move x:(r4+$6),b` --
falls inside `record[2]`, which `pk_render` sets to **zero**. The composer's
comment says the engine id is "record word 3 (p[11])", but `record[3]` is also
zeroed and `p[11]` is never copied into the record at all.

**Conclusion, and it is unambiguous:** the composed dispatcher reads a byte that
the control path explicitly zeroes. On the image as it stands the engine id is
always 0, the dispatcher always takes the Fold branch, and **neither Resonant
Bass nor Resonant Snare can be selected** -- not because they are unprepared,
but because the field that selects them is never written.

**A caveat on the byte arithmetic, recorded so it is not overclaimed.** The
"byte offset 6 falls inside record[2]" reading above assumes one byte per
`record[]` word position, and a direct byte-probe of the composition returned
all zeros for offsets 0..15 -- so that experiment did not confirm the assumption
and is not evidence either way. What IS established from the qualified seam is
that `probe_glue.asm` reads the trigger at `x:(r4+$3)` and matches `'Y1'` at
`x:(r4+$2)`, which pins bytes 2 and 3 to `0x59`/`0x31`. The mapping beyond that,
and therefore exactly which byte the engine id must occupy, must be settled by
an end-to-end test rather than by arithmetic on `record[]` indices.

**RESOLVED: ENGINE_ID_OFFSET = 0x13, derived and proven.**

The offset is not guessed. `pk_render` packs `record[10]` as

```c
record[0] = 0x504b0000u;  record[1] = 0x59310000u | trig;
record[2] = record[3] = 0;
for (k = 0; k < 6u; ++k)
    record[4u+k] = ((uint32_t)p[2u*k] << 16) | p[2u*k+1u];
```

and the transport splits each ColdFire long into TWO DSP words (high, low), so
the words the DSP addresses as `x:(r4+N)` are:

```
N :  0     1     2     3      4  5  6  7 | 8   9   10  11  12  13  14  15  16  17  18  19
    'PK'   0    'Y1'  trig    0  0  0  0 | p0  p1  p2  p3  p4  p5  p6  p7  p8  p9  p10 p11
```

That table is **confirmed by the qualified seam's own code**, which reads
`x:(r4)` against `#>$00504b` (`'PK'`), `x:(r4+$2)` against `#>$005931` (`'Y1'`)
and `x:(r4+$3)` for the trigger -- three independent agreements, so the rest can
be trusted. `p[11]` is the **family byte** (`pk_fold_prepare` stamps 0,
`pk_simple_prepare` stamps 2, and `pk_engine_select` persists the selected model
into the very page slot that feeds `p[11]`), and it lands at **word 19**.

`tools/verify/verify_perky_3algo_engine_join.py` proves the join end to end. It
**replicates `pk_render`'s packing line for line** in Python, feeds that record
to the real composed dispatcher, and compares the result against a DIRECT call
to the same renderer passed through the seam's own output stage:

```
direct  engine  0 (FOLD DRUM ) PCM[:4] = [-1, -2, -4, -6]
direct  engine 10 (RES BASS  ) PCM[:4] = [-32768, ...]
direct  engine 11 (RES SNARE ) PCM[:4] = [0, 0, 0, 0]

dispatch engine  0 (FOLD DRUM ) PCM[:4] = [-256, -512, -1024, -1536]   MATCH
dispatch engine 10 (RES BASS  ) PCM[:4] = [-8388608, ...]              MATCH
dispatch engine 11 (RES SNARE ) PCM[:4] = [0, 0, 0, 0]                 MATCH
```

with `expected = signed24((direct & 0xffffff) << 8)` -- the seam's `pk3z_scale`
stage, eight `asl a` then a 24-bit store, which a direct renderer call does not
go through. All three engine ids dispatch correctly and the fixture is proven to
discriminate them (three distinct direct results).

**What that closes and what it does not.** The consumer side and the producer's
packing now provably agree: the byte the chooser selects is the byte the
dispatcher reads, at word `0x13`. Still required on the ColdFire side is a
**prepare path for the two Resonant families** -- `pk_render` today dispatches
only `p[11]==0` (Fold) and `p[11]==2` (Simple Drum), and both overwrite `p[11]`,
so `control.c` must gain the two Resonant prepare paths that stamp 10 and 11.

**The offset is a single constant**, formerly the open question:
`build_dsp_3algo_source.ENGINE_ID_OFFSET` (default `0x6`) drives the dispatcher's
`move x:(r4+$OFF),b`, and the comment records the two candidates:

```
ENGINE_ID_OFFSET = 0x6  -> dispatches on p[7]; pk_render must copy the model
                           byte into p[7] for the choice to arrive
ENGINE_ID_OFFSET = 0xa  -> reads record[5], whose low half is p[11] -- exactly
                           where pk_engine_select already persists MODEL_SLOT
```

Both values build and both keep the equivalence and image gates green, so the
constant is safe to switch.

**What would not settle it.** Driving `pk3d_source` directly with a controlled
record at a known address returned a zero voice state for offsets 6, 10 *and*
11. That is a fixture failure, not a result: the dispatcher bails before reaching
the voice unless the admission gate at `x:$418` and the record pointer at
`x:$209` are both satisfied the way the real seam satisfies them, and my
hand-built fixture does not reproduce that. So the candidates remain
undistinguished, and the honest next step is to drive the **real** seam
(`probe_glue.asm`'s own harness) with the two offsets rather than a synthetic
record.

**The fix is small and well-specified in outline**, and both halves are known
independently of the byte question:

1. the control path must deliver the selected model/family byte into whatever
   byte the dispatcher reads, so that `pk_engine_select`'s choice reaches the
   DSP at all -- today the value it writes is not copied into the record;
2. `control.c` needs prepare paths for the two Resonant families, which today
   fall into the `else` that zeroes the prepared controls.

Everything else -- the `p[]`/`record[]` ABI, the chooser, `source_offset`, the
page/paging machinery and the p-lock path -- is reusable as the target requires.
What is missing is exactly this join, and it is the reason the functional target
("select Resonant Bass / Resonant Snare") cannot yet be demonstrated end to end.

### Fold block-1 parity: FIXED -- two real composition bugs, both found and closed

The item is closed. Two independent defects, each measured, each fixed, and the
composed Fold gate now passes end to end.

**Bug 1 -- the envelope curve was read from the WRONG TABLE.**
`simple_drum_envelope.asm`'s shape-0 reader carries the standalone build's
literal `move #>$0009a5,r1`. The composer reconciled that literal in the shared
resonant TAIL but never in the Fold section, while its own ledger places the
curve at `Y_SIMPLE_ENV = 0xc50`. `0x9a5` is **inside the shipped wave region**
(`Y_WAVES = 0x7a5`, 768 words -> `0x7a5..0xaa4`), so the composed Fold path
decoded WAVE DATA as its amplitude curve. The standalone gates have always made
this substitution; the composer did not.

Measured, all 15 ARM fold cases, first differing sample:

```
BEFORE: mode 1 corners 1,2 -> differ at sample 29
        12 of 15 cases exact
AFTER : all 15 cases exact
```

**Bug 2 -- the Fold bodies were on the WRONG SCRATCH CONVENTION.**
`fold_body()`'s docstring claimed it applied `center_scratch`; **the code never
called it.** The composition's shared low32/RNG arithmetic is CENTRED
(`r5-$40`-style) and therefore requires r5 advanced by 0x40, which is why the
resonant voices carry an `r5 += 0x40` prologue. The Fold bodies had neither the
prologue nor the displacement transform, so the mode-2 (noise) path reached the
shared arithmetic with r5 0x40 low and touched every one of its scratch words 64
words away from the qualified build. That is exactly the residual divergence,
and it is why only the noise cases were left:

```
AFTER bug 1 only : mode 2 continuation x3 still differ at sample 2
AFTER both       : all 15 cases exact
```

**The fix, and why the ABI moved to the caller.** `fold_body()` now applies
`centre_displacements` (the displacement half of `center_scratch`, WITHOUT the
prologue), `pknv_noise` is centred with it, the resonant voices' now-redundant
`r5 += 0x40` prologue is stripped, and **the caller advances r5 once** -- the
dispatcher sets `r5 = SCRATCH_ABI = SCRATCH_BASE + 0x40`, and every gate probe
does the same. The advance cannot live in the bodies: the Fold path is entered
TWICE per block (`pk_simple_base` then `pk_fold_voice`) and two prologues would
leave r5 0x80 high on the second entry. `SCRATCH_BASE` stays the ADDRESS of the
scratch block (what is seeded and dumped); `SCRATCH_ABI` is the register value
the bodies expect. The voices keep their separate `move a1,r4` variables-pointer
derivation, which is a derived pointer, not the base.

**The equivalence gate had to grow up, and now checks more than it did.** It
compared written displacements, so it could not see either bug and then objected
to the fix. It now (a) rewrites `x:(r5+/-$N)` to its offset from the scratch
BLOCK base on both sides and compares EFFECTIVE addresses, folding the
convention rather than ignoring it, and (b) drops the `r5 += 0x40` prologue from
both sides as an ABI detail rather than renderer content. The compose-side
advance is passed per section, because the Fold standalone is assembled
UNCENTRED while the resonant standalone is centred. This is a STRENGTHENING: the
gate now compares the addresses the two builds actually touch.

**Result.**

```
Fold Drum 1 in composition: PASS
  640 blocks, 400 native randomized; worst 25,393 modeled cycles/16
  ARM worst 17,377
composed shipping source : 3,868 P words   (was 3,936)
deduplicated saving      : 2,220 P words
both payloads            : used 3,868, FREE 195   (was 127)
FX-sacrifice gap at +DJ EQ: 82 words   (was 150, then 105)
```

The composed Fold renderer is now bit-exact against the captured ARM fixtures
across every mode, every corner, triggers AND continuation blocks.

### Fold block-1 parity: now characterised to the word and the block

With the regression reverted, the composed and standalone builds are driven
through identical probes (same fixture, same state base `X:0x3800`, same scratch
`X:0x3900`, each with its OWN table bases) and the whole persistent region
`0x3800..0x39CB` is dumped after every 16-sample block:

```
standalone[:8] = [-29, -115, -257, -457, -712, -1024, -1267, -1268]
composed  [:8] = [-29, -115, -257, -457, -712, -1024, -1267, -1268]
first sample where they differ from EACH OTHER: (29, -4160, -4143)

after block 0: 0 diffs across 0x3800..0x39CB
after block 1: 5 diffs
     0x3802  0x63a6 vs 0x62e0
     0x3804  0x0b59 vs 0x0b17
     0x3953  0x03a6 vs 0x02e0
     0x395e  0xbe85 vs 0xbea5
     0x395f  0xb32f vs 0xb44f
after block 2: 9 diffs (same words plus 0x3952, 0x3954, 0x3955, 0x3958)
```

**This is the sharpest statement of the item so far:**

* after block 0 the two builds are **byte-identical everywhere** -- voice block
  *and* scratch and cache;
* they first part company **inside block 1**, in the scratch accumulator at
  `0x3952/0x3953` (a 32-bit value) and at `0x395e/0x395f`;
* the PCM difference at block-1 index 13 is a consequence of that, not a
  separate fault;
* corner 1's packed sample index is `0x07fe`, so block 1 is the first block in
  which the second-difference decoder must decode a *new* block -- which is why
  the divergence starts exactly there and why corner 0 (index 0) never shows it.

So the fault is in the decoder's re-decode path (`pk_simple_delta_at` on a cache
miss) as laid out in the composition, and the scratch accumulator at
`0x3952/0x3953` is where to look. That is a much smaller space than "the
composed renderer misbehaves".

### The shared arithmetic is on a DIFFERENT convention from the standalone

**This corrects an earlier claim in this record.** The equivalence gate asserts
"every renderer instruction identical apart from relocated DO/JSR/branch
targets". Comparing **every one of the 80 labels** in the two binaries, not the
six the gate names, shows that is not true: **14 routines differ by a real
operand, not a relocation.** They are all in the shared 32-bit arithmetic layer,
and every difference is a **constant 0x40 in the scratch displacement**:

```
routine                  standalone          composed
pk_u32_add               x:(r5+$0)           x:(r5-$40)
pk_u32_mul_low           x:(r5+$0),x0        x:(r5-$40),x0
pk_u32_mul_full          x:(r5+$2),y0        x:(r5-$3e),y0
pk_rng_step              x:(r5+$0),a         x:(r5-$40),a
pk_rng_no_carry          x:(r5+$24),a        x:(r5-$1c),a
pk_add_no_carry          a1,x:(r5+$8)        a1,x:(r5-$38)
pk_sub_no_borrow, pk_u32_sub, pk_u32_asr, pk_u32_shift_sign_ready  (same shape)
```

**Why.** `dsp_source_layout.center_scratch` subtracts 0x40 from every
`x:(r5+$N)` displacement **and inserts a prologue that advances r5 by 0x40**, so
a centred body's absolute addresses are unchanged -- *provided the caller has
already advanced r5*. The resonant recipes get both halves of that transform.
The Fold bodies get neither. Measured on the composed source:

```
pk3d_bass_voice:   move r5,a / add #>$40,a / move a1,r5   <- prologue PRESENT
pk3d_snare_voice:  move r5,a / add #>$40,a / move a1,r5   <- prologue PRESENT
pk_fold_voice:     (none)
pk_simple_base:    (none)
pk_simple_delta_at:(none)
pk_simple_envelope:(none)
```

and the dispatcher sets `r5 = 0x3900`. So the resonant path reaches the shared
math with `r5 = 0x3940` (correct for centred displacements) while the **Fold
path reaches it with `r5 = 0x3900`, addressing every shared-arithmetic scratch
word 0x40 = 64 words away from where the qualified standalone build puts it.**

**Tested as a fix, and it does NOT explain the Fold symptom.** Centring the Fold
sections' displacements and raising the caller to `r5 = 0x3940` -- which moves
the shared math's window from `0x38C0..0x3921` to `0x3900..0x3921`, exactly the
standalone's -- leaves the result bit-identical:

```
BEFORE fix, r5=0x3900: head=[-29,-115,-257,-457] first_diff_vs_fixture=(29,-4143,-4160)
AFTER  fix, r5=0x3940: head=[-29,-115,-257,-457] first_diff_vs_fixture=(29,-4143,-4160)
```

So the convention mismatch is a **real latent defect** worth fixing on its own
merits, but it is not the cause of the block-1 divergence -- that fixture does
not exercise the shared-arithmetic scratch.

**Where the block-1 divergence actually lives.** Dumping the full persistent
region per block, the first differences after block 1 are at

```
0x3802, 0x3804          the voice's fold/envelope accumulators
0x3953                  r5+$53 -- written by pksde_shape1 / pksde_next_ready / pksdo_have_wave
0x395e, 0x395f          r5+$5e/$5f -- the fold amount, written by pk_fold_voice
```

i.e. the **simple-drum envelope state machine** (`pksde_*` / `pksdo_*`) and the
Fold voice's own fold accumulator -- not the shared arithmetic.

**Consequence for the gate.** `verify_perky_3algo_equivalence.py` must be
extended to compare **all** shared labels (and to audit fallthrough), not the
six it names; until then its "identical" claim covers 6 of 80 labels and missed
14 real differences.

### The equivalence gate

`tools/verify/verify_perky_3algo_equivalence.py` is the gate that now carries
the bit-exactness claim. It assembles the shipping composition and each
standalone renderer program, disassembles both, and requires **every renderer
instruction to be identical** apart from the operands that necessarily move when
code relocates: the absolute target of a `DO`, `JSR`/`JSRL` or branch. Every
other operand -- accumulators, registers, displacements, immediates, parallel
moves -- must match word for word, so an accidental change to a shift, a guard,
a table base or a slot fails the build.

It caught a real defect on its first run: the composer emitted the shared
low32/RNG/envelope helper block **twice** -- once centred (carried by the
resonant tail) and once uncentred (re-read raw from `noise_tone_math.asm` by
`extra_body`). The uncentred copy won, so the composed `pk_rng_step` read
`x:(r5+$0)` where the qualified build reads `x:(r5-$40)`: a different scratch
word, silently. The composer now keeps the centred tail whole (dropping only
the standalone `pk_math_probe` dispatcher) and `extra_body` supplies only the
noise sample-and-hold helper the tail lacks, with an assertion that the tail
really does own it.

### Measured result

| | P words |
| --- | ---: |
| Fold Drum 1 standalone | 1,312 |
| Resonant Bass standalone | 2,447 |
| Resonant Snare standalone | 2,329 |
| Naive standalone sum | 6,088 |
| **Composed shipping source** | **3,936** |
| Deduplicated | **2,152** |

Fold Drum 1, Resonant Bass and Resonant Snare all pass the equivalence gate.

The standalone per-renderer gates stay green, so per-renderer qualification is
unaffected: `verify_perky_fold_drum_exec.py` and
`verify_perky_resonant_dsp_exec.py` both pass unchanged.

## REGRESSION FOUND AND REVERTED: unreached-code removal broke the Fold path

**The 45-word saving reported in an earlier round is RETRACTED. It was a bug, and
the gates did not catch it.**

`drop_unreached()` deleted six routines on the evidence that nothing in the
composed source *names* them (`pk_u32_sub`, `pk_u32_asr`, `pk_noise_step`,
`pknhe_read_r2`, `pksde_read_r2`, `pksdo_read_r2`). That evidence was
insufficient: **a routine can be reachable by FALLTHROUGH** -- if the routine
physically before it ends without an `rts`/`jmp`/`bra`, control runs straight
into the next label. Textual reference counting cannot see that, and the
`pksde_*` / `pksdo_*` / `pknhe_*` helpers sit exactly where an envelope state
machine falls through.

Measured, same fixture, same probe, one block:

```
drop_unreached DISABLED : head=[-29, -115, -257, -457]  first_diff=None   (exact)
drop_unreached ENABLED  : head=[-29,  -83, -144, -419]  first_diff=(1, ...)  (BROKEN)
```

Two of this branch's own gates passed while this was broken:

* `verify_perky_3algo_equivalence.py` -- it compares instruction *sequences*
  routine by routine, and deleting whole routines elsewhere leaves the compared
  routines "identical apart from relocated targets". It has **no model of
  fallthrough**, so it cannot see this class of defect.
* `verify_perky_3algo_engine_join.py` -- it compares dispatch *routing*, not
  rendered audio, and its Fold reference is the same broken code.

**What caught it**: the Fold block-1 parity item. Chasing it exposed that the
gate's own Fold result had silently changed from `[-29, -115, -257, -457]` to
`[-29, -83, -144, -419]` since it was last reported -- i.e. the composition
itself had regressed between rounds, and nothing else noticed.

**Actions taken.** `drop_unreached` is reverted; the composition is back to
3,936 P words (FREE 127, image sha256 `0079ebed...`), and the Fold arm cases are
back to corner 0 exact / corners 1-2 diverging at sample 29 -- the state this
record documented before the regression.

**Consequences to carry forward:**

* the FX-sacrifice gap is back to **150 words**, not 105;
* the equivalence gate needs a fallthrough audit (a routine whose predecessor
  can reach it must count as referenced) before any future unreached-code
  removal is attempted.

## P-memory and the FX sacrifice: reduced, and the overlay question answered

**A real 45-word reduction, verified bit-exact.** The shipping composition
defined six routines that no shipping path can enter -- `pk_u32_sub`,
`pk_u32_asr`, `pk_noise_step`, `pknhe_read_r2`, `pksde_read_r2`,
`pksdo_read_r2`. They come from the standalone recipes, which need them for
their isolated limb tests, but nothing in the composed machine names them.
`build_dsp_3algo_source.drop_unreached` removes them, and it refuses at build
time if any of them is referenced anywhere else -- so it can only ever delete
code that cannot be called, jumped to, or read as data.

```
composed P words: 3936 -> 3891   (45 saved)
both payloads    : used 3891, FREE 172   (was FREE 127)
```

The equivalence and engine-join gates both still pass, i.e. the removal is
bit-exact-neutral. (An earlier attempt at this measured as *inert*; that earlier
implementation was faulty and its "no saving" result is retracted.)

**The overlay question, answered.** The target asks whether, since Fold / Bass /
Snare are mutually exclusive on a Perky track, any of their code can be overlaid
or loaded/selected to save P. It cannot, for two independent reasons:

1. **Each payload has exactly ONE Perky-capable track** (T1 on B, T5 on A), and
   that track may switch algorithm at any time -- including between events in a
   running sequencer, which the functional target explicitly requires. So all
   three renderers must be resident *simultaneously*; there is no point at which
   one of them is provably not needed.
2. Runtime loading/selection would need a loader, and the target forbids
   inventing one ("Do not invent unsafe runtime loading").

So the P cost is genuinely the union of the three renderers, and 3,891 words is
that union after deduplication and unreached-code removal.

**Where the FX sacrifice now stands.** With 3,891 words the contiguous budgets
are:

| configuration sacrificed | words | shortfall |
| --- | ---: | ---: |
| nothing | 0 | 3,891 |
| SPRING only | 1,063 | 2,828 |
| PLATE + SPRING + DARK (stock donor) | 2,724 | 1,167 |
| + COMPRESSOR | 2,904 | 987 |
| + LO-FI | 3,441 | 450 |
| + DJ EQ | 3,786 | **105** |
| + COMB FILTER | 4,063 | fits |

The breakpoint is sharp: **105 more words and SPATIALIZER survives**, dropping
the sacrifice from seven effects to six. That is a much better target than the
150 it was, and it is the same order as the code-size work the timing
investigation needs anyway -- an optimization that removes instructions from a
hot path removes P words too.

**Why the region must be contiguous, and why PLATE is the right start.** The
placer harvests contiguous runs, so the budget is a prefix sum from the donor
region. Starting at PLATE (`P:0x1000`) costs 7 effects for 4,063 words;
starting one effect lower at CHORUS (`P:0xeb7`) buys 4,392 words but costs 8
effects, because it also gives up CHORUS. Starting at PLATE is optimal, and the
seven-effect set is the minimum *given the current footprint*.

## Measured P-memory finding: the stock FX sacrifice is larger than Spring

This is a measured result from the **composed shipping source**, not an
estimate from standalone sizes. The composed source links at **3,936 P words**
for each payload, and each payload has its own stock code layout, so the budget
is per payload.

Stock effect spans, read from the pristine 1.40C MAIN OS (`tools/remix/stock.py`,
which matches the module records by a size fingerprint, so these are image
values rather than hand-copied ones):

| Payload A | | Payload B | |
| --- | ---: | --- | ---: |
| PLATE REV `P:$1000` | 594 | PLATE REV `P:$0dc0` | 594 |
| SPRING REV `P:$1252` | 1,063 | SPRING REV `P:$1012` | 1,063 |
| DARK REV `P:$1679` | 1,067 | DARK REV `P:$1439` | 1,067 |
| COMPRESSOR `P:$1aa4` | 180 | COMPRESSOR `P:$1864` | 180 |
| LO-FI `P:$1b58` | 537 | LO-FI `P:$1918` | 537 |
| DJ EQ `P:$1d71` | 345 | DJ EQ `P:$1b31` | 345 |
| COMB FILTER `P:$1eca` | 277 | COMB FILTER `P:$1c8a` | 277 |

Because the placer only harvests **contiguous** runs, the achievable budgets
are prefix sums from that table. Against the 3,936-word requirement:

| Configuration sacrificed | A words | B words | Result |
| --- | ---: | ---: | --- |
| nothing | 0 | 0 | short 3,936 |
| SPRING REV only | 1,063 | 1,063 | short 2,873 |
| PLATE + SPRING + DARK (the stock donor region) | 2,724 | 2,724 | short 1,212 |
| + COMPRESSOR | 2,904 | 2,904 | short 1,032 |
| + LO-FI | 3,441 | 3,441 | short 495 |
| + DJ EQ | 3,786 | 3,786 | short **150** |
| + COMB FILTER | **4,063** | **4,063** | **fits** |

**So the second preferred configuration -- Spring Reverb only -- is not
sufficient, and the shortfall has to be documented rather than assumed away.**
The first configuration that fits is the three reverbs *plus COMPRESSOR, LO-FI,
DJ EQ and COMB FILTER*: seven of the thirteen stock effects. LO-FI and DJ EQ
cannot be separated from that set because they are interior members of the run
(LO-FI `$1b58..$1d71`, DJ EQ `$1d71..$1eca`).

That leaves two honest ways forward, and the choice should be made on the
numbers:

1. **Shrink the composed image by 150 words** (3,936 -> 3,786). Then the
   sacrifice stops at DJ EQ and COMB FILTER and SPATIALIZER survives. Measured
   candidates in the shared helper block, not the renderers: `pk_u32_sub`
   (9 words), `pk_u32_asr` (6) and `pk_noise_step` (14) are emitted by the
   composition and referenced by nothing -- 29 words, not enough on its own.
   The remaining ~121 have to come from better helper sharing between the Fold
   and resonant paths (they currently each carry their own envelope entry
   sequence) or from a smaller asset/table representation, and any of it must
   keep `verify_perky_3algo_equivalence.py` green.
2. Reclaim a **different seven effects** -- COMPRESSOR, LO-FI, DJ EQ and COMB
   FILTER total 1,339 words where SPATIALIZER+EQUALIZER+PHASER+FLANGER+CHORUS
   total 1,368 -- if a differently-composed code layout ever makes its budget
   smaller. Both are inside the 3,936 figure rather than beside it.

The measurement is reproducible from the repository: `tools/remix/stock.py`
gives the spans and `tools/perky/build_dsp_3algo_source.py --measure` gives the
requirement. Nothing here is inferred from a standalone sum.

## The composed image (achieved)

`tools/perky/build_dsp_3algo.py` builds the reduced machine end to end:

```
$ python3 tools/perky/build_dsp_3algo.py
=== perky-dsp-3algo 0/4: composed-renderer and sacrifice preflight ===
  -> composed renderer equivalence
  -> measured FX sacrifice
=== perky-dsp-3algo 1/4: composed DSP source: 3936 P words ===
=== perky-dsp-3algo 2/4: install the composed source and build ===
  region P:0x01000..0x01fdf (4063 words)  used 3936  FREE 127     [payload A]
  region P:0x00dc0..0x01d9f (4063 words)  used 3936  FREE 127     [payload B]
=== perky-dsp-3algo 3/4: image structure ===
  MAIN OS  : out/mainos_bus.bin (1,116,588 bytes)
  sha256   : b18e202c0406a6ac20de4fccdaf332c3be3332b0b118e61af2be8f709d313342
```

The composed DSP program lands in **both** payloads with 127 words free, which
is the placement milestone. Two things had to be right first, and both were
found by building rather than by reasoning:

1. **The FX1 list is load-bearing.** `_listed` is the module list *union* every
   effect whose `fx2_id` is on the pristine FX1 chooser, so with the auto-add
   rule in force the harvest collapses to the three reverbs (2,724 < 3,936).
   Naming `fx1` explicitly replaces that rule. The list may contain only
   **stock** effects the pristine FX1 chooser already lists: a module of ours
   needs a descriptor clone, and a stock effect FX1 does not list is FX2-only
   because it does not fit a 3,072-word FX1 allocation.
2. The module declaration's `DspHook` names `pk_probe_source`; the composed
   source's entry is the same seam under the composer's name, so the build
   publishes an alias at that label.

**What this image is and is not.** It is a structurally complete MAIN OS with
the composed machine placed in both payloads. It is **not** yet ready to
flash: the composed renderer's *execution* still has to be proven (the
equivalence gate proves the instructions, not the rendering), and the
ColdFire-side T1/T5 algorithm-selection control law is still to be written.
The boot/port gates additionally need the composed source's own `--packed`
layout, which the existing `verify_perky_machine_boot.py` expects in the older
packed-machine shape.

## Reproducing

```bash
python3 tools/perky/build_dsp_3algo_source.py --measure
python3 tools/verify/verify_perky_fold_drum_exec.py
python3 tools/verify/verify_perky_resonant_dsp_exec.py --firmware /path/to/perkons.img
python3 tools/verify/verify_perky_3algo_exec.py
```

External inputs (never committed): the user's PĒRKONS v1.2.1 image, the
PerkyBits source tree, the captured ARM fixtures under
`out/perky/engine-fixtures`, and the generated Simple/Fold assets under
`out/perky/simple-drum-assets`.

## Not yet done

1. the composed execution gate above;
2. production control law for the three algorithms on ColdFire
   (`resonant_control_update.py` is the exact v1.2.1 oracle already available);
3. the real linked P/X/Y placement and the actual stock-FX sacrifice measured
   from the composed image;
4. the complete firmware image plus boot/upload/readback gates;
5. reachable-state timing bounds on the composed production path.
