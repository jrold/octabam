# PERKY4 Phase 2 — preserved release and hardware handoff

Hardware comparison later rejected Complex fidelity. The raw renderer gates
below remain valid, but the shipping control bridge omitted three AU behaviors.
See [PERKY4R AU repair](PERKY4R_AU_REPAIR.md) for the correction and direct AU evidence.

PERKY4 starts from PERKY3R source checkpoint
`ca23c76bce2dbe55f30b5fc5547d55e0ba04cdc7` on the isolated
`codex/perky4-phase2` branch. PERKY3R, PERKY2F and the physically working
PERKY2V_light_2voice checkpoints are preserved. PERKY3R passed local gates;
early T1/T5 hardware results were positive, but its extended physical
qualification was still in progress. The pinned PERKY3R rebuild reproduced
MAIN OS SHA256 `3b45204e5aaabb899ee241ec4d7a785635aaebb77a77429a50989b8d86875d38`.
Neither PERKY3R nor this candidate is
claimed physically stable from emulator results.

The six SRC controls remain A TUNE, B DECAY, C ALGO, D PAR1, E PAR2, F MODE.
Displayed ALGO 1/2/3/4 selects Fold Drum 1/Fold Drum 2/Simple Drum/Complex
Drum. T1 runs on DSP B, T5 on DSP A, one voice per core; the other six tracks
remain stock. Complex is original PĒRKONS Voice 2/Algorithm 3; its panel
MODE 1/2/3 maps to original firmware 1/0/2. Noise/Tone remains absent.

Complex reuses the previously ARM/native-qualified arithmetic. The production
42-word overlay reorders that state around the existing common envelope/control
ABI. The modulation oscillator follows the common fields instead of occupying
the amp-envelope slots. Initialization comes from the original pre-trigger
capture, including modulation increment 44389. The native renderer keeps its
rounding, wrapping, clamp, phase-wrap wave change and trigger/update behavior.
Its tune law adds 768 then clamps at 4095; this is the **original control law**,
not a sample-rate tuning correction. The original Complex pitch envelope and
PAR1/PAR2 laws run with PERKY3R's recovered smoothing/update schedule.

The original three engines' renderer and 160/147 FIFO sources are reused.
Only shared dispatch, the qualified fourth-wave reader, initialization constant
loading and placement change in the four-engine profile. A control-rate base
pitch cache removes invariant work from Complex's sample loop. The original
standalone Complex estimate was 33,007 modeled cycles; it is not the current
integrated price. Production timing and memory are recorded in
[PERKY4_MEMORY.md](PERKY4_MEMORY.md).

Raw Complex output is checked separately against independent PerkyBits C++
and original ARM captures. Its PCM and all 42 persistent words agree exactly;
full native ARM object continuation and unchanged reference RNG are checked.
The integrated clock seam compares native state and RNG exactly. Resampled
PCM permits one signed24 LSB for the existing fixed coefficient quantization
against exact rational interpolation; the raw authenticity seam permits no
PCM error. The integration shift of 5, rather than signed16 alignment shift
8, retains the existing −18.0618 dB gain trim.

A trig lock changes that event's tuple. An unlocked following trig returns to
the Part's base ALGO; the prefix of an interior event keeps the previous tuple.
Every engine pair, mode and sample offset 0..15 is tested with an already
active voice. Dirty instance/scratch/FIFO/clock initialization is compared
with clean state. DSP admission also rejects tagged records at the three
unsupported core positions before initialization, protecting the fourth wave
stored in their dormant overlays.

## Main-screen display

The actual stock machine-letter drawer is at `0x4003fed8`. The hook at
`0x40040132` substitutes the stock P bitmap only for an admitted PK/1-signed
FLEX track in the displayed Part. It preserves the underlying FLEX machine id.
FLEX remains F, STATIC remains S, and Pickup retains its stock P and badges.
No machine types, Parts or project bytes are changed by the drawer. The
corrected SRC > PERKY legend and restored stock double-tap behavior remain.

The requested icons are the **play-status triangles beside the main-screen
track strips**. The stock drawer at `0x4004bd48` reads status from each general
voice record (`0x800049d8`, stride 168). Ordinary FLEX/STATIC update those bytes
through sample-player transport; PERKY publishes DSP source records instead,
so that sample-player play bit does not represent its events.

The hook at `0x4004beac` supplies an event latch written only after a true
post-event PK/Y1 trig record is published. Prefixes, empty steps and continuation
records do not set it. The next stock track-strip repaint consumes it; multiple
fast trigs can coalesce at LCD cadence. Bank and Part qualify the latch. Stock
mute handling and the other two status bits retain their priority. This is a
stock play-glyph **event flash**, not a fabricated sequencer event or a claim
that the DSP envelope is still active. Stock FLEX/STATIC/Pickup paths return
their original play status. Conditional trigs flash only when the stock
scheduler actually publishes their event; no condition logic is changed.

The packaged tests execute the real bitmap drawer for all five stock types,
all Parts, signatures and tracks (320 draws), plus 512 producer-to-trig-to-stock
play-drawer cases across all engines, both admitted tracks, mute, selection and
other status-bit priorities; 640 ordinary stock status/mute draws also agree. The project replay uses all four sequencer pages, actual ALGO-lock
records and a full 64-step cycle; selection/mute/condition presentation and
LCD visibility still need the hardware checks below.

## Reproduce and verify

Use your stock OS and original reference assets, not a downloaded patched OS.
Build the emulator in this worktree (`make emu-cf`); do not symlink `out/emu`.
The repo's original qualification input setup remains applicable. The real
project is read-only; gates make private copies and verify its hashes before
and after the complete run.

```sh
OT_PROJECT='/path/to/real/project' PERKY_EFT='/path/to/patched/elektron-firmware-tool' \
  .venv/bin/python3 tools/perky/build_four_machine.py --qualify-only
# Commit the reviewed source after qualification, then:
OT_PROJECT='/path/to/real/project' PERKY_EFT='/path/to/patched/elektron-firmware-tool' \
  .venv/bin/python3 tools/perky/build_four_machine.py --package-qualified
.venv/bin/python3 tools/verify/verify_perky_four_provenance.py \
  --report out/perky/four/PERKY4_RELEASE.json
```

A normal clean-tree run qualifies and packages in one invocation.
`--local-only` produces only an emulator fixture. Packaging rebuilds the clean
commit and requires identical qualified MAIN OS and source-manifest hashes.
Card and MIDI wrappers are produced only after all gates pass and are decoded
back to verify section contents and checksums. The existing card updater size
limit remains enforced. No GitHub CI is used.

`out/perky/four/qualification-checkpoint.json` lists every command, environment,
exit code, log hash and observed PASS/FAIL/SKIP counts. The release JSON pins
the exact source commit, stock OS, assets, native sources, tool binaries,
project files, MAIN OS, both updater formats, source manifest and memory ledger.
Those ignored artifacts accompany the hardware test candidate; proprietary
firmware and extracted waveform bytes are never committed. Repository gates'
two documented skips are covered explicitly by packaged boot/readback and the
four-profile generated odd-access gate. Targeted skips fail the release runner.

Pickup stays enabled. The separate [feasibility audit](PICKUP_FEASIBILITY.md)
credits no recovered DSP words and no recorder/FLEX pool savings.

## Completed local qualification

The final runtime run completed **39 commands, zero failed**. Its repository
floor reports **349 PASS markers, zero FAIL, two explicit SKIP**, with
84 isolated module gates and four image gates successful. All **24 refhash
configurations are bit-identical** to the trusted baseline. The skipped old
canary upload path and old CF-final generated assembly path are covered by the
actual four-profile boot/readback and odd-access gates; targeted skips are zero.

| Final four-profile evidence | Passed coverage |
|---|---|
| Raw Complex, both placements | 4,960 blocks: 864 original ARM, 4,096 randomized native; exact PCM, 42-word state, whole native object continuation and unchanged RNG |
| Renderer + native clock, both placements | 36,864 blocks; 1,536 active interior transitions; 24 dirty initializations; 1,152 unsupported-position cases, each with three whole-wave capture windows |
| Executed ColdFire controls | 1,120 random/clamp/Part/automation and base→locked→base records |
| Packaged UI | 320 machine-letter draws, 512 true-event/mute/selection/priority cases, 640 stock status cases; full SRC/LFO and 32 engine-transition producer paths |
| Main source/AMP/FX | Four algorithms × 32,000 dirty frames, both cores and six unsupported tracks |
| Retained effects | Eight configurations × 2,600 dirty frames, all twelve FX, immutable P/Y/X assets checked |
| Original two-core regression | T1/Dark solo + three T1/T5 interleavings, 9,000 frames each; matched T1 PCM exact |
| Full four-page project | T1 alone, T5 alone and three two-core interleavings, 36,000 frames each; actual 64-step ALGO order and matched T1/Dark PCM exact |
| Upload/startup/CF storage | Final packed loader readback, all 262,144 Y words/core and 33 continuation registers/core; generated C and machine assembly odd-address audit |

The completed qualified MAIN OS hash is
`b412c1a1cfc8f738fcccddb78b1f85f028d7d27aff8eafbc7d05e701940710f2`.
A packaging-only correction expands the inherited short Git revision to full
SHA in the release JSON. Its build/test prefix is unchanged and a separate
local rebuild reproduces this exact MAIN OS; the audit and original qualified
manifest are retained. This adds one explicit qualification receipt. Card/MIDI
wrapper verification and committed-source provenance verification are final
packaging gates recorded with the delivered candidate.

The new admission observer initially read the requested overlay through r6,
which contains waveform data for unsupported positions. The corrected observer
reads fixed primary-state/asset addresses, resolves its own continuation label
and uses the host's documented X/Y dump layout. The failed diagnostic logs are
preserved; no shipping DSP instruction, PCM comparison or cycle ceiling was
changed to clear the observer gate. All final native comparisons remain exact
at the raw seam and retain the existing one-LSB coefficient bound at the clock
seam.

## Short MKII hardware procedure

1. Keep your known-working PERKY2V_light_2voice updater and project backup
   available. Install the candidate with your normal card or MIDI updater;
   record the release JSON's commit/hash and confirm PERKY4 on the unit.
2. Start dry on T1 alone. Visit all four ALGO positions and all three modes;
   compare Complex's three modes with the PerkyBits AU using matching controls,
   note and velocity, accounting for the documented integration gain. Check
   tune, pitch-envelope timing, decay, phase/wave transitions and retriggers.
3. Repeat on T5 alone, then T1 and T5 simultaneously. Add Dark, Spring and
   Lo-Fi with both cores active. Check attacks and tails for clicks/pops,
   stalled clock, stuck voices or transport lockup.
4. Use rapid ALGO p-locks across all four engines, MODE locks, interior trigs
   and retriggers. Follow each locked event with an unlocked event. Exercise
   low TUNE transitions, live A–F controls, LFO destinations and scenes.
5. Verify P on signed PERKY tracks, F on ordinary FLEX, original STATIC and
   Pickup labels, and SRC > PERKY. Check side play triangles for empty and
   ordinary steps, parameter/ALGO locks, all sequencer pages, active/selected
   tracks, mute and conditional trigs. A skipped condition must not flash.
6. Save/reload Parts and the project. Repeat after power cycling; verify
   assignments, base ALGO, locks, LFOs, scenes and retained FX persist.
7. Run a prolonged clock/transport soak with both voices and FX, including
   starts/stops and external MIDI clock. Record duration, tempo and routing.
   Stop at the first pop or transport fault, save the smallest reproducer and
   roll back to the known-working checkpoint. Emulator interleaving fuzz is
   evidence of local regressions only, not a hardware timing measurement.
