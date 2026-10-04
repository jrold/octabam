# PERKY full Noise/Tone machine canary

This is the first development image that combines all current PERKY layers:

- virtual PERKY source-machine row on top of FLEX;
- persisted `PK/1` Part signature;
- `TUNE / DECAY / ENV / MIX / MODE` source page;
- Noise/Tone engine browser entry (`011 NOISE/TONE`);
- generated ColdFire control runtime from `modules/perky/control.c`;
- sample-accurate PK/Y1 source transport;
- complete packed Noise/Tone DSP renderer on both cores;
- 236-word X initializer at `X:$3800`;
- packed wave/envelope payload at `Y:$0795`;
- one shared Octabam loader carrying both the ColdFire runtime and the two
  extended DSP uploads.

The tracked `PERKY PROBE` manifest remains the small impulse diagnostic. This
full machine is assembled by an in-memory module upgrade and never replaces the
fallback canary on disk.

## Build

```sh
python3 tools/perky/build_machine_canary.py
```

Output:

```text
out/mainos_perky_machine.bin
```

The builder has five visible phases and aborts on the first failed invariant:

1. synthetic qualification assets;
2. generated DSP + ColdFire sources;
3. normal Octabam build of the full machine/runtime;
4. replacement of that image's loader append with one carrying the same
   runtime plus PERKY's A/B preboot DSP uploads;
5. final image summary.

The shared-loader repacker refuses extra normal platform payloads, verifies the
runtime bytes reproduce the original loader's `blob0.bin`, checks the PERKY
preboot destination/stage ranges against the runtime, `.bss`, and runtime stage,
and preserves the existing boot JSR at the fixed Octabam loader address.

## Status

This is a **synthetic development canary**. The waves, envelope curves and
prepared control state currently come from the explicitly fabricated test
fixture. They exercise the exact packed runtime ABI and complete synth path but
are not presented as measurements from PĒRKONS v1.2.1 firmware.

The build script does **not** flash hardware.

Before any hardware recommendation, the next gates are the full machine UI /
Part-persistence / source-record port checks and then hardware qualification.
