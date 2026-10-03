# perky-probe

Development-only milestone for the PERKY source-machine port.

This test remix intentionally turns **every FLEX track** into a timing probe.
The ColdFire callback keeps FLEX's native record-span accounting, writes a
compact `PK / Y1 / trig` record into the stock per-track transport slot, and
the DSP hook at the Analog-BD-qualified source seam emits one +0.5 impulse at
the stock event offset. The source renderer is then skipped and processing
resumes through the normal AMP -> FX1 -> FX2 chain.

## What a successful hardware test proves

1. the ColdFire source callback replacement runs on both ping buffers;
2. the fixed per-track transport record reaches the correct DSP/core;
3. the DSP hook is at the correct source seam on payload A and B;
4. the stock event offset in X:$20c lines up with the track trig;
5. skipping the stock FLEX source still leaves AMP, FX1 and FX2 alive.

It does **not** prove the PERKY machine chooser or Noise/Tone synthesis yet.
Those are the next layers after this canary passes.

Because FLEX itself is replaced in this remix, do not use it as a general
Octabam image. It exists only to make the first source-path result unambiguous.
