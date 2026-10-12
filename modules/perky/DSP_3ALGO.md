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

### Timing qualification (measured) -- and a corrected budget model

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

**The fix is small and well-specified**, and both halves are already known:

1. `pk_render` must copy the model/family byte into the byte offset the
   dispatcher reads (or both sides must agree on a new offset), so that
   `pk_engine_select`'s choice actually reaches the DSP;
2. `control.c` needs prepare paths for the two Resonant families, which today
   fall into the `else` that zeroes the prepared controls.

Everything else -- the `p[]`/`record[]` ABI, the chooser, `source_offset`, the
page/paging machinery and the p-lock path -- is reusable as the target requires.
What is missing is exactly this join, and it is the reason the functional target
("select Resonant Bass / Resonant Snare") cannot yet be demonstrated end to end.

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
