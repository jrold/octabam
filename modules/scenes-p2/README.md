# `scenes-p2` — SCENES P2

Scene locks and the crossfader for page 2 of FX1 and FX2. `Kind.CF_PATCH`:
one DRAM unit, nine detours, nothing on the DSP.

## Measured

Under the port, 26 Sep 2026 (`tools/verify/verify_scenesp2.py`):

- bamsep26 and rig-kits (Octakit): pool `{scene 0: MODE 1, TIME 100;
  scene 1: TIME 20}` on T1 (BusDelay), fader 64: T1's record carries MODE 1
  and TIME 60 in both pings, the predicted lerp exactly; fader 0: MODE 0
  (the knob), TIME 20. Scene A disabled: the A side is ignored (the fixture
  project has it off).
- The FX2 editor called with scene A held: the pool and its SRAM twin gain
  one entry, the Part byte and the live lane do not move; with a seeded
  entry the same entry is updated, count 1; with FUNC held the entry is
  removed. Under rig-kits the held call returns cleanly and the pool lands
  in the Part DB's current bank.
- Scene copy fills the clip; paste into another scene adds the clip's
  entry under it; clear drops the scene's entries; the undo snapshot fills
  the undo clip and a write from the undo buffer restores it.

## On the unit

- Anything on hardware beyond being carried by image 88 (pre-fix), not
  exercised there.

## Open

- The dial hook (a draw; the port's LCD was not driven to the page).
- Whether SAVE KIT saves after page-2 lock edits alone.
- The undo row's writer is inferred to be `0x40025b40(0x460bf218, ...)`
  from the paste row's shape; the write hook was exercised with that call.

- A knob PRESS with a scene held toggles the page-1 lock of that knob
  (stock, `0x40053a68`); page 2 has FUNC+turn to
  remove a lock instead.
- The pool holds 47 locks a part.

- **Pool store order.** The frame pass (inside the frame ISR) walks the
  pool without a lock. `pappend` writes the entry's three bytes (track,
  slot, value) and then the count; `premove` moves the tail down and then
  drops the count. An ISR between two stores sees the old count, a whole
  new entry, or a duplicated entry; it does not see an unwritten one. The
  order is by reading the code; the port is lock-step and cannot interleave
  the ISR with the task, so it is not measured on the port or the unit. The
  store order is checked under the port with `--watch-mem`.

## Gates

- `tools/verify/verify_scenesp2.py`.

## What stock does

The frame builder morphs one scene block a track per frame into the DSP
frame: 32 bytes a track a scene, byte *k* the lock for frame halfword *k*,
bytes 0..29 = page 1 of PLAYBACK, LFO, AMP, FX1, FX2, bytes 30..31 skipped.
Page 2 (slots 6..11) has no byte and the loop stops at halfword 17
(`docs/firmware/MIDI.md` Appendix C). Fader position `0x460d16c8`
(0..127) rebuilds a weight table `0x80003c60` (a long per track, hi word
`-xf*258`, Q15): `xf = 127` is scene A, `xf = 0` scene B.

## Why not stock's scene block

Widening stock's scene block to page 2 means changing all of these
together (`docs/firmware/MIDI.md` Appendix C):

1. Block size: 0x20 bytes/track/scene in the project (`0x8f3e2` stride, 24 code
   sites incl. copy/paste/undo at `0x40025b40`, `0x400274cc`, `0x400275a0`).
2. Working copy `0x80000ed4`: 0x40/track, 32 pairs, all fillers assume 32.
3. Frame-builder extents: `moveq #6` (page block) and `moveq #9` (voice
   record) at `0x4000ccb6/0x4000cd0e`, `0x4000cd96/0x4000cdea`,
   `0x4000ce5e/0x4000cee8`; skip at `0x4000cef6`. Halfwords 24..26 are 7 longs
   past where the record pass stops.
4. The scene editor's slot→byte map (`0x40053a2c` region) and the two
   encoder-hook descriptors at `P+0x12a` that call the STRT/LEN morph.
5. The arithmetic itself, to leave the low byte alone.

Two spare bytes per track could host **one** extra halfword, not three, and
the DSP-side companion packing would still be lost at every intermediate
position.

## What this adds

- **The pool.** Each Part window carries 144 bytes at `+0x90522`: `u16`
  magic `P2`, `u8` count, then 3-byte entries `scene<<3 | track`,
  `fx1<<3 | slot2`, `value`; 47 at most. The window is copied whole by
  Part Save, Part Reload and Project Save (`docs/firmware/STORAGE.md` section 3)
  and by KITS's Kit loads and saves (whole Parts), so the pool travels
  with the part. midisc's MIDI-track lock blob lives at the same offset:
  `Claims.part_window` makes the ledger refuse the pair.
  Stock keeps the LFO designs of MIDI tracks 2–8 in these bytes
  (`docs/firmware/PARTS.md` section 9, measured under the port 10 Oct
  2026).
- **The frame pass** (`frame_hook`, at the join after the stock morph,
  `0x4000cf40`). Per track: the current key `(bank, part, scene A, scene
  B)` (bank/part from `0x8000182a[t]` / `0x80001832[t]`, the selectors from
  the part) is compared with a cache row; on a change the track's locks are
  unpacked from the pool (A and B values per slot, `0xff` = none). Every
  locked slot is then written into the voice record's page-2 bytes (FX2
  halfwords 24..26 = bytes 48..53, FX1 18..20 = 36..41): `(A*wA + B*wB +
  0x4000) >> 15`, an unlocked side taking the knob byte the copier left in
  the record; a select (descriptor count < 128) snaps, the A side from
  `wA >= 0x4000`. A disabled scene (`0x80000006` / `0x80000007`) counts as
  unlocked; both disabled skips the track, as stock does. Cost with no
  locks: about 15 instructions a track a frame.
- **The editors.** Both page-2 editors (FX2 `0x4003a9dc`, FX1
  `0x4003abe4`) are detoured at entry. With a scene held (`0x460d169c`: 1 =
  A, else B) a turn on slots 6..11 edits the held scene's lock: the slot's
  own encoder hook and clamp (descriptor `+0x12a`, `+0x6a`, `+0x9a`) from
  the lock's value, or the Part's byte when unlocked; the pool in the
  working window and its SRAM twin (`0x100a4ece + part*0x18b2`); the stock
  scene editor's dirty marks; the slot's redraw flag. With FUNC held the
  turn removes the lock. No scene held: on to the stock body with the entry
  state untouched.
- **Scene copy / paste / clear / undo.** A copy (`0x400274cc`) snapshots
  the scene's entries beside the stock clipboard; the undo snapshot
  (`0x400275a0`) does the same for its buffer; a scene write
  (`0x40025b40(src, part, scene)`: paste, undo) drops the target scene's
  entries and adds the clip's when `src` is the stock clipboard
  (`0x460c8122`) or the undo buffer (`0x460bf218`); the clear writer
  (`0x40038c30(scene)`) drops them.
- **The dial.** The page-2 knob draw reads the Part byte at `0x40037840`
  (FX2) and `0x40037bdc` (FX1); with a scene held it shows that scene's
  lock instead, as the page-1 dials do. With PLOCKS P2 in the remix and
  no scene held, trigs held show the first held step's page-2 lock
  (`plk_dial`).

## Octakit (until 6 Oct 2026)

Her recipe replaced both page-2 editor entries with wrappers that opened a
kit-write token, called the stock body and validated at a marker inside
it; `modules/scenes-p2-kits` overrode her two writes so this unit's stubs
sat at the entries in front of her wrappers. KITS leaves the editors
stock, so `P2_NEXT2` / `P2_NEXT1` are always the stock bodies.

The entry detours displace eight bytes (`lea` + `movem`), and `fx2_stock`
/ `fx1_stock` continue at entry+8 where the stock `moveal %sp@(32),%a2`
still stands. Until 28 Sep 2026 they displaced twelve and the build
nopped that instruction: under Octakit's trampoline the body ran with a
garbage slot in a2 and her marker check halted the unit on every page-2
knob turn (rig-kits, bottleservice; measured under the port; image 88
carried it and the halt was not reported from the unit).
