# Assembly orchestration and Slap loops: PKFM28–PKFM31 — 21 October 2026

**PKFM31 is the best candidate and still fails the fixed performance budget.**
All eight sustained rows keep exact original-reference synth PCM, DSP Hat
state, side words, clocks and feedback. Steady ISR means fall a further
3.5–6.2 µs from [PKFM26](KERNEL_CF_QUALIFICATION.md) (worst row 193.10 →
186.88 µs; 214.98 µs at PKFM21). All eight rows now meet both ACK ceilings
(five did at PKFM26). Every row still fails the steady mean, p99, p99.9, full
peak and total-CF ceilings. The verdict is
`FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK`. No hardware flash was made or
authorized.

The [machine-readable receipt](ORCHESTRATION_CF_QUALIFICATION.json) has every
row, image hash, gate and floor. Times are modelled CF264/PIT132 microseconds
under the frozen observer (`f975b4d2…`) and the unchanged budget (`8608844b…`).

## Candidates

Each candidate is a new layer and work directory over PKFM26's builder
(`tools/perky/build_perky_kernels_cf.py`, which now applies every selected
transform of a unit in `PERKY_KERNELS` order); earlier outputs are untouched.
Algorithms, native clocks, packet formats and the stock path are unchanged;
both DSP uploads and `PERKYAH.DAT` are byte-identical to PKFM26, as are
data/BSS. PKFM31's CF text is 586,460 bytes (+1,538). MAIN SHA256
`77c70410327245324a30bf453dca0d5d092341bdd10ad31f382fac3b476982a9`, ELF
`0d2261861e856404901df2d61f75ed81578c6044cd5043243fc52fcf2d9b4b3a`. Each assembly body is pinned to the C it mirrors: its
generator refuses to build when that C text (by SHA-256) or its anchor
changes.

| Version | Change | Worst-row mean (µs) | Verdict |
|---|---|---:|---|
| PKFM26 | Previous best ([kernel campaign](KERNEL_CF_QUALIFICATION.md)) | 193.10 | baseline |
| PKFM28 | `placement_prepare` and `placement_segment` in assembly (`cf_placement.s`) | 191.25 | kept |
| PKFM29 | + Slap chunk loops in assembly (`cf_slap_render.s`) | 188.16 | kept |
| PKFM30 | + `pk_render` dispatcher in assembly (`cf_render.s`) | 187.42 | kept |
| PKFM31 | + boundary no-op and V4 merge predicates in assembly (`cf_placement_predicates.s`) | **186.88** | **best** |

**Placement seams (PKFM28).** The frozen oracle steps at `placement_prepare`
entry and at `placement_segment` entry and return, so both keep their symbols,
arguments and call positions. The assembly takes the unchanged-control prepare
(still calling `placement_production_event`) and a non-empty traced-off
segment outside Acoustic Hats with the native need inlined, calling the
Wavetable, Slap or Noise/Tone renderer directly and every other engine through
`pk4_render`. Every other case jumps, stack untouched, to the original C
(`placement_prepare_slow`, `placement_segment_c`). Struct offsets come from
absolute symbols the placement unit exports (`offsetof` through `%c`
operands).

**Slap loops (PKFM29).** For 1–20 samples with all tables present, the chunk's
noise source and 64-bit LCG, the counter walk (a run at a time instead of a
sample at a time, with the same envelope-block segments at each retrigger),
the >>16 envelope scale and the velocity saturation run in assembly around the
same filter, envelope block and delay-span callees and the same EMAC context.
All 581 captured Slap vectors (8,715 native samples) replay exactly against the
captured PCM, object and RNG; `cf_cycle_bench` puts the chunk at 266.6
cycles/sample against 301.3 for the PKFM26 C (comparison only, not admission
evidence).

**Dispatcher (PKFM30).** `pk_render` decides from memory reads alone (placed
voice, signed project slot, placement bit, bounds) and otherwise jumps to the
C, now `pk_render_c`. Its body and the five helpers it inlines are pinned; the
control unit's statics and project constants are exported as symbols. The
gain was 0.74 µs, well under the estimate: the per-instruction profile below
shows the dispatcher already near one cycle per instruction, so its cost was
work, not compiler overhead.

**Predicates (PKFM31).** `placement_boundary_noop` and
`placement_v4_merge_eligible` are pure reads; the assembly evaluates the same
terms. The dispatch differential reports identical merge counts (per-voice
whole-frame segments and V4 merges) to PKFM30 at every checkpoint.

**Reproduction (measured, with a correction to the PKFM26 record).** The
committed `tools/perky/generate_cf_v4_merge.py` (SHA-256 `cba1bcd4…`) is the
revision PKFM27 was built from, with `placement_v4_view` unrolled; PKFM26's
BUILD.json records `34864041…`, the earlier loop form, which is not in git
(its generated `placement-v4-merge.c` is retained in `full-map-kernels-v3/`).
[The PKFM26 receipt](KERNEL_CF_QUALIFICATION.json) lists the committed hash, so
it does not identify PKFM26's actual input. Built from the committed tree,
PKFM26's selection gives MAIN `f6778cb4…` / ELF `af2434ae…`, not PKFM26's
`e9502d2c…`; that image is unqualified. The same MAIN and ELF come from the
committed builder and from the new ordered-transform builder, so that change
alters no existing selection. PKFM28–PKFM31 were built from the committed
generator revision.

## Measured rows (32,768 blocks, WT/WT, four stock tracks, all 14 FX)

| T5 / T6 | PKFM26 mean | **PKFM31 mean** | p99 | p99.9 | peak | total CF | ACK p99 | ACK peak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Resonant Bass / metallic Hat | 179.91 | **176.25** | 186.15 | 283.75 | 289.13 | 202.14 | 327 ✓ | 351.5 ✓ |
| Resonant Bass / Noise/Tone | 187.45 | **183.86** | 194.64 | 288.49 | 292.81 | 209.70 | 326 ✓ | 343.2 ✓ |
| Resonant Snare / metallic Hat | 179.92 | **176.41** | 186.35 | 285.68 | 290.54 | 202.31 | 328 ✓ | 352.0 ✓ |
| Resonant Snare / Noise/Tone | 187.57 | **184.06** | 195.01 | 290.30 | 294.64 | 209.92 | 326 ✓ | 344.7 ✓ |
| Snare/Bass MODE locks / metallic Hat | 179.90 | **176.30** | 186.19 | 285.16 | 289.79 | 202.20 | 328 ✓ | 351.3 ✓ |
| Snare/Bass MODE locks / Noise/Tone | 187.48 | **183.93** | 194.80 | 290.01 | 294.47 | 209.78 | 327 ✓ | 343.2 ✓ |
| Slap / metallic Hat | 185.52 | **179.39** | 188.62 | 278.33 | 284.82 | 205.26 | 327 ✓ | 348.2 ✓ |
| Slap / Noise/Tone | 193.10 | **186.88** | 196.84 | 282.77 | 287.12 | 212.72 | 325 ✓ | 345.9 ✓ |
| **Ceiling** | | **158.21** | **166.78** | **237.73** | **250.71** | **189.30** | **328** | **362.2** |

Every row reports 32,768 source frames per CF voice (32,766 for V4), zero PCM,
DSP state/side/clock and feedback mismatches, zero oracle errors and zero
transport failures.

## Where the worst row's time goes (measured, PKFM26 and PKFM30)

Read-only diagnostic observers beside the frozen cost observer
(`tools/harness/perky_cf/diagnostic/`), each valid only because its profile
reproduced the unprofiled control row's steady mean exactly (193.10 µs for
PKFM26, 187.42 µs for PKFM30):

- **Stock code is 96.9 µs per frame and diffuse** (`full_map_stockpc_observer.h`,
  256-byte PC bins). No bin exceeds 4.7 µs. The eight-track DELAY routine
  (0x40003100–0x400038ff) is 15.9 µs, 0x40004000–0x40004eff 13.1 µs, and
  0x4000cf00–0x4000d0ff 8.5 µs (the region `docs/firmware/LFO.md` cites as the
  inline LFO engine; the label is inferred from that citation). The stock
  p-lock copy at 0x4000c400–c6ff is 0.1 µs in steady state.
- **A per-track attribution did not work** (`full_map_track_observer.h`). Its
  contexts, entered at 0x400068e4 and 0x40005ff0, held 7.1 µs of stock and none
  of PERKY's runtime, and 0x40005ff0 was never entered. Those contexts do not
  contain the per-chunk source path, so the observer cannot say how much stock
  work is done per track; treat its per-track figures as unmeasured.
- **PERKY's own code is 90.2 µs per frame at PKFM30** (`full_map_pcbin_observer.h`,
  per instruction). The synthesis kernels (Noise/Tone 13.7, Wavetable 10.6 plus
  its frequency pass 2.1, the Slap delay span 7.0 and filter 6.1, the shared
  envelope 5.6, Slap 3.2) total about 48 µs and run near one instruction per
  cycle. The native converter is 5.2 µs, `pk_render` 8.5, `pk_nhr_frame` 5.2,
  placement prepare and segment 4.9, and the earlier stock replacements
  (DELAY mix, source mix, position) 6.8.

## What is left (inferred)

The worst row is 28.7 µs above the steady-mean ceiling. The remaining
micro-gains found in the profile are small: a precomputed phase sequence in
the converter (~1 µs), 32-bit copies of `pk_nhr_frame`'s packet tail
(~0.5 µs), and the Noise/Tone kernel's shift and round-toward-zero idioms
(~2–3% of 13.7 µs). Together they are about 2 µs. Moving multiplies onto the
EMAC unit would look free only because the port charges A-line EMAC opcodes
zero cycles; like the predictor quirk, that is a model artifact and was not
used. Closing the gap within this architecture therefore needs a structural
change the brief does not yet authorize, such as synthesis on DSP-B
([feasibility](DSP_B_FEASIBILITY.md)); that is the user's decision.

## Gates and floors (PKFM31)

On the PKFM31 image: direct source (5,355 frames, 81 layouts), linked kernels,
CF/DSP state handoff (800 frames), DMA startup, merged segments (11,664
frames: 8,253 merged, 3,411 split), dispatch differential against PKFM21
(1,500 frames, 543 trigs, 7 part changes, 366 V4 merges), lifecycle (52,706
frames, peak 311.11 µs; PKFM26 316.76), the 243-tuple production matrix
(160,054 frames, none missing, peak 329.24 µs; PKFM26 331.38) and scenes
(9,155 frames, peak 282.58 µs; PKFM26 291.99) all pass. The captured WT,
Slap and Noise/Tone vectors (3,441 / 581 / 1,153 calls) replay exactly
against PKFM31's linked image. The default floors (`make check
REMIX=perky-machine`, `scripts/refhash.sh check` with 24 configurations
bit-identical, and `make bus REMIX=perky-machine` restoring the shipping
image) are recorded in the receipt's `default_floors`.
