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
- All six parameters are staged through the normal source-parameter path and
  are independently p-lockable.
- Algo and Mode changes are applied at the exact event split before the trig's
  post-event samples are rendered.
- Supported Algo set for this milestone:
  - Fold 1
  - Fold 2
  - Karplus
  - Noise/Tone, with physical modes M1/M2/M3
- Perky synthesis runs on ColdFire and emits ordinary stock source PCM records.
- The final Perky module has no DSP section, no DSP-range claims, and no DSP
  preboot arena. The stock DSP remains responsible for the normal AMP -> FX1 ->
  FX2 path.
- The final remix retains all 14 stock effects, including Plate, Spring and
  Dark reverb, leaves the stock FX1 chooser untouched, and hides/locks no stock
  effect rows.

## Exact firmware/reference provenance

PĒRKONS v1.2.1 image SHA-256:

`adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6`

The qualification uses the exact extracted pitch, chromatic, envelope and wave
assets from that image and compares production ColdFire output to PerkyBits'
native v1.2.1 reference renderers.

`tools/verify/verify_perky_cf_qualified_sources.py` pins 24 production and test
files by SHA-256. Any source drift invalidates this qualification until the full
suite is rerun and the manifest is deliberately refreshed.

## Executed results

Top-level gate:

`tools/verify/verify_perky_cf_final.py`

Result: **PASS**

### Control/state preparation

- Fold1/Fold2/Karplus: 4,608 OT-domain control states byte-exact against the
  recovered original ARM update/trigger translation.
- Noise/Tone: 1,536 OT-domain control states byte-exact against the recovered
  original ARM update/trigger translation.
- Dynamic four-track p-lock sequence: 1,024 events, 256 per track, with
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

16,384 trigs / 262,144 additional exact samples with dynamic Algo+Mode and all
six SRC values changing. Zero cross-track state mutation.

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

2,304 Algo/Mode transitions / 36,864 samples:

- pre-event segment retains the old Algo/state;
- at the event boundary, Algo+Mode+Decay+Tune+Param1+Param2 are applied;
- post-event segment renders from the new state.

Result: **PASS**.

### Shipping `pk_render()` integration — four simultaneous voices

`tools/verify/verify_perky_cf_production_render.py` executes the actual shipping
`control_cf_final.c` callback against a fixed-address Octatrack memory fixture,
using the same hash-verified v1.2.1 assets as the production renderer.

Result: **PASS — 1,024 simultaneous four-voice frames / 4,096 voice events /
65,536 samples**.

Coverage:

| Voice | Fold1 | Fold2 | Karplus | Noise/Tone |
| --- | ---: | ---: | ---: | ---: |
| Voice 1 | 4,096 | 4,096 | 4,096 | 4,096 |
| Voice 2 | 4,096 | 4,096 | 4,096 | 4,096 |
| Voice 3 | 4,096 | 4,096 | 4,096 | 4,096 |
| Voice 4 | 4,096 | 4,096 | 4,096 | 4,096 |

For every voice/Algo pair all 16 possible event split offsets were exercised.
Within each simulated Octatrack frame all four Perky tracks render sequentially
through the same real source cursor. The gate verifies the real SRC staging
address, trigger byte, pre/post split, exact two-segment stock source-record
bytes, **160 bytes per voice**, and the exact **640-byte four-voice FLEX frame
span**.

This closes the integration chain as:

`OT SRC staging -> shipping pk_render() -> four simultaneous source voices -> event split -> stock FLEX records -> qualified Perky core -> PerkyBits PCM reference`.

## Stock FX qualification

Software architecture gates pass:

- final Perky module: no DSP section;
- DSP ranges: 0;
- DSP preboot arena: 0;
- all 14 stock effects retained in the final remix;
- stock FX1 chooser untouched;
- no stock effect hidden or locked.

`tools/verify/verify_perky_stock_dsp_identity.py` is also part of the final
release builder and requires the entire 156,948-byte stock DSP bootstrap/payload
span to remain byte-identical in the packaged MAIN OS.

That packaged-image identity check has **not** been executed in the current
sandbox because no m68k ColdFire cross-compiler is installed here. The release
builder is committed as `tools/perky/build_cf_final.py`; it no longer requires a
saved `OT_PROJECT`, because the final architecture's p-lock/source-record
transport has dedicated executable gates above.

## Not claimed by this checkpoint

- Physical Octatrack hardware behavior has not been tested here.
- A final card/MIDI firmware image has not been produced in this sandbox because
  the required m68k cross-compiler is unavailable.
- Algorithms outside Fold1, Fold2, Karplus and Noise/Tone are not part of this
  four-algorithm qualification milestone.
