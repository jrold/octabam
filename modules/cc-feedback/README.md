# `cc-feedback` — CC FEEDBACK

The OT transmits a CC for every live knob byte that changes, whatever
changed it, so a controller's encoders (a BCR2000's LED rings) follow the
unit. Stock transmits a page-1 knob's CC on a panel turn only; after a
pattern or part change, a project load, MODE DEFAULTS, an incoming CC or a
page-2 knob turn the controller shows stale values.

`Kind.CF_PATCH`: one DRAM unit (`cc_feedback.s`) and one jmp detour. The
sweep compares the PART's knob bytes with the stock emitter's cache (page
1: the machine's PLAYBACK block `+0x8edaa + t·30 + machine·6` and the
LFO·AMP·FX1·FX2 array `+0x8ee9a + t·24`; page 2: `+0x8f07e`/`+0x8f084 +
t·30`), not the live lane: locks, slides and scenes rewrite the lane every
step and never the Part. Paced: one message per UI tick (120 Hz, `PACE`
in `cc_feedback.s`), so a bank or pattern change with a different Kit
reaches the controller over about three seconds instead of one burst —
on image A2 (4 Oct 2026) the unpaced dump of the new Part locked a
BCR2000 up the moment the bank changed.

## Measured

- Unicorn (`verify_ccfeedback`, the fixture image, the unit linked at a
  test address): eight sweeps enter the emitter 336 times with the Part's
  values; cache, dirty bitmap (exactly the 42 CCs per channel), channel
  mask and the INTFRCH force as the table above; eight more sweeps emit
  nothing; one changed byte is one message; unmapped Part bytes, every
  live-lane byte rewritten (a lock step), AUDIO CC OUT without EXT and a
  track with its channel off emit nothing; the LFO block goes out as CC
  28..33 and AMP as 22..27; PLAYBACK page 1 follows the track's machine
  block; a MIDI track on the channel is refused by the emitter; the first sweep emits
  exactly one message and the next carries on with the track's next slot.
- The port (`verify_set`, bottleservice and usb-audio on OCTABAM89_setgate
  bank 3, before the engine gate): the load's part dumped as 281 CC
  messages, 582 bytes with running status, on all eight channels; UART0's
  transmit interrupt (vector 0x5a) acknowledged once per message; after
  the transport start 9 messages in 900 frames (the eight CCs the gate
  sends in, echoed, and a MODE DEFAULTS neighbour): no step-rate
  transmission on that project.
- The port (`verify_set`, bottleservice, 28 Sep 2026): 277 CCs queued by
  the sweep left UART0 as 573 bytes with running status; the transmit
  interrupt (0x5a) was acknowledged once per message, the soft-timer
  dispatcher (0x62) 35 times over the load. `ot_emu --midi-out FILE`
  writes the bytes.
- The port, the acceptance stress fixture (bottleservice, 900 frames):
  469 CCs; at the end channel 7's bitmap held 15 CCs with the busy flag
  set -- T7's part changed late in the run, the sweep queued the new
  values (the cache equalled the lane where the lane had stopped) and the
  batch timer had not fired yet. `verify_set` therefore checks the
  emitter's cache against the Part's knob bytes (the module's contract;
  the lane until 4 Oct 2026) for every slot the paced sweep has reached
  when the engine is idle at the end, counts the remainder still to come,
  and checks the wire for shape: every CC sent is a mapped slot on a
  track's channel.

## On the unit

- Images 88–A1 (27 Sep – 4 Oct 2026, the lane-watching sweep): a
  BCR2000's rings followed the unit. On 4 Oct, a Midihub capture of the
  OT's output on a pattern whose T1 lane bytes 8 (LFO SPD3) and 14 (AMP
  REL) flipped between two values every step: four CCs per step, 60 a
  second, until the BCR locked up — and each went out twice, as CC 24/30
  and as 30/24: the map had the page-1 array's AMP and LFO blocks the
  wrong way round (lane 6..11 is LFO, 12..17 AMP; `docs/firmware/MIDI.md`
  section 3). Both fixed the same day: the sweep reads the Part, the map
  follows the firmware's numbering. Whether those lane flips were locks
  or two writers disagreeing (a CC-written value against the sequencer's
  per-step refresh from the Part) is open; the Part-based sweep reports
  neither.
- Image A2 (4 Oct 2026, the Part-based sweep, unpaced): no stream while
  B1 played untouched (a Midihub export held only the knob turns, CC 22
  and CC 46), and the BCR2000 died the moment the bank changed — the
  dump of the new Part, up to 336 messages in about a second. Paced to
  one per tick the same day (image A3).
- DIN bandwidth for a full dump of eight tracks is 344 messages, about
  one second at 31.25 kbaud without running status; paced, about three.

## Open

- What rewrote T1's lane bytes 8 and 14 at step rate on a fresh project's
  B1 (4 Oct 2026): locks, or a CC-written lane value against the
  sequencer's refresh from the Part (`0x4000c19c`). The lane is the knob
  store the frame builder copies; the lock arrays are
  `0x80001538`/`0x80001658` (`docs/firmware/MIDI.md` section 3).
- LEVEL (CC 46), AMP VOL as CC 25 outside the AMP page, MUTE/SOLO (49/50)
  and the crossfader (48) are not in the map: their state is not in the
  lane.

## Gates

- `tools/verify/verify_ccfeedback.py` (Unicorn), the manifest's gate.
- `verify_set` reads the port's MIDI OUT bytes when the module is in the
  remix.

## The stock emitter (`0x40033e3c`, disassembled)

`EMIT(track, cc, value)`, stack arguments. Gated on AUDIO CC OUT
(`0x8000004a`) bit 1; bit 0 is INT (the panel crossfader path tests it
before applying the move). Track 8 means the current track. For a track
0..7 the channel is `0x8000003f + track` (−1 = off, returns) and a MIDI
track on the same channel (`0x46c76de0 + 68·i`, byte = ch+1) returns. Then:

| write | address | what |
|---|---|---|
| value byte | `0x46c7bf2c + channel·128 + cc` | the last value queued for that CC |
| bit `cc` | `0x46c7d7d8 + channel·16` (four longs) | the channel's dirty CCs |
| bit `channel` | `0x46c7e0de` | channels with dirty CCs |
| bit 2 | INTFRCH `0xfc048010`, when `0x46c7ca34` is 0 | forces source 34, the soft-timer dispatcher `0x400409f4`, which drains the bitmap to UART0 |

The drainer sends every pending CC of every dirty channel into the UART
ring in one batch, then sets `0x46c7ca34` = 1 and re-arms DTIM2 for that
batch's wire time (`bytes × 0x400a763e[rate]`); the flag clears on a drain
that found nothing. The wire is paced to MIDI bandwidth by stock; a burst
of changes goes out in batches and a value that changes twice inside one
batch is sent once (`docs/firmware/MIDI.md` appendix D).

A repeated CC coalesces in the bitmap. Stock callers: 28 `jsr` sites; the
page-1 knob path at `0x400552f0` (current track, CC `10 + 6·page + slot`,
the clamped value) and the panel crossfader as CC 48 are the two traced.

## What this unit does

`cf_tick` is a jmp detour on the keyrepeat task's loop at `0x4005595c`,
which pends on the UI tick event (`0x46c7e0e2`, signalled by DTIM1's
handler at 120 Hz). Each pass calls `cf_sweep` before the pend: one track
(round robin), its live lane `0x80000810 + track·72` compared byte for
byte against the emitter's cache for the track's channel:

| lane bytes | CC | page |
|---|---|---|
| 0..29 | 16..45 | page 1: PLAYBACK 16-21, AMP 22-27, LFO 28-33, FX1 34-39, FX2 40-45 |
| +0x32..0x37 | 68..73 | FX1 page 2 (CC MAP's numbering) |
| +0x38..0x3d | 62..67 | FX2 page 2 (CC MAP's numbering) |

A byte that differs goes through `EMIT`, which updates the cache itself.
Stock's knob echo goes through the same cache, so a panel turn is sent
once. The sweep skips when AUDIO CC OUT bit 1 is clear or the track's
channel is off; a channel shared with a MIDI track is refused inside
`EMIT` on every call (42 refused calls per sweep of that track). Every
track is covered every 8 ticks (67 ms). PLAYBACK and AMP page 2 have no
CC numbers and are not sent.

The sweep waits while the engine task runs a command. The engine's queue
is `0x460d17ce` (count +4, event flag +8, waiting TCB +0xc): the kernel's
event wait (`0x40000818`) parks the engine's TCB at +0xc while it is
blocked for a command and the post (`0x40000c3c`) clears it, so a
non-zero word there is "the engine is idle". A project load, a bank or
part change transmits nothing until it has settled, as stock does. This
gate was added after the first port run: 272 UART interrupts inside LOAD
PROJECT re-ordered `sys` against the engine and tripped Octakit's
part-byte lifecycle check (`gk_lifecycle_activation_publication_report_fatal`,
the ATA-latency ordering `tools/emu/README.md` records); the same image
loaded at `--ata-latency 32`, and the `rig` test remix (bottleservice without Octakit) loaded at the
default.

## Wiring a BCR2000

OT MIDI OUT to the BCR's MIDI IN, BCR OUT A to OT MIDI IN. The BCR's
encoders in `absolute` mode take an incoming CC on their channel and move
the LED ring (`tools/hw/bcr2000.py`). Whether the BCR's
mode S-4 merges MIDI IN into OUT A is not checked; if it does, every echo
returns to the OT as a redundant CC write of the same value.
