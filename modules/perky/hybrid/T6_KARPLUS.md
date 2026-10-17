# PERKY hybrid: T6 dedicated Karplus

Branch: `perky-cf-dsp-hybrid`  
Candidate build tag: `PKHK6A` (distinct from PKH4O2 / PKH5P1).

## Assignment

- **T1/T5 (DSP):** unchanged Fold 1 / Fold 2 / Simple / Complex.
- **T2 (ColdFire instance 0):** Wavetable V1, Wavetable V2, Resonant
  (Snare, Bass, original shared Noise/Tone M3).
- **T6 (ColdFire instance 1):** Karplus only, with all three original Karplus modes.
- **T3/T4/T7/T8:** stock Octatrack playback/FX/sequencing unchanged.

Karplus uses the existing original-renderer port `cf_karplus.c` and the original
`karplus_init` / `prepare_karp` control laws in `cf_perky4.c`.
Karplus MODE: panel M1 -> firmware mode 1; M2 -> 0; M3 -> 2.
T6 exposes a single ALGO choice. Values 1/2 left in previously saved T6
patterns are clamped to Karplus; **old T6 Wavetable/Resonant patches change
meaning**. T2 assignments and saved T2 algorithm indices are unchanged.

T2's existing heavy-CF state remains one 1,984-byte voice. The 4,320-byte
Karplus ring/state and its separate control/RNG/pristine template are used
only by T6; a second WT/Resonant state allocation is not retained.

## State of qualification

This is a **source implementation**, not a tested MKII firmware and not a claim
that Karplus is necessarily faster on physical ColdFire. Ring-buffer accesses,
bus/cache stalls and the known seven-track UI freeze remain hardware unknowns.
Do not flash an unqualified build. Keep the current rollback image.

To build and run the updated primary gates in the existing local checkout,
with user-supplied OS/assets and toolchains already present:

```sh
WORK=out/perky/hybrid/t6-karplus
mkdir -p "$WORK"
# Link $WORK/baseline to the existing approved baseline/reproduction if absent.
.venv/bin/python3 tools/perky/build_cf_dsp_hybrid.py --work "$WORK"
.venv/bin/python3 tools/verify/verify_perky_hybrid_probe_gates.py --work "$WORK"
.venv/bin/python3 tools/verify/verify_perky_hybrid_cold_safety.py \
  --probe "$WORK/probe" --out "$WORK/COLD.json"
.venv/bin/python3 tools/verify/verify_perky_hybrid_runtime.py --work "$WORK"
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_packages.py \
  --probe "$WORK/probe" --out "$WORK/package-check"
```

The earlier full-pair campaign assumes identical selectable CF algorithms on
both instances; its old 25-row receipts are **historical**. The dedicated
workload matrix now uses T2 old algorithms versus T6 Karplus M1/M2/M3.
Run its real sequencer, STATIC, FX and stress gates before considering
a physical install. Private-stack proofs tied to earlier ELF/source hashes
must be regenerated for this build; do not reuse PKH5P1 certificates.

No original STATIC/FLEX, card I/O, stock sequencer, original DSP producer or
stock effects source was changed. Do not trigger GitHub CI.
