# Final bounded pre-hardware safety decision — 15 October 2026

**B. STRUCTURAL SAFETY CHANGE REQUIRED — STOP FOR APPROVAL.**

The actual sequencer interrupt can reenter itself on a stock 2,048-byte task
stack. Its priority is 3, but it clears its force request and lowers IPL to 2
before doing its work. A new actual-image test establishes the recursion and
its stack growth. No finite arrival/service bound has been established to limit
that recursion. The minimum proposed remedy is an IPL 2→3 guard at the existing
mask write; it has been tested only in a disposable emulator machine and **has
not been applied to firmware**. It is not yet a qualified fix.

This is a structural safety-case failure, **not a reproduced normal-playback
stack overflow, memory corruption, DMA race or deadline failure**. The prior
report's phrase “software safety defects” incorrectly grouped missing lifecycle
and trigger evidence with demonstrated defects. That classification is retracted.

The user's final bounded objective explicitly requires stopping for approval
when a structural stack change is required. That stop condition is reached.
The other two completion gates remain UNVERIFIED; this report does not claim
three successful investigations or recommend a hardware probe. No firmware
correction, optimization, flash, push, branch, worktree or Goal 3 work occurred.
Goal 2 remains closed. Start checkpoint: `689860d71b1b7447223885481c209cc4df5adaf6`.

## Results and executable evidence

| Area | Final result | Evidence and limit |
|---|---|---|
| Stack safety | **FAIL: structural bound** | Actual-image forced arrivals produce nine live sequencer frames on keyrepeat; no all-path bound. A test-only IPL3 control defers another level3 request. |
| Lifecycle completion | **UNVERIFIED** | Prior real Part/STOP/START, working-bank A→B→A, signature/dispatcher components and actual SAVE/cold-reload passes are retained. Full real chooser/machine and playing-bank transitions during mixed playback were not completed before the stack stop. |
| Dense locks/trigger accounting | **UNVERIFIED** | Prior actual source ownership/cursor and bounded panel passes are retained. No independent expected→delivered dense-pattern/lock/reversion/ALGO/MODE/UI-event count is claimed. |

New entry point:

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_stop.py --selftest
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_stop.py
```

Five decision selftests pass. The actual-image C++ harness exits **0** after both
unchanged-image nesting and counterfactual checks pass. The assessment command
exits **1 intentionally**, reporting decision B; that is the failed qualification
gate, not a crashed test. Inputs, linked libraries, test source, commands, binary
and log hashes are in `out/perky/hybrid/safety-close/FINAL_SAFETY_STOP.json`, also
embedded in [SAFETY_QUALIFICATION.json](SAFETY_QUALIFICATION.json).
The original bounded receipts are hash-checked and reused, not rerun.

The first harness draft wrongly omitted the task exit return address; a trace
also showed that the CPU executes the task's PEA before acknowledging the first
request. The accepted harness asserts the actual interrupted-task usage of
16 bytes and decodes every actual exception vector. These were harness
corrections, not firmware defect fixes. Firmware correction iterations: **0**.

## 1. Exact stack path and capacity

Actual boot installs vector `0x60` at `0x400a1e0c` and INTC0 source32 at level3.
The test reaches actual keyrepeat TCB `0x460d4f80`, created with stack
`[0x460d4780,0x460d4f80)`, 2,048 bytes. It writes source32's bit in the actual
modeled INTC force register. Controller delivery and the CPU's exception entry
execute normally; no synthetic ISR or substituted task stack is used.

The self-cycle is:

1. `0x400a1e0c`: mask to IPL7.
2. `0x400a1e10`: reserve 208 bytes; save registers in that allocation.
3. `0x400a1e1a`: clear source32's force bit.
4. `0x400a1e64`: write SR `0x2200`, permitting level3 again.
5. A new source32 request enters the same handler before the older one returns.

Each aligned invocation adds **8 exception bytes + 208 handler bytes = 216**,
before deeper sequencer calls. The accepted trace is:

| Live sequencer depth | Interrupted task B | Sequencer B | Combined B | Free B |
|---:|---:|---:|---:|---:|
|1|16|216|232|1,816|
|3|16|648|664|1,384|
|6|16|1,296|1,312|736|
|9|16|1,944|1,960|88|
|10, arithmetic only|16|2,160|2,176|−128|

The tenth request was **not issued**. Its prologue would reserve below the stack
bottom and its register save would write there. The test stops in-bounds.

These arrivals are deliberately adversarial host force writes at the handler's
unmask point. They are **not a naturally reproduced playback sequence or an
assertion that hardware can generate requests at that rate**. Actual firmware
producers include the source32 force sites at `0x40005a74` and `0x4000ae00`.
A proof based on bounded production rate and complete sequencer service time
has not been established; the permitted nesting graph itself contains a cycle.
Consequently increasing a finite task stack alone does not close that graph.

The hybrid audio ISR uses interrupted-task A7. It temporarily saves 16 bytes,
then returns to the stock audio frame reserving 252 bytes; these saves are
sequential. Compiler audit covers 47 functions, with individual frames of 680
bytes for render, 80 for the CF adapter and 348 for snare. These individual sizes
are not a complete sum of arguments, return addresses and callees. Audio level5
can interrupt the sequencer, and level6 eDMA/UART work can interrupt audio.
The prior run actually observed `0x60→0x41→0x4f`, 9,370 balanced audio entries,
and a **1,316-byte observed audio maximum including observed nested work**.
That peak does not bound every level6 path, interrupted task, or sequencer body.
Level7's terminal halt path also has no returning-service guarantee.

**Maximum established all-path combined requirement: UNKNOWN; no finite bound
for the unrestricted self-cycle.** The new 1,960-byte forced-case observation
and prior peaks are not ceilings. Available DRAM is not an interrupt stack.

Prior accepted capacities / combined observations, preserved unchanged:

| Task | Capacity B | Prior observed use B |
|---|---:|---:|
|storage|2,048|76|
|keyrepeat|2,048|1,352|
|UI|2,048|148|
|engine|16,384|3,016|
|p2c / p2a / p2b|8,192 each|184 / 116 / 180|
|p1b|8,192|2,124|
|main, inferred extent|4,096|1,888|
|sys|8,192|2,104|
|voice|4,096|40|

Main's extent is inferred from adjacent allocations, not a captured create size.
The ten other task sizes are actual RTOS create arguments. The existing observer
calibration covers both step paths, leading LEA/SR entries, level5→6 nesting,
RTE balance, guard/extent violations and positive/negative modeled DMA overlap.

## Proposed minimum structural change — approval required

Change the immediate operand at `0x400a1e66` from `0x2200` to `0x2300`, retaining
IPL≥3 during sequencer processing. This is a **two-byte image operand change**,
with **0 extra DRAM, 0 extra stack, 0 added instructions and 0 direct modeled
instruction-cost delta**. No interrupt-stack architecture or arena is proposed.
Audio5 and DMA/UART6 remain eligible by priority. Same-level ATA DMA14 completion
is deferred along with sequencer reentry; its service delay must be assessed.

The disposable-memory counterfactual boots a second real machine, changes only
that operand, admits one actual tick, then forces another. Through the first
actual body call (`0x400a1608`), the second request stays pending and no second
sequencer frame appears. The original input file remains hash-identical.
This establishes the local guard mechanism only. It does not prove whole-body
callee mask behavior, eventual tick counts, ATA latency, or total stack safety.
The force bit can coalesce arrivals while masked, so replacing recursion with
deferral needs explicit delivery/count semantics.

Acceptance for this proposed change, if authorized: audit all sequencer callees
and SR restores; test pending delivery/counts and absence of recursive growth;
close the finite task+sequencer+CF-engine+level6 bound against every capacity;
check ATA14 service under audio5/DMA6; complete the two remaining lifecycle and
dense-accounting gates; then recheck DSP/guard/FX/PCM/state/RNG identities and
corrected-clock ISR timing. The proposal alone does not qualify those results.
No claim is made that this one operand necessarily suffices for the entire bound.

## 2. Retained lifecycle evidence and precise missing result

The accepted linked-component gate passed 32 signature creation/removal/donor/
SRAM-mirror cases across two banks, four Parts and T1/T2/T5/T6; eight actual stock
continuation delegations; and four generation handoffs matching first-trigger
records and all 3,948 live CF state/RNG bytes. The actual panel changed Part to2
and exercised PLAY→STOP→PLAY→STOP. The stock sys queue changed the **working**
bank A→B→A over 2,048 frames; the playing bank stayed A.

Actual MKII SAVE PROJECT retained 256 staged working-Part signatures and all six
edited T2 controls `[71,112,2,72,56,0]`. A fresh boot reloaded those controls and
rendered all four hybrid post-FX chains for 512 frames, with native DSP T1/T5 and
CF T2/T6 active concurrently. Those tests are reused with their original limits.
DSP/CF routing is fixed by track; UI selection is not a same-track engine switch.

**Missing:** verified real chooser deselection/reselection and playing-bank
transitions during mixed playback, with routing, retained state and stale-record
checks through the transition. No failing case or fix is invented. No new
lifecycle completion run was made after the structural stop condition.

## 3. Retained UI/DMA evidence and precise missing result

The accepted 3.4-second panel run observed 17,635 dispatcher entries per track,
18,740 source DMA starts, 5,190,502 source CPU writes, zero active-source overlaps,
zero channel restarts, zero stack-extent/bottom-watch violations and zero modeled
ISR duration misses. Source TCDs used NBYTES336/CITER4/SOFF16. Source addresses
were `0x80001c90/0x800021d0/0x80002710/0x80002c50` (4,685 starts each).
The mover's contiguous 1,344-byte snapshot defines this modeled ownership claim;
it is not every silicon stride/modulo/cache mode.

Existing exact transport tests distinguish moving cursor `0x80001c80` from fixed
publication `0x80001c90 + ping*0xa80 + track*336` and preserve the trailing176
bytes. Panel input drained, sampled peak2 bytes; firmware RX peak10/32 and sys
queue peak8. Encoder coalescing prevents assuming one event per detent.

**Missing:** independent expected/delivered dense triggers, lock/reversion and
ALGO/MODE transitions, CF/DSP records and DMA publications, plus UI consumed/
queued/dropped counts during mixed DSP/CF/stock playback. Queue peaks and audible
output do not establish these counts. No dropped trigger, corruption or ownership
race was reproduced; no fix is claimed. No new dense run followed the stack stop.

## Corrected timing, identity and disposition

CPU **264 MHz**, PIT **132 MHz**. Retained modeled worst full ISR **323.765 µs**;
frame deadline **362.812 µs**; modeled headroom **39.047 µs**. The 80% ceiling is
290.249 µs, missed by 33.516 µs; **20% engineering margin remains UNWAIVED**.
The shorter panel peak of 320.947 µs does not replace that worst.

Remaining hardware-only uncertainties are physical cache/SDRAM/FlexBus/eDMA
arbitration and coherence; interrupt release-to-entry and completion latency;
independent two-core completion under bus contention; and physical timer-read/
probe/export overhead. Emulator service windows do not establish silicon WCET.
Neither physical timing nor the missed margin causes decision B or is being made
a prerequisite for the experiment intended to measure it.

Candidate MAIN remains **1,483,190 bytes**, SHA256
`a2d6915bc71a97d63f44e223e558cc4941d52113708f7ba92a57bdd669339b40`.
Runtime ELF SHA256
`f35c87b393ecc798eb103fcf9672f7b44ca64bf1f3df684d644d63b96e512a9e`.
No firmware hash changed. Existing DSP identity/166 dependencies, 28 generated
identity checks, exact PCM/state/RNG oracle, nine CTests, 24-case refhash and
package/roundtrip evidence remain scoped passes for this unchanged firmware;
they were not repeated. Original PERKY4S DSP uploads, six-word guard, engines
and all twelve effects remain untouched.

Rollback reference remains PERKY4S source
`16a8de19a17ee4cba765cbdb30ca051f85af4e23`, MAIN SHA256
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
No installation is recommended. Structural implementation requires user approval;
any later flash would require separate explicit user authorization. Stop here.

Historical reports and receipts remain available in
`git show 689860d:modules/perky/hybrid/SAFETY_QUALIFICATION.md` and the archived
`bounded_followup` object in the JSON report. The commit containing this report
records only the verified host tools and documentation; its exact ID is supplied
in the final handoff.
