# `repitch-repeat98-kyoti` -- REPITCH_REPEAT98_KYOTI

Tempo-locked varispeed for STATIC and FLEX tracks, as three TSTR positions after the four stock ones: **RPCH** (the basic Repitch), **RPS9** (an S900/S950-style repitch emulation) and **RPSP** (an SP-1200-style repitch emulation, as its raw outputs 7/8). On a repitch track the PTCH knob becomes **QUAN**, one detent per ratio.

Credit: Jannik Aßfalg ([repeat98](https://github.com/repeat98)) wrote the basic Repitch (`modules/repitch`). Zac Kyoti wrote the S900/S950 and SP-1200 repitch emulations and the Quantizer.

Built from [Zac-Kyoti/octatrack-kyoti-fw](https://github.com/Zac-Kyoti/octatrack-kyoti-fw)
(submodule `upstream/`, pinned to `329b801`). `Kind.HYBRID`. Three DRAM units (`Linked(dram=True)`), 14 `jmp` detours, 7 symbol refs, 5 pokes, and a DSP section reached from two hooks: the voice kernel's prologue, and each payload's one-time memory clear at boot, which copies the tables into Y outside every audio pass (the test remix gives up SPRING REV only: its P run holds the code, 412 words, its own X data the two table blocks, 81 + 384 words). A remix with this module carries the platform loader and its 10 MiB arena reserve, unless another DRAM module already brings them.
`upstream/octabam-modules/repitch-repeat98-kyoti/README.md` is the full description, with what was measured and what was inferred.

## Measured

- Every build re-links `rpk_logic` and `rpk_glyphs` at the author's own addresses and compares them with the standalone image's bytes (`reference`); a difference refuses the build. `rpk_reload` names symbols in `rpk_logic`, so it has no reference of its own.
- `make check REMIX=repitch-repeat98-kyoti` (`remixes/test/repitch-repeat98-kyoti/`) builds and boots the image under the ColdFire port.

## On the unit

- 5 Oct 2026, on the author's MKI, in an octabam image with every KYOTI module, REC_TRIG_MUTE and SIDECHAIN_COMPRESSOR, only SPRING REV given up: RPCH follows the project tempo and PTCH reads QUAN, one ratio per detent; RPS9 and RPSP at several tempos, no clicks at trig starts; RPS9/RPSP on T5-T8 while a SIDECHAIN compressor ducks on that core; TSTR restored by a Part reload; DARK REV, DJ EQ and the other modules unaffected.
- 6-8 Oct 2026, rev 17 (the RPSP kernel reworked: the mid (L + R)/2 through the SP path, the side clean and delay-aligned; the table copy at boot), same image set: RPSP on all four tracks of one core with DARK REV on each runs clean on both cores; adding DJ EQ on FX1 track by track, T1-T4 pass four and T5-T8 three -- a fourth on T5-T8 overloads the DSP (a loud tone, the sequencer stops). Those images had an output filter on the SP mid; the shipped build is raw (outputs 7/8), the same kernel minus the filter.
- Before that: the standalone image (rev 16) and the KYOTI V1.0 combined image, on the author's MKI.

## Notes

- Not with `REPITCH`: both grow the same Repitch (the same detour sites and TSTR words). The module declares the conflict.
- TSTR uses stock's 5-position select at `0x40046ab4`, which nothing in stock 1.40C references, patched in place to seven positions.
