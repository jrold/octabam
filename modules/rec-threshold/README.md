# `rec-threshold` — REC THRESHOLD

A recorder TRIG mode that waits for the input: TRACK + REC arms the
recorder, and the take starts by itself when the input gets louder than the
track's threshold. The Digitakt 2's threshold recording, on an Octatrack.

## Using it

1. Hold **FUNC** and press **REC AB** (RECORDING SETUP 1). Turn **TRIG**
   past ONE, ONE2 and HOLD to **THR**.
2. Hold **FUNC** and press **REC CD** (RECORDING SETUP 2). On a THR track
   two cells change:

   | stock | on a THR track | what it is |
   |---|---|---|
   | QREC | **LEV** | the threshold: −60, −56 … −8 (4 dB steps), −6, −4, −2, 0 dB. Saved with the Part, per track. Setting TRIG to THR makes it −40 if it was never set. |
   | QPL | **IN** | the live input level in dB: the loudest of inputs A–D, held ~0.5 s, then falling ~12 dB/s; `---` below −60. Its knob does nothing; QPL is left as it was. |

   Play the source, read IN, set LEV a few dB below it.
3. Arm: hold **TRACK** and press **REC** (or REC alone for the active
   track), with RECORDING SETUP open or closed: stock 1.40C records from
   either page too. Nothing shows that it is armed.
4. The take starts when the input reaches LEV, and ends at RLEN as usual
   (with RLEN MAX, a press stops it). Arm again for the next one.
5. An arm is dropped, without a take, if the track's TRIG is no longer THR
   when the input arrives (edited, or another Part loaded), or if the
   recorder is already recording by then.

- A second press while armed cancels.
- A press while recording stops the take (THR behaves as ONE2 there).
- The start is immediate: QREC is not applied (its byte is LEV).
- On a track not set to THR, nothing changes: RECORDING SETUP 2 shows QREC
  and QPL, and both edit as stock.
- A Part saved with THR loads on stock 1.40C as TRIG HOLD, with its LEV as
  a QREC value.

## How it works

One DRAM unit (`thresh.s`), nine detours, three pokes. The manifest's
docstring lists them with their addresses.

- **The keys.** TRACK + REC reaches `0x400836d8` (a loop over the held
  tracks) and the other REC path `0x40083544`. On an idle recorder (voice
  byte 1, "recorder running", clear) both post the start through
  `0x40005178` without reading TRIG. Under THR the hooks hold that start
  word, `(keys + 0x8000) | 0x10`, and the track's level instead. On a
  running recorder TRIG is decoded, and THR takes ONE2's path; without
  that hook a value of 3 falls to HOLD, whose key release stops the take.
- **The frame interrupt.** At `0x4000ab72`, where the input page index
  advances, while a track is armed or the meter is wanted: the peak
  |sample| of the newest complete input page (the previous page; 64 longs,
  inputs C D A B × 16) is compared with each armed track's level. At or
  over it, if the track's TRIG is still THR and its recorder is idle (voice
  byte 1 clear), the held word goes into the immediate mailbox
  `0x46c7e9fa`, which the dispatcher at `0x4000d2a0` acts on later in the
  same interrupt; the arm is spent either way. (At or over, not over:
  nothing exceeds full scale, so 0 dB could not fire otherwise.)
- **The pages.** TRIG's count 3 → 4 (the editor clamps by it) and the Part
  validator's hard-coded TRIG maximum 2 → 3 (it rewrites anything larger
  on every bank load). RECORDING SETUP 1 draws THR through its own
  formatter; RECORDING SETUP 2's cell loop and editor are hooked for LEV
  and IN; after the editor's store, TRIG becoming THR sets an unset LEV.

## Measured

Under the ColdFire port (`ot_emu`), 11 Oct 2026, on an empty project:

- **The start word.** TRACK 1 + REC AB on an idle stock recorder posts
  `0x9010` and the take arms (LIMIT written at `0x400069d6`, voice byte 1
  → `0xff`); a second press posts `0x1010` and re-arms. `0x9010` written
  straight into the mailbox of an idle recorder arms it; `0x80` and
  `0x1040` are consumed and arm nothing.
- **The page to scan.** Just after the index advances, the page it names
  is the one eDMA fills during the coming frame and still holds the samples
  of 8 frames ago: scanning it started a numbered input's take 120 samples
  late. The page before it starts the take from input sample 10 of the
  onset. A start waits 5 frames (record +16 counts 80 → 0) and the
  recorder reads 5 pages back (record +20 = 80, `0x400075a4`), so the take
  begins at the detection frame. The first ~100 samples of a silence-to-
  full-scale step rise from about half level in the input chain itself:
  a stock take already running when the step arrives shows the same rise.
- **`verify_rec_threshold`** (in `make check`): RECORDING SETUP sets TRIG
  to THR, TRACK 1 + REC AB arms with `0x9010`; tones start at once,
  silence never, silence-then-loud only after the wait with the take from
  input sample 10, a second press cancels, TRIG moved off THR while armed
  spends the arm with no take, TRIG ONE starts at once through stock's
  path and RECORDING SETUP 2 edits QREC and QPL as stock on that track;
  switching to THR sets LEV −40; LEV set through
  RECORDING SETUP 2 keeps a −20 dBFS tone out at −12 dB and a −46 dBFS
  tone out at −40, and starts on a −50 dBFS tone at −60; turning IN never
  writes QPL.

On a unit (Chupitnik's MKII, 11-12 Oct 2026, images THR1 to THR5 flashed
from the card, `CHANGELOG.md`):

- THR shows on RECORDING SETUP; armed with TRACK 1 + REC AB, silence never
  records, the input starts the take, a second press cancels, and a drum
  hit's attack is whole by ear (THR1).
- LEV and IN on RECORDING SETUP 2 work (THR2); IN's hold and fall read
  steadily on music (THR3); THR4, with LEV −60 to 0 and the −40 default,
  reported working.
- THR5, this code: the above again; with LEV at 0 dB an ordinary source
  does not start it (full scale not tried on the unit); armed in silence,
  TRIG moved from THR to ONE, then the input: no take, and the next TRACK
  + REC AB records at once as ONE.
- With RECORDING SETUP 1 or 2 open, stock 1.40C records (TRIG ONE, TRACK 1
  + REC AB and REC AB alone), and so does THR5 (ONE, and THR armed inside
  the page), RLEN 16 and MAX alike (12 Oct). ❌ Retracted: "the REC keys do
  not record while a recording page is open" and "armed inside one, THR
  starts only sometimes", read on THR1, THR3 and THR4 (11 Oct); most
  likely a take still running (inferred; `docs/contributing/FAILURE_MODES.md`).
- The first boot after the first flash ran 1.40C's own BOOTSTRAP UPGRADE.
  The bootstrap an octabam image carries is stock's, byte for byte (the
  entry's helper buffer moved to `0x41495de0`, above the platform reserve).

## Inferred

- That nothing overwrites the mailbox between the crossing and the
  dispatcher in the same interrupt. Falsified by a crossing (`armed`
  cleared) with no LIMIT write after it.
- That the newest complete page on the unit is the one before the index,
  as under the port. Falsified by a hit's attack clipped on the unit where
  a stock take already running keeps it.

## Open

- QREC with THR (a quantised start), other tracks, REC CD, several tracks
  armed at once, an MKI.
- An armed indicator: nothing on screen shows that a track is waiting.
- Two other routines name TRIG values (`0x400828e0`, N/A past 2;
  `0x40068a94`, blank past 2); which screens draw them is not known.
- The port's REC keys differ from the unit's in one way: REC AB alone does
  nothing there (on the unit it records on the active track). TRACK + REC
  with RECORDING SETUP open records there, as on the unit. The gate uses
  TRACK + REC with the page closed.
- An earlier version kept the level in a BRAIN setting. As an Option with
  labels it crashed under the port after RECORDING SETUP and TRACK + REC
  (with every detour removed); as a Number it was clean. Not chased
  further: the level now lives in the Part.

## Thanks

- [Sam Banks](https://github.com/sambanks), octabam's author: the build, the
  hooks and their checks, the ColdFire port this was measured under, and
  RLEN PLEN, whose RECORDING SETUP formatter hook THR's label follows.
- [Bryan T](https://github.com/bryantysinger): the recorder's control path,
  buffers and write path read out of the binary (`docs/firmware/RECORDER.md`).
- [Yves Rosius](https://github.com/yvesrosius): STEM REC's measurement of
  the input pages (`docs/firmware/STEM_REC.md` 18.7), the layout the
  detector reads.
