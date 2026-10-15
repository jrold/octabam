# Goal 2 resumed-session handoff — INCOMPLETE / BLOCKED

**Timing review required. Do not flash PKHYB2P. No local qualification or
production approval was issued. Goal 3 remains blocked.**

Branch: `perky-cf-dsp-hybrid`. Recovered HEAD:
`82947daee3bf7d02efe947774f3c157620cd50a4`. HEAD at this audit / verified
repair commit: `8a01675e` (the documentation commit containing this handoff
follows it). `perky-machines` remains
`4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`.
Model metadata: gpt-6.1-sol, high, one agent; speed is not exposed and was
not overridden. No branching/worktree/clone, upstream integration, CI or push.

## Reconstructed prior state

Argon left a modified `tools/verify/verify_perky_hybrid.py`, plus untracked
runtime, builder, two hybrid gate scripts and the user's
`PERKY_Hybrid_Goal2_Gemini_Argon4.txt`. Existing PKHYB2P MAIN/card/MIDI,
BUILD/MEMORY/DSP_IDENTITY/TIMING, tests and logs were present. No Phase 2
source reports or hardware request existed. Initial source/artifact hashes
and prior receipts are in `out/perky/hybrid/resume-goal2/initial-inventory.json`
and `prior-*.json`. Existing builder/runtime hashes matched BUILD, but its
recorded source commit contains neither; its clean-tree/qualified-note claims
were unsupported. The earlier T3 smoke failure does not reproduce.

## New work and preserved dirty files

`8a01675e` commits only the verifier's refusal checks, correct qualified EFT
path, mandatory FX execution, nine receipt regression tests, and the trap
record/AGENTS link. A following documentation commit records PHASE2.md/json,
this handoff and the withheld HW_PROBE_REQUEST.md. No synthesis or frozen DSP
source changed. No optimization iteration was attempted; prior total unknown,
zero identifiable. Keep the two-iteration total limit for later work.

All five original untracked files remain outside commits. Runtime, builder,
probe-gates script and user text retain their initial hashes. The workload
script has one new assertion rejecting unknown scripted-action warnings
(current SHA256 `51d76001056f0e043622650fd89542517a83a07a51a43f9f27140c1185433453`).
Its original bytes are preserved as
`out/perky/hybrid/resume-goal2/prior-verify_perky_hybrid_workload.py`
(SHA256 `61b75d7f1c370cd74b566609df15950528dd5ce116e7b2b48f302f4953ac547b`).
The bounded measurements executed that original version. No LEN/RTIM or other
fixture/synthesis controls were changed. No stash, clean or unrelated staging.

Original firmware bytes are intact. BUILD/TIMING/notes were corrected to
BLOCKED; original receipts and notes were archived. The untracked builder
source still needs repair: it emits a premature qualified note and omits
untracked files from its cleanliness check. Do not use it to approve a flash.

## Executed commands and evidence

See `PHASE2.json` for full argv, exit statuses, artifact/log hashes and every
major deliverable's status. All paths below are relative to this checkout.

- PASS: `.venv/bin/python3 tools/verify/verify_perky_hybrid.py --stage baseline --work out/perky/hybrid`
  — 18/18; corrected CTest 9/9, original CF reference/PCM/state and frozen DSP.
  Executed before verifier-only recovery edits; not a final-tree qualification.
- PASS: `.venv/bin/python3 tools/verify/verify_perky_hybrid_workload.py --work out/perky/hybrid --smoke`
  — 22,450 split-drift frames; 1,000 integrated frames; eight-track audio
  assertions in separate 2,400-frame capture. No assertion weakened.
- EXECUTED / FAIL margin: `.venv/bin/python3 out/perky/hybrid/resume-goal2/diagnose_row.py`
  — 27,563 frames, 95,599 cycles maximum = 359.395 us, zero misses.
- EXECUTED / FAIL deadline: `.venv/bin/python3 out/perky/hybrid/resume-goal2/diagnose_transition.py`
  — 4,000 frames, max 98,632 cycles = **370.796992 us**, one miss at frame
  1378, **7.985201 us over period**, 80.547559 us over proposed 80% margin.
  Part-index pokes at frames 1000/2000, not complete UI Bank/Part changes;
  too short to reach family-transition locks. Use histogram maximum/misses,
  not the host budget mean. `transitions-index.json` and its port log are proof.
  The earlier unsupported-action driver was terminated and excluded.
- EXECUTED / FAIL lifecycle: `.venv/bin/python3 out/perky/hybrid/resume-goal2/diagnose_cold_callback.py`
  — decoded-waveform writes observed inside COLD T2 `pk_render`; this diagnoses
  a real-time contract violation, not decoder duration.
- BLOCKED (exit 1): `.venv/bin/python3 tools/verify/verify_perky_hybrid.py --stage probe --work out/perky/hybrid`
  — all eight executable gates pass, including wrappers and both-core P/X/Y/FX
  configurations; missing qualification evidence refused. Final image/tool
  receipt binding additions are tested separately, not another long rerun.
- PASS: `.venv/bin/python3 tools/verify/verify_perky_hybrid_evidence_selftest.py` (9/9),
  `git diff --check`, and `.venv/bin/python3 out/perky/hybrid/resume-goal2/final_audit.py`
  (13 qualification refusal reasons; eight preserved binary/runtime files;
  all 166 frozen DSP dependencies match).
- NOT-RUN: mandatory >=60s matrix, additional/reversed rows, worst >=600s,
  profiler-on/off/armed comparisons, full lifecycle, clean-source rebuild and
  physical MKII. No new flashable artifact was emitted.

Unqualified MAIN SHA256:
`df77a52a56941f1fbb6a97f3cfdc118cf03596b87c22b6389717ee1fe8e6c582`.
Unqualified card SHA256:
`fa222e0bdb3a54dba617e03902300bda93cece2368a9cc55495d00af60db5f40`.
Rollback PERKY4S MAIN remains
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
Exact paths, remaining hashes and rollback card/MIDI are in PHASE2.json and
HW_PROBE_REQUEST.md. Never substitute these unqualified binaries for PERKY4S.

## Blocker and smallest next step

The objective requires user review before a fully armed probe can be treated
as safe after modeled timing exceeds the frame period. Review the 370.797 us
failure and the unresolved lifecycle/profiler design before further qualification.
The current profiler is not usable: 88 MHz assumption versus qualified 132 MHz,
callback sums instead of ISR time, and 60,630 groups for 27,563 real frames;
no qualified physical export, wrap/overhead proof or coherent snapshot.

After that review: establish initialization before real-time callbacks and a
bounded generation-safe handoff; qualify full-frame hardware instrumentation
without changing frozen DSP; repair builder provenance; only then attempt
bounded, measured, bit-exact improvements and the complete workload gates.
The existing split/UI tests do not replace independent integrated PCM/state/RNG,
source-handoff, per-effect active-audio, stack or clean-rebuild proof.
The hardware request is explicitly withheld until these requirements pass.
