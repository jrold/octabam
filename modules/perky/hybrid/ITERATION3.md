# Additional CF-only iteration 3 — rejected and restored

The user authorized one additional local iteration after the original two.
It is now consumed. **No peak saving was retained. No flash or push.**

First measured the unchanged `f1fa347c` runtime over the same 4,000-frame,
132 MHz timer / corrected 266 MHz CPU model, snare/snare integrated workload.
686 zero-length snare renders averaged **1.655 us each** (maximum 1.707 us).
They contributed 0.284 us/frame on average, at most 3.335 us/frame, and **zero
in the worst frame**. An independent target-image proof found 1,024 empty
renders left prepared/rendered state, RNG and destination bytes unchanged
across both instances, three algorithms and all modes.

The one candidate changed only the CF callback's synthesis call condition:
skip it for `count == 0`. All event/control, trigger latch, cursor reservation,
fixed-slot publication and profiler accounting still execute. No control
fusion, renderer rewrite or second candidate was attempted.

| Complete modeled ISR | Before | Candidate | Saving |
|---|---:|---:|---:|
| Mean | 196.577683 us | 195.972475 us | 0.605209 us |
| p99 | 213.917293 us | 214.251880 us | **-0.334586 us** |
| Maximum | 319.860902 us | 320.011278 us | **-0.150376 us** |
| Period misses | 0 | 0 | — |

The candidate removed all empty engine calls and improved the mean, but the
peak and p99 regressed. The mean delta includes compiler/caller/scheduling
effects; it is not a direct attribution solely to the measured empty calls.
The original maximum is frame 0, where there was no empty render to eliminate.
**Rejected for this deadline task and restored the exact prior runtime.**
The retained maximum remains **319.860902 us**, **29.611469 us above** the
proposed 290.249433 us margin. Short-run zero misses are not qualification.

PASS against actual before/candidate images: 4,096 callback boundaries across
all 17 splits (including 242 zero-length callbacks), identical complete two-voice
state/RNG, full 336-byte slots, moving cursor and render/hit counters; the
existing 1,024-frame hybrid runtime suite; single owner, 192 native comparisons,
288 CF split cases and UI bounds. Frozen DSP generation/upload/guard identity
passed. Four 600-frame actual-image configurations assigned all twelve retained
FX and preserved both cores' P/X/Y and immutable tables. DSP and FX source
inputs were unchanged; these checks do not establish independent nonzero
processing of every effect.

Measurements use existing PC watches without adding firmware instrumentation:
every ISR has a matched pair, plus the corrected model's first LEA (1 cycle)
and RTE (10 cycles). Engine spans include model JSR/RTS (3+5 cycles). Results
remain model-only; sustained matrix, full lifecycle/backlog and silicon gates
are unchanged and incomplete. Automatic STOP-to-card export remains available
for future qualified testing without CF METER readings.

Evidence, exact commands/hashes, rejected patch/source/image and before/after
measurements: `out/perky/hybrid/iteration3/RESULT.json`, `candidate.patch`,
`candidate/`, `before/`, `before-measurement/`, `after-measurement/` and
`RESTORED.json`. New reusable tools are
`tools/verify/measure_perky_hybrid_zero_render.py` and
`tools/verify/verify_perky_hybrid_zero_render.py`.

No additional optimization is authorized. The next decision is review of a
separately scoped CF event/control investigation; no fourth attempt was made.
