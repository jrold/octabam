# Hardware-informed emulator target — 21 October 2026

**PKFM6 fails the new performance target.** Its exact-source and nominal-clock
qualification remains valid, but it is not admitted by this performance screen.
No firmware was changed or installed during this replay campaign.

The [machine-readable budget and verdict](EMULATOR_BUDGET.json) and
[measurement table](EMULATOR_BUDGET.csv) are authoritative. All times below
are **measured emulator times at CF264/PIT132**, not physical time predictions.

## Target and current gap

The engineering target is the measured envelope of the previously reported
working configuration: two DSP voices, one CF voice and five stock STATIC
tracks, using the preserved PKH4O2 image. Four algorithm-pair settings sample
that shape; the unused second CF selector does not create another active voice.
The exact hardware-confirmed PERKY4S MAIN was replayed as a separate reference.

| Metric, microseconds | PERKY4S reference | Working-shape target | PKFM6 metallic Hat, all 14 FX |
|---|---:|---:|---:|
| Steady ISR mean | 153.485 | **158.212** | 232.879 |
| Steady ISR p99 | 162.598 | **166.780** | 242.208 |
| Steady ISR p99.9 | 233.735 | **237.731** | 320.614 |
| Full ISR maximum, including startup | 237.739 | **250.712** | 326.413 |
| Total playback CF work / transport frame | 189.171 | **189.298** | 299.144 |
| ACK CPU-work p99 | 323 | **328** | 338 |
| ACK CPU-work maximum | 351.439 | **362.212** | 346.208 |

**[Policy, inferred from the reported working configuration]** Meet every
working-envelope ceiling. These are conservative operating targets, not proven
silicon limits. Independent ceilings can come from different rows. In
particular, passing the ACK peak alone is insufficient: the current candidate
passes that ceiling while failing the sustained-load ceilings substantially.

Metallic Hat needs approximately **32.1% less steady ISR work** and **36.7%
less total playback CF work** to reach this envelope. This is a reduction from
the current measured cost, not the percentage by which it exceeds the target.

| PKFM6, WT/WT + Slap + V4, all 14 FX | ISR mean | ISR p99 | Total CF mean | Verdict |
|---|---:|---:|---:|---|
| White Hat | 231.555 | 240.799 | 277.373 | FAIL |
| Metallic Hat | 232.879 | 242.208 | 299.144 | FAIL |
| Pulse Hat | 218.015 | 226.837 | 270.629 | FAIL |
| Noise/Tone | 232.902 | 242.500 | 259.475 | FAIL |
| Acoustic Hats | 229.176 | 254.129 | 256.004 | FAIL |

The metallic shared-twelve-FX control measures 233.065 / 242.409 / 299.345 us
on these three metrics, versus 232.879 / 242.208 / 299.144 with all fourteen.
Restoring Plate/Compressor therefore does not account for the approximately
110 us total-CF mean gap in this corpus. These comparisons are not an exclusive
per-function profile; they do not attribute all remaining cost to one routine.

## What the historical replay calibrates

The preserved PKH4O2 MAIN is
`f7f04e26969522d2024b1bba5be85f620857d636dbe0b284aa38c0fb087a21db`.
The [physical observations](CF_FOOTPRINT_20261016_HARDWARE.json) report one CF
plus five stock tracks working and two CF plus three stock tracks becoming
sluggish and locking up. The physical firmware tag is supplied by that report;
this campaign did not read a MAIN hash back from the unit.

Each WT/WT, Snare/Snare, Snare/Bass and Noise/Tone pair gets three local rows:
one CF/five stock, one CF/three stock, and two CF/three stock. The last two hold
stock work equal to measure the second CF increment. That increment is
20.4–25.3 us in steady ISR mean and 20.3–25.2 us in total CF mean. Local
measurements do not reproduce the hardware's disproportionate loss of capacity.

The reported physical failure is **not a recovered exact trace**. Its complete
card, control history and algorithm pair are unavailable; the four modeled
pairs are configuration-envelope samples, not four separately established
physical failures or successes. PERKY4S uses its exact hardware-confirmed MAIN
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`,
two DSP voices and six STATIC tracks with the same twelve stock effects.

**[Measured limitation] No single tested timing statistic separates every
working-shape row from every failing-shape row.** For example, the two-WT,
three-stock replay has a lower mean and peak than the working one-Snare,
five-stock replay. The target rejects the Snare/Snare, Snare/Bass and
Noise/Tone two-CF rows, but the two-WT row fits the working envelope. That is
not a new hardware acceptance claim for two WT voices.

Consequently the earlier conversational suggestion of a **200 us peak ceiling
or a 1.8x universal slowdown is withdrawn as a calibration**. A 200 us peak
ceiling would reject these working references too. The nominal 362.812 us
deadline and a nominal 20% reserve also remain insufficient hardware criteria.
Keep the native clocks unchanged and use the explicit load/burst target above.

**[Inference and falsifier]** Matching the working envelope is a necessary
engineering admission policy, not sufficient proof of physical reliability.
Exact paired hardware captures with recorded algorithms, controls and project
could justify different targets or a real cost model. Cache/SDRAM/card/DMA
contention and physical UI latency remain unmodeled. The present evidence does
not identify which of those causes the hardware/model discrepancy.

## Instrument and receipts

Nineteen 16,384-transport-frame rows use **one arm64 observer binary**, the
same dirty-DSP seed, native CF264/PIT132 clock from startup through playback,
the same stock tone, dense controls/LFOs and retained FX. Twelve historical
rows, six PKFM6 rows and the PERKY4S reference are retained under
`out/perky/hybrid/budget-calibration/`. Four additional 4,096-frame runs compare
the parent/new observers on PKH4O2 and PKFM6: target dumps, all source/post-FX
block bytes, cycle totals, maxima and audio summaries are identical.

The extension adds read-only executed-cycle histograms. Steady ISR statistics
exclude the first 512 completed interrupts; full ISR maxima include them. Total
CF mean uses the exact playback cycle sum divided by requested transport
frames, not the ACK histogram's startup-inclusive count or rounded stdout.
ACK quantiles retain the original startup-inclusive CPU-work window. They
include intervening stock tasks and the real CF Hat shadow worker; they do not
measure interrupt latency or whole physical CPU utilization.

Every row completes, has active audio on its selected stock and PERKY chains,
streams actual STATIC card sectors and has no modeled deadline or late-DSP-word
miss. All six PKFM6 rows also have zero independent PCM/state/RNG/clock/feedback
errors, real worker completion and no transport error/overflow. These are the
functional passes; the performance verdict is separately **FAIL**.

The previous full lifecycle/Part/Bank/scene results remain bound to the unchanged
PKFM6 image. They were not repeated just to rediscover a performance failure
already present during steady playback. The existing 355.337 us lifecycle
maximum is still nominal-clock evidence, not an empirical-budget pass.

## Reproduction and admission

Use the existing checkout and preserved stock/image inputs. Replays refuse to
overwrite an existing row. The diagnostic builder and row runner are
`tools/verify/calibrate_perky_hybrid_budget.py`; commands, image/ELF/card hashes,
observer inputs, per-row histograms and the byte-bound PERKY4S replay driver are
retained in the output directory. Generated cards and bulk block captures are
removed after their hashes and audio summaries are saved.

Regenerate the report from those receipts:

```sh
.venv/bin/python tools/verify/qualify_perky_hybrid_budget.py --check
```

The current candidate **must exit 1** with
`FAIL_EMPIRICAL_WORKING_ENVELOPE`. Assess a subsequent measured row against the
saved targets without recalibrating them:

```sh
.venv/bin/python tools/verify/qualify_perky_hybrid_budget.py --assess /absolute/path/ROW.json
```

The check requires the same instrument/clocks and independently exact source
audio. A budget pass will still require the full layout/lifecycle checks and
physical acceptance. Do not replace these fixed targets with the slower
candidate's own measured envelope.
