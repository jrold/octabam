# PERKY two-voice checkpoint — 13 October 2026

> **HISTORICAL CHECKPOINT — not the current PERKY build.** The data and
> procedures below document their original experiment and have been retained
> unchanged for provenance. **PERKY4S** is the current working MKII firmware:
> two DSP voices (T1/T5), Fold1/Fold2/Simple/Complex, 12 retained stock FX.
> The current status and memory ledger are in
> [PERKY4S](PERKY4S_RELEASE.md). **Do not flash or continue this older
> experiment simply because it says "read first," "current," or "next step."**


This record supersedes the round-175 diagnosis in FX_RECOVERY_HANDOFF.md. The
working physical baseline remains `perky2v-hw-baseline` → `fc438e03`. No frozen
branch/tag, historical firmware, main-checkout change, or original project was
reset or overwritten. Complex Drum and Wavetable integration remain deferred.

## Recovery and diagnosis

Recovered `.claude/worktrees/perky-2voice-milestone` at `db7c6e4c`; the only
uncommitted file was `tools/verify/verify_perky_p_records.py`. Its original
command reproduced 16 pieces / 2,353 words, 13 shared records / 1,608 words,
4,950 bytes of upload growth, then `IndexError` in `ab_records.records`.

The parser indexes a full MAIN OS from `BASE=0x40000400`. Passing a payload's
original image VA to a standalone payload buffer reproduces the same crash on
stock bytes. Parsing standalone bytes at `va=BASE`, with the exact payload
length, reconstructs all generated record words and preserves the terminator.
The crash was a verifier defect; it did not prove the firmware was correct.

Independent controls found three production defects:

- Tail records contained unrelocated monolith words. Assigned-origin assembly
  differed in real call/address operands. Records now carry relocated assembly.
- B's local Plate/Compressor addresses are `0x240` words lower than A's. Shared
  P is one physical backing memory: payload-specific shared call operands are
  impossible. Only the seam and shards referenced exclusively by it occupy
  private P. Every shared record is byte-identical on A and B.
- Stock startup clears the shared window after uploading. A real project run
  stalled at two frames; a write watch saw `Y:0x33da3 <- 0` in A's clear loop
  at `P:0x48..0x49`. All shared shards then read zero. A guarded private-P
  routine preserves the reserved tails while clearing every stock-owned word.
  The executable differential checks all 262,144 Y words on each payload.

The final path is: compose four engines → classify/place/assemble shards →
normal builder places the private seam → install remaining local shards and
startup-clear hook → `repack_machine_loader.build(p_records=...)` →
`perky_image.integrate` → `extend_upload` → packed preboot uploads → stock
DSP uploader. No in-place payload growth is used.

## Architecture and memory

PERKY admission is **T1/B and T5/A only**, one voice per core. Other tracks use
the existing stock source path. The project gate also tests attempted excess
PERKY selections with empty FLEX sample slots and observes silence; it does
not claim every possible imported/stale Part is silent.

SRC A–F is **TUNE / DECAY / ALGO / PAR1 / PAR2 / MODE**. All six remain staged
and p-lockable. The executed C-control gate tests base → locked → unlocked
ALGO delivery and proves the next unlocked trig returns to the base engine.
The real source/sequencer tests prove engine bytes reach both DSP cores.

Engines: Fold Drum 1, Fold Drum 2, Simple Drum, existing native Noise/Tone.
Renderer arithmetic was not changed. The existing seam trim is preserved:
signed16 PCM shifted left five, versus full signed24 alignment at eight
shifts — exactly 1/8, −18.0618 dB. Exact PCM/state/RNG tests cover this seam.
The prior hardware report (roughly equal loudness at track LEVEL ≈50) is a
hardware observation, not a matched-material calibration of this trim.
**Final perceived-level calibration remains a physical A/B task.**

See [the complete P/X/Y ledger](TWO_VOICE_MEMORY.md), including every shard,
both core addresses, aliases, stock arenas, tables, scratch and free extents.
P: 3,051 program + 48 reserved startup words = 3,099 / 3,178; 79 free.
Private X: 359 claimed words, 257 free. Packed Y: 1,946 words, 193 free.
The private Y claim still reserves the whole measured 2,139-word gap.

**Retained:** Lo-Fi, Spring, Dark, Filter, Spatializer, EQ, DJ EQ, Phaser,
Flanger, Chorus, Comb, Delay. Spring/Dark/Delay remain FX2-only in stock.
**Unavailable:** Plate and Compressor; both IDs resolve to the stock null
stub. Compressor recovery was not pursued.

## Evidence and scope

All commands run locally. No GitHub CI, PR, remote branch rewrite or hardware
flash was performed. The real project source is read-only:
`/Users/jrold/Documents/EZBot templates/Hyper FX 1.0.6 Template by EZBOT/Hyper FX 1FF 1.0.6`.
Harnesses stage owned copies. Fixture hashes are recorded under
`out/perky/source-fixture-hashes.json`.

Permanent gates cover parser controls and bad records, exact record bodies,
payload-specific installation, disjoint extents, protected FX bytes/dispatch,
zero assembly sizing drift, packed-loader readback, stock-clear differential,
exact relocated rendering and all retained FX initialization/runtime writes.
The normal image is restored after the candidate image gate so later impulse
probe gates examine their intended input.

The generic `recloop` PCM decoder also needed a correction: `PK/Y1` records
are generator commands. It interpreted their signature as a fictitious PCM
input of −16.1 dB. The failure was reproduced with the exact captured packet;
new controls require empty PCM for commands while preserving identical magic
values inside legitimate stock PCM. PERKY output remains covered by its
explicit source/port gates, rather than inferred from command bytes.
The unmodified EZBOT template also has silent T7/T8 chains on stock firmware;
that stock control is preserved in `out/perky/verify-set-stock-control.log`.

Recorded direct qualifications:

- `verify_perky_p_records.py`: exact stock/standalone parser control, headers,
  words, terminators, byte growth; rejects empty/overlapping/out-of-range/
  overflow/protected records on both payloads.
- `verify_perky_fragment_clear.py`: every Y word matches stock except reserved
  tails, for both cores.
- `verify_perky_fragmented_exec.py`: 3,684 Fold1 and 13,878 Simple/Noise exact
  PCM/state/RNG cases at production shard addresses; controls, modes, retrigger
  offsets and long release tails. Worst source paths remain below the existing
  23,040 modeled-cycle ceiling. This host does not prove hardware wait states.
- Four `verify_perky_synth_port.py` runs, engine IDs `0,3,2,10`: each passes
  **32,000 dirty frames on both cores**, later trigs, stock AMP/FX continuation
  and six excess-voice silence checks. Logs: `out/perky/fragmented-engine*-v3.log`.
- `verify_perky_fragmented_fx.py`: four rotated 2,600-frame layouts collectively exercise
  every retained FX and all four FX2 allocator positions on both cores, with
  PERKY active on T1/T5 and ordinary sources on six tracks; every P word is read back afterward and shared execution is watched.
- `verify_perky_cf_odd_access.py --generated out/perky/fragmented`: 149
  word/long operands, none with odd displacement.
- `scripts/refhash.sh save` before changes, then `check`: 24 artifact/report
  configurations bit-identical. The new assembler strict-layout argument is
  opt-in; normal callers retain their prior behavior.

The final project-enabled `make check REMIX=perky-machine` passed: **349 PASS
result lines, 2 actual SKIP results, 0 FAIL**; **84 source gates + 4 image gates**
ran with zero failures. The runner's concluding sentence contains `[SKIP]` but
is not a third skipped check. The two legacy default-path skips are covered by
explicit current-candidate boot/readback and odd-address checks. The eight
`test_recloop.py` cases also pass. Full log: `out/perky/check-final-expanded.log`.

Packaging hashes and exact code commit are appended after qualification. Generated firmware and proprietary inputs remain untracked.

## Physical test procedure

Use the new **PERKY2F** artifact, keeping the known-good PERKY2V files available
for rollback. Start from a fresh/stamped Part with compatible source slots;
keep FX NONE initially. Confirm the version and SRC names/order. Put PERKY on
T1 and T5 together, run all four algorithms, retrigger, and sweep each control
including all MODE values. Try admitting additional PERKY tracks; verify no
extra synth voice is allocated. Check ALGO p-lock → following unlocked trig.

Keep ordinary FLEX/STATIC playback on T2–T4/T6–T8. Add Lo-Fi, Spring and Dark
on both cores, then the other retained effects and stock Delay. Re-select FX
and reload the project/Part to exercise initialization; run a long soak and
listen for channel differences or hangs. Compare PERKY and a reference sample
with identical AMP/FX/LEVEL settings to finish the gain calibration.

These are pending physical tests of fragmented P placement and startup
preservation. Prior T1/T5 smooth operation is the baseline hardware fact;
local port passes do not turn the new candidate into a hardware-qualified one.

## Packaging and exact source checkpoint

The tested DSP/ColdFire implementation was frozen at
`93598f93d9c2aca1b475fc15dcbe343b84bf587d`. The later checkpoint adds the
four-position FX regression and mandatory wrapper validation; renderer and
MAIN OS behavior remain byte-identical to that frozen build.

The release wrapper gate found a separate defect in the shared vendor tool:
`main.c` had the offset correction but still left-justified the version. The
shared checkout was not reset or edited. An isolated build under
`out/eft-perky2f` was made from upstream commit
`065d18f4195793e61891e387813488ee59f6d1ca` plus the existing repository patch.
Both decoded containers differ ONLY at the ten-byte version field. The failed
wrappers and their hashes are preserved under
`out/perky/PERKY2F-leftjust-wrappers/`.

Use `PERKY_EFT=out/eft-perky2f/elektron-firmware-tool` for this local toolchain.
The canary now runs `verify_perky_final_wrappers.py` before reporting READY:
card → exact ELEK/checksum/version, MIDI → exact section-3 MAIN OS. The corrected
wrapper passed that gate. The MAIN OS remains exactly the image qualified on
both cores for all four engines and all FX2 allocator positions.

Final delivery tag: **PERKY2F**. Artifacts stay in this worktree's ignored `out/`:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `OCTATRACK_PERKY2F.bin` | 569,092 | `9d834161e25f3b7f58bf581461fab5b9aabf900d6d9d4353320679390c280fa6` |
| `OCTATRACK_OS1.40C_PERKY2F.syx` | 794,921 | `14164e657529e4c6e7cc802203d4648af2d5133ea0ed0d5aa38f42ff83c8acd9` |
| `elek_PERKY2F.bin` | 569,074 | `a942677c078751acc0d2b473df0a496b5ba3b6b0d44f1fd1ce72c49e5f420127` |
| `perky/light2/fragmented-mainos.bin` | 1,266,004 | `2bcf688d885e5b9b61c4b12a2ca0a9ff1b01d52485d3026c44426d0b744c74ce` |

The card file is below the 1,048,588-byte OS-upgrade limit. See
`out/PERKY2F_checkpoint_manifest.json` for exact code/source/tool/input hashes,
matched platform/table files and qualification-log hashes. No project-dependent
qualification is pending for this fixture. Different real projects, physical
memory-fetch timing, project/Part reloads on the unit, and perceived-level A/B
remain hardware follow-up work.

The exact release-source checkpoint is
`0252129441269a443c096358d4322000496e3fb7`. It was rebuilt cleanly; its 533-file
source manifest matches that commit, and the rebuilt MAIN OS matches the
qualified payload SHA above. This final documentation-only follow-up records
the source commit without changing generated firmware. The final source/tool/
artifact manifest is sealed to that release-source checkpoint.

Reproduction uses the original fixture read-only:

```sh
REMIX=perky-machine BUILD=6 \
PERKY_EFT=out/eft-perky2f/elektron-firmware-tool \
OT_PROJECT='/Users/jrold/Documents/EZBot templates/Hyper FX 1.0.6 Template by EZBOT/Hyper FX 1FF 1.0.6' \
.venv/bin/python3 tools/perky/build_light2_machine_canary.py
```

The image phase can also be resumed with `build_multi_machine_canary.build_image`
after the preflights; `REMIX=perky-machine` is required for assembler import.
The successful preflight and image-resume logs are both pinned in the manifest.
