# Post-closeout hybrid safety qualification — 14 October 2026

**BLOCKED. No physical probe is recommended or authorized.** This is the bounded
safety task after Goal 2 closed at `bee3830134b2061151a3628f6622347de2916f38`.
Goal 2 remains closed; Goal 3 has not begun. No synthesis optimization, DSP/FX
change, flash, push, branch or worktree was performed. The rejected empty-render
optimization remains rejected; the complete `pk_hybrid_render` source body is
unchanged from closeout, including the unconditional engine call for zero samples.

Verified code/tests commit: **`854f2aacad0f73e6654b27ed92a8be6d10666817`** on
`perky-cf-dsp-hybrid`. This assessment is committed separately. Exact evidence,
source/artifact hashes and limitations are in [SAFETY_QUALIFICATION.json](SAFETY_QUALIFICATION.json).
Local execution evidence lives in `out/perky/hybrid/safety-qualification/`.

## Newly closed gates and correctness changes

| Gate | Exact local result | Limit |
|---|---|---|
| Configured CPU clock | Stock PCR `0x16777731`; PFDR 22, CPU divider 2, bus divider 4; boot stores **264,000,000 Hz** at `0x400b9654`. CPU cycle model corrected from 266 to 264 MHz. | Nominal configured rate, not a physical oscillator measurement. VR266 is the rating. |
| PIT basis | [NXP MCF54455RM](https://www.nxp.com/docs/en/reference-manual/MCF54455RM.pdf), table 29-3, selects internal bus/PRE. Stock PCSR `0x0b36`, PMR 643 gives **9.991758 ms** at 132 MHz. Hybrid runs explicitly use `--pit-clock-hz 132000000`. | Emulator legacy PIT 264 MHz default retained for old oracle comparisons; every qualification run now records the explicit choice. |
| Cold initialization | **218,564 B** BSS poisoned at the real loader-to-initializer call, with matching stale Bank/Part and valid same-family native smoother. Clean native split records, initialized CF/native state and all **200,704 decoded PCM bytes** match. | Targeted emulated boot, not physical lifecycle certification. |
| Native BSS bug | Pre-fix same-family stale state changed the first native split record. Explicit native control/prefix/trigger/UI history initialization before RTOS now passes that regression. | Native arithmetic/producer semantics and all DSP sources remain unchanged. No large reset was added to audio/UI callbacks. |
| Timer startup bug | Read pair moved from pre-timer boot to one bounded UI operation after DTMR3/DTRR3 match. Disabled timer and wrong modulus skip calibration; one pair only; unsigned wrap fixture **64 ticks**, PASS. | Read-pair interval is not a bound on all probe overhead. Physical MMIO latency remains unmeasured. |
| Exact runtime comparison | **1,024 frames /2,048 source records**, all 16 split offsets, complete two-voice state/RNG, eight out-of-range smoother cases, PASS. | Against archived retained image `46bd31…`; original 19-section synthesis oracle reused because its engine/asset/control sources did not change. |
| Dispatch/native/UI | **192** native record comparisons, **288** CF transport cases, independent T2/T6, untouched 176-byte tails/cursor reservation, **320** glyph draws and formatter checks, PASS. | Direct component calls; not a complete real panel lifecycle/queue test. |
| DSP/FX identity | **166** frozen dependencies unchanged; **28** generated payload/upload/table/placement/guard checks, PASS. Full MAIN boot and both A/B upload readbacks, PASS. | Identity does not measure physical per-core completion or prove every retained effect actively processed in this new run. |
| Packaging | Actual MAIN→MIDI→MAIN and card→ELEK exact; cap accounting PASS. **Nine** targeted malformed/corruption/cap/overlap rejections plus existing hybrid DSP/card/odd-address negatives, PASS. | No exhaustive malformed compressed-token or runtime loader-table execution matrix. |
| Instrument regression | Final **9/9 CTest** PASS; **24/24 refhash** configurations bit-identical, using existing baseline and `REFHASH_LOCAL=1 REFHASH_JOBS=1`. | No new checkout or baseline was created. |
| Automatic export | Actual stock filesystem wrote one **1,864 B** source-matched PRF after STOP flag; **3,526** frames in snapshot, zero readiness faults; PASS. | STOP flag injected at 3500; not a real panel STOP latency/lost-event test. Physical card export unexecuted. No CF METER reading required. |

The immutable baseline validator explicitly refused the changed emulator binary
hash, as expected. Its sole reported drift was `out/emu/ot_emu`; no old pin was
rewritten. Frozen sources/inputs were checked, and the corrected emulator was
rebuilt and separately tested. **No fresh baseline 18/18 or aggregate probe PASS
is claimed.** A clean-commit rebuild was not repeated: every build-time source
hash was instead checked against both current files and committed blobs at
`854f2aac`. BUILD.json honestly retains its earlier build-time HEAD and dirty flag.

## Corrected full-ISR timing

Current build 11, unchanged engines/FX; CPU 264 MHz, DTIM3/bus 132 MHz, PIT 132 MHz,
44,100 samples/s, 16 samples/frame; existing snare/snare integrated fixture.
Each run is **4,000 frames /1.451247 simulated seconds**, not a sustained matrix.

| Current case | Mean us | p99 us | Maximum cycles | Maximum us | Duration misses |
|---|---:|---:|---:|---:|---:|
| Profiler on, CF armed |197.185584|214.708333|85,474|**323.765152**|**0**|
| Profiler off, CF armed |194.665096|212.064394|84,943|321.753788|0|
| Profiler on, CF disarmed |141.970034|150.863636|59,210|224.280303|0|

Deadline **362.811791 us**; modeled headroom **39.046640 us**, 10.762% of the
frame. Proposed 80% ceiling **290.249433 us**; **shortfall 33.515718 us**.
That criterion has **not** been waived. A future exception requires the user's
explicit decision after independent safety gates pass.

Conditional mean profiler delta is **2.520489 us**; armed/disarmed mean delta
**55.215550 us**. Common hooks remain in the off path. Differences of maxima
are not worst-case overhead bounds. The new model records one DTIM3 tick between
calibration reads (7.576 ns nominal); that is a modeled read-to-read interval,
not measured silicon latency or total instrumentation cost. DTMR3 `0x000b` selects
bus/1, no reference IRQ, restart at DTRR `0xffffffff`; nominal wrap 32.537631 s.

Full spans pair entry+4 with RTE on every frame, adding model LEA 1/RTE 10 cycles.
They include stock ISR work, callbacks, waits and probe bookkeeping, but exclude
pending interrupt/vector-entry latency and do not bound release-to-completion
under arbitrary nesting/backlog. No DSP execution time is added serially to CF.
Both DSPs ran; short exchanges reported zero words not in time. Separate HC
poll sites are still not independently calibrated per-core completion maxima.

Historical 319.860902 us was the retained image at CPU 266/PIT 264 MHz. Re-executing
that image at CPU 264/PIT 264 gave 322.284091 us; this was an actual rerun, not just
rescaling. The safety-fixed image at CPU 264/PIT 264 gave 323.840909 us. The table
above uses the corrected PIT basis. These observations stay separate; the older
number is not a current-hardware bound. No observed duration miss occurred in
these current bounded runs; unseen workloads and physical deadlines remain open.

The cycle pricer still assumes cache hits/zero-wait operands and combines older
core timings with V4e repairs and inherited estimates. Physical SDRAM/cache/DMA,
pipeline effects and interrupt masking/nesting can consume the 39 us. Earlier CF
model/hardware discrepancies prevent treating this estimate as conservative.

## Memory and packaging

Current linked text 350,608 B; rodata 348 B; data 548 B; BSS 218,564 B. Loaded raw
span 359,696 B includes link alignment. Runtime reserve
`0x40c005e0..0x41600de0`; BSS ends `0x40c8d8b4`; packed stage
`0x40c8e000..0x40cc47f6`; gap 1,868 B and 9,684,458 B after stage.
Static physical alias-normalized runtime/preboot ranges do not overlap and fit
their reservations. The main stock heap/buffer reserve geometry is unchanged.
This does not establish physical cache coherence, all recorder/DMA ownership or
interrupt stack bounds.

Current card file 809,148 B = 12 B outer overhead + **809,136 B encrypted payload**;
payload cap 1,048,576 B leaves **239,440 B**. ELEK 809,129 B; MIDI 1,130,245 B.
Uncompressed MAIN size 1,483,190 B is a different quantity from that payload cap.

All files below are in `out/perky/hybrid/probe/`, version PKHYB2P, build 11,
source identity `ee5607e1d4e87dc5eefb15f9c1fda5d2a8040b2f8d7ed33dd1b25dfc4af3d50d`.
**They are unqualified local artifacts, not an approved diagnostic install set.**

| Artifact | SHA256 |
|---|---|
| `mainos_PKHYB2P.bin` | `a2d6915bc71a97d63f44e223e558cc4941d52113708f7ba92a57bdd669339b40` |
| `platform/runtime.elf` | `f35c87b393ecc798eb103fcf9672f7b44ca64bf1f3df684d644d63b96e512a9e` |
| `platform/runtime.raw` | `9662d5b36d9546f8dac0e624a666eb0d5455696ecf48b278dd414ff22ed43478` |
| `elek_PKHYB2P.bin` | `7decf768dfd36b9d78bc7a0e6b43452f94597b1318bc472a91c29f2785718aae` |
| `OCTATRACK_PKHYB2P.bin` | `10c92102780d8795d5944488b78830f2f35fca51a9f234c67bf23cf74f898a69` |
| `OCTATRACK_OS1.40C_PKHYB2P.syx` | `468acc6e44f1b99fcbcbf09f00c87a363496c4c11eee1181cb643624f7cbf1b5` |

## Essential gates still blocked and bounded stopping point

- **Stack/nesting:** compiler audit covers 47 functions, largest hybrid render 680 B,
  snare 348 B. Sampled engine-entry depth 960 B and 4,000 balanced ISR returns are
  lower-bound observations, not a maximum call-chain proof. Stock UI, storage
  and keyrepeat task stacks are 2,048 B. The report's 4,096 B arena allowance is
  not their interrupt stack. Interrupted task use plus nested handlers/canaries
  remains unbounded. No overflow was demonstrated; absence of evidence is not PASS.
- **Lifecycle/UI:** complete real Bank/Part/project loads, repeated machine
  replacement/reselection, first trigger during these operations, real panel
  STOP, queue backlog/lost events and dense end-to-end scene/LFO/lock traffic
  remain unexecuted. Direct generation/ownership tests do not substitute for them.
- **DMA/concurrency:** ABI publication/cursor preservation and static disjointness
  pass; physical recorder/eDMA ownership, cache visibility, nested exchanges and
  independent completion timing for each DSP remain unqualified. No additional
  long stress matrix was run while those essential gates were missing.
- **Timing/containment:** all-workload/silicon timing, physical read/probe overhead
  and physical card export remain unmeasured. CF still defaults armed; no validated
  probe-specific auto-abort exists. Short duration alone cannot contain a stall
  or guarantee responsive UI STOP/export. The unwaived margin fails separately.

The next bounded action is a **stack/nesting census**, before any hardware request:
map actual interrupted TCB stack extents; record minimum A7 and nesting depth at
every instruction/IRQ in a short scripted real Bank/Part/machine/STOP workload;
derive call-chain plus highest-priority nested-handler allowance and verify stack
canaries. Stop on overflow or a missing stock-frame bound. Lifecycle/DMA ownership
must then pass before presenting any margin exception and activation/abort protocol
for explicit review. This report does not authorize that further work or installation.

The pre-fix image and 26 metadata/loader/runtime files are preserved with hashes
under `safety-qualification/before/`. Old image-bound TIMING/PROBE_GATES/VERIFY_PROBE
receipts were removed from the current probe directory only after verifying exact
archive copies; Goal 1/2 manifests and closeout remain historical records. The
original rejected iteration 3 result/source patch is untouched. `perky-machines`
remains `4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`. The unrelated untracked
`PERKY_Hybrid_Goal2_Gemini_Argon4.txt` remains unchanged and unstaged, SHA256
`285b0b0dbf5cf90bb65da481e97cf740858148c9c4e0377d4ebbe8320263766a`.

Recommendation: **BLOCKED BY UNRESOLVED TIMING**. Essential memory/lifecycle
qualification is also incomplete. Stop; no physical probe, further optimization
or Goal 3.
