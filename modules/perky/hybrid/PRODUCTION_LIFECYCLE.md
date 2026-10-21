# Four-voice production lifecycle qualification

**PKNHG3 passes the production reset scope in the local instruction/cycle model.**
WT/WT + Slap + Noise Hat now preserve exact source audio through production
Part/Bank generation resets and CF/DSP-A backend changes. Both lifecycle runs,
all three 16,384-frame stock-workload rows, rapid backend switching and
save/cold-reload have zero
deadline misses. The worst measured frame is **349.439394 µs** against
**362.811791 µs**, leaving **13.372397 µs**, versus G2's 4.902700 µs (2.7× the measured reserve). This remains an opt-in
prototype. Hardware timing and V4 alternative Noise Tone dispatch are unqualified.

The [machine-readable receipt](PRODUCTION_LIFECYCLE.json) binds the actual
MAIN image, ELF, uploaded programs, observers, original references, executed
inputs, source hashes and local verification logs. MAIN SHA256 is
`93b858b0b367e768df7065652bdeaffa1b8e01cd6434e2bf7829b7ea9405a730`; runtime ELF SHA256 is
`f74d24ece762b0b7f992e99b57ad76908d561889c8436d1c725c31fc7d5e7182`. No firmware bytes are included in this document
or its receipt. The physically tested release baseline remains PERKY4S.

## Coherent reset and retirement

The candidate reuses the original production Bank/Part observer and staged
six-control ABI. ALGO maps through the family-local table; MODE is bounded by
the descriptor. UI ticks do not own synthesis resets. Audio renders the old
prefix, resets at the production event, then renders the new suffix.

Each Hat segment carries a generation in CF job metadata. A spare header bit
requests a resident DSP reset before the new segment's control patches. DSP-A
reconstructs all three original compact limbs from build-generated initializer
constants, resets hold/RNG and the native clock, and retains current-block
rendering. CF resets its control state and delay ring at the same event. The
scheduled source/readback DMA transport adds **zero words**, no source latency,
no blocking RPC and no new IPL7 hold.

The interruptible shadow consumes old work in queue order, then resets itself
at the marked half-frame. Neither producer nor consumer counters are reset to
hide pending work. Late feedback is still checked and retired; generation
comparison prevents it from writing into the new ring or cursor. CF-owned
resets mark all limbs dirty, so inactive histories and side state are imported
before DSP ownership resumes. The lifecycle witness checks **68 old-generation
feedback samples** and retires them without applying them to the new ring.
It also checks six feedback jobs returned after CF takeover.

The independent Hat witness resets from its **own original initializer** at
actual production event boundaries. It records each original ring write as
(generation, index, value), including old-prefix writes before a reset. It
checks returned old-generation samples without committing them to the new
reference ring. It never seeds a reset or handoff from target post-state.
Slap is checked against its original native renderer at each actual entry,
including full raw state, ring and RNG. Full-project post-FX bit identity and
other family combinations are outside this exactness claim.

## CF reset cost and memory

G3 profiles actual production reset frames separately from later synthesis
peaks. The G2 worst frames (94,163/94,488 cycles) occur 400 frames after the
Bank reset, during CF-owned metallic Hat synthesis and stock processing;
they are not reset frames. Read-only instruction attribution reproduces
**frames, returns, cycle sums, peaks and misses exactly** against unprofiled
captures for both G2 and G3. Attribution covers every reset frame and the
64 worst frames, rather than an aggregate of the entire run.

All engine objects are initialized before playback. First adoption still avoids
redundant restoration. Later Slap/Hat raw-state resets now clear in unrolled
integer CF assembly and patch the nonzero words from the original boot-time
pristine bytes. Every track's initializer has 14 Slap and 72 Hat patches;
no initializer values are assumed. More than 96 patches falls back to the
original full copy, and tails retain the original bytes. Templates add
**6,176 BSS bytes**. The linked restore passes **1,056** byte/tail/guard/ABI
cases plus **512** dirty generation events checking the complete engine,
including forced dense fallback. The retained generic copy passes **404** cases.

For generations 2–5, measured restoration buckets (copy plus sparse helpers)
fall from **18,652–18,673 to 7,681–7,709 cycles**, about **59%**. These exclude
the event's other work. The worst later-reset full ISR falls from
**92,446 to 79,469 cycles** (350.174→301.019 µs). Including startup, the worst
reset frame is 88,130 cycles / **333.826 µs**, leaving **28.986 µs**. Scheduling
and phases change with target speed; these are observed campaign bounds,
not paired identical-phase microbenchmarks. The older G2 no-Part calibration
first-event bucket was 424 cycles versus G1's 14,425; that result described
startup only, not the later resets.

G3 also removes a redundant intermediate source-packet copy, clears the same
required zero placeholders with an integer assembly loop, and replaces source
resampling division with exact EMAC reciprocal arithmetic. Packet headers,
stereo PCM, clocks, carry and negative floor rounding remain unchanged.
The reciprocal identity is proved over all **306,179,667** possible nonnegative
numerators; **9,996** linked clock/PCM cases exercise all 147 phases, lengths
0–16 and edge/random PCM. **1,088** packet and **258** clear cases check bytes,
guards, return pointers and ABI. MACSR, raw ACC0 and ACCExt01 are preserved
under six MACSR modes and randomized accumulator state. No new IRQ-mask hold
is added. Experimental metallic synthesis rewrites were not retained because
the measured gain did not justify them; the synthesis implementation stays
unchanged.

The new resident reset fits after compacting the existing register saves.
Disassembly is retained; the final upload passes **1,536** source/import and
feedback-embed register-canary cases, **768** poisoned imports, **96** reset
packets, and the persistent original-author audio/arithmetic gates. The code
uses counted DO loops rather than REP. The shared-P allocation is
**2,306 / 2,404 words**; A service code is **1,946 words**. A private X uses
**564 / 616 words**, including three 17-word upload records for the packed
initializer. The ledger checks every private range for overlap.

Linked text/data/BSS is **1,061,870 / 588 / 1,138,484 bytes**; BSS remains below
the existing 2 MiB initialization bound. Generation fields add queue metadata.
The Slap/Hat synthesis assembly bodies remain byte-identical to F7, as does
B-owned program code and B X/Y/private-P data. Both complete DSP uploads are byte-identical to G2. Relative to F7, shared P
mirrors G2's changed A service into both uploads; B-owned code/data stay exact.

## Measured full workload and lifecycle

All captures run **264 MHz CF / 132 MHz PIT** uniformly through startup,
pre-roll and playback. The fixture keeps all eight tracks active, twelve
retained FX across sixteen slots, parameter locks, LFOs, scenes and sustained
card reads. Stored ALGO/MODE values determine the production choices; their
locks are removed for the declared rows. Part/Bank fixtures store different
modes and compare stored and actual selections.

| Run | G3 completed/source ISRs | G2 peak (µs) | G3 peak (µs), misses |
|---|---:|---:|---:|
| CF-only STOP/START, Part and Bank | 52,500 returned | 356.678 | 348.042, 0 |
| DSP-enabled lifecycle, six backend transitions | 52,193 returned | 357.909 | 349.439, 0 |
| WT/WT + Slap + white Hat | 16,397 observed | 326.867 | 321.121, 0 |
| WT/WT + Slap + metallic Hat | 16,397 observed | 330.712 | 324.061, 0 |
| WT/WT + Slap + pulse Hat | 16,395 observed | 315.814 | 310.205, 0 |
| Rapid backend switches with cycling MODE locks | 9,480 returned | 341.682 | 341.898, 0 |
| CF calibration, no Part change | 4,932 returned | 341.038 | 333.826, 0 |
| Saved-project cold reload | 512 requested | 336.920 | 331.598, 0 |

Both G3 lifecycle captures observe **five generations/resets per voice**, zero
stored/actual selector errors, and zero Hat PCM/state/clock/ring/feedback or
Slap mismatches. The CF-only run checks 52,500 Hat frames. The mixed-backend run
checks 22,503 CF plus 29,689 DSP frames; two final source jobs remain in flight,
with normal three-frame feedback latency. No queue overflow, transport failure,
blocking RPC, DMA overlap/restart, stack/guard violation or card-write error is
reported. The largest observed worker queue across the two lifecycle and rapid
switch captures is 249 of 1,024 frames.

The separate rapid-switch capture performs **18 backend transitions** with
production MODE locks cycling 0/1/2. Snapshots observe all three actual MODE
values on both owners. Hat PCM/state/clock/ring/feedback and Slap remain exact;
all stock tracks/FX stay active. Only backend-enable is poked; downstream
diagnostic MODE pokes are removed from this driver. This fixture's peak is
0.216 µs above G2, while remaining below the overall worst frame.

Across the lifecycle, sustained, rapid-switch and reload witnesses, **163,864
Hat source frames** and **2,854,005 Slap native samples** match exactly.

The sustained rows independently check **16,395 / 16,395 / 16,393 exact DSP
Hat frames**, respectively. All eight tracks have active source and post-FX
audio, retained programs match loaded P memory, and card streaming continues.
The **13.372 µs** minimum measured reserve is 2.7× G2's **4.903 µs**. It does
not establish physical cache/card-arbitration headroom or B-tail silicon behavior.

## Selection and persistence

All **32 linked signature/stock-validation cases** pass: two bank pointers,
four Parts and four PERKY tracks. Reselecting preserves the six controls and
SRAM signatures; UI ticks leave synthesis state unchanged.

The actual MKII encoder/SAVE PROJECT test saves T2 controls
**71, 108, 0, 64, 64, 2** identically in `bank01.work` and `bank01.strd`. A fresh
process cold-loads the saved card without selector/state pokes. All eight
tracks have active post-FX audio; 510 DSP Hat frames and 8,917 Slap native
samples match their references, with zero deadline misses. Endpoint encoder
turns qualify these edits; fine-detent response and power-loss atomicity are
not established. V4 Noise Tone's persisted selector is not audio admission.

## Retained G2 baseline, G1 failure and F7 scope

The current source/report snapshot is preserved under
`out/perky/hybrid/noise-hat-production/source-g3`. The passing G2 image, reports
and 59-file source snapshot remain under
`out/perky/hybrid/noise-hat-production-g2`. Its worst 357.909 µs frame and
4.903 µs reserve are historical measurements, superseded by G3 for the current
candidate. Both versions have separate true-reset profiles and unchanged
normal/profile timing totals.

G1 remains a **failed** historical admission, preserved with its source and
captures under `out/perky/hybrid/noise-hat-production-g1`. It passed persistence
but missed the deadline in both lifecycle runs and all three sustained rows.
Its DSP lifecycle produced **363,906 source PCM mismatches**, first showing a
resident-state difference at source frame 6,514. G1 reset CF state without an
equivalent resident/shadow reset or generation-aware feedback retirement.
Those measurements remain valid for G1; G2 and G3 supersede the unresolved-reset
conclusion for the tested WT/WT + Slap + Hat combination.

F7's separately qualified continuing-history baseline remains preserved. Its
diagnostic dispatcher bypasses production generations, so its pass does not
qualify pristine reset behavior. The existing F7 report is checked for image
identity here; this G3 campaign reruns the production candidate. Raw driver
receipts retain inherited diagnostic/G1 scope notes for audit; the bound G3
receipt labels those separately from its current production scope.

## Reproduction

Use the existing hybrid branch and checkout. Builds sharing output run
serially. Runtime captures use separate ignored directories.

```sh
.venv/bin/python tools/perky/build_noise_hat_production_probe.py
.venv/bin/python tools/verify/verify_perky_noise_hat_production_dsp.py
.venv/bin/python tools/verify/verify_perky_production_dsp_registers.py
.venv/bin/python tools/verify/verify_perky_production_copy.py
.venv/bin/python tools/verify/verify_perky_production_sparse.py
.venv/bin/python tools/verify/verify_perky_production_transport.py
.venv/bin/python tools/verify/build_perky_noise_hat_production_observer.py
.venv/bin/python tools/verify/verify_perky_noise_hat_production_selection.py
.venv/bin/python tools/verify/qualify_perky_noise_hat_production.py --backend cf
.venv/bin/python tools/verify/qualify_perky_noise_hat_production.py --backend dsp
.venv/bin/python tools/verify/measure_perky_noise_hat_production.py --frames 16384
.venv/bin/python tools/verify/qualify_perky_noise_hat_production_switching.py
.venv/bin/python tools/verify/verify_perky_noise_hat_production_persistence.py
.venv/bin/python tools/verify/profile_perky_noise_hat_production.py
.venv/bin/python tools/verify/profile_perky_production_resets.py --source out/perky/hybrid/noise-hat-production --work out/perky/hybrid/reset-profile-g3 --build-only
.venv/bin/python tools/verify/profile_perky_production_resets.py --source out/perky/hybrid/noise-hat-production --work out/perky/hybrid/reset-profile-g3 --backend cf
.venv/bin/python tools/verify/profile_perky_production_resets.py --source out/perky/hybrid/noise-hat-production --work out/perky/hybrid/reset-profile-g3 --backend dsp
make check REMIX=perky-machine
REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check
.venv/bin/python tools/verify/verify_perky_noise_hat_production_campaign.py
```

All **84 shared + 4 image** repository gates report zero failures; optional
project-less skips are named in the log and the production captures separately
exercise a mounted project. All **24 local identity configurations** are
bit-identical. The default bus image is restored to SHA256
`354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58`.
See the [reset profiling trap](../../../docs/contributing/TRAPS.md#trap-reset-profile) and the [production-generation trap](../../../docs/contributing/TRAPS.md#trap-production-generation).
