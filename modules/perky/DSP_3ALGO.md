# Composed reduced Perky DSP machine — implementation record

**Branch:** `perky-dsp-2voice-3algo` (from `perky-optimize`, commit `a522d2f2`).

This is the reduced production target: **two Perky voices total, one per DSP
core, three selectable algorithms each.** It is deliberately smaller than the
superseded twelve-family / four-voice target and it does **not** move synthesis
back to ColdFire.

## Final architecture

| | |
| --- | --- |
| Capable tracks | Octatrack **T1** and **T5** only |
| Core mapping | T1 on payload **B** (its core carries T1–T4); T5 on payload **A** (T5–T8) |
| Voices per core | exactly **one** |
| Algorithms | **Fold Drum 1**, **Resonant Bass**, **Resonant Snare** |
| T2–T4, T6–T8 | ordinary Octatrack tracks |
| FX1 + FX2 | preserved on all eight tracks |
| Wavetable | not used |

The three algorithms reuse the already-qualified renderers. Nothing was
rewritten: `build_dsp_3algo_source.py` composes the *same* bodies the
standalone gates execute, and every state/trigger/mode behaviour is theirs.

## Composition and deduplication

`tools/perky/build_dsp_3algo_source.py` emits one source for both payloads.
Its `measure()` reports the real linked size, never the sum of standalone
probes.

| | P words |
| --- | ---: |
| Fold Drum 1 standalone probe | 1,337 |
| Resonant Bass standalone probe | 2,456 |
| Resonant Snare standalone probe | 2,338 |
| Naive sum | 6,131 |
| **Composed shipping source** | **4,000** |

The 2,131-word difference is measured, not estimated. Deduplication is
*proved*, not assumed:

* the bass and snare resonator/decay cores must canonicalise to
  byte-identical instruction text or the build stops;
* the exact `pk_u32_*` low32 arithmetic, the RNG/noise stream, the hardware
  noise sample-and-hold helper and the shared envelope renderer
  (`pk_noise_hat_envelope`) are emitted once;
* the standalone math dispatcher (`pk_math_probe`), which shipping code never
  calls, is dropped from the resonant tail;
* the Fold/Simple primitive set (`pk_simple_envelope` / `_frequency` /
  `_oscillator` / `_delta_at` / `_base`) is emitted once.

`resonant_dsp.source()` gained a keyword-only `core_variables_fixed` hook so
two families can share one decoder body; with its defaults it reproduces the
standalone probe byte-for-byte, which is why the existing gates still pass.

### How the cores were made shareable

The decoder cores address their temporaries through `r4`. Bass and snare
reached the generator with different variable counts, so the same instruction
sequence carried different displacements. `core_variables_fixed` pins the
twelve temporaries plus `r_input` to a private slot block and moves each
family's own variables above it. A canonical-label comparison then shows the
two bodies are the same machine code, and one copy ships.

## Private X ledger (per core)

| Range | Words | Purpose |
| --- | ---: | --- |
| `X:$3800..$386b` | 108 | the one voice object (largest algorithm is the 101-word snare) |
| `X:$386c..$38e7` | 124 | spare |
| `X:$38e8..$38eb` | 4 | shared RNG stream (two u32 limbs) |
| `X:$38ec` | 1 | source-seam event offset |
| `X:$38ed` | 1 | one-Perky-track-per-core admission latch |
| `X:$3900..$39bb` | 188 | shared render scratch (resonant needs 184) |

The RNG limbs are a **fixed absolute address** owned by the shared helper, not
a register-relative slot. The composer refuses to build if the helper moves
them, because every renderer would silently read a different stream.

## Y ledger

The Fold/Simple bodies carry their table bases as absolute immediates, so
their addresses are fixed by the qualified renderer and the ledger fits around
them:

| Base | Words | Content |
| --- | ---: | --- |
| `Y:$07a5` | 512 | three 256-point Fold/Simple waves |
| `Y:$0c50` | 683 | shape-0 amplitude curve |
| `Y:$0efb` | 68 | packed pitch basis (+padding) |
| `Y:$2000` / `Y:$2280` | 683 / 683 | resonant curve banks 1 and 2 |
| `Y:$2500` / `Y:$2600` | 257 / 257 | resonant interpolation tables A and B |

Total ≈ 3,320 words of the 2,139-word *private* low-Y budget plus the resonant
tables; placement of the resonant banks is the next measurement (see below).

## Status this round

**Done and verified**

* the composed source builds; `4000` P words measured with `dsp_asm` at
  `P:$1000`;
* each retained standalone renderer gate still passes unchanged
  (`verify_perky_fold_drum_exec.py`, `verify_perky_resonant_dsp_exec.py`);
* the deduplication identities are enforced by the builder itself;
* the RNG base and the Fold/Simple table bases are asserted, not assumed.

**Open — the composed execution gate**

`tools/verify/verify_perky_3algo_exec.py` assembles the shipping composition
twice and drives each renderer entry point directly. Its Fold case fails today.

The composition itself is now **proved equivalent** to the qualified standalone
renderers, by measurement:

* every composed renderer body is byte-identical to its standalone counterpart.
  A full structural diff of `pk_fold_voice` (78 instructions) reports **6
  differences, all of them relocated `JSR`/`DO` target addresses**; the same is
  true of `pk_simple_base` (one relocated `JSR` word) and of
  `pk_simple_delta_at`, `pk_simple_envelope`, `pk_simple_frequency` and
  `pk_simple_oscillator`;
* with matched registers, state and tables, the composed and standalone
  binaries return the **same values**: `pk_simple_base` yields `base_lo = 0x8`
  and `cache0 = 0x0` from both, `pk_simple_delta_at` yields `0x594d` from both,
  and `pk_simple_frequency` yields `0x237` / `0x5777` / `0xffffeb` from both;
* the reference model agrees with the capture: `FoldDrum1.from_arm(...).render(16)`
  reproduces `arm-pcm.bin` exactly (`-1, -2, -4, -6, ...`), and
  `cached_base_frequency` is `0x8` for this fixture -- so the ARM capture's
  first samples are *not* generated by a zero base frequency.

That last pair is the crux: the Python model renders the capture from this
state, and the composed renderer's primitives are the model's, yet the rendered
PCM comes back zero. Whatever the remaining difference is, it is **not** in the
renderer bodies and **not** in the primitives -- it is in how the gate drives
them. The concrete next step stays as before: port the standalone gate's host
invocation into the composed gate verbatim and diff the two command lines and
data files argument by argument, rather than re-deriving either by hand.

Two facts found this round and worth keeping:

* the second-difference decoder's cache entry 0 aliases the voice's
  prepared-base word (`x:r4+0 == x:r6+$34` when `r4 = r6 + 0x14`), so a first
  call whose index equals `state[0x34]` takes the cache-hit path. The qualified
  standalone gate seeds `X 3964 = 0xffffff` for that reason;
* `pk_simple_base`'s `r4` is the fixed absolute `0x3964`; it is not
  register-relative, while `r5` (scratch) is the caller's base.

The standalone per-renderer gates stay green, so per-renderer qualification is
unaffected: `verify_perky_fold_drum_exec.py` and
`verify_perky_resonant_dsp_exec.py` both pass unchanged.

## Reproducing

```bash
python3 tools/perky/build_dsp_3algo_source.py --measure
python3 tools/verify/verify_perky_fold_drum_exec.py
python3 tools/verify/verify_perky_resonant_dsp_exec.py --firmware /path/to/perkons.img
python3 tools/verify/verify_perky_3algo_exec.py
```

External inputs (never committed): the user's PĒRKONS v1.2.1 image, the
PerkyBits source tree, the captured ARM fixtures under
`out/perky/engine-fixtures`, and the generated Simple/Fold assets under
`out/perky/simple-drum-assets`.

## Not yet done

1. the composed execution gate above;
2. production control law for the three algorithms on ColdFire
   (`resonant_control_update.py` is the exact v1.2.1 oracle already available);
3. the real linked P/X/Y placement and the actual stock-FX sacrifice measured
   from the composed image;
4. the complete firmware image plus boot/upload/readback gates;
5. reachable-state timing bounds on the composed production path.
