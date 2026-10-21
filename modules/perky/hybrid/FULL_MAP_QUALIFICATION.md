# Full PERKONS map — PKFM6

**Subsequent performance admission: FAIL.** The
[hardware-informed emulator budget](EMULATOR_BUDGET.md) rejects this unchanged
image on sustained ISR and total CF work. The receipts below establish exact
source behavior and nominal-clock timing at their original scope; they do not
establish that the candidate meets the new working-envelope target.

**Local candidate; physical MKII acceptance pending.** The final qualification
receipt beside this document is authoritative for completion and exact hashes.
PERKY4S remains the hardware-confirmed release. Nothing in this campaign was
flashed, pushed, merged, or committed.

The work continues in the existing `perky-cf-dsp-hybrid` checkout, at source
checkpoint `4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus the implementation
fingerprint in the qualification receipt. G3, G2 and F7 keep their historical
evidence; their narrower admissions are not substituted for this full map.

## Final local outcome

**[Measured, final PKFM6 image]** Every required local receipt passes. The
maximum observed full ISR is **355.337 µs / 93,809 cycles**, leaving **7.475 µs**
against 362.812 µs. It occurs in the lifecycle campaign. This is a thin modeled
reserve; it does not establish physical or whole-CPU headroom.

| Final workload | Observed maximum ISR | Misses |
|---|---:|---:|
| WT/WT + Slap + white Hat | 323.905 µs | 0 |
| WT/WT + Slap + metallic Hat | 326.280 µs | 0 |
| WT/WT + Slap + pulse Hat | 311.792 µs | 0 |
| WT/WT + Slap + Noise/Tone | 324.727 µs | 0 |
| WT/WT + Slap + Acoustic Hats | 329.140 µs | 0 |
| 243-tuple layout sweep, 160,096 frames | 349.129 µs | 0 |
| 324-tuple Cartesian-mode sweep, 247,902 frames | 337.508 µs | 0 |
| Lifecycle, 53,189 frames and 22 handoffs | 355.337 µs | 0 |
| Actual scene/fader controls | 327.561 µs | 0 |

Every independent source/defined state/RNG/clock/feedback mismatch counter is
zero. The lifecycle witness checks 35 old-generation feedback deliveries before
retirement; the shadow queue peaks at 195/1,024 with no overflow. It deliberately
enters a Part on NT, selects its first Hat later under CF ownership, then hands
it back to A. Both final source/import/embed register canaries and all 17
external-PCM split canaries pass their actual stock source-tail ABI.

Each fixed row runs 16,384 frames with all eight source/post-FX chains active,
actual STATIC card reads and exact loaded private/custom-shared P. Three FX
arrangements include Plate/Compressor on both cores and in FX1. The fresh
`PERKYF6/RIG` handoff project also passes an independent 512-frame playback and
full target asset-byte comparison. Source snapshots, logs and final hashes are
bound in the JSON receipt.

## Voice contract and placement

| Track | Voice | ALGO 1 | ALGO 2 | ALGO 3 | Source processor |
|---|---|---|---|---|---|
| T1 | V1 | Fold Drum 1 | Wavetable V1 | Simple Drum | ColdFire |
| T2 | V2 | Fold Drum 2 | Wavetable V2 | Complex Drum | ColdFire |
| T5 | V3 | Resonant Drums | Slap | Karplus | ColdFire |
| T6 | V4 | Noise Hat | Noise/Tone | Acoustic Hats | Noise Hat on DSP-A; alternatives on ColdFire |

All twelve choices have three panel modes. SRC remains TUNE, DECAY, ALGO,
PAR1, PAR2, MODE, including event-split ALGO/MODE locks. Mode indices in local
receipts are zero-based; panel values are 1–3. Noise Hat maps panel indices
`0,1,2` to original firmware modes `1,0,2` (white, metallic, pulse).

The two WT objects share immutable tables and retain independent histories.
Every algorithm keeps its own history within a Part generation. RNG belongs
to the logical voice, including switches between Hat and its CF alternatives.
The 48 kHz native clocks and exact 44.1 kHz conversion apply to every source.
Original initializer/control/render streams are the audio oracle.

The earlier paired DSP-B experiment remains a measured rejection against its
conservative source allowance, not a physical impossibility claim. The final
placement uses the measured CF alternatives. DSP-B resumes its original stock
source path. Additional DSP portfolios, cross-core PCM forwarding, WT service,
and SRAM relocation are not dependencies of this candidate.

## DSP transport and memory

**[Measured assembled/upload facts]** Custom DSP code occupies **2,220/2,404
shared P words**, leaving 184. It uses no private-P donor or upper-tail space.
DSP-A reserves **564/616 private X words**, including the original initializer,
and **2,093/2,139 low-Y words**. Shared storage is counted once. The complete
stock program/data and both FX dispatch tables are checked independently in
each final upload, except the explicit startup/source/readback hooks.

Removing the unused B oscillator portfolio and placing startup-preservation
helpers in shared P restores **all fourteen stock effects**, including Plate
Reverb and Compressor. Whole-machine rows use all fourteen in sixteen slots;
three arrangements exercise Plate/Compressor on opposite cores and in FX1.
Loaded private/custom-shared P is read back after playback. The four stock
packer-mask literals are checked against their documented runtime values.
Inherited stock shared upload ranges at P `0x30000`/`0x38000` are mutable
after boot. They are excluded from the post-boot custom-program identity
comparison; the separate upload-byte check covers their initial contents.

Hat histories, delay arithmetic and resampling stay resident on A. The
4,805-sample feedback ring stays on CF. Existing source DMA padding carries
commands/taps or exact external CF PCM for each half of the current frame.
Existing readback padding carries ring feedback; the carrier is stripped before
stock CF audio readers. There are no added transfers, source-latency blocks,
live history round-trips, synchronous HI08 RPCs, or added audio IPL7 holds.
The tests check feedback contents and generations before retirement.

The interruptible main-task shadow supplies nonblocking backend handoff.
Source ownership changes only after pending jobs retire and the appropriate
state/clock imports finish. A first Hat use after a generation began on another
algorithm resets the ordered shadow and exports **all three** Hat limbs before
cutover. The lifecycle gate exercises that case through actual selector
publication. Queue overflow, transport and clock-error counters must stay zero.

## Card footprint and saved projects

**[Measured]** The final card wrapper is **934,480 bytes**, below the stock
**1,048,588-byte** limit. Both upgrade paths round-trip to MAIN SHA256
`c062f9232949f0073198b5e073c2948558275ff1d02f716054d82b9a314bfa77`.
The actual card checksum rejects corruption. The preceding embedded-sample
PKFM3 image exceeded the card limit and was never admitted as a handoff.

Acoustic Hats needs the supplied **`/PERKYAH.DAT`** companion file: 452,124
bytes including its 16-byte version/length/CRC header. It holds the exact
original closed/open/ride PCM, without resampling, quantization or synthesis
changes. The UI task reads bounded 4,096-byte chunks and publishes readiness
only after the expected payload CRC. No file operation runs in the source
callback. Whole-machine playback compares every loaded target asset byte.
Native injected-I/O negatives check missing/corrupt/truncated inputs and
publication bounds. Repeated linked-CF boot initialization invalidates readiness
and clears all three buffers, including when the prior loaded cookie was READY.

Without a valid file, Acoustic Hats stays silent; the other choices remain
available. Initial loading begins while transport is stopped. Put the file in
the card root before booting this candidate. The stock buffered reader may
return bytes from sector padding after the logical file end; the loader checks
the declared payload and CRC, and the handoff pins the complete file SHA256.

This map uses **PK/2** project signatures. PK/1 is not silently reinterpreted.
Creating a machine over legacy bytes seeds the new layout's defaults; reselecting
a complete PK/2 signature preserves its six controls. No user project is
automatically edited. The handoff supplies a fresh `PERKYF6/RIG` SET. Preserve
older projects for their original firmware. Automatic legacy conversion is not
claimed.

## Evidence and limits

The compact JSON binds the final MAIN/runtime/uploads, source snapshot,
individual receipts and final upgrade wrappers. The local output retains the
full reports and logs under `out/perky/hybrid/full-map-release/`.

- Actual linked CF plus final DSP parser: 81 layouts × three mode tuples × all
  17 splits, plus 24 directed within-voice algorithm transitions: **5,355 frames**.
  Active raw CF state, all valid resident Hat limbs, PCM, RNG/holds and clock are
  compared with independent original streams.
- Mixed DSP parser: **1,224 frames**, Hat prefix/suffix, every split, three modes,
  three control corners, signed external PCM and poisoned unused wire bits.
  Separate persistent/import/arithmetic/epoch-reset gates check the final upload.
- Whole-machine layout matrix: every one of the **243** staged algorithm/mode
  tuples must actually arrive through sequencer locks and panel pattern changes.
- Additional mode campaign: the full **81 mode tuples** for each of four
  demanding layouts: WT/WT/Slap/Hat, Fold1/Fold2/Resonant/Hat,
  WT/WT/Slap/Acoustic, WT/WT/Resonant/Noise-Tone (**324 tuples**).
- Five sustained 16,384-frame WT/WT+Slap rows cover all Hat modes and both T6
  alternatives, eight active source/post-FX chains, STATIC card reads and all
  fourteen effects. Separate actual scene/fader, lifecycle and saved-project
  reload gates remain required. The oracle is PERKY source PCM/state; whole-project
  post-FX bit identity across UI actions is not asserted.
- The lifecycle witness compares every rendered PCM sample, side state,
  defined native clock and pending feedback. Resident Hat state is compared
  while the independent original engine marks it initialized in the current
  generation. Inactive, not-yet-initialized old raw bytes are undefined; the
  first subsequent Hat use must match its own pristine initializer in full.
- Repository floor: `make check REMIX=perky-machine`. Build regression floor:
  `REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check`, all 24 configurations.

**[Measurement scope]** These are CPU264/PIT132 instruction/cycle-model
observations with read-only independent witnesses. They are not a silicon WCET
bound, a 20% whole-CPU reserve, or exhaustive Cartesian control/mode coverage.
The additional mode campaign covers four specified layouts, not all 6,561
algorithm/mode combinations. Event controls and renderer vectors expand
offline; physical cache, SDRAM/card/DMA arbitration, DSP prefetch/rotation
contention and UI responsiveness still need the single consolidated MKII run.
A nonzero mismatch/miss/overflow, lost stock track, or measured physical overrun
would falsify the corresponding admission claim.

## Reproduce locally

```sh
.venv/bin/python tools/perky/build_perky_full_map_card.py
export PERKY_FULL_MAP_WORK="$PWD/out/perky/hybrid/full-map-release"
.venv/bin/python tools/verify/build_perky_full_map_observer.py
```

Run the named receipt drivers above on that work directory, then the final
qualification aggregator and packager. Do not infer qualification from the
builder's `BUILT` label or wrap an earlier CF-only intermediate image. The
hardware handoff contains one final firmware version and one procedure.
