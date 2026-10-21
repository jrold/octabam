# Noise Hat delay arithmetic and resampling on A — 20 October 2026

The opt-in **PKNHD1**, build 18, moves delay arithmetic and resampling onto
DSP-A, while retaining the original 4,805-sample ring on ColdFire. It removes
the previous resident experiment's **48-sample added source queue**. This is
relative to the existing stock source DMA schedule, not a measurement of
physical input-to-DAC latency. The [receipt](NOISE_HAT_TAPS.json) binds the
image, runtime, local instruments, source checkpoint and uncommitted sources.
The user-authorized branch remains `perky-cf-dsp-hybrid`; PERKY4S is still the
physical baseline.

## Current source, delayed feedback

CF preserves the original control law, smoothing and raw control shadows.
A retains the original classic/pulse compact histories and white hold/RNG.
The complete T6 source record carries commands and delay taps, rather than
80 halfwords of PCM followed by commands. The hook renders both sides of the
CURRENT stock split, applies the original native delay arithmetic, resamples
that block, and jumps directly to stock AMP/FX at A P:0426. It advances the
stock source-ring cursor and discards the seam JSR return as the existing
PERKY source contract requires. Other tracks use their existing source path.

Each segment carries its OT count, firmware mode, trigger/mute flags, delay
mix, controlled-field patches and five ring taps per newly generated classic
sample. Evolving synthesis state never makes a round-trip. At most 20 native
samples and 23 control/reset patches require **154/168 halfwords**: two frame
headers, six segment headers, 46 patch halfwords and 100 taps. Pulse needs no
taps. The builder preserves all twelve retained stock FX code and dispatch
bytes, and the live packet writer counts any overflow as a failure.

A returns up to twenty **feedback ring-write samples**, with tag/sequence/count,
through the same 24-word mailbox and discarded readback padding as the prior
resident experiment. CF extracts and clears those bytes at stock DMA state
zero, then commits writes to their reserved ring positions. No extra host
command, DMA transaction, transferred word, polling loop or CF SR write is
introduced. The original stock transfer ISR retains its normal masking.

CF advances a logical ring cursor when it emits taps; a separate cursor records
committed feedback. The fixed taps are 573, 1201, 1538, 3139 and 4804 samples.
The production guard conservatively requires fewer than 573 pending writes,
so requested taps cannot depend on unreturned feedback. A trigger resets the
native PCM FIFO, not the delay ring. Pulse and wrapper mute do not advance the
classic ring. Fixed tap/gain configuration is checked against the original
initializer. STOP/Part/Bank changes, mode/backend migration and long sequence
wrap remain outside this bounded experiment.

## Exact arithmetic and memory

The five stage gains remain 1, 1, 3, 5 and 7, with the original arithmetic
shift, clamp to ±32767, final dry/wet sum and signed16 wrap. Each stage's
absolute coefficient weights sum to 16, so signed24 arithmetic suffices before
the shift; the dry/wet sum uses the DSP's wide accumulator. The ring consumes
**9,610 CF bytes**, with no DSP ring allocation.

The old DSP clock's fractional coefficient table allows a one-source-LSB
approximation. This prototype uses that table only to estimate the quotient,
then computes `D*phase-147*q` and corrects it, preserving exact floor division
by 147. The shipping clock is unchanged. A poisoned-halfword test also caught
stale B2 after masking a patch count; masked accumulator values are now
reloaded cleanly before use. Both failures and their gates are recorded in
[the trap register](../../../docs/contributing/TRAPS.md#trap-dma-halfword-a2).

A uses **1,940 P words**. Together with B specialization, shared P uses
**2,308/2,404 words** (96 free), A private P **761/774** including the startup
clear helper, and B private P **1,333** including its candidate upper tail.
A private X claims **513/616 words**, including all initializer padding;
low Y uses **2,093/2,139 words**. Actual linked shards and uploads are checked,
not estimated from source lengths. The private-B tail and hooks remain
hardware-unqualified.

The persistent source gate covers all nine original ARM cases, 720 complete
frames, all 17 stock splits, and varied poison in every packet word's upper
byte. Native continuation still matches the captured ARM PCM. Current source
PCM, resident state/hold/RNG, clock phase/carry and ring writes match the
original complete CF renderer plus independent rational clock exactly.
Another **2,560 actual-DSP delay vectors** cover signed extremes, clamps,
dry/wet endpoints and wrapping. A separate CF ring model commits feedback
three frames later and verifies every supplied tap; the actual production
pending guard is tested at and beyond its boundary.

## Combined workload

**Pulse meets the tested model deadline; white and metallic still fail it.**
Each of the three candidates and three same-image CF controls runs 4,096
transport frames. Each panel mode uses WT V1 / WT V2 / Slap / Noise Hat, stock
T3/T4/T7/T8, all twelve retained FX across sixteen slots, real locks/LFO/scenes
and sustained STATIC reads. The CF control changes only `pk_nhr_enabled` in
the same image. Current source PCM is observed on DSP-A before AMP, separately
from control/tap records; feedback and the committed CF ring have independent
complete-renderer witnesses. Model CF clocks are 264 MHz / PIT 132 MHz;
the DSP scheduler remains 4,532 instructions/sample, not cycle-accurate silicon.


| Panel | A peak µs | CF peak µs | A mean µs | Deadline misses A / CF |
|---|---:|---:|---:|---:|
| M1 white | 370.841 | 390.989 | 233.984 | 9 / 10 |
| M2 metallic | 372.485 | 406.053 | 236.181 | 10 / 10 |
| M3 pulse | 358.504 | 376.553 | 223.936 | 0 / 10 |

The deadline is **362.812 µs**. The white and metallic maxima exceed it by
8.029 and 9.673 µs. Pulse has 4.308 µs of observed margin; this is a model
finding, not hardware admission. No startup or first-trigger misses are
removed. The all-mode complete voice layout therefore remains unqualified.
Private-stack use peaks at **940/4,096 bytes**, versus 1,212 for the CF control.

Across the candidate rows, **12,320 current source frames**, 214,669 submitted
native samples and 23,620 native segment requests have zero source-PCM,
resident-state, feedback, clock or committed-ring mismatches. All eight audio
chains remain active, STATIC reads continue after PLAY, loaded private/shared
program words match the uploaded image, and no DMA short transfer, restart,
read/write overlap, stack ownership or guard failure occurs. Feedback remains
three stock frames behind submission. The largest pending count at a tap
read is 52, well below the guard's 573-sample boundary; pulse uses no ring taps.
The tag comparison binds the source PCM to the CURRENT submitted control
frame before AMP, rather than deriving audio latency from feedback lag.

Local verification:

- `tools/verify/verify_perky_noise_hat_taps.py`: nine ARM cases, 720 source
  frames, 2,560 actual-DSP arithmetic vectors and production guard boundaries.
- `tools/verify/verify_perky_noise_hat_taps_campaign.py`: all six sustained
  rows and their surviving raw witnesses, hashes, program readback and clocks.
- `make check REMIX=perky-machine`: 84 shared and four image gates pass;
  project-specific gates skip without `OT_PROJECT`.
- `REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check`: all 24 shipping
  configurations bit-identical against the existing local baseline, which was
  not re-saved. The shipping bus image is restored to SHA256
  `354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58`.

Reproduction uses `build_noise_hat_taps_probe.py`,
`build_perky_noise_hat_taps_observer.py`, the persistent gate, and
`measure_perky_noise_hat_taps.py --frames 4096` with and without `--reference`.
Run shared-output builds serially. No firmware bytes or flash wrapper are
stored in the source tree. Generated image and ELF hashes are in the receipt;
this remains a local feasibility prototype, with no commit, push or flash.
