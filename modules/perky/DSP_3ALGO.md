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

### Isolating the composed Fold silence

The composed Fold renderer returns silence for a fixture the standalone binary
renders as `-1,-1,-2,-2,...`. This round isolated it further, by measurement:

* a full 2x2 matrix -- {standalone, composed} x {state at `X:200`, `X:3800`} --
  gives `-1,-1,-2,-2,...` at **both** addresses for the standalone and zeros at
  **both** for the composed build, so it is not an addressing artifact;
* stubbing **both** resonant voices to a bare `rts` and re-running the composed
  Fold entry still returns silence, so the resonant renderers are not the
  cause: the composed **Fold path itself** is;
* the composed `pk_fold_voice` disassembles correctly (`do n7`, the envelope
  and frequency calls, `pk_simple_base` writing `x:(r6+$34)`) and is
  instruction-identical to the standalone body.

So the fault is in the Fold path *as composed* -- something about the shared
helpers and layout as they are emitted together -- and not in any single
renderer body. The next step is to bisect the composed Fold path by rebuilding
it from the standalone pieces one section at a time (fold body first, then the
shared low32/RNG block, then the resonant tail) until the silence appears.

### What an image would have to give up

The 150-word gap matters because it decides whether SPATIALIZER survives. The
options measured for closing it, none of them a renderer change:

* dead routine removal: `pk_u32_sub` (9), `pk_u32_asr` (6), `pk_noise_step`
  (14), `pknhe_read_r2` (5) are defined and never reached -- but removing all
  of them measured as **inert** (3,936 words before and after), so the
  assembler was already not paying for them and this avenue is closed;
* genuine cross-path duplication does exist and is small: `pknhe_read_r1` /
  `pksde_read_r1` (11 instructions each), `pknhe_commit` / `pksde_commit` (6),
  and the `read_r0`/`read_r2` pairs. Sharing those is a few tens of words, not
  150;
* the remaining distance has to come from how the Fold and resonant paths each
  carry their own envelope entry sequence, or from a smaller table
  representation.

### Why the harvest is capped at 2,724 words (measured)

`stock.harvested()` is `{effects with DSP code} - listed`, and the build's
`_listed` is not just the remix's module list:

```python
_listed = set(REMIX.modules) | set(REMIX.fx1 or [
    k for k in stock.p_spans("A")
    if _MODS[k].menu.fx2_id in stock_mod.fx1_ids()])
```

`stock.fx1_ids()` is read from the pristine image's **FX1 chooser**, and the
DSP dispatch table is indexed by the raw id and shared by both menus, so an
effect on FX1 cannot have its code harvested without taking it off FX1 as well.
Measured membership:

| Effect | fx2 id | on the stock FX1 chooser? | harvestable? |
| --- | ---: | :---: | :---: |
| PLATE REV | 0x14 | no | **yes** |
| SPRING REV | 0x15 | no | **yes** |
| DARK REV | 0x16 | no | **yes** |
| COMPRESSOR | 0x18 | yes | no (FX1 needs it) |
| LO-FI | 0x1c | yes | no |
| DJ EQ | 0x0d | yes | no |
| COMB FILTER | 0x13 | yes | no |
| FILTER / EQUALIZER / PHASER / FLANGER / CHORUS / SPATIALIZER | 0x04/0x0c/0x10/0x11/0x12/0x05 | yes | no |

The **only** DSP code on neither chooser is the three reverbs, so the maximum
free contiguous region is **2,724 words** -- and the composed Perky program
needs **3,936**. The measured shortfall against the whole available region is
therefore **1,212 words**, not zero.

This is why the earlier attempt to build with the seven-effect remix overran:
listing `DELAY` in `modules` pulled its FX1 id (0x08) into `_listed`, the
auto-add rule then listed every effect whose id is on the FX1 chooser, and the
harvest collapsed back to the three reverbs. The remix no longer lists DELAY,
but that alone cannot raise the cap -- the cap is the chooser membership, not
the listing.

**Consequence for the target.** Fitting the composed machine as it stands
requires taking **COMPRESSOR, LO-FI, DJ EQ and COMB FILTER off the FX1 chooser
as well** (4,063 words total, re-measured and contiguous in both payloads).
That is a real loss of stock functionality -- those four would no longer be
selectable on FX1 -- so it is a product decision, not one to take silently.
The alternative is to bring the composed program down from 3,936 to 2,724
words, a 1,212-word (31%) reduction, which cannot come from dead code (measured
inert) and would have to come from a materially different composition.

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
