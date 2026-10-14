# PERKY hybrid foundation contract

Goal 1 qualifies the frozen PERKY4S baseline and the independent ColdFire
foundation for a later probe build. The only success status is
**PASS_FOR_PROBE_BUILD**; hardware feasibility remains **UNVERIFIED**.
`PHASE1.md` and `PHASE1.json` record the executed result. No hybrid firmware
is built by this stage. The executable entry point is:

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid.py --stage baseline --work out/perky/hybrid
```

Every required check must execute successfully or validate complete, unchanged
prior execution evidence. Missing inputs, failed checks, required skips and
source drift produce `BLOCKED` and a nonzero exit.

## Product invariant

| Tracks | Engine and local ALGO |
|---|---|
| T1/T5 | Frozen DSP: 0 Fold Drum 1, 1 Fold Drum 2, 2 Simple Drum, 3 Complex Drum; original saved-project meanings |
| T2/T6 | Exactly two independently active CF instances: 0 Wavetable V1, 1 Wavetable V2, 2 Resonant Drum |
| T3/T4/T7/T8 | Stock |

All four PERKY tracks retain A TUNE, B DECAY, C ALGO, D PAR1, E PAR2,
F MODE, with parameter locks, stock AMP, LFOs, scenes, crossfader, sequencer
and FX. No engine browser. Resonant MODE 0 is snare, 1 bass, 2 the original
shared Noise/Tone behavior, including continuing RNG/state. Noise Hat and a
simplified resonator do not satisfy that contract.

Keep FILTER, SPATIALIZER, EQUALIZER, DJ EQ, PHASER, FLANGER, CHORUS,
COMB FILTER, DELAY, SPRING REVERB, DARK REVERB and LO-FI. Plate Reverb
and Compressor remain unavailable. Remove no other FX.

The public `PK4_ALGO_*` historical enum and voice silos remain intact.
A future adapter must define its family/profile map separately from physical
track numbers. A shared WT renderer is acceptable only after original V1 and
V2 initialization, update and continuing state are independently proven.

## Frozen DSP and baseline

The original DSP reference is `16a8de19a17ee4cba765cbdb30ca051f85af4e23`.
The qualified integrated baseline is
`4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`, including merge
`58acc80687015e8aa7e60eb9b5155c8aa9445ac6` and timing repair
`c2d99dad5c279b4e8eef722afb5136e369f3b75d`.
The reproduced MAIN hash is
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.

Freeze the actual DSP uploads, P/X/Y ownership and immutable tables; helpers,
placement, initialization, admission, controls, native clock conversion and
six uploaded zero/NOP guard words at P:0x3fffa..0x3ffff. Private P uses
770/774 words per core; all four spare words are reserved. Shared P uses
2398 executable words plus six guard words = 2404/2404. No DSP waveform
cache. Any DSP-side change needs a quantified proposal and explicit approval.

`BASELINE.json` records the boot-read-back uploads in their original record
order, destinations, lengths and hashes, alongside the actual ownership ledger.
Its 647-source inventory is retained as historical evidence. The separate
`DSP_DEPENDENCIES.json` freezes 166 dependencies: executed payload/placement
imports and reads, compiler includes, and explicitly labeled installation
source tracing. Each hash is checked against its historical Git object.
Independent CF files in the historical broad inventory may change only with
fresh exact-reference qualification; the frozen DSP closure may not change.
All firmware, native tables, captures and original receipts stay local and
ignored. Only metadata, hashes, source code and reports are committed.

## Source hook contract

`machine.s:pk_sig_check` recognizes FLEX plus PK/1. Registration seeds source
defaults on a fresh signature, persists them into Part/SRAM, and registers
each track's recorder-buffer donor (zero-based slots 128..135). Reselection
preserves its existing sound. The stock FLEX scheduler still owns admission
to its callback. These are measured-source interfaces, not a new machine type.

`control_four_candidate.c` includes `control_three_candidate.c`, which
includes `control.c` under renamed legacy entry points. The four-machine
`pk_admit_track` restricts synthesis to T1/T5. Its `pk_render` falls back to
stock for other/unsigned tracks, stages the six page values, publishes PK/Y1
records at frame completion, carries the pre-event tuple and preserves
source cursor/record geometry. The DSP consumes that transport. Complex adds
its existing AU-proven preparation and UI event latch.

The historical CF callback admits T1..T4. `pk_final_voice_index` maps physical
tracks to silos; `pk_final_fixed_slot` computes per-track/ping record slots;
`pk_final_commit_longs` uses a separate non-inlined two-pointer commit.
`pk_final_reset_runtime_if_needed` uses a loaded .data cookie and resets
engine/latches on Bank/Part changes. `pk_final_ensure_pcm` decodes PKR1 in the
UI task, with a callback guard. A future hybrid must route T2/T6 through two
logical instances while retaining T1/T5 DSP transport and stock behavior on
the other four tracks. No routing implementation is included here.

`pk4_init`, `pk4_preinit_voice`, `pk4_prepare_event`, `pk4_process_segment`,
`pk4_render` and `pk4_encode_stock_segment` retain their public API. The profile probe
calls these production preparation/render functions through a narrow host
bridge; it does not implement a replacement synthesizer.

## Correctness acceptance

Require exact PCM, meaningful object state, prepared controls and RNG against
the original firmware/native references, separately for V1, V2, snare, bass
and Resonant's third mode. Cover all WT selections and boundaries, three WT
modes per profile, raw endpoints/intermediate values, initialization, dirty
control cadence, smoothing, retrigger/release, long tails, mode/family changes
and simultaneous two-instance independence. Never normalize away behavioral
differences. Object identity pointers are distinct from renderer state;
WT state comparisons cover bytes 0x1c..0x12b: the first smoother is included,
and the adjacent original parameter array beginning at 0x12c is excluded.
An independent original-memory sentinel test proves that object boundary.
The full source captures and authoritative reference hashes remain unchanged.

Any synthesis/control correction requires a failing original-reference test
and subsequent exact PCM/state success. Source pins and final banners alone
are insufficient. A skipped required test is a refusal.

## Timing and memory acceptance

A frame is 16 samples at 44100 Hz: 362.811791 microseconds. The predictor-era
115.2 microseconds and 66 microseconds headroom claims are retracted. The
repaired emulator's instruction tests must pass before accepting any costs.
Use the actual CF compiler and corrected execution model; host wall-clock
time and half of an old four-voice measurement are not CF timing evidence.

Required pairings include V1/V1, V1/V2, V2/snare, V1/bass, snare/snare,
bass/snare, third/third, V2/V2 and reversed assignments, plus a sufficient
mode/profile sweep to find a worse pairing. Record the clock, cycles-to-time
conversion, maxima/distribution, initialization separately, transitions and
model limits. Those lower-level measurements cannot approve production or
establish hardware feasibility. See `PHASE1.md` for executed target costs.

Inventory proposed linked text/rodata/data/BSS, exact two-instance state,
stack, decoded assets, loader/runtime/preboot staging and reservations,
including cached and uncached aliases. The decoded WT allocation is
200704 bytes (4096 primary plus 196608 bank); reuse original hashes and
lossless PKR1 packing. The historical 118200-byte generic-engine figure is retracted: the target
compiler measures 118096 bytes. Neither generic figure is a hybrid allocation
or an available-RAM proof; the narrow two-instance diagnostic is linked and
measured separately.

The loader does not clear BSS. Engine and PCM readiness therefore require
loaded .data cookies. The PCM gate executes the actual shipping ensure path
with poisoned BSS, rejects incorrect asset counts, compares every decoded
byte, and proves that a READY call does not read or overwrite asset memory.
PKR1 assets are serialized explicitly little-endian on the big-endian CF.
The existing production DSP build's DRAM/preboot ledger is frozen metadata,
not proof of a proposed hybrid allocation.

The pinned stock disassembly enforces a 1 MiB encrypted ELUP payload cap
at 0x4007f396, after subtracting 12 bytes at 0x4007f390. Historical comments
citing 0x4007f748 are retracted for this image. Container bytes are
12 + align4(4 + ELEK bytes); the reproduced uncompressed
MAIN is 1265674 bytes and is not itself an ELUP payload-size test.
`build_cf_final.py` suppresses stock DSP mailbox remaps only after proving
its CF-only remix owns no DSP. A hybrid must preserve PERKY4S remaps/uploads
instead of applying that suppression.

## Workspace and stopping

Only `perky-cf-dsp-hybrid` is authorized for this work. Preserve the original
`perky-machines` ref, user fixtures and frozen PERKY4/PERKY4R/PERKY4S receipts.
Use this checkout and existing local toolchains; no new checkout, worktree,
upstream integration, CI, push or firmware package. Stage explicit paths.

Resolve the failing reference checks and missing evidence before Goal 2.
The only success status is PASS_FOR_PROBE_BUILD, with hardware feasibility
UNVERIFIED. The verifier requires original-reference correctness, isolated target costs,
initialization and a checked packaging budget before issuing that status.
The budget preserves all frozen allocations and includes explicit integration
allowances. Goal 2 must still validate the actual linked hybrid and container.
