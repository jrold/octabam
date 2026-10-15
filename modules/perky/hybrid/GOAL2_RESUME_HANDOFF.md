# Goal 2 handoff — INCOMPLETE / BLOCKED

Branch `perky-cf-dsp-hybrid`. Build-source HEAD at report generation:
`19d1810429765d4a1c4e18bd24d92b9fa2c6f1f3`. This report is committed separately afterward; the build source
is immutable in BUILD.json. Runtime/optimizations: `ce882def`; measurement
switch/scope repair: `28701a6d`. Model: GPT-6.1 Sol / High, one agent; speed not
exposed, no override. **Do not flash, push, start Goal 3 or attempt a fourth
optimization under the current authorization.**

## Reconstructed prior state and new work

At continuation HEAD `942f6572`, inherited runtime, builder and hybrid tests
were untracked. They had useful dispatch/transport code and an unqualified
built image, but callback asset decoding, UI/audio reset ownership and an
88 MHz callback-only profiler were invalid. Their original bytes/artifacts
remain in `out/perky/hybrid/resume-fixes/before/` and recovery archives.
Reused them; did not start over.

New implementation initializes lossless assets and compact voices in the
loader before RTOS, uses loaded cookies, and gives the audio ISR ownership
of event-boundary generation resets. CF-only entry/tail hooks, 132 MHz DTIM3,
bounded counters/rings, coherent UI snapshots, separate HC polling counters
and automatic STOP-to-card `.PRF` export replace callback grouping. The user
needs **no CF METER reading**. No DSP insert or frozen DSP change was made.

The original two retained performance iterations were: same short case 368.167 -> 349.598 ->
315.871 us runtime timer peak. Original-reference 19 sections and packaged
PCM/state/RNG comparisons pass. Iteration 2 batches exact smoother recurrence
and retains first/last and finite-decay-boundary side effects; corrupt state
uses the reference fallback. Ledger: resume-fixes/PERFORMANCE_ITERATIONS.json.

A separate final short case measured **319.860902 us** complete model ISR,
zero observed misses, **29.611469 us above** the 80% margin. Profiler mean
delta 3.194657 us; armed mean delta 54.948951 us. PC pairs cover all 4,000
frames; first LEA + RTE add 11 corrected model cycles. This is not hardware
or sustained qualification. Boot-model timer-read calibration zero is not
physical zero cost. HC polling sites are not independent-core completion proof.

Retractions: old 370.797 us/one miss represented ACK-to-ACK task-inclusive work,
not ISR latency. New instrumentation independently reproduced the initial true
ISR overrun. Inherited on/off pokes wrote only a byte, leaving flags enabled;
invalid comparisons were discarded. Four-byte pokes now assert effective flags.

## Executed checks

All Python commands below use `.venv/bin/python3` from the repository root.
Exact argv, result/log hashes and every major contract status are in PHASE2.json.

- PASS: `tools/verify/verify_perky_hybrid.py --stage baseline --work out/perky/hybrid/resume-fixes`, 18/18 including corrected CTest and original-reference gates.
  Later source changes only cleaned decoder whitespace and fixed measurement
  switch setup; current synthesis source matches the tested snapshot.
- PASS: `tools/verify/verify_perky_hybrid_runtime.py --frames 1024`, 2,048 exact
  records/full state/RNG, all splits, eight fallback cases, poisoned readiness,
  no RT asset writes/UI reset, snapshot collision, wrap and export ABI.
  Evidence: resume-fixes/RUNTIME_1024.json (preserved before aggregate rerun).
- PASS: `out/perky/hybrid/resume-fixes/final_safety.py`, single ownership,
  192 native comparisons, 288 CF split cases, UI and four 600-frame both-core
  readbacks with twelve FX assigned. Per-effect nonzero audio remains unproven.
- PASS: `tools/verify/verify_perky_hybrid_workload.py --work out/perky/hybrid --smoke`,
  22,450-frame split drift and eight-track audio; no historical T3 failure.
- PASS execution / FAIL margin: `out/perky/hybrid/resume-fixes/measure_overhead_resume.py`,
  three 4,000-frame comparisons; effective disabled/disarmed flags verified.
- PASS: `out/perky/hybrid/resume-fixes/check_card_export.py`, actual stock FS
  writes 1,864-byte PKH20000.PRF after scripted STOP; source-matched decoder.
  Six malformed-record tests rejected; evidence in PROFILE_NEGATIVES.json.
- PASS: `tools/verify/verify_perky_hybrid_evidence_selftest.py`, 9 negative tests.
- PASS: `REFHASH_JOBS=1 scripts/refhash.sh check`, all 24 cases bit-identical.
- PASS: `tools/perky/build_cf_dsp_hybrid.py --profile probe --work out/perky/hybrid --no-wrap`,
  clean committed build inputs and exact MAIN/fragmented/ELF/raw reproduction.
- EXPECTED BLOCKED: `tools/verify/verify_perky_hybrid.py --stage probe --work out/perky/hybrid`;
  wrappers absent, timing margin failed, sustained/lifecycle/silicon evidence missing.

NOT RUN at the initial two-iteration stopping gate, still incomplete after iteration 3: full >=60 s matrix and >=600 s
worst row; complete stock Bank/Part and backlog stress; independently active
nonzero processing for every retained effect; current wrapper/corruption/cap
qualification; physical MKII validation. Therefore no qualified probe exists.

## Artifacts and workspace

Simulation MAIN: `out/perky/hybrid/probe/mainos_PKHYB2P.bin`,
SHA256 `46bd31dba62651500de6c672ec0e3e50c38533f8edbe39cd12e200318c93ca2a`.
Runtime ELF SHA256 `290b82c30c0f813df159a555a01f5f81cb43b2cb93ebe9571196491a07fad0e6`.
Frozen original MAIN remains
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
BUILD/MEMORY/TIMING/DSP_IDENTITY and VERIFY_PROBE are in that probe directory;
all before/after cases and hashed receipts are in resume-fixes/. Current
wrappers were not emitted; old wrappers were checked against archived copies
before removal from the current output directory. Never use archived wrappers.

Preserved unrelated untracked `PERKY_Hybrid_Goal2_Gemini_Argon4.txt`:
SHA256 `285b0b0dbf5cf90bb65da481e97cf740858148c9c4e0377d4ebbe8320263766a`.
It was not staged or edited. `perky-machines` remains
`4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`. No upstream/CI/push/physical update.

Workspace exception: the first plain refhash helper unexpectedly created
checkouts. Source identity was audited and only its helper checkouts removed;
`refhash-cleanup.json` records this. The subsequent JOBS=1 cached-baseline run
passed and only the original checkout remains. Do not repeat plain refhash
without inspecting its worker/baseline behavior.

The smallest next step is review of the remaining 29.611 us modeled margin
shortfall and unrun qualification scope before any additional optimization
or package/hardware authorization. Stop here after all three authorized attempts. Future qualified hardware extraction can use automatic card files;
it need not impose CF METER readings on the user.

## Additional authorized iteration 3

See ITERATION3.md and out/perky/hybrid/iteration3/RESULT.json. Measured
empty renders first: 1.655 us/call, 0.284 us/frame mean, zero in peak frame.
The one skip candidate passed 4,096 callback comparisons, including 242 empty
callbacks, all 17 splits, exact PCM/slots/state/RNG/cursor/counters and the
existing runtime suite. DSP identity and both-core FX readback passed.
Mean full ISR improved 0.605 us, p99 regressed 0.335 us, peak regressed
319.860902 -> 320.011278 us. Candidate rejected; source and all four runtime
binaries restored bit-identical. Retained peak is 319.860902 us and remaining
margin is 29.611469 us. The extra authorization is consumed; no fourth attempt,
flash or push. Build-source HEAD and exact restoration are recorded in
iteration3/RESTORED.json and current BUILD.json. Only measurement/tests/reports
were committed for this experiment; no candidate runtime change is retained.
