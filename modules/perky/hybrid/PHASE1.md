# Phase 1 checkpoint — 14 October 2026

**BLOCKED. Hardware feasibility UNVERIFIED. Goal 2 must not start.**
The verified PERKY4S baseline is retained, but the requested CF correctness
contract does not pass. No synthesis or DSP source was changed, no hybrid
image was built, and nothing was pushed. This is a reproducible blocked
checkpoint, not PASS_FOR_PROBE_BUILD.

## Baseline evidence

The sole checkout was clean on `perky-machines`. Local and queried remote refs
both resolved to `4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`; no fetch was needed.
That tip contains the upstream merge and corrected timing instrument.
Before creating `perky-cf-dsp-hybrid`, the existing production provenance gate
passed for 647 committed sources, 2748 inputs, 51 completed commands and
seven artifacts. The original `perky-machines` ref remains unchanged.

The actual receipt has 51 commands (50 targeted), although the integration
prose says 50 (49 targeted). This checkpoint uses the validated receipt counts.
Its two historical repository-floor skips do not cover any new required test.

The production builder's CLI was inspected. The fresh `--qualify-only` command
was started with the actual read-only project and qualified EFT. It was
interrupted after the independent CF reference failures, exit **130**. Its
partial repository-floor log is retained; that attempt is **not a PASS**.
The separate `--local-only` production rebuild completed with exit 0:

```sh
.venv/bin/python3 tools/perky/build_four_machine.py --local-only --work out/perky/hybrid/baseline/reproduction
```

MAIN is 1265674 bytes and reproduces
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
The builder executed the actual loader/RTOS-handoff gate: the runtime and
both extended DSP uploads read back byte-identically. `BASELINE.json` records
124 ordered A records and 117 B records with hashes, exact P/X/Y ownership,
immutable uploaded table hashes, initialization, guards, placement and linker/
packaging inputs. All four private spare words and all six guards remain
reserved. The original project inventory matches its release receipt.

The existing emulator already matches the binary pinned by the qualified
post-repair receipt; no rebuild was necessary. `ctest --test-dir out/emu
--output-on-failure` passes 9/9, including `mc68kColdFireTimingTest`, EMAC,
divide, RTOS and DSP contracts. The release-guard selftest and actual
production prefetch guard pass. No instruction cost was changed.

## Executed CF gates

Exact argv, environment, exit status, tool/source hashes and log hashes are
in `PHASE1.json` and local `out/perky/hybrid/results.json`. The entry point
runs these checks again and validates the frozen historical evidence.

| Gate | Result and actual scope |
|---|---|
| `verify_perky_cf_final.py` | FAIL, exit 1 at qualified-source identity; no final qualification banner accepted |
| `verify_perky_cf_wavetable_dsp.py` | PASS; original V1/V2 snapshots, three modes/corners, first/continuation/retrigger; 6912 exact samples per profile |
| `verify_perky_cf_resonant_dsp.py` | FAIL, snare M1 corner 2 continuation, sample 1: -18038 versus -16928 |
| `verify_perky_cf_noise_tone.py` | PASS; 128000 shared and 128000 M1 samples with exact PCM/state, shared RNG |
| `verify_perky_noise_tone_control_evidence.py` | FAIL, required detailed original-control report absent |
| `verify_perky_cf_freestanding.py` | PASS |
| `verify_perky_cf_hotloops.py` | PASS |
| `verify_perky_cf_stock_record_abi.py` | FAIL, obsolete direct-loop source assertion after the non-inlined commit repair |
| `verify_perky_cf_runtime_memory_final.py` | PASS for historical four-track generic layout only; not a hybrid allocation proof |
| `verify_perky_hybrid_wt_profiles.py` | FAIL; 216 state-stage comparisons plus PCM checks against original V1/V2 captures, each on logical instances 0 and 1 separately |

The first Resonant attempt stopped on its hardcoded dependency on
`out/perky/cf-final-verify/fixtures/assets/pitch.bin`. That directory was
populated using the existing hash-pinned asset extractor, then the original
gate was rerun unchanged and failed at the PCM comparison above. The missing
asset attempt and retry logs remain separate. No substitute fixture was made.

The Noise/Tone control gate names the missing local original-reference file:

`out/perky/control-probes/noise-tone/noise-tone-control-analysis.json`

It also requires the independent exact-grid report at
`out/perky/control-probes/noise-tone-grid/noise-tone-ot-control-analysis.json`.
Neither requirement can be waived by the passing renderer differential.

The source-identity gate reports five mismatched pins:
`modules/perky/control.c`, `tools/build/build_bus.py`,
`tools/verify/verify_perky_cf_odd_access.py`,
`tools/perky/build_machine_canary.py`, and `modules/perky/CONTROL_RECOVERY.md`.
Their current identities are frozen in the baseline. Pins were not advanced
without a fresh CF qualification. The stock-record assertion expects
`record[pre_longs + i] = encoded[i]`, while the historical shipping callback
uses `pk_final_commit_longs` after the hardware-confirmed codegen repair.
This is evidence of a stale assertion, not proof that transport is incorrect.

## Narrow original-reference reproducer

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid_wt_profiles.py \
  --firmware /Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img \
  --work out/perky/hybrid/cf-contract/wt-profiles
```

It compiles the unchanged production CF sources with a small host bridge,
calls `pk4_init`, `pk4_prepare_event` and `pk4_render`, and compares original
pre-trigger, trigger, first block, continuation and retrigger state/PCM.
It excludes only the original object's 32-byte identity/pointer header.
Full captures are hashed; only aggregate counts and the first 24 bounded
mismatch records are retained in its JSON. No PCM dump is generated.

Measured example: original V1, panel MODE 0, raw controls 127, first-block
sample 1 is **31 versus 32**. State differences also occur outside the
identity header; initial raw-zero state first differs at object offset 0x62.
The cause of those differences is not established here.

An additional source/capture observation is concrete: both original WT
families' snapshots contain oscillator flag byte 0x128 = 0, 1, 2 for their
three panel modes. `pk_cf_wt_render` uses value 1 for half-rate frequency.
The CF `wt_init` zeros the field and `wt_update` does not assign it.
This is a missing preparation behavior to investigate under the failing
reference test; it does not by itself prove the full correction.

`EngineCatalog.h` maps both original families' panel modes to firmware modes
1, 0, 2. `PerkonsVoices::usesNativeWavetableDrum` identifies a shared original
per-sample renderer, and the existing seeded-state test verifies both
profiles. That supports renderer reuse within the measured corpus. It does
not prove full profile equivalence, initialization, dirty cadence, release,
long tails, all selections/boundaries or simultaneous logical independence.
Two renamed identical choices cannot yet satisfy the product contract.

The unchanged existing Resonant gate is an independent minimal reproducer:

```sh
.venv/bin/python3 tools/verify/verify_perky_cf_resonant_dsp.py \
  --firmware /Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img \
  --work out/perky/hybrid/cf-contract/resonant
```

It starts directly from original continuation state and RNG, so its failure
does not depend on the new WT preparation bridge. Whether synthesis,
block-boundary behavior, or capture/reference assumptions explain it remains
unresolved; no correction was made.

## History and limits

Full per-path commit histories for the requested source list are retained at
`out/perky/hybrid/baseline/path-history.json` and `.txt`; the compact inventory
is also embedded in `PHASE1.json`. The requested
`tools/perky/generate_cf_final.py` actually lives at
`modules/perky/generate_cf_final.py`.

Relevant milestones include `86379101` (four-track control/render core),
`2292f22f` (WT plus original fixture gate), `84ea0151` (PKR1 packaging),
`0a23d534` (typed accesses/initialization hoist), `9eb8d179` (WT invariants),
`c77e9219` and `7cc4f48a` (block caching), `735c6b29` (preinit), and
`a522d2f2` (record commit). The full inventory includes the pre-optimization
versions and fixture additions. No archaeology was repeated to replace an
existing reference with a new guessed law.

The source-hook map and future routing/memory/packaging constraints are in
`CONTRACT.md`. The frozen 647-source inventory is conservative; an actual
audited DSP dependency closure remains required. The proposed two-instance
linked allocation and stack are not measured. The generic 118200-byte engine
and historical memory gate are not a hybrid budget. `pk_final_pcm_ready` is
a BSS byte separate from the loaded runtime cookie; deterministic decode
readiness needs its own executable proof.

No target-cost benchmark was run after the required reference failures.
Requested pairings, distribution, initialization and transitions remain
**NOT RUN / REQUIRED**, not zero cost or a passing skipped test. Historical
115.2 us/66 us claims remain retracted. No ELUP cap/header experiment or
proposed hybrid packaging was performed. Hardware feasibility is unverified.

## Exact prerequisite for Goal 2

Resume this foundation first: resolve the original WT preparation/profile
and Resonant PCM failures with exact state/PCM/RNG tests; recover the required
existing original Noise/Tone control evidence; reconcile stale source/ABI
gates using fresh proof. Then complete exhaustive profile and simultaneous
two-instance coverage, corrected-model target costs, audited DSP dependency
closure, deterministic readiness and actual linked memory/container contracts,
and finish fresh production qualification. Extend the verifier with those
executable checks. Only a zero-exit PASS_FOR_PROBE_BUILD permits Goal 2;
hardware feasibility must still be reported UNVERIFIED.

The user-requested configuration was Astra/Max/Fast. This session exposes
only the system identity GPT-6; variant, effort and speed are not available
to the agent. The prompt was not claimed to change them. No parallel writer
or subagent was used.
