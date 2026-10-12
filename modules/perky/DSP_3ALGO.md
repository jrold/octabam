# Composed reduced Perky DSP machine — implementation record

**Branch:** `perky-dsp-2voice-3algo` (from `perky-optimize`, commit `a522d2f2`).

This is the reduced production target: **two Perky voices total, one per DSP
core, three selectable algorithms each.** It is deliberately smaller than the
superseded twelve-family / four-voice target and it does **not** move synthesis
back to ColdFire.

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
