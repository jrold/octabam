# Sustained four-voice Resonant workload — 21 October 2026

**PKFM17 remains FAIL_HOLD for performance.** The corrected four-voice screen
now measures Resonant Snare, Resonant Bass and sequenced Snare/Bass MODE locks,
with matched Slap controls. All eight runs preserve original-reference synth
PCM and complete without nominal ISR deadline misses, but every run fails six
of the seven unchanged calibrated timing ceilings. The
[qualification receipt](RESONANT_WORKLOAD_QUALIFICATION.json) binds the actual
image, ELF, frozen instrument, fixtures, coverage and results.

The earlier [CF synthesis campaign](CF_SYNTHESIS_QUALIFICATION.md) held V3 at
Slap in all five sustained rows. Its selector matrix exercised Resonant, but
that aggregate sweep did not establish separate sustained Snare/Bass means.
The old 221.328 us figure was the worst of those five Slap rows, not a measured
worst case across all algorithms. Those historical receipts remain unchanged.

## What actually ran

Each row executes **32,768 transport blocks**, 16 output samples per block at
44.1 kHz: **11.889 seconds**. A real 64-step, 120 BPM, 1X sequence triggers all
four PERKY voices, with four stock sample tracks and all fourteen stock FX.
T1 and T2 run WT V1 and WT V2 on CF. T5 runs the selected Slap or Resonant
case on CF. T6 runs either metallic Noise Hat on DSP-A or Noise/Tone mode 1
on CF; the latter configuration has all four source voices on CF.

The eight fixtures share the same workload construction and controls; the T5
ALGO/MODE selection and locks distinguish each matched group. Final-card scans
verify all sixteen banks, eight Part records per bank and four patterns per
bank. Each pattern has 45 triggered T5 steps. Alternating fixtures lock MODE
0/1 on successive triggered steps within the pattern; the odd trigger count
repeats mode 0 across the loop boundary. Runtime source observations confirm
**16,880 Snare blocks and 15,888 Bass blocks** in each alternating run. They
prove both modes rendered; the frozen observer does not count or timestamp
every mode transition.

Steady ISR means exclude the first 512 completed interrupts. Full ISR peaks
include the whole capture. Total-CF means divide exact playback CF cycles by
32,768 and 264 MHz, including background work. Values below are microseconds
in the fixed local model, not measured hardware durations.

| T5 selection | T6 selection | Steady ISR mean | Full ISR peak | Total-CF mean |
|---|---|---:|---:|---:|
| **Fixed ceiling** | — | **158.212** | **250.712** | **189.298** |
| Slap control | Metallic Hat, DSP-A | 210.437 | 300.667 | 236.154 |
| Resonant Snare | Metallic Hat, DSP-A | 205.582 | 303.083 | 231.353 |
| Resonant Bass | Metallic Hat, DSP-A | 205.612 | 301.947 | 231.386 |
| Snare/Bass MODE locks | Metallic Hat, DSP-A | 205.566 | 303.004 | 231.338 |
| Slap control | Noise/Tone, CF | 221.681 | 307.125 | 247.371 |
| Resonant Snare | Noise/Tone, CF | 217.005 | 310.947 | 242.744 |
| Resonant Bass | Noise/Tone, CF | 216.536 | 309.330 | 242.251 |
| Snare/Bass MODE locks | Noise/Tone, CF | 216.772 | 310.867 | 242.505 |

For these exact controls, current firmware and this model, Resonant reduces
the mean ISR by 4.677–5.146 us relative to the matched Slap controls, while
increasing full ISR peaks by 1.280–3.822 us. This does **not** reproduce the
user's reported much greater Resonant burden on hardware. It does not falsify
that observation: hardware cache/bus effects, other parameters and the older
firmware involved in that experience are outside this matched comparison.
These are measured fixture results, not a claim that Slap is universally
more expensive or that all Resonant settings have been bounded.

The worst Resonant mean here is Snare with CF Noise/Tone: 217.005 us ISR and
242.744 us total CF. Reaching the unchanged ceilings requires another
**27.1% ISR-mean reduction and 22.0% total-CF reduction** in that case. The
corrected test therefore does not admit the current placement for hardware
performance acceptance. The broader four-voice feasibility goal remains open;
nominal 362.8 us deadline passes alone are insufficient.

## Correctness and evidence limits

All four rendered synth sources match the independent original-source oracle
with zero PCM differences. DSP Hat state, side values, clock and ring feedback
checks also pass at the frozen observer's scope. This sustained observer does
not compare every raw CF Resonant state byte on every block. The separate,
unchanged-image 5,355-frame direct source gate supplies prior raw-CF-state
evidence across layouts, modes, segment splits and transitions; the new
qualification binds that receipt separately.

Every track contributes significant source and post-FX audio, with continued
card reads after PLAY. These aggregate checks do not establish uninterrupted
stock PCM on every frame. The bound measurement adapter extracted those
activity counts before deleting the bulk audio dump; its SHA256 survives,
but the stock capture cannot be replayed from these retained receipts.
Ownership, private-stack, DMA overlap and transport
error checks pass. Normal DSP Hat rendering performs zero duplicate CF Hat
renders, snapshots or replay jobs. Existing lifecycle results remain the
earlier unchanged-firmware evidence; this measurement-only correction does
not claim a new lifecycle campaign.

Every row fails ISR mean, p99, p99.9 and peak, total-CF mean and ACK p99; only
ACK peak passes. The observer SHA256 remains
`f975b4d2c4b6a2d993d3158bc8e68c8a786b328e2902b58bdde418225287d022` and the
budget SHA256 remains
`8608844b96c6f20daed514147dc6cadab7a2c82aae80d2ef7c9a875a22ccaec4`.
CF/PIT clocks remain 264/132 MHz, with uniform startup/pre-roll/playback cycle
clock x1.00. The hardware-informed budget is an engineering screen, not a
universal emulator-to-hardware multiplier or a guaranteed silicon threshold.

Firmware was not changed. MAIN remains
`7f3eeecafcfb6746207d981e3677e224d5321e2100b748fe5ba7e633dd314dcb`; ELF remains
`e16f1da5b17b55083ab7fa7f165efd4e6ec262ada259291d4927b2412921d6c9`.
PERKY4S remains the hardware-confirmed release.

## Required sustained screen

Future four-voice performance claims must include sustained Snare, Bass and
sequenced Snare/Bass rows, actual source-selection witnesses and matched
controls, alongside the existing Hat alternatives and lifecycle gates. A
selector matrix alone does not replace this screen. The dedicated qualifier
requires all eight current cases and rejects missing or inconsistent receipts.

```sh
for pk_v3 in slap-control snare bass alternate; do
    for pk_v4 in hat noise-tone; do
        .venv/bin/python tools/verify/measure_perky_resonant_workload.py \
            --build out/perky/hybrid/full-map-packet-reserve-v2 \
            --work out/perky/hybrid/resonant-feasibility-v1 \
            --v3 "$pk_v3" --voice4 "$pk_v4"
    done
done
.venv/bin/python tools/verify/qualify_perky_resonant_workload.py
```

Run measurements in a fresh output directory when repeating; existing cases
are preserved. The current eight measurements exit zero. The final qualifier
returns **1** and writes a fresh **FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK**
receipt after validating functional evidence. No firmware build, flash,
package, push or release commit was made for this correction.
