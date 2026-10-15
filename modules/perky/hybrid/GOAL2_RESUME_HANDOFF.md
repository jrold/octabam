# Goal 2 final handoff — CLOSED / UNQUALIFIED

The bounded investigation is finished. **No further optimization experiments,
no margin waiver, no flash/push/new branch/worktree, and no Goal 3.** The rejected
zero-length fast path is not retained. The engineering assessment is complete;
implementation/functionality/hardware qualification remains incomplete.

The authoritative assessment is [CLOSEOUT.md](CLOSEOUT.md), with exact commands,
hashes, the full PASS/FAIL/NOT-RUN matrix and timing history in CLOSEOUT.json.
Iteration3.md and out/perky/hybrid/iteration3/ preserve the rejected experiment.

- **Implemented and locally working:** mixed T1/T5 native DSP and independent
  T2/T6 CF dispatcher; stock continuation for other tracks; exact bounded
  PCM/state/RNG and stock source records; pre-RTOS initialization/loaded cookies;
  audio-owned event resets; CF-only ISR profiler and automatic STOP-to-card PRF
  export. Existing local tests validate these scopes. No CF METER reading needed.
- **Functional verdict independent of 20% margin:** not fully qualified. Complete
  Bank/Part/BSS/native-state lifecycle, six-control scenes/LFO/persistence workflow,
  sustained mixed combinations, stack/nesting/backlog, sampler/recorder/DMA safety,
  every effect's independently active audio and per-core completion are unverified.
- **Exact passed scopes:** 18/18 baseline prerequisites (not integrated qualification);
  current CF original-reference 19 sections / 22,098 cases / 3,046,272 PCM samples,
  zero failures; retained runtime 1,024 frames / 2,048 exact records/state/RNG;
  192 native and 288 CF split cases; 22,450-frame sequencer drift; 1,000-frame
  mixed smoke and separate 2,400-frame eight-track audio capture; whole boot/readback;
  static memory and frozen DSP/FX identity; four 600-frame twelve-FX assignment
  readbacks. Fresh closeout CTest 9/9 and evidence negatives 9/9 PASS; six profile
  negatives reject. See assessment for source binding and every scope limitation.
- **Timing:** retained complete ISR service-code window **85,083 modeled cycles /
  266 MHz = 319.860902 us**, 4,000 frames, zero observed duration misses. Deadline
  **362.811791 us**, nominal headroom **42.950889 us**; proposed ceiling
  **290.249433 us** still missed by **29.611469 us**. Historic pre-optimization
  images did exceed the period (368.167/374.538 us), and are distinct from current.
- **Rejected iteration 3:** bit-exact 4,096 callback boundaries, including 242 empty
  callbacks/all 17 splits; mean improved 0.605 us, p99 worsened 0.335 us, peak worsened
  **319.860902 -> 320.011278 us**. Rejected and four binaries restored exactly.
- **Hardware risks:** clock/model discrepancy (documented 264 MHz vs modeled 266),
  unbounded physical cache/bus/DMA and interrupt latency, unknown stack/lifecycle
  interference and two-core completion. First-frame peak; short duration does not
  avoid it. No probe-specific automatic abort; UI-dependent export may not capture
  a stall. Zero model misses is not physical worst-case proof.
- **Packaging/availability:** no qualified diagnostic firmware set. Current wrapper
  check exits 1 for missing ELEK; combined negative gate exits 1 at missing card.
  Current cap/header/checksum/decrypt/roundtrip/corruption tests are NOT-RUN, not
  proven passing or proven overflow. Old archived wrappers must not be substituted.
- **Single recommendation:** targeted **non-optimization** investigation of the
  demonstrated clock/timer-basis discrepancy and missing lifecycle/stack/package
  safety evidence before considering hardware. No controlled hardware probe now;
  do not label the design infeasible from the margin failure alone.

Retained simulation-only MAIN:
`out/perky/hybrid/probe/mainos_PKHYB2P.bin`, SHA256
`46bd31dba62651500de6c672ec0e3e50c38533f8edbe39cd12e200318c93ca2a`.
ELF SHA256 `290b82c30c0f813df159a555a01f5f81cb43b2cb93ebe9571196491a07fad0e6`.
There is **no qualified flash identity**. Frozen PERKY4S MAIN remains
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.

Git branch: `perky-cf-dsp-hybrid`; assessment parent HEAD
`9b8039491631dfcb88f71e5c83662638a44f2820`; compiled build-source commit
`19d1810429765d4a1c4e18bd24d92b9fa2c6f1f3`. All implementation/tests were already
committed; closeout changes reports only. The commit containing this document
is the final closeout commit. Its exact HEAD/status is recorded after committing
in `out/perky/hybrid/closeout/FINAL_GIT.json` and the final assistant handoff.
Only unrelated untracked `PERKY_Hybrid_Goal2_Gemini_Argon4.txt` remains, unchanged,
SHA256 `285b0b0dbf5cf90bb65da481e97cf740858148c9c4e0377d4ebbe8320263766a`.
`perky-machines` stays `4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`; one checkout.
No source or runtime changes, performance reruns, new packages, physical actions
or upstream operations occurred during closeout. **Stop here.**
