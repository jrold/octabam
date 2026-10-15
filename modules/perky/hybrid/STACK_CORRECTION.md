# Stack correction decision — 15 October 2026

**Historical deliverable B; subsequently approved and implemented.**

The approved successor is [PRIVATE_STACK_QUALIFICATION.md](PRIVATE_STACK_QUALIFICATION.md),
with the changed firmware, scoped private/residual budgets and new package hashes.
The decision and unchanged checkpoint evidence below predate that approval.

Starting checkpoint: `821cc49c05728b6e3730ce3c934dfef7f04b7b90`, existing
`perky-cf-dsp-hybrid` checkout. The IPL3 guard is preserved. No firmware source,
DSP, synthesis, FX, loader, stock allocation, wrapper or hardware changed in this
task. The local commit adds this assessment and reproducible host probes.

Relocating the small stacks is **spatially feasible**. It is not established safe
within this bounded task: there is still no closed combined task/interrupt
requirement from which to choose their new capacities. Lack of a bound is not
proof of overflow, insufficient DRAM, or impossibility of relocation. Increasing
the sizes to an attractive round number would not resolve that proof obligation.
The requested fallback/stop boundary applies here; no further callback census or
performance investigation is started.

## Ownership and initialization

✅ The actual firmware's create routine at `0x400005fc` takes
`(TCB, entry, priority, base, bytes)`. It computes `top = base + (bytes & ~3)`;
stores the exit address at top−4, entry PC at top−8 and exception format/SR at
top−12; saves top−12 at TCB+`0x48`; and initializes the ready and waiter fields.
The new probe checks those stores **before** make-ready, for all ten created
tasks, and cross-checks the creation records and actual scheduler dispatches.

| Task | Create call | Entry / priority | Actual stack [base, top) | TCB |
|---|---|---|---|---|
| USB storage worker | `0x4001dfec` | `0x4001ee30` / 5 | `[0x460bc42c,0x460bcc2c)`, 2,048 B | `0x460bcc2c` |
| Keyrepeat | `0x400403f0` | `0x4005593c` / 4 | `[0x460d4780,0x460d4f80)`, 2,048 B | `0x460d4f80` |
| UI | `0x4004041a` | `0x40056c40` / 3 | `[0x460d51d4,0x460d59d4)`, 2,048 B | `0x460d59d4` |

These are absolute static addresses passed by stock initialization, not malloc
results. All three tops equal their TCB addresses: **changing size alone writes
through the TCB**. Growing downward also needs ownership proof: storage's queue
buffer ends at its base; the keyrepeat callback word is immediately below its
base. Relocation must replace both base and size while retaining each TCB, entry
and priority. Main's extent remains inferred; this task does not promote it to
a captured allocation.

## The cited storage call is resolved

✅ Mount calls `0x40015e28` and writes its returned table pointer to
`0x460d16cc` at `0x400616a4`. The returned table is `0x46c85c76`.
Its first entry is `0x400157b4` for PIO or `0x400157dc` for DMA, selected from
IDENTIFY capabilities. Both reach `0x4001568c` → `0x40015098`. The selector's
other operations include write entries at table+8; they are not the read entry
at `0x4001eef2`. Unmount clears the table pointer.

✅ The bounded control-flow audit closes **this read call**, including both
wrappers, all branches of the common dispatcher, its seven command leaves,
memcpy and event-wait/trap accounting. Repeated polls/loops have constant SP;
there is no recursion in this closed subgraph. The target input is hash-pinned.

| Simultaneously retained component | Bytes |
|---|---:|
| Task exit word + worker frame + outstanding arguments + indirect JSR | 4 + 44 + 28 + 4 = 80 |
| Read wrapper's arguments and JSR | 24 + 4 = 28 |
| Common command queue frame and JSR | 24 + 4 = 28 |
| Dispatcher's saves, command arguments, JSR and largest command leaf | 8 + 16 + 4 + 8 = 36 |
| **Scoped total, excluding preempting interrupts** | **172** |

The actual PIO worker is exercised through `0x4001eef2`; its A0 equals
`0x400157b4`. At dispatcher depth 144, the real sequencer interrupts it, and
UART6 interrupts the sequencer. A7 returns exactly to the interrupted instruction's
stack. Observed combined peak 624 B; zero writes to the 32-byte bottoms of all
ten created stacks after initialization. These are bounded observations. This
focused run has no active DSP/audio playback and uses the IPS sample clock;
it does not replace the previous integrated audio5/eDMA6 runs.

✅ Keyrepeat's closed task subgraph needs 104 B below entry A7, **108 B including
its exit word**, with trap/scheduler-frame accounting. Neither 172 nor 108 is a
combined interrupt-stack ceiling. The DMA wrapper is statically audited; the
new actual-card execution uses PIO only.

## Combined budget: still open

A sufficient budget must include the task maximum and every permitted live
interrupt prefix: level 2 storage timer; level 3 sequencer **or** ATA DMA14;
level 4 USB/serial; level 5 audio **or** ATA/counter; and level 6 eDMA/UART, plus
their exception records/alignment. Mask lowering must also be audited, rather
than assuming one frame per level. The IPL3 change closes sequencer self-reentry;
it does not bound every callee or every other mask transition. Level 7's terminal
halt remains the existing fault policy, not a returning workload.

**Conservative all-path combined budget: UNKNOWN.** The audit refuses an unknown
call instead of assigning it zero. Its recorded stopping sites include UI's
loaded callback at `0x40056aa2`, other storage cases at `0x4001c7c0`, sequencer
register calls at `0x4009ee14`, and audio source dispatch at `0x4000a150`.
Some of these can be resolved with further analysis; this is an explicit bounded
stop, not a claim that they are inherently unresolvable. No proposed relocated
stack is designated safe. A different target, missed edge, SP-writing form or
table writer would falsify the scoped bounds and requires re-audit.

## Available DRAM and the proposed resource envelope

✅ Actual guarded MAIN operands at **all 24** arena-base/derived sites and all
four count/fill/clear/cap sites agree with the existing reservation. The sampler
starts at `0x41600de0`, retains 12,653 usable pages / 77,740,032 B, and ends at the
stock arena end. The runtime's live BSS and retained loader stage end below
`0x40cc4800` after 32-byte alignment. No recorded preboot/runtime extent overlaps
`[0x40cc4800,0x41600de0)`: **9,684,448 B available within the existing reserve**.
The uncached alias adds `0x08000000` and is the same physical memory.

**Proposed one architectural change:** give the full audio IRQ, including its
existing profiler prelude and nested higher-priority handlers, a private stack.
Extend the existing `pk_hybrid_isr` / `pk_hybrid_isr_rte` assembly hooks:

1. On entry, save interrupted A7 to a private word, then load the private top.
2. Run the existing prelude, stock frame body, CF callbacks and higher IRQs.
3. After the existing register restore/252-byte release, restore interrupted
   A7 immediately before the existing RTE. The original exception record stays
   on the task stack. The IPL3 sequencer guard stays in force.

This avoids a new scheduler, common-IRQ nesting counter or additional mask window.
🟡 It relies on audio remaining non-reentrant at IPL≥5 and on higher handlers
neither rescheduling tasks nor modifying the private saved-A7 word. These must be
proved over the completed implementation before acceptance. The residual task,
sequencer and non-audio IRQ budgets still require proof; the switch alone does
not qualify them.

| Proposed resource (cached view) | Extent / cost |
|---|---|
| Bottom guard | `[0x415ffd80,0x415ffda0)`, 32 B |
| Private audio stack | `[0x415ffda0,0x41600da0)`, 4,096 B |
| Top guard | `[0x41600da0,0x41600dc0)`, 32 B |
| Saved interrupted A7 | `0x41600dc0`, 4 B |
| Alignment padding | `[0x41600dc4,0x41600de0)`, 28 B |
| **Total reservation** | **4,192 B; zero additional sampler pages** |
| Remaining available reserve | 9,680,256 B |

**4,096 B is an approval/qualification envelope, inherited from the existing
hybrid design allowance; it is NOT a derived safe minimum or an implemented
stack.** The current maximum observed audio requirement is 1,348 B including its
exception record and nested work. That peak cannot certify 4,096 B. Approval
would authorize this architecture within the stated resource cap; acceptance
must reject it unless the complete private-stack bound fits the cap and every
residual task budget fits its actual allocation. No automatic size escalation.
The named region must become an enforced module/build allocation, with BSS,
compressed-stage, preboot and cached/uncached ownership checks in the fresh build.

## Measured cost and qualification boundary

✅ Independently assembled/disassembled instruction specimens, 100 repetitions
each in the existing ARM64 emulator, cost: A7 store 1 modeled cycle, absolute
LEA 1, A7 reload 2. Extending the existing hooks needs **three extra instructions,
18 instruction bytes and 4 modeled cycles per audio IRQ** (0.015152 µs at 264 MHz).
No wrapper or switched firmware was built. This is instruction calibration;
cache/SDRAM and integrated timing costs remain unmeasured. The guard regressions
still pass; all old firmware, ELF and ELEK/card/MIDI artifact hashes are unchanged.
Final ELF alignment and compressed/wrapped size changes require the approved build.

The previous integrated maximum remains 85,537 cycles / 324.003788 µs, with zero
observed modeled duration misses in its recorded runs. Adding the isolated cost
arithmetically gives 324.018939 µs; **this is not a new integrated measurement**.
The deadline is 362.811791 µs. The unwaived 80% ceiling is 290.249433 µs: the existing
shortfall is 33.754355 µs and the arithmetic projection is 33.769506 µs. No new
firmware deadline-pass claim, timing-margin waiver or synthesis optimization.
The existing profiler timestamps would omit part of the added switch; a future
qualification must measure actual exception entry through final RTE, including
the added instructions, rather than hiding them outside the timestamp window.

The guarded MAIN remains
`055cced1bb5319c35ee7d4708359a60a3e207a69d73711d2d536beadca060fbe`;
runtime ELF remains
`f35c87b393ecc798eb103fcf9672f7b44ca64bf1f3df684d644d63b96e512a9e`.
Existing card/MIDI wrappers contain the **older unguarded MAIN**, not this trial.
They are not offered as an installable candidate. Exact unchanged identities,
probe/source/library bindings and commands are in [STACK_CORRECTION.json](STACK_CORRECTION.json).

Reproduction (local only, existing private fixtures):

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid_stack_structure.py --selftest
.venv/bin/python3 tools/verify/verify_perky_hybrid_stack_structure.py --probe
.venv/bin/python3 tools/verify/verify_perky_hybrid_ipl_guard.py --selftest
```

Four new analyzer controls and five guard controls pass. The focused C++ probe
passes. The structural assessment deliberately exits 1 for the still-open
combined bound and writes `out/perky/hybrid/stack-correction/STRUCTURE.json`.
The existing guard's actual-image `--unit` was also rerun successfully; its fresh
receipt is retained separately and the historical receipt is byte-identical.
No full historical qualification rerun, firmware rebuild, new package, flash,
MKII test, push, branch/worktree creation or Goal 3. **Finish and STOP.**
