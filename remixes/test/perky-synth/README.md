# PERKY Noise/Tone synth canary

This is the next layer after `perky-probe`.

`perky-probe` stays the minimal ColdFire -> PK/Y1 transport -> DSP impulse diagnostic.
This remix deliberately omits PLATE REV, SPRING REV and DARK REV so the first
complete correctness-first Noise/Tone renderer can use their contiguous DSP P
region without changing the tracked PERKY module manifest.

Build the complete synthetic canary with:

```sh
python3 tools/perky/build_synth_canary.py
```

The wrapper will:

1. generate clearly labelled synthetic Noise/Tone waves/envelopes/state;
2. pack the 236-word X initializer and packed Y tables;
3. generate/deduplicate/assemble the complete Noise/Tone DSP source;
4. temporarily replace `PERKY PROBE`'s DSP source in memory for this build only;
5. build `REMIX=perky-synth`;
6. restore the normal impulse-probe registry entry;
7. append the preboot loader carrying the extended A/B DSP uploads.

Output:

```text
out/mainos_perky_synth.bin
```

This file is a **synthetic development canary**. It is intended to prove the
Octatrack source seam, complete DSP renderer, X/Y memory layout, table loader,
and stock AMP/FX continuation. It is not yet a claim of PĒRKONS sonic
bit-identity because the current canary tables/control state are fabricated
development fixtures rather than measured v1.2.1 firmware data.

The build script never flashes hardware.
