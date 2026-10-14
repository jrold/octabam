# perky-hookdebug

> **ARCHIVED EXPERIMENT — NOT THE CURRENT PERKY FIRMWARE.** This README
> documents the original **source-hook debugging probe**, including historical results and
> instructions for *that specific image*. The working MKII release is
> **PERKY4S** (T1/T5, Fold1/Fold2/Simple/Complex on DSP, 12 retained FX).
> Read the [current PERKY status](../../modules/perky/README.md) before building or flashing.
> Do **not** treat older "flash next" instructions here as current guidance.

**A debug image, not an instrument.** It renders nothing and puts no Perky
machine on any track.

It exists to answer one question about the hardware wedge: *does the source hook
itself stop the sequencer?* It carries the source hook, its site, its admission
test and its two continuations, and nothing else.

See `remix.py` for what each outcome means when flashed.
