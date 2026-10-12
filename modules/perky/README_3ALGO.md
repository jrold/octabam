# Reduced Perky DSP machine — implementation report

**Branch** `perky-dsp-2voice-3algo` (from `perky-optimize`; `perky-optimize` is untouched)
**Scope** the reduced target: **two Perky voices total, one per DSP core, three
algorithms each**, six normal Octatrack tracks remaining.
**Headline artifact**

```
out/mainos_bus.bin   1,116,588 bytes
sha256               b18e202c0406a6ac20de4fccdaf332c3be3332b0b118e61af2be8f709d313342
```

Reproduce everything with one command:

```bash
python3 tools/perky/build_dsp_3algo.py
```

It runs, in order: the composed-renderer equivalence gate, the measured
sacrifice gate, composition, the full Octabam build, and image validation.

---

## 1. Final architecture

| Track | Core (payload) | Perky? | Algorithms |
| --- | --- | --- | --- |
| T1 | **B** (`P:0x0dc0`) | yes | Fold Drum 1, Resonant Bass, Resonant Snare |
| T2–T4 | B | no — ordinary Octatrack tracks | — |
| T5 | **A** (`P:0x1000`) | yes | Fold Drum 1, Resonant Bass, Resonant Snare |
| T6–T8 | A | no — ordinary Octatrack tracks | — |

The track↔core mapping is the repository's measured one (payload A serves
tracks 5–8, payload B serves 1–4; AGENTS.md, established via the MrkVerb32
marker flash). Because T1 and T5 are on **different** cores, exactly one Perky
voice can execute per core, which the composed seam enforces itself: it reads
the per-core track slot at `x:$418` and returns without rendering unless it
holds the admitted value.

Wavetable is not used. Simple Drum, Fold Drum 2, Complex Drum, Slap, Karplus,
Noise Hat, Noise/Tone and Acoustic Hats are not included. Synthesis is on the
DSP, not ColdFire.

## 2. Included algorithms and how they were composed

Fold Drum 1, Resonant Bass and Resonant Snare are composed into **one** source
by `tools/perky/build_dsp_3algo_source.py`, which deduplicates their shared
low32/RNG/envelope helper block rather than emitting each renderer's copy.

| | P words |
| --- | ---: |
| Fold Drum 1 standalone | 1,312 |
| Resonant Bass standalone | 2,447 |
| Resonant Snare standalone | 2,329 |
| Naive standalone sum | 6,088 |
| **Composed shipping source** | **3,936** |
| Deduplicated | **2,152** |

This is the measured composition, not a sum of standalone sizes.

## 3. Memory ledger

### Program memory

```
payload A: region P:0x01000..0x01fdf (4063 words)  used 3936  FREE 127
payload B: region P:0x00dc0..0x01d9f (4063 words)  used 3936  FREE 127
```

### Stock FX sacrifice — measured, and it is more than Spring

`verify_perky_3algo_sacrifice.py` reads the stock effect spans out of the
pristine 1.40C MAIN OS and compares them with the composed requirement. The
placer can only harvest **contiguous** runs, so the budgets are prefix sums:

| Configuration sacrificed | A | B | Result |
| --- | ---: | ---: | --- |
| nothing (preserve all) | 0 | 0 | short 3,936 |
| **SPRING REV only** | 1,063 | 1,063 | short **2,873** |
| PLATE + SPRING + DARK (the stock donor) | 2,724 | 2,724 | short 1,212 |
| + COMPRESSOR | 2,904 | 2,904 | short 1,032 |
| + LO-FI | 3,441 | 3,441 | short 495 |
| + DJ EQ | 3,786 | 3,786 | short 150 |
| **+ COMB FILTER** | **4,063** | **4,063** | **FITS** |

**Spring Reverb alone is demonstrably not sufficient.** The first configuration
that fits sacrifices seven of the thirteen stock effects: the three reverbs
plus COMPRESSOR, LO-FI, DJ EQ and COMB FILTER. LO-FI and DJ EQ cannot be split
out of that set because they are interior members of the run.

A second, non-obvious constraint applies: `stock.fx1_ids()` is read from the
image's **FX1 chooser**, and the DSP dispatch table is indexed by the raw id and
shared by both menus, so an effect on FX1 cannot have its code harvested unless
it is taken off FX1 as well. Naming `fx1` explicitly in the remix is what
replaces that auto-add rule; with it in force the harvest collapses to the three
reverbs (2,724 < 3,936 — the reason the first attempt at this remix overran).

### Retained and removed

**Retained, still selectable and still callable:** FILTER, EQUALIZER, PHASER,
FLANGER, CHORUS, SPATIALIZER.

**Removed:** PLATE REV, SPRING REV, DARK REV, COMPRESSOR, LO-FI, DJ EQ,
COMB FILTER — explicitly confirmed by the sacrifice and image gates.

### X / Y

The composed X/Y ledger is in `modules/perky/DSP_3ALGO.md`: voice block
`0x3800`, RNG `0x38e8`, scratch `0x3900` (188 words), and the Y regions
`Y_WAVES 0x07a5`, `Y_ENV1 0x2000`, `Y_ENV2 0x2280`, `Y_INTERP_A 0x2500`,
`Y_INTERP_B 0x2600`. No Wavetable allocation exists in this target, so no
stock FX data/state was displaced for Y.

## 4. Tests run and results

| Gate | Result |
| --- | --- |
| DSP assembler / link | PASS — composed source assembles, 3,936 words |
| Composed-renderer equivalence | **PASS** — every renderer instruction identical to the qualified standalone builds apart from relocated `DO`/`JSR`/branch targets |
| Measured FX sacrifice | **PASS** — names the minimum sacrifice, fails if nothing fits |
| Image placement and admission | **PASS** — 4,063/4,063 words present in both payloads, top exact, 4/4 ordered admission fingerprints at the region entry |
| Fold Drum 1 (standalone) | PASS — 15 original ARM blocks + 400 randomized blocks, PCM/state/RNG |
| Resonant Bass (standalone) | PASS — 1,024 blocks, exact stereo PCM/state/RNG |
| Resonant Snare (standalone) | PASS — 1,024 blocks, exact stereo PCM/state/RNG |
| Full build (`make bus`) | PASS |
| Composed **execution** parity | **NOT PASSING** — see below |

## 5. Timing

Not yet measured on the composed production path. The standalone measurements
are on record — Fold Drum 1 worst 26,121 modeled cycles per 16-sample block
(19,424 on the physical noise-hold subset); Resonant Bass worst 76,319;
Resonant Snare worst 82,263 — against a full-core frame deadline of 72,512
cycles and the historical development allowance of 23,040. Bass and Snare
exceed both and **must** be measured in the composed production path, on
reachable control/state domains rather than randomized impossible states,
before any timing claim is made. Because load is the **maximum** of the
selected algorithm per core, only one of the three runs on a core at a time.

## 6. The blocker: two algorithms exceed the physical frame deadline

This is measured, not estimated, and it is the single fact that decides whether
this target is achievable as written.

The target's runtime policy says: *"Never exceed the physical full-core DSP
deadline."* That deadline is **72,512 cycles per 16-sample block**
(`docs/firmware/CHIP.md`). Measured on the composed production renderer
(`tools/verify/verify_perky_3algo_timing.py`, report at
`out/perky/dsp-3algo/timing.json`):

| algorithm | modeled worst | vs 72,512 physical deadline | vs 23,040 model allowance |
| --- | ---: | --- | --- |
| Fold Drum 1 | 26,112 | under (46,400 headroom) | over by 3,072 (12%) |
| **Resonant Bass** | **74,515** | **OVER by 2,003** | over by 51,475 (69%) |
| **Resonant Snare** | **80,722** | **OVER by 8,210** | over by 57,682 (71%) |

**Resonant Bass and Resonant Snare do not fit the frame at one voice per core.**
This is not a composition artefact and not a host-timing artefact:

* the composed source is **instruction-identical** to the qualified standalone
  renderers (word-level proof in `DSP_3ALGO.md`), and lands within 9 cycles of
  the standalone Fold figure;
* the same overage is present in the **standalone** gates that qualified these
  renderers, which pass because they assert **no timing bound at all**;
* the figures are already over the physical 72,512-cycle deadline *before* the
  repository's 2x model margin and stock reserve are applied, so no
  interpretation of the model rescues them.

**Why this blocks rather than delays the work.** Closing it needs 51,475 cycles
off Bass and 57,682 off Snare -- the order of removing most of the resonator
work per sample. That is an **algorithmic** change, and the target explicitly
forbids it ("Do not redesign the project", "Do not reopen discarded
architectures", "Preserve bit-exact behavior ... for every optimization"). The
code is already deduplicated and already executes the qualified instructions, so
there is no instruction-level headroom of that magnitude.

**What would unblock it** is a decision this branch is not authorised to take:

1. a deliberately smaller resonant algorithm (a redesign -- the target forbids
   this branch from choosing it); or
2. accepting a per-voice budget above the 72,512-cycle frame for the resonant
   algorithms, which contradicts "never exceed the physical full-core DSP
   deadline"; or
3. reducing the target to the algorithms that do fit -- **Fold Drum 1 does**, at
   36% of the frame with 46,400 cycles of headroom.

Option 3 is worth stating plainly because the target's own framing prefers it:
*"Prefer a working, tightly scoped T1/T5 machine over preserving abandoned
ambitions."* A T1/T5 Fold-only machine is achievable; a three-algorithm one is
not, on the measured numbers.

## 7. What is not done, stated plainly

This image is **not yet ready to flash**. Two things remain, and neither is a
formality:

1. **The composed renderer's execution is not proven.** The equivalence gate
   proves the composed machine executes the *same instructions* as the
   qualified standalone renderers, and the image gate proves those words are in
   the shipped image. But driving the composed Fold entry directly in the DSP
   emulator returns silence for a fixture the standalone binary renders as
   `-1,-1,-2,-2,…`. This has been narrowed substantially: it is not the
   renderer bodies, not the scratch convention (built and measured), not the
   resonant voices (stubbed out and still silent), not addressing, not
   duplicate labels and not dead code. It is still open.
2. **The control side does not deliver the algorithm selection.** `pk_render`
   has prepare paths for exactly two families (Fold and Simple Drum) and writes
   the record fields the dispatcher reads as zero; the two Resonant families
   have no prepare path at all. So Bass and Snare are not merely over budget,
   they are unselectable in the image as it stands. The exact byte the
   dispatcher must read still needs an end-to-end test to pin down (see
   `DSP_3ALGO.md`).

## 7. Remaining physical-hardware validation

Once (1) and (2) above are closed: flash, then confirm on the unit that T1 and
T5 each select and trigger all three algorithms, that algorithm changes between
events are clean, that retriggering and sequencer operation survive, that T2–T4
and T6–T8 remain ordinary tracks, and that the six retained stock effects still
run on FX1 and FX2. Nothing in this repository can see audio quality, the panel,
or the real unit's timing.
