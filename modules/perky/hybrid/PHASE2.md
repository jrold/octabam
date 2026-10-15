# Goal 2 recovery — 14 October 2026

**INCOMPLETE / BLOCKED: modeled deadline miss; timing review required. DO NOT FLASH PKHYB2P.**
No locally qualified hybrid probe or hardware test request is issued.
`PHASE2.json` contains commands, evidence hashes, deliverable status and limits.

Recovered checkout: `perky-cf-dsp-hybrid`, HEAD
`82947daee3bf7d02efe947774f3c157620cd50a4`. One modified verifier and five
untracked files were present. The existing runtime, builder, tests, firmware
and logs were inspected and reused. Their inventory and original receipts
are preserved under `out/perky/hybrid/resume-goal2/`. No branch, worktree,
upstream integration, CI, push or physical update was performed.

Local session metadata identifies **gpt-6.1-sol / high**, one agent. Speed
is not exposed; no speed or model override was made.

## Executed recovery results

| Check | Result |
|---|---|
| `verify_perky_hybrid.py --stage baseline --work out/perky/hybrid` | PASS_FOR_PROBE_BUILD, 18/18 gates; includes 9 corrected-emulator CTest tests |
| `verify_perky_hybrid_workload.py --work out/perky/hybrid --smoke` | PASS: 22,450-frame T2/T6 split drift, 1,000-frame snare row, and source/post-FX audio assertions in a separate 2,400-frame capture |
| `resume-goal2/diagnose_row.py` | 27,563 frames: 95,599 cycles maximum = 359.395 us at modeled 266 MHz; no deadline misses; FAIL proposed 80% margin |
| `resume-goal2/diagnose_transition.py` | 4,000 frames: 98,632 cycles maximum = 370.796992 us; **one deadline miss**; runtime generation reaches 3 |
| `resume-goal2/diagnose_cold_callback.py` | **FAIL lifecycle**: observed waveform-asset writes inside signed T2 `pk_render` with COLD readiness, before UI initialization |
| Repaired `verify_perky_hybrid.py --stage probe --work out/perky/hybrid` | Eight executable gates PASS; aggregate correctly **BLOCKED** for missing qualification evidence |
| `verify_perky_hybrid_evidence_selftest.py` | PASS, 9 tests; subsequent image/tool binding checks included |
| Clean-source rebuild, complete sustained matrix, physical MKII | NOT-RUN |

Commands above use `.venv/bin/python3 tools/verify/` for verifier scripts and
`.venv/bin/python3 out/perky/hybrid/` for the recovery diagnostic drivers.
Full argv, exit statuses and hashed logs are in `PHASE2.json`.

The frame period is 16/44100 seconds = 362.811791 us. The observed transition
run peak is **7.985201 us over that period** and **80.547559 us above the
proposed 290.249433 us margin**. Worst frame index: 1378. These are corrected
model observations, not measured MKII timing or a complete workload bound.
No performance optimization was attempted. No reliable prior iteration ledger
exists; zero prior targeted performance iterations were identifiable.

The transition diagnostic uses the inherited workload's documented memory
pokes at frames 1000/2000 to change both Part indices. It does not exercise
the complete stock UI Bank/Part change. Its 4,000 frames do not reach the
family-transition locks at steps 46/58. Its histogram maximum/miss count is
used; the host budget mean covers a different interval when scripted actions
split execution and is not accepted as the whole-run mean. An initial local
driver used unsupported `part` actions and was terminated; that log is
preserved and excluded from accepted evidence.

The historical T3 smoke assertion does **not** reproduce. Assertions were
not weakened. T3's inherited playback values match the stock FLEX descriptor
defaults, including LEN and RTIM. No playback or synthesis parameter was
changed. The sole workload-script edit rejects unexecuted `--step` actions;
its original bytes and execution hash are preserved separately.

## Implementation and qualification gaps

| Deliverable | Status and evidence |
|---|---|
| Foundation | COMPLETE+VALIDATED for unchanged CF/reference and frozen DSP inputs. Aggregate source inventory predates verifier-only recovery changes. |
| Composition | IMPLEMENTED+UNVERIFIED. Existing MAIN/runtime/builder source hashes match, but runtime and builder are untracked and absent from recorded source commit. |
| Frozen DSP | COMPLETE+VALIDATED: original generation/uploads/guard, startup and actual-image P/X/Y readback checks pass. Frozen source was not changed. |
| Dispatcher, transport, UI | PARTIAL: 192 native record comparisons, 288 CF split cases, independent T2/T6, fixed-slot sentinels/cursor and UI stubs pass. Full source-handoff and original-state proof remains missing. |
| Hybrid PCM/state/RNG | IMPLEMENTED+UNVERIFIED. Phase 1 helpers pass original-reference tests; that does not independently prove the new adapter. |
| Initialization | FAILED. Asset decode remains reachable in `pk_render`; Bank/Part changes also initialize both instances there. Generation-safe ownership/readiness is unqualified. |
| Hardware profiler | FAILED. Runtime assumes 88 MHz; qualified stock DTIM3 uses 132 MHz. It sums PERKY callbacks and groups 27,563 frames into 60,630 entries. No full-ISR measurement, coherent export, wrap/overhead proof or silicon extraction path is qualified. |
| Memory/packaging | PARTIAL. Actual link/map and 200,704-byte waveform BSS evidence exist. Wrapper/cap/round-trip gates pass. The stack reserve is not a measured hybrid ceiling. |
| Twelve retained FX | PARTIAL. Four actual-image configurations preserve both cores' P/X/Y and tables with all 12 effects assigned. Their gate does not independently prove active nonzero processing by every effect. |
| Integrated workload | FAILED deadline; long matrix NOT-RUN. Seven >=60-second combinations, additional/reversed cases and worst >=600-second run remain required. |
| Corruption tests | PARTIAL. Existing release/card/DSP-span checks and receipt tests pass; complete lifecycle/loader fault coverage remains unqualified. |
| Clean commit/rebuild/hardware handoff | MISSING / WITHHELD. The verified receipt-gate repair is committed as `8a01675e`; incomplete inherited runtime/build code remains untracked. |

The original notes' `LOCAL_PROBE_QUALIFIED_HARDWARE_PENDING` claim is
withdrawn. The previous TIMING statement that long tests were skipped by user
permission is not accepted for this goal. Original binary bytes are preserved;
BUILD/TIMING/notes now explicitly describe the blocked state. Original receipts
remain archived. No PERKY4S output was overwritten or relabeled.

The next step is user timing/design review under the objective's explicit
modeled-overrun gate. Any later work must qualify initialization and a real
full-frame hardware profiler, then use at most the remaining two identifiable
targeted, measured, bit-exact CF/control/packing optimization iterations.
No extra FX removal, synthesis approximation, or DSP change is authorized.
See `HW_PROBE_REQUEST.md` and `GOAL2_RESUME_HANDOFF.md`.
