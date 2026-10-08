# Perky Machines — final four-algorithm software qualification

Date: 2026-10-08

This checkpoint covers the locked four-voice milestone implemented by the ColdFire source-machine architecture. It is separate from physical Octatrack audition and from the final real `m68k-elf` card/MIDI cross-link step.

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
- The Perky module has **no DSP section, no DSP-range claims, no FX2 ownership and no DSP preboot arena**. The unmodified stock DSP remains responsible for AMP -> FX1 -> FX2.
- The final remix retains **all 14 stock effects**, including Plate, Spring and Dark reverb; the stock FX1 chooser is untouched and no stock effect is hidden or locked.

## Exact firmware/reference provenance

PĒRKONS v1.2.1 image SHA-256:

`adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6`

The qualification extracts the exact pitch, chromatic, envelope and wave assets from that image and compares the production ColdFire implementation to PerkyBits' native v1.2.1 reference renderers.

`tools/verify/verify_perky_cf_qualified_sources.py` pins **52 production, qualification, build and release files**. The set includes the renderers, original-control translations, shipping `pk_render()` path, long-tail PCM gate, p-lock/lifecycle tests, stock-record ABI, final release builder, codegen audit, release-guard corruption self-test, wrapper verifier and stock-DSP identity checker. Any pinned-source drift invalidates qualification until the suite is rerun and the manifest is deliberately refreshed.

## Latest executed qualification

Top-level gate:

`tools/verify/verify_perky_cf_final.py`

Fresh result after the guarded-builder/52-file release sync: **PASS**.

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

Result: **PASS — 144 cases / 1,179,648 exact samples**, with **512 consecutive 16-sample blocks per case**.

Per voice, every Algo accumulated **73,728 exact samples**. Noise/Tone modes each accumulated **98,304 exact samples**. This gate catches delayed envelope/RNG/oscillator/ring/state drift that short trigger blocks can miss.

### Sample-accurate p-lock timing

**2,304 Algo/Mode transitions / 36,864 samples**:

- pre-event segment retains the old Algo/state;
- at the event boundary, Algo+Mode+Decay+Tune+Param1+Param2 are applied;
- post-event segment renders from the new state.

Result: **PASS**.

### Non-sticky p-lock reversion

Result: **PASS — 44 voice/lock cases / 132 events / 2,112 exact samples**. A following unlocked/default trig returns to reference PCM and the shipping callback leaves staged and persistent SRC defaults unchanged.

### Shipping `pk_render()` integration

The actual `control_cf_final.c` callback is executed against a fixed-address Octatrack memory fixture.

Result: **PASS — 1,024 simultaneous four-voice frames / 4,096 voice events / 65,536 exact samples**.

Every voice exercises every Algo and every one of the **16 possible split offsets**. The gate verifies staged SRC values, trigger bytes, pre/post split behavior, exact two-segment stock source records, **160 bytes per voice**, **640 bytes per four-voice frame**, and exact cursor advancement.

### Stock packer/source-slot isolation

Result: **PASS — 4,096 cases** covering T1/T2/T5/T6, both ping buffers and all 16 event splits. The source callback consumes exactly the measured FLEX span and leaves the trailing stock slot bytes untouched.

### Part/Bank runtime reset

Result: **PASS — 16 voice/Algo cases** across **Part A0 -> A1 -> A0** and **Bank A -> B**. Every transition restarts from exact cold-reference PCM with no state leakage.

### Stock FLEX source-record ABI

Result: **PASS** for all **17 legal split positions**. The encoder is pinned to the measured stock FLEX count/ring/rate/read-position header, Q26 unity-rate transport, consecutive L/R lanes, and a fixed two-segment total of **40 longs / 160 bytes per voice**.

### ColdFire runtime memory/init

Result: **PASS**.

- one track state: **5,580 bytes**
- four-track engine state: **22,324 bytes**
- authentic PĒRKONS assets: **22,552 bytes**
- asset view: **56 bytes**
- callback scratch: <= **256 bytes**
- known total: <= **45,188 bytes**
- platform DRAM reserve: **10,487,808 bytes**
- known margin: **10,442,620 bytes**

A non-zero `.data` cookie forces deterministic `pk4_init()` before BSS-resident engine state can be used.

### ColdFire hot-loop safety

Result: **PASS** — no renderer division/modulo, heap allocation or libc memory calls; Noise/Tone waveform/filter/noise setup is outside its per-sample loop.

## Stock FX/release qualification

Architecture gates pass:

- Perky DSP section: none
- DSP ranges: 0
- DSP preboot arena: 0
- FX2 buffer ownership: none
- all 14 stock effects retained
- stock FX1 chooser untouched
- no stock effect hidden/locked

The final builder requires `tools/verify/verify_perky_stock_dsp_identity.py` to compare the complete **156,948-byte stock DSP bootstrap/payload span** byte-for-byte against stock 1.40C before release packaging succeeds.

The builder also runs `tools/verify/verify_perky_cf_codegen.py`, which rejects hidden compiler/libgcc/libc helper leakage, floating-point codegen and unexpected unresolved symbols in the generated ColdFire units.

`tools/verify/verify_perky_release_guards_selftest.py` is now executed **before ColdFire toolchain preflight**. It proves the stock-DSP identity guard accepts an unchanged image and rejects a one-byte DSP mutation, and proves the card/MIDI wrapper verifier accepts valid wrappers and rejects corruption. Therefore these fail-closed release guards can be tested even on a host that does not yet have `m68k-elf-gcc` installed.

The DSP-pristine release guard was also tested directly: the current ColdFire-only module is accepted, while an injected one-word DSP Y claim is rejected.

## Post-link structural packaging proof

A **fake-toolchain image is never hardware-safe**, but it has been used to exercise the release machinery after code generation:

- all-stock-FX remix construction completes;
- the generated MAIN OS passes the full **156,948-byte stock-DSP identity** comparison;
- valid card and MIDI wrappers round-trip exactly;
- deliberate wrapper corruption is rejected.

This proves the post-link image/wrapper/identity machinery independently of the unavailable real cross-compiler.

## Advisory ColdFire budget evidence

This is pre-hardware evidence, not target-cycle certification.

A same-process host benchmark of the exact four-track production core, rendering all four voices for one 16-sample frame, measured approximately:

| Path (4 voices) | Host time / 16-sample frame |
| --- | ---: |
| Fold1 | 1.846 us |
| Fold2 | 2.086 us |
| Karplus | 0.521 us |
| Noise/Tone M1 | 0.669 us |
| Noise/Tone M2 | 2.040 us |
| Noise/Tone M3 | 2.064 us |

The real 16-sample audio interval at 44.1 kHz is **362.8 us**. These host figures are used only as a regression/ranking signal; they are not treated as ColdFire timings. The worst host paths are Fold2 and Noise/Tone M2/M3.

For a hardware-calibrated reference, Octabam's WAVE LOAD probe measured one four-voice ColdFire WAVE engine at **69.2 us/frame** on an Octatrack MKII. That engine's worst path was 10,339 executed m68k instructions/frame under its emulator. Perky still requires a real MCF54455 codegen/instruction-count or hardware timing measurement before its exact target margin is certified.

## Remaining packaging limitation in this runtime

A real final card/MIDI image has **not** been produced inside this sandbox because the runtime does not provide a usable `m68k-elf` GCC/binutils toolchain and blocks importing binary toolchains via outbound transfer.

The final release builder remains `tools/perky/build_cf_final.py`. Its current fail-closed path is:

0. release-guard corruption self-test;
1. complete executable PCM/control/p-lock/runtime qualification;
2. real MCF54455 cross-compile;
3. generated assembly/object linkage audit;
4. DSP-pristine all-stock-FX remix build;
5. full stock-DSP byte identity;
6. card/MIDI wrapping;
7. wrapper round-trip verification;
8. provenance/hash release manifest.

The builder refuses a compiler that is not target `m68k-elf` or cannot compile with `-mcpu=54455 -msoft-float`.

## Not claimed

- Physical Octatrack behavior has not been tested here.
- Real ColdFire instruction/cycle timing has not yet been measured for the Perky build.
- Algorithms outside Fold1, Fold2, Karplus and Noise/Tone are not part of this qualified four-algorithm milestone.
- Experimental Simple Drum/fifth-Alg work is intentionally excluded from this frozen release.
