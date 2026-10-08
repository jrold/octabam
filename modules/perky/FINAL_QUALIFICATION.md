# Perky Machines — final four-algorithm software qualification

Date: 2026-10-08

This checkpoint covers the locked four-voice milestone implemented by the
ColdFire source-machine architecture. It is intentionally separate from physical
Octatrack audition and from card/MIDI firmware packaging.

## Qualified architecture

- Four independent Perky Machines voices on Octatrack tracks T1/T2/T5/T6.
- First SRC page is exactly:
  - A Decay
  - B Tune
  - C Param 1
  - D Param 2
  - E Mode
  - F Algo
- All six parameters are independently p-lockable through the normal source
  parameter staging path.
- Algo and Mode changes are applied at the exact event split before the trig's
  post-event samples are rendered.
- Qualified Algo set:
  - Fold 1
  - Fold 2
  - Karplus
  - Noise/Tone, with physical modes M1/M2/M3
- Perky synthesis runs on ColdFire and emits ordinary stock source PCM records.
- The final Perky module has no DSP section, no DSP-range claims and no DSP
  preboot arena. The stock DSP remains responsible for AMP -> FX1 -> FX2.
- The final remix retains all 14 stock effects, including Plate, Spring and
  Dark reverb, leaves the stock FX1 chooser untouched, and hides/locks no stock
  effect rows.

## Exact firmware/reference provenance

PĒRKONS v1.2.1 image SHA-256:

`adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6`

The qualification extracts the exact pitch, chromatic, envelope and wave assets
from that image and compares production ColdFire output to PerkyBits' native
v1.2.1 reference renderers.

`tools/verify/verify_perky_cf_qualified_sources.py` pins **39 production,
qualification and release files** by SHA-256, including the production renderers,
shipping `pk_render()` path, top-level qualifier, hot-loop safety, stock-record
ABI, p-lock reversion, runtime-reset and runtime-memory gates, source/FX
architecture gates, stock-DSP identity checker, final release builder and
ColdFire codegen/linkage audit.

Any pinned-source drift invalidates the PCM qualification until the complete
suite is rerun and the manifest is deliberately refreshed.

## Executed results

Top-level gate:

`tools/verify/verify_perky_cf_final.py`

Result: **PASS**

### Control/state preparation

- Fold1/Fold2/Karplus: **4,608** OT-domain control states byte-exact against the
  recovered original ARM update/trigger translation.
- Noise/Tone: **1,536** OT-domain control states byte-exact against the recovered
  original ARM update/trigger translation.
- Dynamic four-track p-lock sequence: **1,024 events**, 256 per track, with
  Algo+Mode+Decay+Tune+Param1+Param2 changing and zero cross-track state
  mutation.

### Production control -> PCM differential

All figures below are bit-exact PCM plus final state, and RNG where the engine
uses RNG:

| Algo | Exact samples |
| --- | ---: |
| Fold 1 | 196,608 |
| Fold 2 | 196,608 |
| Karplus | 196,608 |
| Noise/Tone | 196,608 |
| **Total** | **786,432** |

Noise/Tone's 196,608 samples are evenly split across physical modes:

- M1: 65,536
- M2: 65,536
- M3: 65,536

### Four-track mixed stress

**16,384 trigs / 262,144 additional exact samples** with dynamic Algo+Mode and
all six SRC values changing. Zero cross-track state mutation.

Every independent voice exercised every supported Algo:

| Voice | Fold1 | Fold2 | Karplus | Noise/Tone |
| --- | ---: | ---: | ---: | ---: |
| Voice 1 | 16,384 | 16,384 | 16,384 | 16,384 |
| Voice 2 | 16,384 | 16,384 | 16,384 | 16,384 |
| Voice 3 | 16,384 | 16,384 | 16,384 | 16,384 |
| Voice 4 | 16,384 | 16,384 | 16,384 | 16,384 |

The same stress gate round-tripped 16,384 stock source records exactly at unity
rate with mono duplicated to L/R.

### Sample-accurate p-lock timing

**2,304 Algo/Mode transitions / 36,864 samples**:

- pre-event segment retains the old Algo/state;
- at the event boundary, Algo+Mode+Decay+Tune+Param1+Param2 are applied;
- post-event segment renders from the new state.

Result: **PASS**.

### Non-sticky p-lock reversion

`tools/verify/verify_perky_cf_plock_reversion.py` drives the actual shipping
callback through **default -> locked Algo/Mode -> default** sequences.

Result: **PASS — 44 voice/lock cases / 132 events / 2,112 exact samples**.
The following unlocked/default trig returned to reference PCM after the locked
trig, while `pk_render()` left both the staging values and persistent track SRC
defaults unchanged.

### Measured stock source-record ABI

`tools/verify/verify_perky_cf_stock_record_abi.py` pins the production encoder
to the hardware-measured FLEX source ABI: count/ring/rate/read-position header,
unity-rate Q26 transport, and consecutive L/R sample lanes.

Result: **PASS** for all **17** legal split positions; the two segments always
total **40 longs / 160 bytes per voice**.

### Shipping `pk_render()` integration — four simultaneous voices

`tools/verify/verify_perky_cf_production_render.py` executes the actual shipping
`control_cf_final.c` callback against a fixed-address Octatrack memory fixture,
using the same hash-verified v1.2.1 assets as the production renderer.

Result: **PASS — 1,024 simultaneous four-voice frames / 4,096 voice events /
65,536 samples**.

| Voice | Fold1 | Fold2 | Karplus | Noise/Tone |
| --- | ---: | ---: | ---: | ---: |
| Voice 1 | 4,096 | 4,096 | 4,096 | 4,096 |
| Voice 2 | 4,096 | 4,096 | 4,096 | 4,096 |
| Voice 3 | 4,096 | 4,096 | 4,096 | 4,096 |
| Voice 4 | 4,096 | 4,096 | 4,096 | 4,096 |

For every voice/Algo pair all 16 possible event split offsets were exercised.
Within each simulated Octatrack frame all four Perky tracks render sequentially
through the same real source cursor. The gate verifies real SRC staging,
trigger bytes, pre/post split behavior, exact two-segment stock source-record
bytes, **160 bytes per voice**, and the exact **640-byte four-voice FLEX frame
span**.

### Part/Bank runtime reset

`tools/verify/verify_perky_cf_runtime_reset.py` executes the real shipping
callback across **Part A0 -> A1 -> A0** and **Bank A -> B** transitions.

Result: **PASS — 16 voice/Algo cases**. Every transition restarts from exact
cold-reference PCM, with no state leakage between Parts or Banks.

### ColdFire runtime memory/init

`tools/verify/verify_perky_cf_runtime_memory_final.py` prices the exact 32-bit
ColdFire state layout and enforces deterministic startup despite the Octabam DRAM
loader not clearing `.bss`.

Result: **PASS** — four-track engine state **22,324 bytes**, authentic firmware
assets **22,552 bytes**, callback scratch <=256 bytes, and more than **10.4 MB**
known margin in the platform DRAM reserve. A loaded non-zero `.data` cookie is
required to force `pk4_init()` before the BSS-resident engine state is used.

### ColdFire hot-loop safety

`tools/verify/verify_perky_cf_hotloops.py` audits the production sample renderers
for operations that would be especially dangerous on the MCF54455 audio path.

Result: **PASS** — no renderer division/modulo, heap allocation or libc memory
calls, and the optimized Noise/Tone renderer performs waveform lookup plus
filter/noise setup outside its per-sample loop. Event-time control preparation
is outside this hot-loop rule.

## Stock FX qualification

Software architecture gates pass:

- final Perky module: no DSP section;
- DSP ranges: 0;
- DSP preboot arena: 0;
- all 14 stock effects retained in the final remix;
- stock FX1 chooser untouched;
- no stock effect hidden or locked.

`tools/verify/verify_perky_stock_dsp_identity.py` is part of the final release
builder and requires the entire **156,948-byte stock DSP bootstrap/payload span**
to remain byte-identical in the packaged MAIN OS.

The release builder also cross-compiles the five ColdFire units and runs
`tools/verify/verify_perky_cf_codegen.py`, which rejects compiler/libgcc/libc
helper leakage, floating-point codegen and unexpected unresolved symbols before
firmware linking. Its toolchain preflight requires a real `m68k-elf` target and
successful `-mcpu=54455 -msoft-float` compilation before any release work begins.

The packaged-image DSP identity check has **not** been executed in this sandbox
because no m68k ColdFire cross-compiler can be imported here. The final release
builder is `tools/perky/build_cf_final.py` and does not require a saved
`OT_PROJECT`; transport behavior is covered by the executable gates above.

## Advisory ColdFire budget evidence

This is **not** hardware certification, but it is useful pre-hardware evidence:

- authentic PĒRKONS asset payload: **22,552 bytes**;
- four-track `pk4_engine` state is about **22.3 KiB** (22,324 bytes with a
  32-bit ColdFire pointer), so state + authentic assets are about **44.9 KiB**
  before code;
- the shipping callback's visible local PCM/record/SRC arrays total 182 bytes;
- five same-process host benchmark runs of the exact shipping `pk_render()`
  path — four voices, two source segments per voice, all six controls changing
  and every voice triggering — measured **2.175x to 2.385x** the existing WAVE4
  reference path;
- using the existing WAVE4 hardware calibration of 69.2 us/frame only as a
  scaling heuristic gives **150.5 to 165.0 us** for the complete four-voice
  Perky callback, versus **362.8 us** of audio time for 16 samples at 44.1 kHz.

That leaves roughly **198-212 us heuristic frame headroom**, but only physical
Octatrack measurement can certify the real ColdFire timing margin.

## Not claimed by this checkpoint

- Physical Octatrack hardware behavior has not been tested here.
- A final card/MIDI firmware image has not been produced in this sandbox because
  the required m68k cross-compiler is unavailable to this runtime.
- Algorithms outside Fold1, Fold2, Karplus and Noise/Tone are not part of this
  four-algorithm qualification milestone.
