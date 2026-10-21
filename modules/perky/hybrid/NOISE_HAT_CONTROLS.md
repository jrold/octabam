# Profiled Noise Hat control settling — 20 October 2026

**PKNHE1, build 19, meets the modeled deadline in all three Noise Hat modes**
with WT V1 / WT V2 / Slap, all eight tracks and all twelve retained stock FX.
Each mode runs 4,096 transport frames. The slowest observed ISR is
**327.299 µs**, leaving **35.513 µs** against the **362.812 µs** deadline.
This is a bounded local model result, with no hardware qualification or flash.
Work remains on the user-authorized `perky-cf-dsp-hybrid` branch. PERKY4S is
still the physical baseline. The [receipt](NOISE_HAT_CONTROLS.json) binds the
image, ELF, instruments, raw witnesses and uncommitted source fingerprints.

## What the missed frames spend

A host-only instruction observer attributes actual modeled CF cycle deltas to
linked function ranges within each complete audio ISR. It reads the existing
cycle counter; it inserts no target timer calls or peripheral reads. Frame
bucket sums equal the existing safety observer's complete ISR counts,
including entry/RTE overhead. All nine white and ten metallic misses are
retained, including the first frame. The profile reproduces PKNHD1's original
maxima exactly: **97,902 / 98,336 cycles**, or **370.841 / 372.485 µs**.

The worst white frame spends **13,987 cycles** in `nh_update` and
`nh_common_update`, versus 2,902 in packet emission. Metallic spends **14,005
cycles** in `nh_update` on its worst frame. These bursts come from sixteen
complete control updates after a dirty control event, followed by a trigger
and seventeenth update. Repeated envelope/pitch/filter/oscillator derivation,
rather than ring-tap transport, is the measured avoidable bottleneck.

The optimized white profile has the same 85,758-cycle maximum as its normal
run. Its named control buckets total **2,300 cycles**, including the new
control function's dispatch and smoothing. Stock-code cost changes only from
51,686 to 51,672 cycles on that frame. Total ISR reduction is **12,144 cycles
(46.000 µs)** relative to the historical image.

## Preserve the recurrence and the attack lag

The opt-in header `cf_noise_hat_controls.h` batches fifteen updates of the
wrapper and active limb's four smoothed values using the existing exact
integer recurrence. It retains the final full `nh_update`. The limb's attack
parameter at `+0x0a` must contain the **penultimate smoothed PARAM2**, because
the original common update derives attack before replacing that parameter.
The header writes that penultimate value before the surviving sixteenth
update. The original trigger and seventeenth update remain afterward, in
order; the sixteenth update therefore still uses the previous note.

The intermediate derived fields have no feedback into later control updates
apart from that attack lag. The complete raw-state gates check this claim;
they do not assume fixed envelope configurations, notes, mode or smoother
initialization. Existing `common_smooth_many` uses its exact bounded shortcut
where applicable and the original recurrence for arbitrary 32-bit values.
No waveform, envelope, RNG, delay or resampling arithmetic changes.

The builder changes only an ignored generated copy of the control path. The
original `cf_perky4.c` and shipping build remain unchanged. `prepare_nh` is
outlined so the target control call has an observable pre/post boundary, and
`pk_nhf_enabled=0` retains the original sixteen updates in the same image.
Outlining and changed CF layout also affect timing: this unbatched control
is **not** the old PKNHD1 binary. Both comparisons are kept below, so the
historical improvement is not attributed entirely to batching.

## Sustained combined workload

Each row includes stock T3/T4/T7/T8, all twelve retained FX across sixteen
slots, real locks/LFO/scenes and continued STATIC card reads after PLAY.
CF uses the verified native clock: 264 MHz / PIT 132 MHz. The DSP scheduler
remains 4,532 instructions/sample, not cycle-accurate hardware. No startup or
first-trigger samples are excluded from the maxima or deadline counts.

| Panel | Optimized peak µs | Same-image unbatched peak µs | Full-CF peak µs | Misses optimized / unbatched / CF |
|---|---:|---:|---:|---:|
| M1 white | 324.841 | 362.053 | 382.015 | 0 / 0 / 10 |
| M2 metallic | 327.299 | 370.102 | 403.485 | 0 / 9 / 10 |
| M3 pulse | 316.902 | 355.799 | 373.636 | 0 / 0 / 10 |

The same-image batching reductions are **37.212 / 42.803 / 38.898 µs** at
the observed white/metallic/pulse maxima. Optimized mean ISR costs are
**232.409 / 234.849 / 222.413 µs**. Private-stack use remains **940/4,096
bytes**, versus 1,212 for the full-CF controls. The complete-CF rows disable
both offload and batching; the unbatched rows disable batching alone.

Both DSP uploads are **byte-identical to PKNHD1**. A still uses 1,940 P words;
shared P is 2,308/2,404, A private P 761/774, private X 513/616, and low Y
2,093/2,139. All twelve FX retain exact code/dispatch bytes. The CF ELF gains
2,900 text/rodata bytes, four loaded data bytes and four BSS bytes, including
the retained unbatched comparison and counters. Its existing arena still fits.
The CF ring and stock source/readback DMA protocol are unchanged. Feedback
still returns three frames later, while source PCM has **zero added queue**.

## Exactness and verification

The host differential starts from all fifteen captured Noise Hat corners and
compares the entire 11,736-byte object, control history, rendered PCM, dynamic
state, ring, hold and RNG. **2,880 calls and 24,525 native samples** agree across
repeated and fresh controls, triggers, mode/note changes, arbitrary 32-bit
smoother values and 16-bit envelope configurations.

A separate live observer copies the target's complete pre-control shadow,
executes the original sixteen-update control routine independently, and
compares every raw byte and control-history field when the ColdFire call
returns. It also retains the existing current-source PCM, state, exact
rational clock, feedback and committed-ring witnesses. Thus the audio oracle
cannot silently accept an incorrect control update by taking its output as
the reference input.

The six offload rows (optimized and unbatched) check **24,651 ColdFire control
calls** and **24,639 current source frames**, with zero control, source-PCM,
state, clock, feedback or ring mismatches. Optimized rows alone check 12,325
control calls and 12,319 source frames. All nine rows pass active eight-track
audio, loaded-program readback, private-stack ownership and DMA gates. The
previous 720-frame / 2,560-vector DSP gate is reused by exact upload identity.

Local checks:

- `verify_perky_noise_hat_controls.py`: full raw-state/PCM differential passes.
- `verify_perky_noise_hat_fast_campaign.py`: binds both old profiles, optimized
  profile, all nine sustained rows and their surviving raw witnesses.
- `make check REMIX=perky-machine`: 84 shared and four image gates pass;
  project-specific gates skip without `OT_PROJECT`.
- `REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check`: all 24 shipping
  configurations bit-identical to the existing local baseline; no re-save.
  Shipping bus SHA256 is restored to
  `354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58`.

Reproduce with `build_noise_hat_fast_probe.py`,
`verify_perky_noise_hat_controls.py`, `build_perky_noise_hat_fast_observer.py`,
and `measure_perky_noise_hat_fast.py --frames 4096`, then repeat with
`--unoptimized` and `--reference`. `profile_perky_noise_hat_taps.py` profiles
the preserved PKNHD1 image, or the new image with `--controls --source ...
--work ...`. Shared-output builds run serially. No firmware bytes, release
wrapper, commit, push or flash are added by this experiment.

At this stage STOP/Part/Bank transitions, mode/backend migration, long
sequence-wrap runs, private-B tail behavior and physical timing remained
unqualified. The result admits this three-mode combined workload in the tested model; it is not a
hardware release or qualification of every voice-family combination.

The subsequent [lifecycle campaign](NOISE_HAT_LIFECYCLE.md) covers scoped
STOP/START, Part/Bank navigation and all directed mode pairs, reproduces these
fixed-mode timings, and rejects live backend switching with six target
transport failures. Its dynamic audio proof stops at the first departure;
stateless CF arithmetic is checked separately. Production selector/generation
semantics and physical qualification remain open.

The later [PKNHF7 handoff](NOISE_HAT_HANDOFF.md) supplies the nonblocking
backend protocol and continuous author-stream proof. The PKNHE1 timing and
DSP-identity measurements above remain historical results for that image.
