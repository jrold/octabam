# PERKY4R Complex Drum AU authenticity repair

PERKY4R repairs three independently demonstrated shipping Complex controls. The
installed **PerkyBits AU 0.2.0** is the sonic oracle. PERKY4 source
`11f0165f702ddac17bd61a5b19cdbe43cca740f9` and its Downloads updaters remain the
rollback checkpoint. Work is isolated on `codex/perky4-au-authenticity`; no
original project, previous checkout, plugin, or PerkyBits source was modified.
Physical MKII qualification remains pending.

| Stage | Preserved PERKY4 | AU-proven correction |
|---|---|---|
| Trigger-note TUNE conversion | Added 768 to prepared TUNE and clipped; approximately 18 semitones while unclipped | At the AU's default note 45, use prepared TUNE directly |
| PAR1 modulation oscillator | Kept the increment from the low-control startup capture, 44,389 | PAR1 controls its exponential frequency, 24..2032 Hz, as well as pitch-envelope decay; midpoint increment 5,417, maximum-PAR1 increment 524 |
| Maximum DECAY | Forced amplitude gate off | Preserve the original gate at prepared DECAY >= 4080; the AU sustains here |

MODE 1/2/3 still maps to firmware 1/0/2 and main target waves
`0x080222a0/0x080224a0/0x080228a0`. The modulation wave stays
`0x080226a0`. Main waveform changes wait for phase wrap. Direct AU comparisons
verify these identities rather than inferring them from the catalog.

The repair changes Complex preparation in `control_four_candidate.c` and its
placed control seam in `build_four_payload.py`. Packet size stays fixed: byte 9
carries modulation frequency divided by eight, MODE bit 7 carries the sustain
gate, and MODE bits 0..1 retain the public selection. The prefix marker stays
in byte 10. The existing exact frequency converter runs before base-pitch
preparation can reuse r4. No renderer arithmetic, wave assets, Fold1/Fold2/Simple
primitive, clock ratio, integration trim, admission rule or retained FX changes.

## Why the old tests passed

The 4,960 raw comparisons import original ARM object state, including the
**correct modulation increment and note-derived pitch**, before comparing
placed DSP assembly with `NativeV121ComplexDrum.cpp`. Those tests demonstrate
PCM/state arithmetic equivalence for supplied state; they never execute the
public-controls-to-shipping-state bridge. They remain intact.

The 36,864 integrated clock/audio comparisons execute actual placed control and
renderer code, but their Complex oracle deliberately shared the same omissions:
it applied the +768 TUNE offset, left modulation increment at startup, and
forced amplitude gate off. The expected controls were derived from that model,
not independently constrained by a triggered AU. The 1,536 interior-transition
comparisons inherited those values. The ColdFire control test likewise expected
the incomplete recovered field census. Passing these comparisons established
internal agreement, timing and transport continuity, not complete instrument
fidelity. Executable AMP/FX, uploader and boot tests validated downstream
integration; they could not establish the source sound's authenticity.

The historical control sweep used an untriggered object's default note. The
real note-45 trigger removes its +768 offset. Recovery omitted the PAR1-driven
modulation field and the common maximum-DECAY gate. These are control defects,
not a wrong engine, wrong native clock, alternative waveform asset, AU EQ or
DSP arithmetic approximation.

## Actual AU capture and independent proof

The component is `/Library/Audio/Plug-Ins/Components/PerkyBits.component`, AU type
`aumu`, subtype `PkBt`, manufacturer `Prky`, component version 512, bundle
version/build 0.2.0. The capture receipt hashes its actual executable, the
user's PĒRKONS 1.2.1 image and the local capture host. Version text alone does
not identify a binary. Local PerkyBits sources are used for understanding and
an independent reference, never substituted for installed-AU output.

`tools/harness/perky_au_capture.cpp` instantiates the installed component via
Apple's AudioUnit API, loads the user-owned image through the plugin's saved
state, sets public controls, delivers scheduled MIDI and renders floating-point
stereo offline. It uses no audio device or external effects. `Algo` is the raw
0..11 choice index (Complex 5); Tune/Decay/PAR1/PAR2 are AU-normalized 0..1 but
represent public integer 0..4095; MODE normalized 0/.5/1 represents panel 1/2/3.
Chromatic is off, note is 45, Note-On velocity is 127 (firmware 255), output gain
is unity, optional engine-switch declick is off. Fresh captures trigger at sample
zero after the plugin's authentic 16 initialization updates, with no idle priming.

The reference tool drives PerkyBits' public original-ARM control/trigger path
and its independently native-qualified renderer. Its output is first required
to equal **actual AU audio**, then the real ColdFire-C producer records feed the
placed shipping controls and DSP renderer. Captured PCM is never obtained from
the shipping side. A separate 512-case note-45 ARM sweep constrains every
control axis and both admission tracks' records.

The direct matrix covers all modes and nine purposeful corners each: low/mid/high
controls, low tuning, higher tuning, short/long decay, low/high PAR1 and PAR2,
pitch envelope off/on, and maximum-decay sustain. Four seconds include complete
attacks and decay tails (or the intentional sustained interval). Acceptance is
**zero differing native int16 samples**, with no alignment fit, normalization,
EQ, time stretching or pitch correction. IEEE float conversion at unity maps
these exact integer samples to multiples of 1/32768; a loose tolerance is unnecessary.

Nine additional direct AU captures at 44.1 kHz compare the actual shipping
source entry, 160/147 FIFO interpolation and 1/8 integration gain over complete
four-second sounds on both cores. Acceptance is at most two Q23 source-output
LSBs: a bound for float32 AU interpolation, Q23 DSP coefficient quantization
and integer-store flooring. There is no fitted gain or phase. These source-entry
captures are before stock AMP/FX; the executable FX/project gates exercise
normal downstream continuation in the packaged image.

Additional actual-AU MIDI captures at samples 7207, 19003, 33017, 45011, 69013,
85001 and 120007 cover interior retriggers, velocity 64, and sustained PAR1,
PAR2, TUNE and DECAY CC changes. The AU's once-per-host-block deferred smoother
is explicitly distinguished from the preserved Octatrack control-update cadence.
An exact dynamic AU/native comparison establishes the independent renderer/control
reference; existing shipping interior-transition gates check shipping continuity.
It does not claim that the two hosts' automation smoothing latency is identical.
Cross-family ALGO p-lock tests preserve PERKY4's single-overlay initialization
policy; the fresh-instance AU matrix does not establish equality to retained
cross-algorithm AU object histories.

All captured audio, object state and extracted tables stay under ignored `out/`.
`capture-manifest.json`, per-core reports, WAVs and command logs carry conditions
and hashes; nothing proprietary is committed.

## Reproduction

Use the supplied original image and local PerkyBits checkout through
`PERKONS_FIRMWARE` and `PERKYBITS_SOURCE` if their default Downloads paths differ.
Initialize an isolated worktree with the dependencies described in `AGENTS.md`;
copy its ignored engine fixtures and static assets from the trusted checkpoint,
or regenerate them with the existing extraction/capture tools. The AU reference
compiler uses the existing local Unicorn libraries and Darwin cache-discovery
fallback object; it fails when these prerequisites are absent.

```sh
python3 tools/verify/verify_perky_complex_au.py --capture
PERKY_CORE=B python3 tools/verify/verify_perky_complex_au.py
python3 tools/verify/verify_perky_complex_control_contract.py
python3 tools/verify/verify_perky_complex_au.py --baseline
python3 tools/verify/verify_perky_complex_au.py --baseline --isolate tune --baseline-case 0
python3 tools/verify/verify_perky_complex_au.py --baseline --isolate modulation --baseline-case 4
python3 tools/verify/verify_perky_complex_au.py --baseline --isolate sustain --baseline-case 2
```

The baseline command must demonstrate a material mismatch, not merely accept a
compiler failure. `--isolate` restores one erroneous behavior at a time while
keeping the other repairs. Ordinary runs fail on the first differing sample.
`--capture` intentionally makes a new independently captured reference receipt;
ordinary runs reuse its captured audio and verify its content against the
independent path. Future Wavetable work can reuse the generic installed-AU host;
this release adds no Wavetable engine or assets.

## Local qualification and resources

The pre-package run completed **46 commands, zero failed**. The repository
floor produced **349 PASS markers, zero FAIL, two explicit archival SKIP**, with
84 isolated module gates and four image gates passing. All 45 targeted commands
had zero skips; the two archival omissions are covered by packaged upload/boot
readback and generated four-profile odd-access checks. The original project
inventory was unchanged. Packaging adds the required wrapper round-trip command.

Both cores matched all 27 native four-second AU sounds with **zero PCM error**.
Nine four-second 44.1 kHz source comparisons per core peaked at **1.1875 Q23
output LSB**, below the justified bound of two. Three dynamic AU/native MIDI
captures matched exactly. The three isolated regressions demonstrated RMS
errors of 1,837.634 / 11,134.815 / 14,258.690 native LSBs for the old TUNE,
modulation, and sustain behaviors respectively; repaired native error is zero.

The full local release runner retains every previous gate and adds direct AU
comparison on both cores, the preserved-baseline and three isolated negative
controls, and the independent producer contract. No GitHub CI is invoked.
Its command receipts list exact exit codes, assertion markers and explicit skips.
The read-only real EZBot project is copied into generated fixtures; its inventory
must match before and after qualification and packaging.

Measured assembled P occupancy is 770/774 private words on each core (4 free)
and 2398/2404 physical shared words (6 free across separate gaps). X/Y reservations,
wave regions and the original twelve retained FX are unchanged. The preliminary
integrated Complex maximum is 18,280 modeled cycles; worst transition 22,139,
under the unchanged 23,040 development ceiling. Private-P free extents are A `0x1220..0x1222`, `0x1b56..0x1b58` and B
`0xfe0..0xfe2`, `0x1916..0x1918` (two words each). Shared-P gaps are
`0x33fff..0x34000`, `0x37eff..0x37f00`, `0x37ffd..0x38000`,
`0x3ffff..0x40000` (1/1/3/1 words). ColdFire runtime is 17,204 bytes, BSS 496
bytes, packed stage 5,719 bytes; its reserved ceiling retains 10,463,113 bytes
beyond the stage. Final release receipts are the
source of truth for the packaged build's exact extents and timing.

## Physical MKII comparison

Keep PERKY4 available for rollback. Flash PERKY4R only after its release report
and wrapper round trips pass. Use a copy of the project, T1 first, T5 next,
then simultaneous T1/T5. Select ALGO 4, disable LFO/scenes initially, leave stock
AMP neutral and FX off, and compare all three MODE positions. Use TUNE/DECAY/
PAR1/PAR2 64/64/64/64; the AU values are 2048/2048/2048/2048, note 45, chromatic
off, velocity 127. Compare against the captured midpoint WAV for each mode.

Then compare 16/96/0/0 against 16/96/127/0 (AU public targets 512/3072/0/0 and
512/3072/4095/0); this isolates modulation response with pitch envelope off.
Check low tuning and higher tuning, retriggers, DECAY 127 sustain and subsequent
DECAY reduction. Exercise ALGO p-lock return, LFO routing and scenes, then both
voices through Dark Reverb during a full 64-step cycle. For a dry audio recording,
retain fixed gain and account for the known source trim of 1/8 (-18.0618 dB);
do not normalize away a discrepancy. Physical analog/main-output behavior and
DSP hardware timing remain unmeasured until that MKII test.
