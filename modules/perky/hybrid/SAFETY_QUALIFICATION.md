# Bounded pre-hardware safety qualification — 15 October 2026

**BLOCKED — SPECIFIC SOFTWARE SAFETY DEFECTS**

The unresolved defects are in the software safety case: there is no established
combined stock-task/nested-interrupt stack ceiling, and complete machine/playing-bank
transition and dense lock/trigger delivery guarantees remain unproved. **No firmware
memory corruption, stack overflow, DMA ownership race or current deadline failure
was demonstrated.** An unestablished ceiling is not a measured overflow, but it
cannot be certified safe for a physical probe. No flashing is recommended or
requested. Physical timing is not being made a prerequisite for its own experiment.

This completes the bounded investigation from checkpoint
`ece602d083f7b999b00df4dee109814738eb1579` on the existing
`perky-cf-dsp-hybrid` branch/check-out. Goal 2 stays closed; Goal 3 has not begun.
No firmware, engine, FX, DSP payload, six-word guard, build system, shared emulator,
branch, worktree or upstream state changed. There were **zero firmware correction
iterations and zero synthesis optimization iterations**. Only host verification
tools and reports changed. The commit containing this report records those changes;
its exact ID is given in the final handoff.

[SAFETY_QUALIFICATION.json](SAFETY_QUALIFICATION.json) retains the earlier
clock/initialization/package evidence and embeds the new assessment. The local measurement logs are dated 14 October; this report was finalized on
15 October. Fresh local receipts are in `out/perky/hybrid/safety-final/`. The previous report remains at
`git show ece602d:modules/perky/hybrid/SAFETY_QUALIFICATION.md`.

## 1. Stack and interrupt nesting

The disassembly confirms that the ISR uses the interrupted task's A7; it does
not switch to the proposed 4,096-byte runtime arena allowance. ColdFire's modeled
exception frame is eight bytes plus zero to three alignment bytes. The stock
handler at `0x4000aad0` reserves 252 bytes. The hybrid entry temporarily saves
16 bytes and returns to that stock handler; its tail restores the stock register
save, releases 252 bytes and executes RTE. The entry and stock frame allocations
are sequential, not simultaneous.

The existing exact-source compiler audit covers 47 functions: hybrid render
680 bytes, CF render adapter 80 bytes and snare 348 bytes are individual frames.
They are not a complete stack bound; outgoing argument space and call paths must
also be accounted for. The linked snare prologue actually reserves 348 bytes.

Priorities and mask changes matter:

- Audio is INTC0 source 1, vector `0x41`, level 5. Its observed minimum IPL is 5.
- eDMA vectors `0x48/0x49/0x4f` and MIDI/panel UART interrupts run at level 6;
  same-level requests cannot preempt each other under the normal IPL rule.
- The sequencer vector `0x60` is level 3 in this image. Its handler at
  `0x400a1e0c` masks to 7, reserves 208 bytes, then lowers IPL to **2** at
  `0x400a1e64`. Consequently, the observed chain is **sequencer → audio → eDMA**,
  not just audio → eDMA. UART RX entries mask to 7 before their own saves.
- Level 7 includes a terminal halt path. Fault/halt paths and unexamined indirect
  stock callees are not certified returning-stack or completion bounds.

A separate host observer was compiled from staged copies of `machine.cpp` and
`periph.cpp`, linked to the existing libraries. The shared emulator remains exact.
It observes every host instruction boundary in boot, `step` and `stepFast`, tracks
TCB stack extents, decodes exception frames and RTEs, and watches the bottom 32
bytes of each task stack after that task first executes. These are **passive write
watches**, not painted target canaries or a physical memory-integrity test.

Musashi can execute the first handler instruction before the next observation.
The observer handles the leading LEA and immediate SR-write forms used here.
Four executable calibration cases cover both step paths and both entry forms,
real level-5/6 exception nesting, exact 284-byte synthetic stack use and balanced
RTEs. Deliberate source-DMA overlap, stack underflow and bottom-guard writes are
required to be detected; the non-overlap controls must remain clean.

Fresh actual-image panel run: **1,256,423,292 instruction observations; 9,370 audio
entries and 9,370 returns; maximum observed nesting 3; maximum observed audio-ISR
requirement 1,316 bytes including its exception frame and observed nested work**.
There were zero out-of-extent observations and zero stack-bottom writes.

| Task | Actual capacity B | Maximum observed combined use B | Remaining at observed peak B |
|---|---:|---:|---:|
| storage |2,048|76|1,972|
| keyrepeat |2,048|1,352|696|
| UI |2,048|148|1,900|
| engine |16,384|3,016|13,368|
| p2c |8,192|184|8,008|
| p2a |8,192|116|8,076|
| p2b |8,192|180|8,012|
| p1b |8,192|2,124|6,068|
| main (inferred allocation extent) |4,096|1,888|2,208|
| sys |8,192|2,104|6,088|
| voice |4,096|40|4,056|

Main's observed allocation top is `0x46c7bed8`. Its 4,096-byte extent down to
`0x46c7aed8` is a structural inference from the adjacent 84-byte TCB and the next
TCB at `0x46c7bed8`, rather than a captured create-size argument: boot constructs
main directly. The observer uses that inferred extent; it is not an independent
proof that every byte is reserved exclusively for stack use. The ten created
tasks' extents instead match actual create arguments under the stock RTOS gate.
The older documented `0x46c7becc` is main's initial saved exception-frame pointer,
not its top: boot writes the initial PC at `0x46c7bed0` and exit address at
`0x46c7bed4`. The first observer draft used that saved pointer as the top and
falsely flagged main's initial entry. The corrected top and a new run show no
violation of the inferred extent.

**Maximum established all-path requirement: UNKNOWN.** 1,316 and 3,016 bytes are
observations, not ceilings. No closed call-graph/inductive bound covers every
preemptible stock task path, lower-priority nested handler or indirect callback.
In particular the small task stacks cannot be qualified by subtracting an observed
ISR peak from an observed task peak taken at a different preemption point. This
is the first essential software blocker. More free DRAM does not close it.

Falsification: any stack extent/guard violation fails the executable gate.
Closing this blocker requires a justified upper bound for the actual permitted
stock paths and nesting, compared with each task's capacity; another clean short
run alone would not close it. No multi-hour stress was attempted.

## 2. Lifecycle transitions

The new component gate executes the **linked signature writer and dispatcher**
from the actual hybrid image; it does not substitute a host renderer.

| Investigation | Established result | Limit |
|---|---|---|
| Cold boot/first trigger | Existing poisoned-BSS/decoded-asset proof reused unchanged; new four generation handoffs match eight fresh-reference first-trigger records and all 3,948 live CF state/RNG bytes per comparison | Fresh reference is another boot of the same qualified implementation; original engine oracle remains prior evidence |
| Selection/deselection | 32 two-bank/four-Part/T1/T2/T5/T6 cases pass: actual PK signature creation/removal, donor assignment, SRAM mirror, reselection preserves sound, fresh selection restores defaults | Assembly writer/component execution, not complete stock chooser workflows |
| CF/DSP-to-stock dispatch | Eight stock delegations over four tracks pass; no CF-state/source-slot write during the intercepted stock continuation; reselection publishes again | Stock continuation intercepted in this component test |
| Bank change | Actual stock queue post executes in sys; working bank pointer A → B → A, 2,048 frames, both calls return | This tests the working-bank path. The sequencer's playing bank stays A; full panel bank/pattern transition remains unqualified |
| Part change | Real MKII Part chooser changes Part to 2 while audio runs; component gate covers all four Parts | First-trigger races during every loader/chooser phase are not exhaustively exercised |
| Stop/start | Actual panel PLAY → STOP → PLAY → STOP observed in firmware transport state | No stop-latency ceiling or automatic stall-abort claim |
| Saved project | Actual MKII SAVE PROJECT writes stock FAT/ATA files; 256 previously staged working-Part signatures survive; newly saved bank01 `.work` and `.strd` retain all six controls `[71,112,2,72,56,0]` | Other untouched stored banks are not required to contain signatures never staged into them; no power-loss atomicity claim |
| Cold reload | Fresh current-image boot loads that saved card; six controls match exactly; 512 frames have 8,192 post-FX samples each on T1/T2/T5/T6, respectively 8,176/8,175/8,171/8,182 samples above magnitude 64; both CF source streams active | Bounded saved-project fixture, not every project/loader variant |
| Simultaneous DSP + CF | Both actual DSP payloads run; T1/T5 native and T2/T6 CF chains are independently active on reload | No independent physical per-core completion bound |

DSP versus CF routing is fixed by track: T1/T5 use DSP, T2/T6 use CF. Track
selection changes the UI target; there is no same-track DSP↔CF engine switch.
Source-machine removal/reselection and stock delegation are the relevant actual
source transitions. No new routing capability was added.

The earlier exact split/cursor/native-record/PCM/state/RNG gates remain evidence
for the unchanged implementation and unchanged image hash. They were not rerun
as Goal 2. **Complete real chooser/playing-bank transitions, stale-record exclusion
through all transition phases and first-trigger-during-load cases remain a second
software qualification blocker.** Component passes are not promoted to those paths.

## 3. UI and DMA concurrency

The 3.4-second real panel script exercises six encoders at five-millisecond
spacing, T2/T6 selection, Part selection and STOP/START while both DSPs and CF
voices run. Every track enters the actual source dispatcher 17,635 times.
The panel input queue drains to zero (sampled peak 2 bytes); the firmware's
32-byte panel RX ring peaks at 10 and sys queue count peaks at 8. Those are
observations, not arbitrary-traffic backlog bounds. Encoder events can legitimately
coalesce in the stock parser; detents are not assumed to map one-for-one to events.
The separate save/reload test proves an actual T2 knob edit persisted.

The source observer records **18,740 source DMA starts**, 4,685 for each of four
source addresses: `0x80001c90`, `0x800021d0`, `0x80002710`, `0x80002c50`.
These are the two core halves of both ping buffers. All observed source TCDs use
NBYTES 336, CITER 4, SOFF 16; the existing host-port model snapshots a contiguous
1,344-byte source extent. The observer follows that model from start to completion.
Across **5,190,502 source-buffer CPU writes**, it finds **zero writes overlapping an
active modeled source-DMA extent** and zero active-channel restarts. A deliberate
overlap in calibration is detected. This is useful ownership evidence for these
exact TCD shapes, not a generic hardware eDMA/cache proof.

The moving cursor at `0x80001c80` remains separate from fixed per-track publication
at `0x80001c90 + ping*0xa80 + track*336`. Existing exact transport tests prove cursor
reservation, fixed-slot publication and preservation of the trailing 176 bytes;
new deselection and generation tests exercise those same linked paths. UI ticks
interleaved between lifecycle events never reset live CF state. Both-core exchanges
report zero words not in time. All 9,370 measured ISR service windows fit the model
period; this script's peak is 84,730 cycles / 264 MHz = **320.946970 µs**.

**Still unqualified locally:** a full event→trigger→record accounting under dense
real parameter locks/reversion and competing UI/lifecycle events, complete queue
saturation/refusal behavior, and every allowed sampler/recorder/streaming state.
No dropped trigger or buffer corruption was observed, but their universal absence
is not proven by drained queues and completed frames. This is the third software
qualification blocker. Existing direct p-lock/reversion component evidence does
not substitute for this end-to-end condition.

Physical SDRAM/FlexBus/cache coherence and arbitration, eDMA/DSP bus contention,
release-to-entry latency and independent per-core completion remain hardware-only
uncertainties. They are reported separately from the missing software guarantees.

## Timing policy and disposition

The authoritative corrected bounded modeled worst remains **323.765152 µs** at
CPU **264 MHz**, PIT **132 MHz**, versus the **362.811791 µs** frame deadline:
**39.046640 µs** modeled headroom. The proposed 80% ceiling is **290.249433 µs**;
it is missed by **33.515719 µs**. The **20% margin remains UNWAIVED**.
The new panel peak is a different, shorter workload and does not replace that worst.
No physical WCET claim is made. Cache misses, SDRAM waits, pipelines, bus contention,
physical timer/probe cost and release-to-completion behavior remain unmeasured.

The missed engineering margin and missing physical timing do **not** cause this
software BLOCKED decision. Four decision-gate selftests verify missing/failed
software evidence refuses review and that complete software gates can permit
**user review** while physical timing and the margin decision remain outstanding.
No decision path authorizes a flash.

A restricted diagnostic protocol is not offered while those three software gates
remain open. The known rollback baseline is PERKY4S, source
`16a8de19a17ee4cba765cbdb30ca051f85af4e23`, MAIN SHA256
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
Any later proposal must bind the exact diagnostic package, restricted activation,
a stall/deadline containment and capture procedure, and verified rollback files,
then obtain explicit user authorization. Existing unqualified build-11 files are
not newly approved by these tests.

## Executable receipts and stopping point

Commands below use the existing tools, checkout, project fixture and build:

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety.py --work out/perky/hybrid/safety-final/final-observer
# PASS: isolated observer build and four calibrated positive/negative cases
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety.py --work out/perky/hybrid/safety-final/final-observer --panel
# PASS: real 3.4-second MKII panel run, stack/guard/DMA assertions
.venv/bin/python3 tools/verify/verify_perky_hybrid_lifecycle_safety.py
# PASS_COMPONENT_SCOPES: 32 selection cases, four-track delegation, four generation handoffs
.venv/bin/python3 tools/verify/verify_perky_hybrid_saved_project.py
# SAVE itself passed; first analysis wrongly expected PK in untouched stored banks
.venv/bin/python3 tools/verify/verify_perky_hybrid_saved_project.py --reuse-save
# PASS_SCOPED_SAVE_RELOAD: exact hash-verified SAVE reused, fresh reload executed
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_assessment.py --selftest
# PASS: 4/4 decision/refusal tests
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_assessment.py
# EXPECTED EXIT 1: the three software safety obligations above remain unestablished
```

The explicit working-bank command and its successful stock sys pointer writes
are recorded in the embedded bank receipt and `safety-final/banks/port.log`.
Earlier live-path borrowed calls were refused because the CPU was inside the
ISR; their nonzero-free process exit is **not a bank PASS**. The final panel run
contains no borrowed calls and now rejects such refused-action logs. The bad
watch-range attempt was terminated and replaced before accepting bank evidence.
These are harness failures/corrections, not demonstrated firmware defects.

Fresh CTest/refhash/engine-oracle/full-remix builds were not repeated: no firmware,
build or shared emulator source changed. Prior 9/9 CTest, 24/24 refhash, original
engine oracle, poisoned initialization, DSP/FX identity, packaging and corrected
clock receipts are reused at their established scopes and exact artifact hashes.
No full stress matrix, physical probe, flash, upstream operation or push occurred.

**Stop here. BLOCKED — SPECIFIC SOFTWARE SAFETY DEFECTS.** No further optimization
or Goal 3. The unrelated Argon4 note remains untouched and unstaged; the preserved
`perky-machines` ref remains `4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`.
