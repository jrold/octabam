# Perky Machines — final four-algorithm software qualification

Date: 2026-10-08

This checkpoint covers the locked four-voice milestone implemented by the ColdFire source-machine architecture. It is separate from physical Octatrack audition and from the final card/MIDI cross-link step.

## Locked architecture

- Four independent Perky Machines voices on Octatrack tracks **T1/T2/T5/T6**.
- First SRC page is exactly:
  - A = Decay
  - B = Tune
  - C = Param 1
  - D = Param 2
  - E = Mode
  - F = Algo
- All six parameters are independently p-lockable through the normal source-parameter staging path.
- Algo/Mode/Decay/Tune/Param1/Param2 take effect exactly at the trig/event split.
- Qualified Algo set:
  - Fold 1
  - Fold 2
  - Karplus
  - Noise/Tone, physical modes M1/M2/M3
- Perky synthesis runs on ColdFire and emits ordinary stock FLEX-compatible source PCM records.
- The Perky module has **no DSP section, no DSP-range claims, and no DSP preboot arena**. The unmodified stock DSP remains responsible for AMP -> FX1 -> FX2.
- The final remix retains **all 14 stock effects**, including Plate, Spring and Dark reverb; the stock FX1 chooser is untouched and no stock effect is hidden or locked.

## Exact firmware/reference provenance

PĒRKONS v1.2.1 image SHA-256:

`adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6`

The qualification extracts the exact pitch, chromatic, envelope and wave assets from that image and compares the production ColdFire implementation to PerkyBits' native v1.2.1 reference renderers.

`tools/verify/verify_perky_cf_qualified_sources.py` now pins **43 production, qualification, build and release files** by SHA-256. This includes the production renderers, shipping `pk_render()` path, long-tail PCM gate, p-lock/lifecycle tests, stock-record ABI, final release builder, codegen audit, wrapper verifier and stock-DSP identity checker. Any pinned-source drift invalidates the qualification until the suite is rerun and the manifest is deliberately refreshed.

## Executed qualification

Top-level gate:

`tools/verify/verify_perky_cf_final.py`

Fresh result after release sync: **PASS**.

### Control/state preparation

- Fold1/Fold2/Karplus: **4,608** OT-domain control states byte-exact against the recovered original ARM update/trigger translation.
- Noise/Tone: **1,536** OT-domain control states byte-exact against the recovered original ARM update/trigger translation.
- Dynamic four-track p-lock sequence: **1,024 events**, 256 per voice, with Algo+Mode+Decay+Tune+Param1+Param2 changing and **zero cross-track state mutation**.

### Production control -> PCM

All figures are bit-exact PCM plus final state, and RNG where the engine uses RNG:

| Algo | Exact samples |
| --- | ---: |
| Fold 1 | 196,608 |
| Fold 2 | 196,608 |
| Karplus | 196,608 |
| Noise/Tone | 196,608 |
| **Total** | **786,432** |

Noise/Tone split:

- M1: **65,536**
- M2: **65,536**
- M3: **65,536**

### Four-track mixed stress

**16,384 trigs / 262,144 exact samples** with dynamic Algo+Mode and all six SRC values changing. Zero cross-track mutation.

Every independent voice exercised every supported Algo:

| Voice | Fold1 | Fold2 | Karplus | Noise/Tone |
| --- | ---: | ---: | ---: | ---: |
| T1 | 16,384 | 16,384 | 16,384 | 16,384 |
| T2 | 16,384 | 16,384 | 16,384 | 16,384 |
| T5 | 16,384 | 16,384 | 16,384 | 16,384 |
| T6 | 16,384 | 16,384 | 16,384 | 16,384 |

The same stress gate round-tripped **16,384 stock source records** exactly at unity rate with mono duplicated to L/R.

### Long-tail continuity

`tools/verify/perky4_long_tail_diff.cpp` is now mandatory in the top-level qualifier.

Result: **PASS — 144 cases / 1,179,648 exact samples**, with **512 consecutive 16-sample blocks per case**.

Per voice, every Algo accumulated **73,728 exact samples**. Noise/Tone modes each accumulated **98,304 exact samples**. This gate catches delayed envelope/RNG/oscillator/ring/state drift that short trigger blocks can miss.

### Sample-accurate p-lock timing

**2,304 Algo/Mode transitions / 36,864 samples**:

- pre-event segment retains the old Algo/state;
- at the event boundary, Algo+Mode+Decay+Tune+Param1+Param2 are applied;
- post-event segment renders from the new state.

Result: **PASS**.

### Non-sticky p-lock reversion

The actual shipping callback was driven through default -> locked Algo/Mode -> default.

Result: **PASS — 44 voice/lock cases / 132 events / 2,112 exact samples**. The following unlocked/default trig returned to reference PCM, while the callback left staged and persistent SRC defaults unchanged.

### Shipping `pk_render()` integration

The actual `control_cf_final.c` callback was executed against a fixed-address Octatrack memory fixture.

Result: **PASS — 1,024 simultaneous four-voice frames / 4,096 voice events / 65,536 exact samples**.

Every voice exercised every Algo and every one of the **16 possible split offsets**. The gate verifies staged SRC values, trigger bytes, pre/post split behavior, exact two-segment stock source records, **160 bytes per voice**, **640 bytes per four-voice frame**, and exact cursor advancement.

### Part/Bank runtime reset

Result: **PASS — 16 voice/Algo cases** across **Part A0 -> A1 -> A0** and **Bank A -> B**. Every transition restarts from exact cold-reference PCM with no state leakage.

### Stock FLEX source-record ABI

Result: **PASS** for all **17 legal split positions**. The encoder is pinned to the measured stock FLEX count/ring/rate/read-position header, Q26 unity-rate transport, consecutive L/R lanes, and a fixed two-segment total of **40 longs / 160 bytes per voice**.

### ColdFire runtime memory/init

Result: **PASS**.

- four-track engine state: **22,324 bytes**
- authentic PĒRKONS assets: **22,552 bytes**
- callback scratch: <= **256 bytes**
- known total: <= **45,188 bytes**
- platform DRAM reserve: **10,487,808 bytes**
- known margin: **10,442,620 bytes**

A non-zero `.data` cookie forces deterministic `pk4_init()` before BSS-resident engine state can be used.

### ColdFire hot-loop safety

Result: **PASS** — no renderer division/modulo, heap allocation or libc memory calls; Noise/Tone waveform/filter/noise setup is outside its per-sample loop.

## Stock FX qualification

Architecture gates pass:

- Perky DSP section: none
- DSP ranges: 0
- DSP preboot arena: 0
- all 14 stock effects retained
- stock FX1 chooser untouched
- no stock effect hidden/locked

The final builder requires `tools/verify/verify_perky_stock_dsp_identity.py` to compare the complete **156,948-byte stock DSP bootstrap/payload span** byte-for-byte against stock 1.40C before release packaging succeeds.

The builder also runs `tools/verify/verify_perky_cf_codegen.py`, which rejects hidden compiler/libgcc/libc helper leakage, floating-point codegen and unexpected unresolved symbols in the generated ColdFire units.

## Advisory ColdFire budget evidence

This is pre-hardware evidence, not physical certification:

- authentic asset payload: **22,552 bytes**
- four-track runtime plus assets: about **44.9 KiB** before code
- five same-process host benchmark runs of the exact shipping four-voice callback measured **2.175x–2.385x** the existing WAVE4 reference path
- using the existing WAVE4 hardware calibration of 69.2 us/frame only as a scaling heuristic gives roughly **150.5–165.0 us** for a complete four-voice Perky callback versus **362.8 us** of audio time for 16 samples at 44.1 kHz

Only physical Octatrack measurement can certify the true ColdFire timing margin.

## Remaining packaging limitation in this runtime

A final card/MIDI image has **not** been produced inside this sandbox because the runtime does not provide a usable `m68k-elf` GCC/binutils toolchain and blocks importing one via outbound binary transfers. Direct GitHub archives, Homebrew bottles, Debian package-manager access, direct-IP mirror access and other local toolchain searches were exhausted.

The final release builder remains `tools/perky/build_cf_final.py`. It reruns the complete executable qualification, cross-compiles/audits the ColdFire units, builds the all-stock-FX remix, requires stock-DSP byte identity, wraps card/MIDI firmware and verifies the wrappers before declaring release success.

## Not claimed

- Physical Octatrack behavior has not been tested here.
- Algorithms outside Fold1, Fold2, Karplus and Noise/Tone are not part of this qualified four-algorithm milestone.
- Experimental Simple Drum/fifth-Alg work is intentionally excluded from this frozen release.
