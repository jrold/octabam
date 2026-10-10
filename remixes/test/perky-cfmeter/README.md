# `perky-cfmeter` — what the Perky frame really costs on the unit

[Perky Machines](../../../modules/perky/README.md) (four ColdFire voices on
T1/T2/T3/T4, as `perky-cf-final`) plus [CF METER](../../../modules/cfmeter/README.md)
on T8's FX2.

## Why

Every local number for the Perky frame is a **model** number:
`verify_perky_cf_realtime_budget.py` and `ot_emu --cf-frame-deadline` both
scale the model's ColdFire cycles by a factor measured on the **stock**
image (126 us model vs 213.5 us on the unit). That gap is uncached traffic —
the delay rings through the alias `0x4f502c10` and the cache-inhibited
shared RAM at `0x80000000`. The Perky renderers live entirely inside `ACR0`
(`0x40a9b230..0x40a9e000`), small state, sequential, so the same factor may
not describe them. This image measures it instead of arguing about it.

## What was given up for it

DIAGNOSTIC ONLY. CF METER needs a DSP insert and takes FILTER's FX2 id
`0x0e`; the insert's words are DARK REV's. Both are absent here and both are
back in `perky-cf-final`. Neither runs on the ColdFire, so neither affects
the measurement. The Perky spec's "all fourteen stock FX" is a property of
the release profile, not of this probe.

## Procedure

**Both halves are needed.** The Perky tracks are what is being measured; if
they are not selected and running, the meter measures the stock frame again.

1. Flash `out/OCTATRACK_OS1.40C_<VER>.syx` (or the card image), power-cycle.
2. Load a project. Set **T1/T2/T3/T4 to the PERKY machine** (the chooser lists
   it) and put a **trig** on each — a trig on step 1 is enough — so the voices
   render every frame.
3. On **T8**: **FX2 = CF Meter**, T8 LEVEL high (say 100). The meter's insert
   replaces T8's post-FX2 audio, so T8's output *is* the readout.
4. Press **PLAY**.
5. **Record T8's audio.** Best: a recorder buffer with **source = T8**, saved
   to the card — the Perky tracks then play normally, which they must. (The
   OT's MAIN OUT into an interface also works, but then T1/T2/T3/T4 have to be
   out of the mix, and the ratio must not be contaminated.) Keep it
   **stereo**: the readout is a square wave whose L/R amplitude ratio is
   N / 8192, so the ratio carries the number and any level that does not clip
   is fine.
6. Decode it:

   ```
   python tools/harness/cfmeter.py capture.wav --lr 0,1
   ```

   (`--lr` is the 0-based pair in the file — `0,1` for a stereo MAIN capture,
   the default `14,15` for a USB AUDIO capture of T8.)

The eight slots cycle once per second, in this order:

| k | meaning |
|---|---|
| 0 | 0 (sync) |
| 1 | 8192 (the reference) |
| 2 | idle time (0 without CF METER IDLE) |
| 3 | **frame interrupt, mean duration** |
| 4 | **frame interrupt, longest** |
| 5 | **frame period** — the rate check: it must read ~362.8 us |
| 6 | the idle loop's shortest step |
| 7 | BURN |

The decoder prints microseconds directly. **Slot 3 against slot 5 is the whole
question**: the firmware is safe while the interrupt fits inside the frame,
and the margin is the answer.

⚠️ The panel is NOT a usable readout: a page-2 knob carries only bits 16-23
of the lane word (`docs/firmware/PARAM_PAGES.md` section 6), i.e. the low byte
of the 16-bit meter value — so the display shows N mod 256 and nothing else.
Use the audio.

## Notes

- The stock reference is already known: image 92, Sam's MKII, 3 Oct 2026,
  T8 FX2 = CF Meter on a fresh project read **213.5 us** playing of a
  362.8 us frame. Perky with four voices is the number to compare against it.
- Perky renders inside the frame interrupt, so CF METER's window contains it.
- Not a release artifact: it never passes `verify_perky_cf_final.py`'s
  stock-DSP identity requirement, and it is not meant to.
