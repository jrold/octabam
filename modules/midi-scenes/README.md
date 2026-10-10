# `midi-scenes` — MIDI SCENES

MIDI-driven scene locks, built from
[bkkbrls-del/midisc](https://github.com/bkkbrls-del/midisc) (submodule
`upstream/` at his `4f9a894`, MIDISC2.0; the units linked here are his
`gas/*.s`, which are the 1.40MIDISC8.2 code, unchanged by 2.0 -- see
"MIDISC2.0" below). `Kind.CF_PATCH`: twelve linker-placed
units in DRAM, 38 detours, four pokes. No DSP code, no menu row.

Stock 1.40C has no per-scene parameter lock over MIDI: XF morph reads one live
8×30 lock table that only the panel writes. midisc adds a second, addressable
table (`MSC`, `scene<<8 | track<<5 | flat`, 4 KB) and rewires scene hold, XF
morph, part save/reload and the scene clear/copy/paste rows to read and write
it when a MIDI event is driving. The panel path is untouched. His README
(`upstream/README.md`) is the behaviour list.

Not carried: his MIDI → CONTROL CC48/55/56 tick rows (UI-table pokes, not a
cave; off in his own builds since 8.1); CCs behave as stock in an octabam
image. His `voice_reload` cave has no caller since 8.2 and is not linked.

## Measured

- Under the ColdFire port: the boot detour reaches the loader, the loader's
  hash gates pass, the window reads back equal to the linked image except his
  own state words, i.e. his code ran from DRAM during boot. Arms the control
  fixture's five tracks.
- The submodule pin is his `main` at `4f9a894` (MIDISC2.0, 1 Oct 2026).
  The pin moved from `63ca127` (his PR #6: 8.2 `8cba0fa` plus the two gas
  commits) on 4 Oct 2026 and the `midi-scenes` image is bit-identical
  across the move (`OCTABAM_NO_CACHE=1 make bus REMIX=midi-scenes`, sha256
  `abe21844…` both sides): 2.0 touched no `gas/*.s`. The 1.40MIDISC8
  `gas_port.py` (region table checked against his image) regenerates them,
  linking `cc_gate` only while his CONTROL filter is on, as his `build.py`
  does. His `build.py` at `8cba0fa` stops at `SAFE_CAVE overrun 2068`
  (`SAFE_CAVE_END` allows 2060): the 8.2 `xf_mix` probe adds 12 bytes. The
  linked units are unaffected (DRAM).
- His own `1.40MIDISC8` image fails project load under the port: his CAVE2
  (`0x400d2ee6`, 308 bytes) overruns the enable words (`0x400d3014/18`) of a
  stock descriptor at `0x400d2e8a` that the loader reads; stock also writes
  `0x400d2e84..89`, where his VOICE_RELOAD_CAVE starts. This build links
  every unit into DRAM and is immune. Told him.

## MIDISC2.0, not carried

His 2.0 release (`4f9a894`) is `tools/midisc/release20.json`: 843 writes
(7,604 B) applied to a hash-checked stock MAIN, "source: MIDISC8.20", from
what his TECH.md calls the hardware MIDI-scenes line. The Python encoder
and `gas/*.s` in the same tree are the 8.2 code; TECH.md says the JSON is
authoritative for 2.0. No 2.0 source is published. Measured here, 4 Oct
2026, against our stock image (his `stock_sha256` is ours, and applying the
writes reproduces his `main_sha256`):

- 7,196 B in 750 writes land in stock filler: ten ROM caves,
  `0x400c45cb..0x400c47a4`, `0x400d24eb..0x400d2cd8`,
  `0x400d35ad..0x400d3644`, `0x400d46ee..0x400d479e`,
  `0x400d64e0..0x400d7c48` (four clusters) and `0x400e1ed1..0x400e1ff6`.
  Octabam places code and state in five of those ranges
  (`docs/contributing/PLACEMENT.md`: `0x400c4702`, `0x400d24f0`,
  `0x400d64e0`, `0x400d6b00`, `0x400d7000..0x400d7100`, `0x400d7bbc`,
  `0x400d7c3c`).
- 408 B in 93 writes land in live code. 41 of this module's 42 sites are
  among them; the post-plock rebuild site `0x4009d1de` is not (dropped or
  moved). 51 writes are at sites this module has no detour for: 23 of them
  change the `0x40a955e0` literal to `0x40aa7500` and the arena counts
  `0x390a`/`0x390b` to `0x38fe`/`0x38ff` (14,602 -> 14,590 pages), i.e. 2.0
  takes 12 pages at the bottom of the audio page arena, where the platform
  reserve sits (PLACEMENT.md "The platform reserve"); the rest are new
  hooks (`0x4004abc0`, `0x40062219`, `0x40087eac`, `0x4009faaa`,
  `0x4009fe4e`, `0x400a169a`, `0x400a19da`, `0x400a1d32`, `0x400a3c2a`,
  `0x400a44f4`, `0x400a4ba0`) and two displacement edits (`0x40097009`,
  `0x40097128`).

A port of 2.0 needs his 8.20 sources (or a `gas_port.py` regeneration from
them): the units must relocate into the DRAM runtime and his arena pages
into the platform reserve. His 2.0 image has not been run under the port.

## On the unit

✅ 14 Sep 2026 as `OKMS1` (remix `ok-ms`, with Octakit), confirmed working
by him on his own unit.

## Open

- His freeze twin and sparse blob (Part `+0x1712..+0x1832`) are the
  LFO designer records of audio and MIDI tracks 2–8 (measured under the
  port, 10 Oct 2026; `docs/firmware/PARTS.md` section 9,
  `docs/contributing/FAILURE_MODES.md`).
- The apply_part entry (`0x40009094`) stays stock since his 1.40MSCN6 (his
  earlier wrapper hung project load on hardware). Beside KITS (since 6 Oct
  2026) his Part save and reload hooks run on the stock routines; a LOAD
  KIT calls the stock reload directly, so his post-reload restore does not
  run for it (not measured).
- His MIDI CONTROL tick rows, if wanted, need a menu-table mechanism.

## Gates

- `tools/verify/verify_midiscenes.py` (in `make verify`): every region
  assembles and links to his encoder's bytes at his addresses, and the
  committed `gas/*.s` are what `gas_port.py` regenerates.

## How it is built

His caves are written in his Python encoder (`upstream/tools/ot3_asm.py`) and placed
at fixed addresses by his `build.py`. His `upstream/tools/gas_port.py` drives the same
builders with an encoder subclass that records one GNU-as line per
instruction, writes `gas/*.s`, then assembles and links every region at his
address and compares. Cross-cave references are linker symbols, so octabam
places each unit where it chooses: every unit is `dram=True`, linked into the
platform runtime, appended behind octabam's loader and depacked at boot into
the arena reserve (`docs/contributing/PLACEMENT.md`). Inside the OS the module
changes only the detour and poke sites, plus the boot redirect when no other
module supplies it.
