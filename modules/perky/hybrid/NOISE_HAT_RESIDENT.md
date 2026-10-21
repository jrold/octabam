# Resident Noise Hat and scheduled transport — 20 October 2026

**Resident state and scheduled transport work in the tested model, but this
placement still fails the complete CF deadline.** All three 4,096-frame rows
pass eight-track audio, resident inner-state/native-PCM comparison, bounded
pipeline ownership and loaded-program readback. Peak ISR cost reaches
**380.530 µs**, against **362.812 µs** available. The added source delay is
**48 OT samples (three frames, 1.088 ms)**. This is an opt-in prototype,
not a release, flash candidate or admission of the complete voice layout.

The source checkpoint is `4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus the
uncommitted implementation fingerprints in the [receipt](NOISE_HAT_RESIDENT.json). Work stays
on the user-authorized `perky-cf-dsp-hybrid` branch. PERKY4S remains the
physical reference.

## Transport and ownership

ColdFire retains the original control law and smoothing, the 4,805-sample
classic delay ring, and the native 48 kHz to 44.1 kHz clock. DSP-A owns the
121-word classic state, separate 59-word pulse state, global white-noise
hold/RNG, and the qualified original inner renderers. All limbs initialize
once through the per-core preboot upload. Live packets send control writes
and explicit trigger resets, never evolving phase, envelope, filter or RNG
history. The prefix uses the previous controls; the suffix applies the event.

T6's ordinary source record has 80 halfwords of PCM and 88 of padding.
Commands fit in that padding. The source hook renders the next native block
into a private 24-word mailbox, then resumes ordinary PCM unpack and AMP/FX.
The original source-packet segment lengths must match the CURRENT stock
split, even though the audio itself has been delayed.

The return path uses the existing DSP-A post-FX readback DMA. Stock's packer
at A P:055a stores each 24-bit sample as two halfwords; the low eight bits of
the second halfword are zero. The original unpacker at P:056a discards those
bits. A frame-end hook carries the mailbox's 48 bytes in those padding bits.
At stock transfer state zero, CF extracts and clears the carrier before stock
CF audio processing. No extra HI08 command, DMA transaction or payload word
is introduced, and the new CF path has no polling loop or SR write. Its
interrupt masking is the existing stock transfer ISR's masking.

Sequence tags measure a stable three-frame added audio delay in all rows.
The source produced from command N is packed for playback at N+3. AMP/FX
parameter alignment and backend migration remain unqualified. Exact
inner history and native PCM do not by themselves prove exact delayed
end-to-end track behavior.

## Fit and combined timing

The linked A service uses **1,644 P words**. The full specialized image uses
**2,015/2,404 shared P words**, **758/774 A private P words**, and **1,333 B
private P words** including its previously experimental tail. A claims
**496/616 private X words**, including all initializer padding, and
**2,093/2,139 low-Y words**. All twelve retained FX code/dispatch bytes are
exact against stock. The classic ring remains **9,610 CF bytes**.

Each row runs WT V1 / WT V2 / Slap / Noise Hat, with stock T3/T4/T7/T8,
all twelve retained FX across sixteen slots, actual locks/LFO/scenes and
sustained STATIC card reads. The CF control sets only `pk_nhr_enabled=0` in
the same image and uses the original complete CF Noise Hat renderer.

| Panel mode | Resident peak µs | CF control peak µs | Resident mean µs | Misses resident / CF |
|---|---:|---:|---:|---:|
| M1 white | 377.667 | 392.201 | 242.541 | 10 / 10 |
| M2 metallic | 380.530 | 407.496 | 245.069 | 10 / 10 |
| M3 pulse | 363.284 | 376.777 | 232.533 | 1 / 10 |

These are complete observed ISR maxima, not isolated render timings. The
slowest row exceeds the deadline by **17.719 µs**; pulse still exceeds it by
**0.472 µs**. The evidence does not locate all misses in startup, so none are
discarded. Measured private-stack use is **940/4,096 bytes**, versus 1,256 for
the same-image CF control. No ownership violation, source-DMA overlap or
transport failure is observed.

The three rows check 23,622 native requests, 214,686 generated native samples,
and 12,318 completed return frames without an inner PCM/state mismatch.
Exactly three command frames remain in flight at shutdown. The 52–53 pending
native samples are bounded pipeline contents, not an uncompleted same-frame
transaction; converted native counts equal generated minus pending samples.
No target cleanup wait is used.

## Gates and rejected evidence

The persistent source-parser gate uses one DSP instance across irregular
1/18/7/17/16/3/19-sample requests. All nine original ARM cases compare PCM,
compact continuation state, hold/RNG, and the original complete raw
continuation. The five-tap delay remains the original CF implementation.

An initial isolated gate used clean 16-bit words and missed the live bus's
nonzero upper byte. Stock DMA delivered the marker as `0x034e52`; an unmasked
comparison rejected it. Counts, patch addresses and patch values also require
16-bit masking. The corrected gate poisons every packet word's upper byte
and includes a control patch. This catches the initially blind instrument.
The initial run's absent PCM is NOT proof of bank-handshake interference;
that earlier attribution is retracted. Its timing is not admitted.

A separate failed build/check campaign overlapped writers of common generated
outputs. Those runs do not count; the candidate and shared matrix must be
rebuilt serially. Neither failure is hidden by the final status.

The separate complete-renderer witness runs 1,024 frames per mode on the
same firmware image. Across **3,102 completed source blocks**, the target's
delayed 24-bit source PCM matches the original complete CF renderer (including
the five-tap ring) and an independent rational clock, with **zero source-PCM or
clock mismatches**. This establishes the source stream with its explicit
48-sample delay; it does not align that stream with current AMP/FX events.

The early 422-word X estimate omitted initializer writes and is superseded by
the 496-word ledger above, which includes every initializer and its padding.
No stock AMP initialization/history was changed. Passing the new pulse row
does not close the earlier pulse/stock-AMP dirty-start investigation.

## Reproduction and checks

```sh
.venv/bin/python tools/perky/build_noise_hat_resident_probe.py
.venv/bin/python tools/verify/verify_perky_noise_hat_resident.py
.venv/bin/python tools/verify/build_perky_noise_hat_resident_observer.py
.venv/bin/python tools/verify/measure_perky_noise_hat_resident.py
.venv/bin/python tools/verify/measure_perky_noise_hat_resident.py --reference
.venv/bin/python tools/verify/build_perky_noise_hat_resident_full_observer.py
.venv/bin/python tools/verify/verify_perky_noise_hat_resident_full.py --frames 1024
make check REMIX=perky-machine
REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check
.venv/bin/python tools/verify/verify_perky_noise_hat_resident_campaign.py
```

Run image builds and the matrix serially: they share generated outputs. The
final campaign validator checks all six rows, raw witness hashes, bounded
three-frame pipeline contents, source/stock audio, program ownership and the
complete-source comparison. A zero exit from a measurement driver alone is
not timing admission. The final status is
`FUNCTIONAL_RESIDENT_PROTOTYPE_NOT_TIMING_QUALIFIED`.

`make check` passes **84 shared and four image gates**; project-specific gates
name their skips. All **24 local refhash cases are bit-identical**, without
re-saving the baseline. The shipping bus is restored to SHA256
`354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58`.
The candidate remains `PKNHC1` build 17, MAIN SHA256
`f31a94e7369bd3d30028f76fd85eef761960930223f99a0f6149b2518cc7e296`.

## Measurement scope and limits

Every admitted row must bind the actual candidate image, ELF, observer and
fixture hashes, run the native 264 MHz CF / 132 MHz PIT clock from startup,
exercise four stock STATIC tracks plus WT/WT and Slap, retain all twelve
stock effects across sixteen slots, and include real locks/LFO/scenes/card
activity. The resident-state observer compares each completed DSP state and
native return against an independent host shadow outside target time.

The integrated DSP scheduler uses 4,532 instructions per sample, not
cycle-accurate hardware timing. Private-B tail/guard ownership, dirty-start
lifecycle, algorithm/backend changes, mode transitions, sequence wrap, added
latency and AMP/FX event alignment require further qualification. This
experiment is not a flash candidate or proof of the full 81-choice map.

The diagnostic sequence tag is 16 bits. The current adapter does not handle
its wrap and must not be used beyond the bounded campaign window; wrap-safe
ownership and STOP/Part/Bank migration need implementation before sustained
or physical qualification. The workload pins Noise Hat on V4; live switching
to another V4 algorithm is unsupported by this experiment.
