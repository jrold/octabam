# CF synthesis and ISR optimization — 21 October 2026

PKFM17 reduces ColdFire work while preserving the complete voice map and exact audio, but remains **FAIL_HOLD for performance**. All five sustained workloads fail six of the seven unchanged calibrated gates. Functional passes and zero nominal deadline misses do not establish sufficient hardware headroom. The [bound qualification receipt](CF_SYNTHESIS_QUALIFICATION.json) records functional passes at the stated local-model scopes and the failed performance admission. PERKY4S remains the hardware-confirmed release.

The candidate retains WT/WT and Slap on CF, resident Noise Hat on DSP-A, CF Noise/Tone or Acoustic Hats when selected, stock DSP-B source handling, and all fourteen stock FX. All twelve algorithm choices and their three modes retain original precision, native 48 kHz synthesis and 44.1 kHz output. Selecting Noise/Tone or Acoustic Hats puts all four source voices on CF. Normal DSP Hat ownership still performs zero duplicate CF Hat synthesis.

The accepted changes are WT oscillator block assembly; NT blocks enlarged from sixteen to twenty native samples; AH state cached within each render call; Slap RNG high products in EMAC with caller state restored; batched original control settling; exact rational-table resampling; guarded bulk tap gathering for spans without wrapping; guarded unity-rate stock sample-position loops; and bounded packet reservations with the original checked fallback. Controls and histories refresh at their real call boundaries.

Each row below executes **16,384 transport frames**, WT/WT, Slap, all stock tracks and all fourteen FX. Steady ISR statistics exclude the first 512 interrupts. Times are microseconds; total-CF means use exact playback cycles divided by requested frames and 264 MHz, including background work. These are measured local-model results, not a hardware multiplier.

| V4 selection | PKFM15 total-CF mean | PKFM17 total-CF mean | Saving | PKFM17 steady ISR mean | Full ISR peak |
|---|---:|---:|---:|---:|---:|
| **Fixed ceiling** | — | **189.298** | — | **158.212** | **250.712** |
| White Hat, panel mode 0 | 249.200 | 237.284 | 11.917 | 211.451 | 298.208 |
| Metallic Hat, panel mode 1 | 248.054 | 235.939 | 12.115 | 210.117 | 297.723 |
| Pulse Hat, panel mode 2 | 238.074 | 228.602 | 9.473 | 202.766 | 292.030 |
| Noise/Tone, mode 1 | 258.174 | 247.122 | 11.053 | 221.328 | 304.655 |
| Acoustic Hats, mode 1 | 254.924 | 243.043 | 11.881 | 217.005 | 312.152 |

The measuring binary, CF/PIT clocks (264/132 MHz), oracle and budget remain fixed. All five rows have exact PCM/state/RNG/clock/feedback comparisons, active post-FX audio on every track, zero nominal misses, and all seven native-work/snapshot/replay counters zero. Nevertheless, each fails ISR mean, p99, p99.9 and peak, total-CF mean, and ACK p99. Only ACK peak passes. The mean gates remain 158.212 µs ISR and 189.298 µs total CF; current total means exceed the latter by 20.8–30.5%. The worst row requires a further 28.5% reduction in ISR mean and 23.4% in total-CF mean to reach those ceilings.

The final NT profile reports `PASS_UNCHANGED_AUDIO_STATE_AND_CYCLES` against its frozen measurement row. Its exclusive steady costs group to stock ISR 107.445 µs, both WT paths 26.961 µs, Slap including filter/delay 24.607 µs, and NT including envelope/noise/filter 17.229 µs. Stock background work adds 26.036 µs. These measured buckets identify remaining cost; they do not establish an irreducible lower bound.

Actual-image evidence includes 5,355 mixed-source frames across 81 layouts, three mode rotations, every split 0–16 and 24 directed transitions; 528 linked NT, 792 AH and 792 Slap kernel calls against independent native histories; and an 800-frame CF/DSP handoff gate. The paired 400-frame DSP snapshot gate checks four coherent captures and 5,403 ring-feedback words. Exact resampling additionally has 19,267,437 mathematical difference/phase cases and 9,996 linked-CF cases. Linked tap and stock-position gates cover 43,245 and 4,256 cases respectively.

Packet reservation proof compares 540 actual linked Hat-producer cases, including full/overcapacity failures, all packet bytes, counters, control caches, capture buffers and logical engine state. Its 252 external-capacity cases execute the exact old/new function bodies as separately compiled CF probes with declared PCM. That extracted proof establishes append/fallback semantics; actual-image source and lifecycle gates establish synthesis. Image-specific asset pointers are validated against each image's registered symbol before/after calls; only those four pointer bytes are omitted from host comparison.

Lifecycle passes **52,937 frames**, STOP/START, production Part/Bank generations, lazy first Hat use, all modes and 22 backend switches: eleven snapshots, 804 replay frames and 815 completed real jobs, with exact audio/state and no nominal timing/safety violations. Scene/fader delivery passes **9,162 frames** with all eight post-FX tracks active. Lifecycle and scene ISR maxima are 328.280 and 301.277 µs. The matrix passes all **243 observed tuples**, with none missing, **160,057 ISR entries / 160,056 completed returns**, exact source/state/feedback and no nominal deadline misses. Its largest ISR is 332.364 µs; steady CF Hat synthesis/snapshot/job counters remain zero.

DSP uploads are byte-identical to PKFM15. Shared program occupancy remains 2,312/2,404 words, with stock FX retained. Actual CF ELF text grows 3,756 bytes (577,620→581,376); data remains 588 and BSS 1,612,664 bytes. Observed stack/ownership/DMA guards pass within the completed traces.

NT filter assembly and fixed Slap delay specialization were exact but regressed in combined isolated timing. Stock DELAY-loop unrolling was excluded before integration: weighted isolated deltas implied only about 0.155 µs/frame saving; that estimate is not a full-ISR measurement. The isolated Slap alignment failure is documented at `docs/contributing/TRAPS.md#trap-cf-live-alignment`: live `.balign 4` emitted zero padding; explicit `.balignw 4,0x4e71` restored exactness, but corrected delay timing still regressed. It never entered PKFM16/17.

The build source checkpoint is `4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus uncommitted implementation hashes in `BUILD.json` and the pre-qualification 1,027-entry `SOURCE_SNAPSHOT.json` (SHA256 `f09ea8302cb5c6efd969c595126193e96e7b76935e9a445a0e5a56c2f4639203`). MAIN SHA256 is `7f3eeecafcfb6746207d981e3677e224d5321e2100b748fe5ba7e633dd314dcb`; ELF SHA256 is `e16f1da5b17b55083ab7fa7f165efd4e6ec262ada259291d4927b2412921d6c9`.

The existing hybrid branch and checkout contain the local build and verification inputs. Key commands are below; direct kernel receipts and their source bindings are indexed by `OPTIMIZATION_PROOFS.json`. No flash, package, push or release commit was made:

```sh
PK_WORK=out/perky/hybrid/full-map-packet-reserve-v2
PERKY_SYNTHESIS_WORK="$PK_WORK" PERKY_SYNTHESIS_VERSION=PKFM17 .venv/bin/python tools/perky/build_perky_packet_reserve_probe.py
.venv/bin/python tools/verify/verify_hat_state_handoff.py --build "$PK_WORK"
.venv/bin/python tools/verify/measure_perky_state_handoff.py --build "$PK_WORK" --work "$PK_WORK/measurement" --frames 16384 --v4 5 --mode 1 --witness "$PK_WORK/HANDOFF_GATE.json"
PERKY_FULL_MAP_WORK="$PK_WORK" .venv/bin/python tools/verify/qualify_hat_state_matrix.py
PERKY_FULL_MAP_WORK="$PK_WORK" .venv/bin/python tools/verify/qualify_hat_state_lifecycle.py
PERKY_FULL_MAP_WORK="$PK_WORK" .venv/bin/python tools/verify/qualify_perky_full_map_scenes.py
```

Repeat measurement for `(V4,mode)=(5,0),(5,2),(3,1),(10,1)`. Clean local `make check` and `scripts/refhash.sh check` passed, with recorded fixture-dependent skips and default-image restoration. The final `.venv/bin/python tools/verify/qualify_perky_synthesis_optimized.py --build "$PK_WORK"` completed all binding checks and returned **1**, with `FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK` written to its fresh report. That is the expected performance failure, not a failed functional test. The standard build was restored to SHA256 `c9e292bec49f54820355c76dca904c5dc02d1378120f7a34042c10dfe1bbe1a4`.

Final code and verifier sources are retained in the local `SOURCE_EVIDENCE.tar.gz`, bound by `FINAL_SOURCE_EVIDENCE.json`; this archive excludes stock images, asset binaries and dependency trees. The earlier source snapshot remains the pre-qualification record.
