# Authorized IPL3 guard qualification — 15 October 2026

**Historical IPL3-only result: combined stack bound was not established.**

The subsequently approved private-stack correction and its current scoped local
diagnostic qualification are in [PRIVATE_STACK_QUALIFICATION.md](PRIVATE_STACK_QUALIFICATION.md).
The IPL3-only evidence below is preserved for its original image and task.

The subsequent bounded stack-correction task returns **deliverable B**, with
resolved storage-read bounds, verified task initialization and available DRAM,
and a concrete private-audio-stack proposal, subsequently approved. See
[STACK_CORRECTION.md](STACK_CORRECTION.md). The preserved IPL3-only trial remains unchanged; its qualification was blocked
at that checkpoint. The IPL3 evidence below is preserved.

The authorized minimal guard is implemented and its **bounded local checks pass**.
Real chooser/Part/playing-bank transitions, saved-card reload and dense
trigger/lock/UI/DMA accounting now have additional executable passes. No guard
regression, corruption, DMA ownership race or modeled deadline failure was
reproduced. **The guarded firmware is not locally qualified for a physical probe:**
the combined interrupted-stock-task/ISR upper bound is still UNVERIFIED.
Missing evidence is not being called a demonstrated firmware defect.

This is the final result of the bounded authorization beginning at
`3167a977c78beda86ade048f3f71545c3005508d`. It does not satisfy the requested
qualified-candidate acceptance. The remaining stack obligation could not be
closed within this bounded task. No architectural change, synthesis optimization,
flash, push, branch/worktree creation or Goal 3 work was performed. Stop here.

## Exact implementation and identity

Preflight checked the original MAIN hash, disassembly and actual interrupt
behavior **before creating the trial**:

- `0x400a1e64`: original instruction `46fc 2200`, `move.w #0x2200,sr`.
- `0x400a1e66`: two-byte operand, file offset `0xa1a66` relative to MAIN base
  `0x40000400`. It becomes `0x2300`; the opcode remains `0x46fc`.
- The operand write spans two bytes; **one byte actually differs**, `0x22→0x23`
  at `0x400a1e66`. Every other MAIN byte is identical.
- Actual boot installs source 32/vector `0x60` at level 3, handler `0x400a1e0c`.
  It masks to 7, reserves 208 bytes and clears the force bit before the mask write.

The hybrid module factory in `tools/perky/build_cf_dsp_hybrid.py` now declares
only this additional operand poke. An executable comparison against the factory
at `3167a977` verifies every other module field unchanged, including hooks, DSP,
FX and claims. Applying that declaration to the frozen MAIN exactly reproduces
the tested post-link trial. `tools/perky/apply_hybrid_ipl_guard.py` provides the
strict hash-bound application and inverse operation without overwriting inputs.

| Artifact | SHA256 |
|---|---|
| Original MAIN, preserved | `a2d6915bc71a97d63f44e223e558cc4941d52113708f7ba92a57bdd669339b40` |
| Guarded post-link trial, 1,483,190 bytes | `055cced1bb5319c35ee7d4708359a60a3e207a69d73711d2d536beadca060fbe` |
| Unchanged runtime ELF | `f35c87b393ecc798eb103fcf9672f7b44ca64bf1f3df684d644d63b96e512a9e` |

Trial: `out/perky/hybrid/ipl3/trial-mainos.bin`. This is a derivative of the
existing build11 image; it is **not a fresh runtime rebuild or a newly qualified
installable set**. Existing encrypted/card/MIDI wrappers still contain the old
image. No guarded wrappers were produced. Frozen DSP uploads, six-word guard,
all twelve retained FX, engines and assets remain byte-identical. Existing exact
PCM/state/RNG and dependency evidence is retained for the unchanged code; three
new original/guarded integration pairs also have byte-identical source/DSP blocks.

The inverse patch was tested and restores the exact original MAIN hash.
No legitimate guard regression triggered the mandatory revert condition; the
verified guard is retained. Firmware correction iterations: one. Synthesis
optimization iterations: zero.

## Executable result

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid_ipl_guard.py --selftest
.venv/bin/python3 tools/verify/verify_perky_hybrid_ipl_guard.py --unit
.venv/bin/python3 tools/verify/verify_perky_hybrid_ipl_guard.py
```

Five decision/input selftests pass. The focused actual-image C++ test exits0.
The consolidator checks the recorded runs without repeating them and deliberately
exits **1 for the unverified essential stack gate**, after scoped assertions pass.
It does not label that qualification failure a reproduced firmware bug.

New receipt: `out/perky/hybrid/ipl3/IPL3_QUALIFICATION.json`, embedded in
[SAFETY_QUALIFICATION.json](SAFETY_QUALIFICATION.json). It binds the trial,
module declaration, test sources, linked libraries, observer sources, private
fixtures, logs, records and outputs. Reproduction inputs are the existing private
safety fixture and saved card; no proprietary image/project bytes are committed.
The supplemental observer is linked from staged emulator sources; shared emulator
sources, libraries and executable are unchanged.

| Obligation | Result | Established scope |
|---|---|---|
| Exact guard/rollback and other-byte preservation | **PASS** | Full-file comparison and inverse hash |
| Level3 non-reentry / one deferred request | **PASS locally** | Full quiescent actual handler; guarded exception-entry SPs stay equal; original image reenters as negative control |
| Legitimate higher-priority IRQs | **PASS locally** | Actual UART6 unit input; actual audio5/eDMA6 integrated chains |
| Actual clock producers | **PASS bounded pairs** | 143/143 internal requests/services; 986/986 external-clock workload requests/services; zero pending/coalesced requests |
| Full-ISR timing impact | **PASS observed comparison** | Same maximum cycles and identical source/DSP blocks in all three original/guarded pairs |
| Real chooser, Part, working/playing banks | **PASS bounded paths** | T1/T2/T5/T6 deselection/reselection, Part change and actual panel A→B→A |
| Saved-project compatibility | **PASS scoped** | Reuse prior actual SAVE; guarded cold reload restores all six edited controls and four active hybrid chains |
| Dense triggers / locks / UI / DMA | **PASS bounded paths** | Counts, sample spacing, CF delivery counters, native DMA trigger records, lock tuples, queue accounting and modeled ownership |
| Combined all-path stack ceiling | **UNVERIFIED — blocking** | No closed stock-task/indirect-callee and nested-ISR bound |

## Stack: what the guard proves and what it does not

The actual keyrepeat task is created with `[0x460d4780,0x460d4f80)`, 2,048 bytes.
Each sequencer invocation adds eight aligned exception bytes plus 208 handler
bytes. The original negative control reenters; the guarded handler defers the
request until it returns, with the next exception entering at the same SP.
Actual audio5 and level6 work still execute above IPL3. Same-level ATA DMA14 work
is deferred while that mask remains3. No returning level7 completion guarantee
is claimed; its terminal halt remains a fault policy outside the bounded probe.

The original nine-frame adversarial nesting result remains historical evidence,
not a natural playback overflow. Arbitrary host writes can still merge in the
single force latch while masked. They are **not independent musical ticks**:
the sequencer uses due flags and countdown state. An early test assertion that
multiplied IRQ acknowledgements by a fixed phase increment was invalid and was
removed. It is not reported as lost musical ticks or a firmware fix. Actual
producer/workflow results, below, are the clock evidence.

All accepted new observed task extents and bottom watches remained clean.
Maximum observed audio requirement is **1,348 bytes**, including observed nested
work; the earlier1,316 observation is not a ceiling. Created-task capacities are
unchanged: storage/keyrepeat/UI 2,048; voice 4,096; p2a/p2b/p2c/p1b/sys 8,192;
engine 16,384. Main's 4,096-byte extent remains inferred from adjacent allocations.
Across the new traces, smallest-task observed maxima include storage 76,
keyrepeat 1,352 and UI 1,384 bytes. Those are observations, not reserves or bounds.

**Maximum established all-path combined requirement: UNKNOWN.** The guard still
runs on interrupted-task A7. It does not turn the unused runtime-arena stack
allowance into an interrupt stack. The unchanged compiler audit's 680-byte render,
80-byte CF adapter and 348-byte snare entries are individual frames, not a closed
sum of stock callers, arguments, return addresses and higher-priority handlers.

The specific unresolved example is storage entry `0x4001ee30` → indirect call
`0x4001eef2`, through the driver table at `[0x460d16cc]`. No closed bound for that
preemptible call chain plus sequencer/audio/level6 work has been established.
Qualification needs the combined requirement compared with its 2,048-byte
capacity. A clean observed peak does not discharge that obligation. No overflow
or unsafe numerical ceiling was demonstrated, so no additional byte fix can
honestly be designated necessary from these results. Closing this specific
budget is the remaining remedy to the safety case; stack relocation/resizing
would be a separately approved structural change, not silently added here.

## Actual producers, progression and timing

Three original/guarded pairs used CPU 264 MHz, PIT 132 MHz and the cycle-driven
clock, real DSP payloads and simultaneous native DSP/CF/stock playback:

| Workload | Frames each image | Tick source writes / services, each | Max full ISR cycles, original / guard | Source/DSP blocks |
|---|---:|---:|---:|---|
| Existing mixed snare fixture |2,048|143 /143|85,474 /85,474|Identical |
| External MIDI clock |1,024|986 /986|85,484 /85,484|Identical |
| Eight-track dense locks at 300 BPM |4,096|Producer counts separately checked in bounded UI run|85,537 /85,537|Identical |

External input comprised 984 F8 bytes, one per16-sample frame, about 2,756 bytes/s
(below the MIDI wire limit), plus two startup source requests. The firmware
consumed all bytes and its musical clock counter reached 984. Source force writes,
clears and services agree; no request remained pending or coalesced in these
runs. This does not prove every malformed or arbitrarily timed input safe.

The dense fixture has eight active tracks, every step triggered, alternating
six-control locks and reversion, disabled source LFOs and retained active FX.
The first run delivers 30 triggers per track; the UI run delivers 31 per track.
All successive source events are exactly **2,205 samples apart at 300 BPM**,
including active retriggers and repeated pattern loops. No cumulative drift was
observed. Native published trigger flags and CF delivery counters match.

The existing live/interactive runners retain their instruction-rate sample clock;
the parsed cycle-clock option is applied by the sequencer runner. Consequently
the UI/chooser traces establish functional ordering and counted delivery in that
model, not cycle-driven physical arrival guarantees. The three paired sequencer
workloads above are the cycle-driven timing/progression comparisons.

New bounded modeled maximum: **324.003788 µs**, deadline **362.811791 µs**,
headroom **38.808004 µs**. The previous323.765152 µs remains a correct earlier
workload result; the denser case extends the observed maximum. Its85,537-cycle
maximum is the same in original and guarded images: observed guard peak delta0.
The 80% ceiling remains 290.249433 µs, now missed by 33.754355 µs. **The 20% engineering
margin remains UNWAIVED.** No synthesis optimization was attempted.

## Lifecycle and concurrency details

Actual SRC SETUP opened on PERKY row 5. Moving to FLEX row 1 and committing removed
the signature on each of T1/T2/T5/T6; returning to PERKY restored it while other
native/CF/stock tracks continued. Deselecting retained the old stored six values;
fresh PERKY admission intentionally initialized six defaults. Track selection
and dense knob edits retained each track's own control state. A real Part change
selected another pre-staged Part with its six controls and signatures intact.

The first bank script reopened PATTERN after BANK B had already opened
“BANK B: SELECT PTN”; that replaced the temporary choice. It was a harness-path
failure, not a demonstrated guard defect. The corrected real-panel path selects
the pattern trig directly and waits for the queued switch. Working and playing
banks both change A→B→A. The separate corrected bank run also performs actual
STOP-to-card profile export, producing `PKH20000.PRF`. Bank/Part tests remain
bounded cases, not every possible loader interleaving.

The actual earlier SAVE PROJECT receipt is reused. A fresh guarded boot loads
that saved card, restores T2's `[71,112,2,72,56,0]` exactly and produces significant
post-FX audio on T1/T2/T5/T6 over 512 frames. Serialization, init, native control,
PCM/state/RNG and six-word-guard code did not change.

The dense UI run supplies 16 key edges and 12 encoder reports; all are consumed.
Encoder deltas total+2 for each of A..F across the two selected CF tracks.
These one-detent reports leave the stored MODE choice unchanged; MODE transitions
are established by the lock tuples, not inferred from encoder report counts. There are 253 sys posts and 253 dequeues,
with zero final backlog. Alternating locked tuples and subsequent base-value
reversion match the fixture, including ALGO/MODE transitions.

For every captured active publication, native trigger flags match source events;
CF fixed-slot segment geometry matches the event split and sums to 16 samples;
stock records decode to 16 samples. The initial empty/inactive publications and
one terminal nontrigger frame not yet published at capture end are accounted
separately. No trigger is hidden in that terminal exception. The unchanged exact
transport tests retain their moving-cursor/fixed-slot/trailing 176-byte proof.
Modeled source ownership watches report zero overlaps or restarts, and all
accepted complete ISR samples meet the modeled period. A live quit can interrupt
a final ISR; it is excluded from completed-duration claims rather than called
an unbalanced firmware return.

## Physical uncertainties and stop

Physical cache/SDRAM/FlexBus/eDMA arbitration/coherence, interrupt release-to-entry
and release-to-completion latency, independent core completion, and actual timer/
probe/export cost remain unmeasured. Emulation establishes none of their silicon
worst cases. Physical timing is not made a prerequisite for its diagnostic
experiment; the **software stack qualification gap** is the blocking criterion.

No qualified guarded installable set is offered, and no flash authorization is
requested. The known physical rollback remains PERKY4S source
`16a8de19a17ee4cba765cbdb30ca051f85af4e23`, MAIN SHA256
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
No hardware changed. The current bounded task stops with the guard's scoped
passes and one explicit unverified essential gate.

Historical pre-guard report: `git show 3167a977:modules/perky/hybrid/SAFETY_QUALIFICATION.md`.
The exact commit containing this implementation and assessment is in the final handoff.
