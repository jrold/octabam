# PERKY hybrid implementation history — closed 14 October 2026

**CLOSED / UNQUALIFIED. No further performance experiments or margin waiver.**
The final engineering verdict and exact PASS/FAIL/NOT-RUN matrix are in
[CLOSEOUT.md](CLOSEOUT.md) and CLOSEOUT.json. This page retains implementation
history; the closeout supersedes its earlier next-step wording.
Cold-start initialization and full-ISR instrumentation are implemented and
locally tested. The final short-run modeled ISR peak is **319.861 us**,
including the small entry/return correction: zero observed period misses,
**29.611 us above** the proposed 290.249433 us advancement margin. The full
sustained workload and silicon qualification remain incomplete.

Branch `perky-cf-dsp-hybrid`; committed build source `19d1810429765d4a1c4e18bd24d92b9fa2c6f1f3`.
Runtime/optimization commit `ce882def`; measurement-harness correction
`28701a6d`. GPT-6.1 Sol / High, one agent, no model or speed override.
The preserved `perky-machines` ref remains `4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`.

## What changed

The hybrid loader decodes the lossless assets and initializes the two compact
CF voices plus a pristine reset template after hash verification, before RTOS
handoff. Loaded COLD/READY cookies replace BSS readiness assumptions. The audio
ISR owns generation changes and copies the 1,974-byte template at the event
boundary; UI callbacks never reset live state. No decoding, large constructor,
allocation or filesystem work occurs in `pk_render`.

A CF-only entry/tail hook measures each whole audio ISR once, independently
of split source callbacks. DTIM3 is declared at the established stock 132 MHz.
Fixed counters/rings, wrap-safe subtraction, a histogram, bounded seqlock
snapshots and two separate HC polling-site counters are included. HC sites
are not assumed to represent independent DSP core completions. No DSP code,
upload, placement, table or guard changed.

**No CF METER reading is required.** The UI task automatically writes a fresh
`/PKH20000.PRF` (then increasing names) after observing RUN followed by STOP.
It never overwrites an existing file. The 1,864-byte record contains a source
identity and coherent counters; `tools/perky/read_hybrid_profile.py` validates
it against the exact BUILD.json. Actual stock filesystem export passed under
the port. Physical card export and silicon timer read cost remain unverified.

## Two retained measured, bit-exact iterations

Same 4,000-frame delayed-trigger / Part-index-poke short case, corrected
`--cf-cycles-clock 1.0`; these are runtime late-stamp spans, not hardware bounds:

| State | Max ISR timer span | Result |
|---|---:|---|
| Fixed initialization/profiling, before optimization | 368.167 us | Period exceeded |
| Iteration 1: defer overwritten control derives to last pass | 349.598 us | Bit-exact; 80% margin fails |
| Iteration 2: retain exact smoother recurrence and required boundary/sticky updates | 315.871 us | Bit-exact; 80% margin fails |

Both iterations passed all 19 original-reference sections. The final packaged
adapter passed 1,024 frames / 2,048 exact source records and complete two-voice
state/RNG snapshots, every split offset, plus eight out-of-range fallback cases.
A subsequently authorized third iteration was measured and rejected; see ITERATION3.md.

A separate final 4,000-frame snare/snare comparison measured **319.861 us**
for the complete corrected ISR model span, leaving 42.951 us to the period.
Mean conditional profiler overhead was **3.195 us**; disarming CF reduced
mean service by **54.949 us**. Common hook overhead remains in the off run;
differences of maxima are not an overhead bound. External PC pairs cover
4,000 frames; adding the model's first LEA (1 cycle) and RTE (10 cycles)
accounts for the omitted instructions. The runtime late stamp itself excludes
small entry/footer work. Its boot calibration reading zero is not evidence
of zero physical timer-read cost. Cache/stall effects and silicon remain unproven.

**Retraction:** recovery's 98,632 cycles / 370.797 us was ACK-to-ACK CPU work,
including intervening tasks, not an ISR duration. The original ISR-miss
interpretation is withdrawn everywhere in the current reports. Independent
new ISR timing reproduced a true pre-optimization overrun as shown above.
The inherited `--poke-before-play` long-word syntax also wrote only one byte;
invalid off/disarmed comparisons were discarded. New code writes four explicit
bytes and asserts the effective switch and counter activity.

## Verification and limits

- PASS: baseline/CF foundation 18/18 (including corrected-emulator CTest),
  original-reference PCM/state/control gates, boot/loaded-cookie readback,
  single ownership, 192 native comparisons, 288 CF split cases and UI bounds.
- PASS: frozen DSP identity and both-core P/X/Y/table readback through four
  600-frame configurations assigning all twelve retained FX. Independent
  nonzero processing proof for every effect remains incomplete.
- PASS: final smoke, 22,450-frame sequencer split drift and separate eight-track
  source/post-FX audio capture. The historical T3 assertion does not reproduce.
- PASS: dirty initialization, no RT asset writes/UI reset, snapshot collision,
  timer wrap, actual filesystem export, six profile-file negatives and nine
  evidence negatives. Direct-call lifecycle fixtures are not complete stock
  Bank/Part replay or backlog bounds.
- PASS: `REFHASH_JOBS=1 scripts/refhash.sh check`, all 24 cases bit-identical.
- PASS: committed-source rebuild; MAIN, fragmented image, ELF and raw runtime
  bit-identical. Only unrelated user text remains untracked. Baseline receipt
  predates a decoder whitespace cleanup and measurement-switch helper fix;
  synthesis inputs are identical and exact executed source hashes are retained.
- BLOCKED as expected: aggregate probe gate. Current card/MIDI/ELUP wrappers
  are deliberately absent. Archived old wrappers were hash-checked against
  their preserved copies before removal from the current probe directory.
- NOT RUN at the initial two-iteration stopping gate, still incomplete after iteration 3: all mandatory/additional
  >=60-second rows, worst >=600-second run, complete lifecycle/backlog stress,
  current wrapper corruption/cap roundtrip and physical MKII tests.

The actual ELF has 200,704 decoded waveform BSS bytes and 3,948 live CF voice
bytes. Physical normalized extents do not overlap; the stack reservation is
not a measured hybrid ceiling. Current MAIN is only a simulation input:
`out/perky/hybrid/probe/mainos_PKHYB2P.bin`, SHA256
`46bd31dba62651500de6c672ec0e3e50c38533f8edbe39cd12e200318c93ca2a`.

The first plain refhash helper unexpectedly created temporary checkouts,
contrary to the workspace restriction. Their source identity was audited;
only those helper checkouts were removed. The compliant single-checkout rerun
passed, and `git worktree list` now contains only the original directory.
Evidence is in `out/perky/hybrid/resume-fixes/`; complete commands, hashes and
status-by-contract are in PHASE2.json. No flash, push, upstream integration,
CI or Goal 3 work occurred.

The bounded investigation is closed after the original two improvements and
one rejected extra attempt. Functional/safety qualification remains incomplete
independently of the timing margin. The single closeout recommendation is a
targeted non-optimization investigation of clock/timer and missing safety gates;
no hardware probe or additional tuning is authorized. Hardware handoff remains
withheld. Automatic card export avoids CF METER reading if a future probe is
separately qualified and approved.

## Authorized additional iteration

[Iteration 3](ITERATION3.md) measured empty renders first and tested one
bit-exact skip. It saved 0.605 us mean ISR time but worsened peak by 0.150 us
and p99 by 0.335 us, so the runtime was restored exactly. Retained peak and
remaining shortfall are unchanged. All three authorized attempts are consumed.
