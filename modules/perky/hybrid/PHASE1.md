# Phase 1 qualification — 14 October 2026

**PASS_FOR_PROBE_BUILD. Hardware feasibility UNVERIFIED.**
The five original blockers are resolved locally. No hybrid firmware was built,
no DSP source was changed, and nothing was pushed. The source qualification
commit is `f3b300ec1ce09e723137cf4d56602575e564169a`; the earlier BLOCKED
8/13 checkpoint remains available as
`git show c7397d74:modules/perky/hybrid/PHASE1.md` and its corresponding JSON.
Original failure logs remain under `out/perky/hybrid/cf-contract/`.

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid.py --stage baseline --work out/perky/hybrid
```

The completed entry point reports 18/18 required checks passing, with no
required skips or source drift. `PHASE1.json` records exact commands, selected
environment, tool/source/log hashes, child receipts and limitations. Current
execution outputs are under `out/perky/hybrid/qualification/`. Source hashes
are bound across the entire run, not just within each subprocess. Missing or
corrupt frozen inputs were also checked to produce a refusal.

## What caused the original failures

| Failure | Established cause and resolution |
|---|---|
| WT preparation / exact PCM | Genuine preparation defects: four missing original constructor words, the missing mode byte at +0x128, and fifteen new-target smoothing passes where the original wrapper executes sixteen. A separate harness error included adjacent wrapper parameter memory at +0x12c while omitting the first smoother at +0x1c. The corrected comparison covers all owned state at +0x1c..+0x12b. Original ARM constructor/update/trigger/render calls and opposite sentinel tails independently prove that boundary; capture bytes and hashes are unchanged. |
| Resonant PCM | Genuine synthesis regressions: optimization `77b2cadf` removed snare bypass handling although DECAY writes it, and `2f4f324e` removed decay-sign handling although triggers set it. The unchanged original gate reproduced sample 1 as -18038 versus -16928. Broader tests also exposed an uncleared finite-decay noise floor, missing original third-mode callback words, separate mode control histories where the wrapper shares one, and initialization at the event note instead of the original note 63. Restored behavior matches the original executable and captures. |
| Noise/Tone control evidence | Missing generated evidence, recoverable locally. Historical PerkyBits commit `210d3672b309ec8d41747526073637516d9bd32f` contains the deleted detailed and exact-grid probes. The gate recovers their pinned source bytes, checks historical wrapper identity, executes the original firmware, and runs the unchanged analyzers/acceptance check. No external input remains missing. |
| Source hashes / reference pins | Outdated source-identity expectations. All 91 authoritative source pins remain unchanged, as do firmware, native-reference and capture pins. The strict legacy pin gate still refuses drift. Explicit `--requalify` verifies the historical Git blobs, records current differences, executes the full legacy suite, and rejects source changes during execution. New WT/Resonant acceptance is separate; a provenance audit alone cannot pass it. |
| Stock audio record assertion | Outdated source-text expectation. Hardware-confirmed repair `a522d2f2` replaced the inline loop with `pk_final_commit_longs`; the old assertion still required the removed loop. The gate now checks the actual commit path and executes an independent encoder oracle over 85 records, lengths 0..16, signed endpoints, invalid arguments and sentinels. The production callback suite separately verifies exact stock records, fixed slots, source cursors and split-frame behavior. |

The initial five stale source pins were `control.c`, `build_bus.py`,
`verify_perky_cf_odd_access.py`, `build_machine_canary.py`, and
`CONTROL_RECOVERY.md`. Their historical blobs and current differences are in
the fresh legacy receipt. They were not silently repinned.

“Noise/Tone” names the original shared synthesis used by **Resonant MODE 2**.
It adds no algorithm or control. T2/T6 still expose exactly WT V1, WT V2 and
Resonant, with Tune/Decay/Algo/Par1/Par2/Mode. The new original-reference gate
also tests Resonant's third mode directly through Voice 3/engine 7, not just
through the historical standalone Noise/Tone reference.

## Original-reference correctness

The original-ARM gate passes all **19 sections: 22,098 cases, 325,277 exact
state/RNG/sentinel checks, 3,046,272 exact PCM samples, and 138 actual original
release calls**. Coverage includes constructor state, fresh/direct and settled
controls, all 128 values of each sound control, modes, dirty and clean events,
retrigger, mode/family retention, paired instances, and 65,536-sample release
tails. The shared renderer is independently checked against original V1 and V2.

Each original WT profile reaches all 48 tables: indices 0..15, 16..31 and
32..47 in its three modes. Six executable coverage records require those
addresses, crossfade endpoints 0/255, and all fourteen adjacent raw-control
boundaries on both instances and both preparation paths. Every internal
12-bit smoothed threshold is not individually forced; every public seven-bit
control position is covered. Resonant MODE 2 alone has 2,048 grid cases,
11,264 state/RNG checks and 65,536 PCM comparisons, plus corpus and trajectories.

The unchanged WT renderer and Resonant capture gates pass separately. The
historical shared/M1 Noise/Tone renderer differential passes 256,000 samples.
Recovered control probes cover 1,536 exact grid states plus detailed control
and pairwise observations. The freshly executed legacy suite includes
786,432 production-control PCM samples and 1,179,648 long-tail samples, as well
as production callback, p-lock reversion, Part/Bank reset and stock transport.
Its success banner now explicitly names its legacy scope.

An optional historical WT→Fold round trip remains a separate failing diagnostic:
that wrapper shares targets differently. Fold runs on frozen DSP in this
product. It is not used to qualify the required WT V1/V2↔Resonant paths, which
are explicitly tested and pass. No general all-engine equivalence is claimed.

## Frozen baseline and completed qualification

`perky-machines` remains `4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`.
`BASELINE.json` is byte-identical to the earlier checkpoint; its embedded
BLOCKED status is historical. This report and the executable result carry the
current qualification verdict. MAIN remains
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`
(1,265,674 bytes). Its boot readbacks retain all 124 A records and 117 B records,
in order, with destinations, lengths, P/X/Y ownership and table hashes intact.
Private P remains 770/774 per core, with the spare four reserved. Shared P
remains 2398 executable plus six guard words = 2404/2404.

The frozen dependency audit executes composition/placement, observes source
reads/imports, runs compiler include discovery, and labels additional static
installation tracing. All **166 dependencies** match historical Git objects;
93 were absent from the earlier broad 647-source inventory. All seven generated
payload artifacts and the 22 shared-P records per upload match the baseline.
Independent CF changes do not enter this closure.

The interrupted qualification was restarted with the existing tools and project:

```sh
# BASELINE.json environment, with PERKYBITS_SOURCE unset; see explanation below.
.venv/bin/python3 tools/perky/build_four_machine.py --qualify-only --work out/perky/hybrid/resume/baseline/build
```

All **50 commands completed successfully (49 targeted)**. The original MAIN
hash is reproduced; the 24-configuration local refhash check passes. There
are no targeted skips or failures. The repository-wide `make check` floor has
361 PASS markers and two historical, non-targeted skips: the default PERKY
PROBE boot inputs and the absent default CF generated-assembly directory.
The production PERKY4S startup/project gates and explicit generated-assembly
audit execute separately and pass. All nine corrected-instrument CTest tests
also pass in the final aggregate run.

The first restart exposed a local harness environment conflict: two legacy
Fold2 gates interpret `PERKYBITS_SOURCE` as the `Source/` subdirectory, while
other gates use it for the checkout root. Unsetting that optional override lets
the existing correct defaults resolve both; `PERKYBITS_ROOT` remains explicit.
Its failed attempt is preserved separately. No frozen gate was edited.

The original release receipt contains 51 commands/50 targeted, including its
wrapper check; the new qualification-only run has 50/49 because it does not
package a release. Historical component reports whose canonical output paths
were reused have been archived byte-for-byte from the original receipt's
embedded results, with every original hash checked. `BASELINE_REPORT_ARCHIVE.json`
records those aliases without changing authoritative reference hashes.

## Corrected-model costs and target correctness

The existing corrected timing instrument passes all nine CTest tests, including
`mc68kColdFireTimingTest`. The actual m68k compiler builds independent diagnostic
ELFs, not firmware. A 9×9 ordered profile/mode matrix at three control corners
covers every requested pairing and reversal, with dirty/clean preparation,
retrigger, mode changes, family changes, return without trigger and long tails.
There are 15,552 matrix render frames, 243 clean render frames and 4,608 tail
frames. Every frame is 16 samples at 44,100 Hz: **362.811791 µs**.

| Observation at the model's 266 MHz | Cycles | Time |
|---|---:|---:|
| Largest matching control + render frame | 31,618 | 118.865 µs |
| Largest matrix render alone | 13,010 | 48.910 µs |
| Largest long-tail render | 13,031 | 48.989 µs |
| Largest two-instance initialization | 5,919 | 22.252 µs |
| Actual shipping PKR1 first decode | 9,882,727 | 37.153 ms |
| Actual shipping READY guard | 37 | 0.139 µs |

The maximum combined frame is snare/snare, middle corner, dirty retrigger.
Per-phase minima, means, medians, p95, maxima, stack use and worst cases are
recorded in the target receipt and complete CSV. Clean and tail frames enter
the frame-budget assertion. Initialization/decode are measured separately;
first decode must complete before real-time rendering in the later integration.

Target/native replay compares **22,608 snapshots / 90,612,864 canonical bytes**
exactly: all five retained state arrays per instance, control fields, RNG, PCM
and status. Only ABI padding is excluded. Host comparisons run after timed
calls and add no target instructions. Production generated assembly passes the
existing odd-access audit and runtime-helper checks. The diagnostic's compiler
can use an odd base plus an odd displacement, so calibrated read/write watches
check actual effective addresses during every target call; no odd wide access
was observed. The renderer disassembly also excludes division/runtime helpers.

These are observed isolated costs, not full-machine bounds: the hybrid adapter,
stock callback, DSP traffic, cache behavior, stalls and arbitration are excluded.
Predictor state persists across ordered cases. Historical 115.2 µs / 66 µs
headroom claims remain retracted. Hardware feasibility remains UNVERIFIED.

## Memory, initialization and packaging

The target link measures text 54,774, rodata 76, data 4 and BSS 4,136 bytes.
Two independent narrow instances occupy **3,940 bytes**; observed maximum
stack is **460 bytes**, checked against a 1,024-byte diagnostic reserve. This
is not a production stack ceiling. The generic engine is compiler-measured at
118,096 bytes; the old inferred 118,200-byte figure and unsupported 256-byte
stack ceiling are retracted and are not hybrid RAM requirements.

The target decoder found an additional genuine defect: native-endian `int16_t`
output is wrong for table readers expecting original ARM little-endian bytes.
The corrected decoder explicitly serializes little-endian output; all 200,704
bytes match the original assets. The PKR1 stream remains 133,408 bytes with SHA
`e0ea652c4a53c8b7e201afbc08924f164fa75341c2a1df5bdef562954b48b854`.

The loader does not clear BSS. The actual shipping ensure function now uses a
loaded .data COLD/READY cookie, tested with poisoned 200,704-byte destinations.
Asset counts 0, 1 and 3 are rejected without writing PCM or becoming READY.
Successful decode is exact; a subsequent READY call performs zero input reads
and zero destination writes, even with a corrupted stream and destination
canaries. The two-instance state initializer likewise matches clean and dirty
memory. No DSP initialization path was changed.

The packaging gate assembles production assets separately: 23,580 ancillary
bytes + 4 alignment bytes + 133,408 PKR1 bytes = 156,992 loaded bytes, with
200,704 decoded bytes in BSS. It verifies original ELUP decryption/checksum,
exact ELEK identity and `ELUP bytes = 12 + align4(4 + ELEK bytes)`.
The pinned stock cap is measured at 0x4007f396 after subtraction at 0x4007f390;
old cap comments citing 0x4007f748 are retracted for this image. The cap is
1,048,576 encrypted payload bytes, separate from uncompressed MAIN size.

A checked component envelope preserves all frozen preboot/runtime ranges and
normalizes cached/uncached aliases. It includes 65,536 loaded bytes and 16,384
BSS bytes of integration allowance, a 4,096-byte stack reserve and a literal
encoding envelope for staging. The projected payload is **884,188 bytes**,
leaving **164,388 bytes** below the cap; the disjoint DRAM proposal leaves
9,639,400 bytes inside the existing runtime reservation. These are explicit
design budgets, not an exact combined firmware size. Goal 2 must fit its actual
link, integration and outer compression within them and verify the final card.

## Retained history and source map

The full relevant path history remains in
`out/perky/hybrid/baseline/path-history.json` and `.txt`, with the compact
inventory retained in `PHASE1.json`. Relevant milestones are `86379101`
(control/render core), `2292f22f` (WT original fixtures), `84ea0151` (PKR1),
`0a23d534` (typed accesses/initialization hoist), `9eb8d179` (WT invariants),
`c77e9219`/`7cc4f48a` (block caching), `735c6b29` (preinit) and `a522d2f2`
(stock-record commit). The requested CF generator is actually
`modules/perky/generate_cf_final.py`. `CONTRACT.md` retains the source-hook,
registration, donor-buffer, controls, cursor and future routing map. No new
engine browser or hybrid adapter was installed.

## Handoff

No essential external input remains unavailable. The existing checkout and
local toolchains were reused; no branch, worktree, upstream integration or CI
was created. One writer applied source changes; read-only subagents investigated
independent failures and reviewed the gates. The authoritative references and
frozen DSP remain unchanged. Goal 2 may begin only from the completed
PASS_FOR_PROBE_BUILD receipt and still requires a separate probe build and
full integration/hardware qualification.

The requested model configuration was Astra/Max/Fast. The session exposes the
system identity GPT-6, but not a verifiable variant, effort or speed setting;
no claim is made that the prompt changed them.

The goal API returned no active persistent goal at handoff, so there was no
goal object to mark paused. No new goal was created, and work stops at this
completed foundation milestone.
