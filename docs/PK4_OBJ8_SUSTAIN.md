# PERKY: object+8 is the sustain threshold (why DECAY did nothing)

## Symptom on the unit (after the silence fix landed)

- The DECAY knob did nothing; every hit rang out.
- Later trigs in a 16-step pattern sounded worse than the first.
- PERKY tracks were ~+20 dB versus a FLEX track, even one driven +12 dB.

All three are one bug: the amplitude envelope never released, so the voice sat
at full scale and each new trig stacked onto the previous one.

## The firmware truth (PĒRKONS v1.2.1, `perkons_both_v1.2.1-0-gbcccfd0.img`)

The M7 image is the second container segment (load `0x08020000`, Thumb).

`common_update` at **0x08024714** ends with, verbatim:

```
0x080247e4  bcf80830   ldrh.w  r3, [ip, #8]      ; r3 = u16(obj + 8)
0x080247e8  a342       cmp     r3, r4            ; r4 = smoothed DECAY word
0x080247ea  8cbf       ite     hi
0x080247ec  0023       movhi   r3, #0
0x080247ee  0123       movls   r3, #1
0x080247f0  8cf87b30   strb.w  r3, [ip, #0x7b]   ; obj[0x7B] = (obj8 <= decay)
```

`obj[0x7B]` is the amplitude envelope's re-trigger/sustain gate. PerkyBits'
`renderEnvelope` (the reference transcription) uses `state[base+7]` — that is
exactly `obj[0x74+7] = obj[0x7B]` — in cases 0, 3 and 4: when it is 1 the
envelope keeps re-attacking and can never enter release; when it is 0 the note
decays normally.

So the DECAY knob only "takes effect" when `obj[0x7B] == 0`, i.e. when
`u16(obj+8) > decay`.

### Where obj+8 comes from

It is **not** written by the engine init. `common_init` at **0x080246ac**
zeroes and seeds `0x38/0x3C/0x58/0x60/0xA8/0x7A/0x7C/0x8C/0x90/0x94/0x96` and
never touches offset 8.

It is set once, by the voice-default pass at **0x0802775c**, whose base is
`0x200001e0` (literal at `0x080279D0`):

```
0x0802776c  4ff47f65   mov.w   r5, #0xff0
0x080277a6  a3f8a850   strh.w  r5, [r3, #0xa8]   ; slot 0 pair
0x080277b6  a3f8a850   strh.w  r5, [r3, #0x16c]  ; -> 0x200001e0+0x16C = 0x2000034C
```

`0x2000034C` is wrapper `0x20000280` + engine offset `0xC4` + 8 — the fold-1
engine object. The same pass also stores `0x3FFF` at `+0x16A`, which lands as
`engine+6 = 0xFF` (velocity 255) and `engine+7 = 0x3F` (note 63), the two
defaults visible in every capture.

### Measured on the real object (PerkyBits runs the real firmware under Unicorn)

`out/perky/engine-fixtures/engine-*-mode-*-corner-*/wrapper-window-*.bin` are
raw RAM snapshots of the firmware's own voice objects.

| engine | u16(engine+8) |
|---|---|
| Fold Drum 1 / 2, Karplus, Noise/Tone, Simple, Rest, Wavetable, Slap, Complex, Acoustic, Noise Hat | **0x0FF0** every case |

and `engine[0x7B]` tracks `(0x0FF0 <= decay)` exactly across the control
corners: 0 at `0x000`/`0x800`, 1 at `0xFFF`.

## The bug in the port

`modules/perky/cf_perky4.c::common_init` (and the three Python oracles) never
wrote offset 8, so the port's engine object had `obj+8 == 0`. The comparison
`0 <= decay` is then always true, so `obj[0x7B]` was stuck at 1 forever: the
envelope re-attacked every sample and never reached release. DECAY inaudible,
trigs stacking into a drone, level pinned at full scale — the exact report.

## Fix

- `cf_perky4.c::common_init`: `w16(s,8,0x0ff0u);`
- `fold_control_update.py::_init_common`, `karplus_control_state.py::fresh_state`,
  `noise_tone_control_update.py::fresh_state`: `p16(...,8,0x0ff0)`
- Re-pinned `tools/verify/verify_perky_cf_qualified_sources.py`; fixtures
  regenerate from the corrected oracle.

## Verification

- `verify_perky_cf_final.py`: PASS — prepared states, control→PCM (196,608
  exact samples per Algo), four-track sequence, long-tail continuity
  (1,179,648 exact samples), p-lock reversion, runtime reset.
- `verify_perky_cf_userpath.py`: PASS with **four trigs per bar** on
  T1/T2/T5/T6 (steps 1/5/9/13 — the previous fixture had one trig per pattern,
  which is why the drone hid).
- Emulator envelope now releases: per-track post-FX2 RMS falls between hits
  where it previously sat at full scale continuously.

## Ruled out (measured, not inferred)

- **Not frame cost.** The init write is outside every render loop.
- **Not the DECAY law.** Measured at the engine: fold-1 decay rate is 44033 at
  DECAY 0 and 1536 at DECAY 127 — the rate was always delivered.
- **Not the rate config.** `env_rate_cfg` already matched helper 0x08028784.
- **Not the stock record header.** That was the earlier, separate silence bug
  (`pk4_encode_stock_segment`).

## Still open

- **Level.** The voice now peaks at ~0.92 FS, which matches the authentic
  firmware PCM (`arm-pcm.bin`, peak 30,187/32,767). In the emulator the FLEX
  control track's chain output is ~0.093 FS for a 0.366 FS source, i.e. the
  chain attenuates FLEX but not PERKY. That is a machine-injection/level
  question, not voice scaling, and needs a decision before a trim is invented.
- **Release frame budget.** `build_cf_final.py` still refuses to emit at the
  frame/2 gate (measured 258.6 µs vs 181.4 µs allowed); the unit itself ran
  283.9 µs in a 362.8 µs frame. Unchanged by this fix.
