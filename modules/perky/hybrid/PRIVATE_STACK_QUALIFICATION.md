# Approved private audio stack — local diagnostic qualification

**Diagnostic candidate for review; no hardware testing authorized or performed.**
The approved 4,192-byte architecture is implemented in source commit
`7878b3d6` on the existing `perky-cf-dsp-hybrid` branch. The IPL3 guard remains
at `0x400a1e66`. No synthesis, DSP, FX, sampler capacity, task creation parameter
or TCB changed. The exact source commit, embedded source identity, artifacts and
local evidence hashes are in [PRIVATE_STACK_QUALIFICATION.json](PRIVATE_STACK_QUALIFICATION.json).

This closes the scoped private-audio / three vulnerable 2,048-byte task-stack
budget described in [STACK_CORRECTION.md](STACK_CORRECTION.md). Qualification
assumes valid stock dispatch indices/tables, the stock C ABI and the normal
seven-state eDMA transfer protocol. It does **not** assert a new exhaustive proof
of every unchanged stock task or corrupted-input path. The larger stock tasks'
base call graphs remain explicitly open in the receipt; the correction cannot
increase their audio-related task-stack demand. Physical timing and memory
coherence remain untested. The production 20% timing margin is unwaived and unmet.

## Structural change and actual ownership

✅ The entry saves original exception A7 to the private word, loads private top,
then runs the existing profiler and complete stock audio frame, including CF
callbacks. After the existing 252-byte frame/register restoration, it reloads
original A7 immediately before RTE. The original exception format/SR/PC stay on
the interrupted task's stack. There is no scheduler change or new mask window.

The three added instructions occupy 18 instruction bytes; ELF alignment makes
`runtime.raw` **20 bytes larger**, 359,716 bytes. Independent model calibration
measures **four additional instruction cycles per audio IRQ**, 0.015152 µs at
264 MHz. The synthetic switch test independently checks complete measured ISR
cycles against executed cycles, excluding the interrupted task's four-cycle NOP.
This is not a silicon latency claim.

✅ The existing module `DramRegion` allocator owns the whole envelope. The linker
places it at the top of the **existing** runtime reservation; both the ordinary
placement checks and hybrid disjoint-stage overlap check enforce it. The fresh
memory report includes cached/uncached normalized extents and reports no overlap.

| Resource | Cached physical interval |
|---|---|
| Bottom write-watch guard, 32 B | `[0x415ffd80,0x415ffda0)` |
| Usable private stack, 4,096 B | `[0x415ffda0,0x41600da0)` |
| Top write-watch guard, 32 B | `[0x41600da0,0x41600dc0)` |
| Saved interrupted A7, 4 B | `[0x41600dc0,0x41600dc4)` |
| Alignment padding, 28 B | `[0x41600dc4,0x41600de0)` |

The saved word is written on **every entry before being read**. Neither BSS zero
initialization nor guard initial contents are required. The uncached view adds
`0x08000000`; the negative guard test verifies that alias reaches the same watch.
Runtime/BSS and retained loader stage end below aligned `0x40cc4800`, leaving
**9,680,256 unallocated bytes** before the private envelope. The sampler still
starts at `0x41600de0`, with 12,653 usable pages / 77,740,032 bytes. No additional
sampler page is reserved; all arena base/derived/count/fill/clear/cap operands
agree with the fresh allocation report.

✅ The actual create/init probe checks all ten created task contexts before
make-ready, then actual scheduler dispatches. Storage, keyrepeat and UI retain
exactly the allocations and TCBs recorded in STACK_CORRECTION.md. Their original
exit words and exception initialization are checked. Main's inferred extent is
not promoted to a newly captured allocation.

## Static requirement, including residual nesting

✅ The hash-pinned MAIN and ELF audit follows stack changes, arguments and return
addresses, CFG branches, fixed compiler tables and resolved indirect callees.
Unknown edges, recursion without a separate bound, growing SP loops, inconsistent
joins and undecoded SP/control instructions fail closed. The private boundary
ends **before** A7 is restored to the task; the original exception is counted on
the residual side. Peaks observed below are not used as static callee bounds.

The largest private body path is:
**252-byte stock frame + 16 bytes retained arguments + 4-byte JSR + 1,036-byte
`pk_render` call graph = 1,308 bytes**. This includes both routes and stock source
fallbacks. It does not assume that signed PERKY tracks are the only sources.

Important indirect/control contracts, read from this exact image:

- Storage `0x4001eef2`: the mounted `0x460d16cc` table at `0x46c85c76` permits both
  PIO `0x400157b4` and DMA `0x400157dc`. The complete worker bound includes its
  other valid operation cases, not just that read call.
- Audio previous/current callback arrays `0x400d61d0..0x400d6210` are **mutable**.
  Initialization writes the empty renderer; the masked source type selects the
  eight-entry renderer table at `0x400d6434`; the audio loop copies current to
  previous. The audit includes every table target, including patched `pk_render`.
- The voice renderer's local sample-reader pointer has two assignments at
  `0x40008132` / `0x40008142`; its four PCM-format branch entries and four
  sign-combination helpers are included. Valid stock mono/stereo 16/24-bit
  formats, machine types 0..7 and LFO shapes 0..31 are preconditions, not observed
  current RAM values promoted to immutable tables.
- UI's sole `0x460d1e60` writer and its three setup callers supply both valid
  callback targets. All seventeen unique binding lists passed at the twenty
  `0x4007e760` registration sites contribute their possible primary callbacks;
  the `0x4007e760` / `0x4007e81c` rebuild paths own the eight RAM binding records.
- Pinned compiler jump tables include all range-checked sequencer/UI arms.
  Stop-all at `0x40006820` makes eight sequential calls with arguments 0..7;
  those calls take the nonrecursive arm. Its extra recursion depth is at most one.
- Generated CF helper spills resolve to `pk_hybrid_commit_longs` and both
  resonant update helpers. No function-pointer value is inferred merely from
  the initial contents of writable MAIN/runtime memory. Register propagation
  uses the stock C callee-save ABI; restored registers and auto-updated address
  registers are invalidated conservatively.

✅ The actual post-mount controller census also includes DTIM0/1/2/3: vectors
`0x61/0x62/0x64/0x65`, levels 3/1/4/4. The earlier interrupt summary omitted these
from its level table. The dormant level-5 counter handler is included as well.
The private reachable graph has no scheduling TRAP. Its literal SR writes are
IPL5/7; the other writes restore saved SR. PIT0 rescheduling is level 1 and is
masked throughout private ownership. IPL3 prevents sequencer self-reentry.

One eDMA state lowers IPL6 to IPL5 during housekeeping. It increments state 5
**to 6 before lowering**; state 6 never lowers its mask. UART6 immediately masks
to 7. Thus the additional live prefix is bounded by eDMA 168 + exception/alignment
11 + max(UART0 28, UART1 24, state6 16) + exception/alignment 11 = **218 bytes**.
Repeated arrivals cannot accumulate returning same-level UART frames. The
normal DMA state/acknowledgement protocol is required; arbitrary spurious DMA
interrupts outside that protocol are not qualified. Level 7 retains stock's
terminal halt policy.

| Private requirement | Bytes |
|---|---:|
| Complete body call graph | 1,308 |
| Higher-priority nesting, including alignment | 218 |
| **Conservative total / capacity** | **1,526 / 4,096** |

For a residual task, sum one permitted live frame at each level, including both
DMA levels in its special nesting window. This deliberately overcounts mutually
exclusive paths. Every exception receives eight frame bytes plus **three alignment
bytes**, even where the caller is aligned.

| Level | Largest body + exception/alignment | Bytes |
|---|---|---:|
| 1 | DTIM1 96 + 11; also covers PIT0/trap context prefix | 107 |
| 2 | PIT1 28 + 11 | 39 |
| 3 | sequencer 684 + 11; also covers DTIM0/ATA DMA | 695 |
| 4 | DTIM3 100 + 11; also covers USB/serial/DTIM2 | 111 |
| 5 | ATA 72 + 11; also covers counter or audio's original exception prefix/tail | 83 |
| 6 | special eDMA/UART nesting above | 218 |
| **Residual IRQ allowance** | | **1,253** |

| Vulnerable task | Body below entry A7 | Exit word | IRQ allowance | Total / capacity |
|---|---:|---:|---:|---:|
| Storage | 320 | 4 | 1,253 | **1,577 / 2,048** |
| Keyrepeat | 104 | 4 | 1,253 | **1,361 / 2,048** |
| UI | 584 | 4 | 1,253 | **1,841 / 2,048** |

The tightest result leaves **207 bytes**, including the untouched 32-byte bottom
watch band. Original audio can no longer add its body to those task stacks.
A missed table writer/target, ABI-breaking callee, out-of-contract index, SP form,
mask-lowering cycle or scheduler path would falsify these scoped budgets and
requires re-audit. This is a bounded engineering correction, not an assertion
that the entire proprietary OS has been formally verified.

## Actual changed-firmware qualification

✅ Six scenarios complete **52,608 balanced private switches/returns**: mixed
2,048 frames; dense 4,096; external clock 1,024; chooser/Part/bank lifecycle
28,392; real panel SAVE PROJECT 16,536; cold saved-card reload 512. The maximum
observed private requirement is **1,340 bytes**, within the derived 1,526-byte
budget. There are zero task-extent violations, bottom/top guard writes,
A7/GPR/exception-record/owner/mask violations, or modeled DMA read/write overlaps.
The memory-only probes do not write back to the user's input cards.

The batch harness stops immediately after its last frame ACK. Its final saved-A7
store can therefore be in flight before the next private switch; the receipt
records this partial entry explicitly, rather than counting a missing return.

Actual interrupted-storage → sequencer3 → UART6, real eDMA housekeeping → UART6,
and real eDMA housekeeping → state6 paths pass. The latter two observe 208 and
200 bytes below a seeded interrupted SP, both within the independently derived
218-byte allowance (212 before alignment). This focused test seeds the SP/state;
the integrated scenarios separately execute complete real audio and task paths.

Twelve synthetic calibration cases cover both stepping modes, nested IRQs before
the entry LEA, at first private instruction, in the body, before reload and before
RTE, plus deliberately low IPL, changed owner and uncached guard writes. They
caught and corrected observer double-counting of an instruction preempted before
execution. Four inherited observer controls, five new static-flow controls, four
inherited stack controls and five IPL3 controls pass. The unchanged and guarded
actual-image IPL3 adversarial regression still passes, including the documented
one-bit force-latch burst limit; no claim of arbitrary burst preservation is made.

✅ Rebuilt actual firmware also passes exact CF PCM/state/RNG/dependency checks,
poisoned-BSS native first record/state/decoded PCM, owner/codegen, all 288 split
cases, all eight dispatch tracks, SRC/PMTR/UI, malformed/corruption refusals,
both DSP cores and all twelve retained FX. Mixed **20,480** and dense **40,960**
source/DSP block records equal the preserved IPL3 runs exactly. Internal clock
progression and all 984 scheduled external F8 inputs progress through the guarded
path; the external run records 987 ticks including three startup ticks. Real
chooser, Part, playing-bank, project save and cold reload preserve signatures,
all six saved controls and four active post-FX chains.

✅ No new modeled frame deadline miss: zero in the 7,168 batch frames with the
sample-cycle/deadline mode enabled, and zero measured complete ISR duration misses
across the six scenarios. Maximum complete ISR is **85,562 modeled cycles /
324.098485 µs**, including entry, nested work and RTE. The period is 362.811791 µs;
the unwaived 80% ceiling is 290.249433 µs: **33.849052 µs shortfall**. Interactive
panel tests use the existing IPS scheduler clock; they do not establish a
release-to-entry deadline or substitute for the batch timing runs. No synthesis
optimization or production timing-margin waiver occurred.

## Exact diagnostic packaging

✅ Card and MIDI round-trip to the exact ELEK/MAIN. Malformed/truncated packages,
memory overlap and arena-cap errors are rejected. Build12's MAIN is 1,483,166
bytes. These are new packages containing **both** IPL3 and the private stack:

| Artifact under `out/perky/hybrid/private-stack/probe/` | SHA256 |
|---|---|
| `mainos_PKHYB2P.bin` | `d254bc2f72a1c78d75f1652f89311d0b841246ad228fc6dc3324fd6717c00f48` |
| `platform/runtime.elf` | `3ec97322ae4ff9fbe53c6d58e051a7174bac324abe594e90db20ca0d702d9bcf` |
| `elek_PKHYB2P.bin` | `c0328837340929a1bee7a0b837baecd77662bd1702b25284775d01a92b51e1a4` |
| `OCTATRACK_PKHYB2P.bin` | `aec75e1484ed37f70801d51ba78d44fbd83501d4c9875799acf7f8328c4652c4` |
| `OCTATRACK_OS1.40C_PKHYB2P.syx` | `f155d1eff0b816250bb17b656b3353b3d08df7afaab74d2ed768027069a20304` |

Reproduction uses existing private stock/card fixtures and local toolchains:

```sh
.venv/bin/python3 tools/perky/build_cf_dsp_hybrid.py --work out/perky/hybrid/private-stack
.venv/bin/python3 tools/verify/perky_private_stack_bounds.py --selftest
.venv/bin/python3 tools/verify/perky_private_stack_bounds.py
.venv/bin/python3 tools/verify/verify_perky_hybrid_private_stack.py --build-observer
.venv/bin/python3 tools/verify/verify_perky_hybrid_private_qualification.py --units
.venv/bin/python3 tools/verify/verify_perky_hybrid_private_stack.py --run mixed --frames 2048
.venv/bin/python3 tools/verify/verify_perky_hybrid_private_stack.py --run dense --frames 4096
.venv/bin/python3 tools/verify/verify_perky_hybrid_private_stack.py --run external --frames 1024
.venv/bin/python3 tools/verify/verify_perky_hybrid_private_qualification.py --panel --saved
.venv/bin/python3 tools/verify/verify_perky_hybrid_runtime.py --work out/perky/hybrid/private-stack --frames 128
.venv/bin/python3 tools/verify/verify_perky_hybrid_cold_safety.py --probe out/perky/hybrid/private-stack/probe --out out/perky/hybrid/private-stack/COLD.json
.venv/bin/python3 tools/verify/verify_perky_hybrid_probe_gates.py --work out/perky/hybrid/private-stack
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_packages.py --probe out/perky/hybrid/private-stack/probe --out out/perky/hybrid/private-stack/package-check
.venv/bin/python3 tools/verify/verify_perky_hybrid_private_qualification.py --assess
```

The final committed-source rebuild is byte-identical to the tested MAIN, ELF,
raw runtime, ELEK, card and MIDI. No proprietary firmware bytes are committed.
Remaining physical risks: cache/SDRAM/FlexBus/eDMA arbitration/coherence and actual
interrupt latency; silicon worst-case timing; stock fault paths and malformed
input outside the pinned dispatch contracts. PERKY4S remains the physically
working release. This candidate awaits the user's review **before any MKII test**.
No flash, push, GitHub CI, new branch/worktree, upstream integration or Goal 3.
**Finish and STOP.**
