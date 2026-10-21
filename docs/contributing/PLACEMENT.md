# Placement: where a module's code goes, and what is free

The OS is a fixed 1.1 MB block of Elektron's code. A module declares what
it is, not an address; the build decides which bytes land where.

## The two placement classes

| class | declared as | where it lands | budget |
|---|---|---|---|
| **ROM cave** | `CavePatch` (pinned hex, or a `.s` source that is the truth) | one of the OS image's free zero runs; floats after what precedes it unless pinned | ~8.4 KB total, shared by everyone |
| **DRAM unit** | `Linked(..., dram=True)` | linked with every other DRAM unit in the remix as one image, packed, appended after the OS behind octabam's loader, depacked at boot into the platform's arena reserve | the pages the remix claims (MEMORY), off the unit's sample/recorder pool |

Until 6 Oct 2026 there was a third, the appended runtime (`Runtime` + 
`ArenaReserve`): Em's Octakit, built from her recipe and carried as a
payload of the same loader in its own 528 pages of the arena. KITS
(`modules/kits`) replaced it; the class went with it (`git show
2063370f:tools/remix/schema.py`).

A DSP-side class exists for one kind of code (sanderlegit, PR #542):

| class | declared as | where it lands | budget |
|---|---|---|---|
| **Pinned DSP section** | `DspSection(pins=(...), pin_split_label=...)` | fixed P addresses instead of the harvested effect region: the interrupt vectors stock leaves as `jmp *`. One address per piece, cut at one label with a one-word bridge jump, so a section can span two runs and cost the region nothing | ✅ read from the image: payload A 50 dead words (`$02..$0F`, `$1A..$1B`, `$1E..$3F`), payload B 58 (`$02..$0F`, `$14..$3F`) |

Stock's unused vectors are self-jumps: an interrupt that fired there would
spin the core in it for good, so stock never enables them.
`tools/verify/verify_dspvectors.py` checks that on every build (the runs
are all self-jumps; no DMA whose vector is in one has DIE set; no ESAI
control word has an interrupt enable; the set of peripherals either
payload configures is the audited one), and that gate is the licence for
the class. The build refuses to pin over anything that is not still the
stock pattern and asserts that both pieces assemble to the same length at
either origin. The ledger claims the pin by name.

REMIX SWITCH's DSP park is the one user: 31 words at `P:$20..$3E` (entered by
`jsr` at `P:$1E`, host command `$0F`), a one-word bridge, and 8 words at
`P:$06..$0D`. `$02` (stack error) and `$04` (illegal instruction) stay
stock's freeze-traps. ✅ On an MKII, 29 Sep 2026: an image with stock's
fourteen effects and the park wholly in dead vectors booted from a switch,
played, and switched away again, so the chip runs code in the
exception-vector slots and takes the bridge jump between two runs.

The top of P is free and unreachable. ✅ Measured 29 Sep 2026: the core's
default map gives 8K words of P (`0x2000`); payload A's code ends at
`0x01fdf` (33 words spare), payload B's at `0x01d9f` (609). Code is placed
by rewriting words inside the payload's existing load records and no
record covers that space; a new record grows payload A's blob, and payload
B's begins on the byte A's ends, so it would shift B, the
`FUN_40001b18(0x400f59ef)` call site and the boot copy. Stock's low P is
full: A loads all 8,159 words in 66 records, B all 7,583 in 46, with no
holes.

The OS-image edits every class needs (a detour at a stock instruction, a
poke, a grown table) are `Detour`, `Poke`, `TableGrow`, wired by symbol;
stock bytes a module relies on without writing are a `Keep`.
`tools/remix/ledger.py` refuses two modules that claim one byte before
a byte is written.

## The free ROM (measured)

Zero runs inside the OS image (`0x400c0000..0x400d8000` scanned for runs
≥ 64 B). The region above `0x400d8000` reads zero but is the PROJECT
subsystem's RAM and is refused: octalab put a menu table in the 15 KB zero
run at `0x401087e4` and the unit raised `VEC:03` in the menu draw loop
(octalab, 13 Sep 2026).

```
0x400c45b0..0x400c4702     338 B
0x400d24d0..0x400d2ce0   2,064 B
0x400d2ee6..0x400d3020     314 B   (refused at placement by the build, 25 Sep 2026:
                                    a live descriptor, modules/midi-scenes' CAVE2 note)
0x400d64da..0x400d7c3c   5,986 B   (the FX2 chooser's NONE row + terminator sit at
                                    0x400d6b00 in every build; descriptor clones
                                    grow from 0x400d6b20)
```

midi-scenes as a pinned ROM snapshot needed 8,196 of these 8,364 bytes.

## The DRAM (measured under the ColdFire port unless marked)

Measured with `tools/emu/ot_emu`: boot to the RTOS handoff, project load
and 300-2,000 frames of play, `--watch-pc` armed before boot, `--mem-dump`
at exit, the write watch folding the uncached alias.

| range | what | status |
|---|---|---|
| `0x40000000..0x47ffffff` | the cached SDRAM, 128 MB | boot code (ACR0 mask) + hardware |
| `0x48000000..0x4fffffff` | the same memory uncached: `SDCS0 = 0x4000001b` is a 256 MB decode over a 128 MB part (NXP's own example uses `0x1a` for 128 MB); `CACR = 0xa50ce100` has `DDCM_P` (default data mode cache-inhibited) and `ACR0 = 0x4007e020` covers only the lower 128 MB copyback; no MMU | boot code; hardware (Octakit writes through `0x4dd0dde0` and executes at `0x45d0dde0`; mxldyn's canary at `0x47800000` was clobbered by the rings the OS addresses at `0x4f8…`) |
| `0x40a955e0..0x46025de0` | the audio page arena: 14,602 × 6,144 B = 89,720,832 B = 85.56 MiB, Elektron's "85.5 MB" (cold init `0x40096f7a`: count `0x390a`, free-list fill to 14,603, `memset(0x40a955e0, 0x05590800)` at `0x40097006`; the Flex cap is the `0x04000000` literal at `0x40004028`). Octakit took the top 528 pages (until 6 Oct 2026), octamax 2.0 the bottom 64 (base moved to `0x40af55e0`), the platform reserve the bottom pages its remix claims (1,707 in every DRAM remix until 11 Oct 2026; MEMORY) | measured; both authors' placements hardware-proven |
| `0x45d0dde0..0x46025de0` | Octakit's window until 6 Oct 2026 ("reserved recorder pages"). Stock's engine zero-fills exactly this extent at project load, twice; her post-clear relocation re-depacks from a stage the OS never touches | measured |
| `0x46025de0..0x4763d580` | zero-filled at boot by the loop after the boot detour (`0x40000518`); the base of stock's object pool (`pool_init(0x46025de0)` at `0x4002000e`): globals and heap. Not free; its first long is also zeroed by every clear that ends at the arena's top (the stock `memset` writes one long past a length that is a multiple of 16; `docs/firmware/STEM_REC.md` section 19.1) | static |
| `0x47500a10` | an 8,704 B sector bounce buffer just below the rings (`0x4f500a10 − (offset & 511)` at `0x40091f94`) | static |
| `0x47502c10..0x47fc7410` | the stock delay rings, 10.8 MB: eight rings of 1,411,200 B (wrap `cmpil #1411200` at `0x4000359e`) at a stride of 1,411,328 (`addil #1411328` at `0x40003386`; 128 B, one 16-sample frame, of pad); the boot memset at `0x40002fb4` (`lea 0x4f502c10`, 705,664 × 16 B) ends at `0x47fc7410`; the delay frame routine's four `#0x4f502c10` adds. Stock never names `0x47502c10`; every reference is through the alias. Cleared ~38 M instructions after the boot detour returns; live audio memory after that. Not free | static + port + Bryan T's write-up (`docs/firmware/COLDFIRE_DELAY.md`) + mxldyn's hardware. An earlier "8.8 MB free at 0x47700000" was a watch on cached addresses blind to the clear through the alias: retracted |
| `0x47fc7410..0x47fe0000` | 101,360 B between the end of the rings and the 128 KiB Octakit kept below the reset stack (until 6 Oct 2026). Octakit's boot-time stage (72,959 B) at the bottom. Not clean: stock's engine task names four buffers inside it through the alias (`0x4ffc7610`, `0x4ffc9010` sector bounce buffers; `0x4ffcb220`, `0x4ffce230` two arrays of 769 × 16 B descriptors), and with static samples in the project the port fills `0x47fc8fe4..0x47fcd9e4` (18,944 B, 37 sectors, the PIO sector loop `0x40015472..0x4001548e`) at project load, inside her stage from `+0x1bd4`. Nothing seen above `0x47fcd9e4`; no literal names anything above `0x47fd1240` | measured on the port's PIO path; a DMA-capable card and play-time streaming unexercised. Em (12 Sep 2026): the stage is needed on boot only, so the fills after boot are a non-issue for Octakit; whether her wrapper's re-hash at project load (`0x40013304`) tolerates a clobbered stage is unconfirmed |
| `0x46000000..0x47502c10` | ~21 MB outside both big clears | unmeasured; stock's sample pool may live there. Measure with samples loaded and the recorder running before placing anything |
| inside the row above | fixed firmware buffers named by static reads (addresses are the uncached alias; cached = minus `0x08000000`). Sizes unmeasured. `0x4ec94004`/`0x4ec94008`: READ CAPACITY(10) reply, 8 B (`0x4001e350`, `0x4001e35a`). `0x4ec94800`: USB dQH list (`usbaudio_in.s`). `0x4ec94900..`, `0x4ecc8000`, `0x4ecc9000`: EP2 dQHs, dTDs and buffers (`modules/usb-midi/README.md`). `0x4ecb8000`: the USB mass-storage worker's sector buffer (`0x4001eed8`, `STEM_REC.md` section 7.7). `0x4ecd3000`: the buffered file layer's staging buffer (`STEM_REC.md` section 7.5) | static; not placed on |

What the port cannot see: caches (it has none), the recorder, anything
after the handoff, and DMA traffic (the eDMA's descriptors and completions
are modelled but no bytes move, so a region only DMA writes to reads as
never written). The rings are known from the CPU's own memset.

### Em's DRAM (`m68k-elf-nm` on her `runtime.elf`; Octakit, until 6 Oct 2026)

| | range | bytes |
|---|---|---|
| runtime (code + data) | `0x45d0dde0..0x45d32675` | 149,653 |
| code budget (`0x25000`) | ends `0x45d32de0` | 1,899 spare |
| 256 Kits × 6,322 B (`PART_PAYLOAD_SIZE 0x18b2`) | `0x45d32de0..0x45ebdfe0` | 1,618,432 |
| 128 spill payloads (undo, clipboard, rollback) | `..0x45f838e0` | 809,216 |
| descriptors, bitmaps, names, UI rows, undo | `..0x45fb2f42` (`__gk_planned_end`) | ~190,050 |
| slack | `0x45fb2f42..0x4600154b` | 320,009 |
| backup copy of the runtime | `0x4600154b..0x46025de0` | 149,653 |
| her region (`RUNTIME_START..RUNTIME_END`) | `0x45d0dde0..0x46025de0` | 3,244,032 |
| her stage (signature + packed runtime) | `0x47fc7410..0x47fd910f` | 72,959 |

(Sizes as of her ec70dda; ot-26914's runtime is 154,718 B.)

## The platform reserve

Hardware: an image built at origin `9a49f21` (loader at `0x4010fdf0`,
boot site `0x4000050c`, the 10 MiB reserve at `0x40a955e0`, FX2 chooser
rebuilt with 15 rows at `0x400d7bbc`) ran on nordseele's Octatrack MKI on
11 Sep 2026 as octalab: the first hardware run of the DRAM platform, on
the model we cannot test. ❌ Retracted on that run: `FLASHPLAN.md`'s
"MEMORY reports ~75 MB" — the MEMORY page still shows 85.5 MB total while
the Flex list reads FREE MEM 71.4 MB; the page count `0x390a` appears at
18 sites and which one the page reads is unpinned. Their standalone cave
`0x400d64e0..0x400d7bf5` straddles the FX2 chooser's NONE row at
`0x400d6b00`; as a module they claim `LAB_MENU`, 402 B at
`0x400d64e0..0x400d6671`.

octabam's runtime and stage live in pages taken off the bottom of the
audio page arena at `0x40a955e0` (`tools/remix/arena.py`), the way
octamax 2.0 takes its 64. MEMORY (`modules/memory/README.md`) sizes the
reserve per remix from the claims: the linked runtime, its stage and
`.bss`, every DramRegion and every fixed-address ArenaReserve (a fixed
1,707 pages, 10,487,808 B, `0x40a955e0..0x41495de0`, until 11 Oct 2026).
The base literal moves up by that much at its 24 sites (23 direct plus
`lea base+6144` at `0x40094a62`), and the four geometry words (page count,
free-list fill limit, arena clear length, recorder page cap) are computed
from the reservation (`tools/remix/arena.py` stacks any number; until 6
Oct 2026 Octakit's 528 at the top were the other one, and the `octakit`
remix alone yielded exactly her four words `36fa / 36fb / 05278800 /
36fa`). `midi-scenes` yields base `0x41495de0` and 12,895 pages (75 MB)
left. The runtime is linked at the reserve's base; the stage follows it
page-aligned; the ceiling is the reserve's end; a unit's `.bss` must end
below it. KITS's library (1,622,944 B) and PLOCKS P2's table (1,572,864 B)
are `.bss` there.

**REMIX SWITCH's stage** (`modules/remix-switch`) is the top of this reserve,
`0x41200000..0x41495de0`: a 64-byte mailbox, a 40-byte copy stub at
`+0x100`, the staged image from `+0x1000` (2,706,400 B). The running OS
writes it just before a reset and the next boot's OS entry reads it before
anything else runs; nothing between a reset and the OS entry writes SDRAM
outside the image the bootstrap unpacks (`docs/firmware/ARCHITECTURE.md`
section 3a). In a remix carrying the module, `verify_remixswitch` refuses a
runtime and stage that reach the mailbox.

The OS never touches a reservation again: the arena clear starts at the
new base, the boot-time copies follow the literal, and the page allocator
hands out only indexes below the new count. The cost is 10 MB of an
85.5 MB pool, off the recorder share by default.

Measured under the port on the static-sample card (boot → LOAD PROJECT →
400 frames): the `hello-dram` image reproduces the stock run to the count
(6,232 ATA commands, 30,573 sectors read, 292 written, the same five
tracks armed at frame 0, the same 18,005 bytes landing in the old top
window) with 0 writes into the reserve and the runtime read back
identical. The `midi-scenes` image has no stock write into the reserve
(28,700 writes, all from his own code: the MSC table and his state).

Against his 1.40MIDISC, same card, the `hello-dram` control rebuilt
bit-identical:

| image | ATA cmds | sectors read | written | armed at frame 0 |
|---|---|---|---|---|
| `hello-dram` (control) | 6,189 | 30,467 | 297 | 5: tracks 0,1,2,4,7 |
| midi-scenes 1.40MSC | 5,234 | 21,958 | 0 | 3: tracks 0,5,7 |
| midi-scenes 1.40MIDISC | 6,189 | 30,467 | 297 | 3: tracks 0,5,7 |

The card I/O difference was his: `bank_switch` / `bank_invalidate`
preserved only `d0` across a `jsr` that replaced a plain `move.l
d0,(BANK_PTR).l`; 1.40MIDISC saves `d1-d7/a0-a6`. The arming difference
was the port's: its saved-bank watch was keyed on the stock PC of the
`BANK_PTR` store at `0x40087d44`, which his cave makes from its own PC, so
the port played bank 0 pattern 0; with the watch following the detour,
1.40MIDISC5 and 1.40MSCN6 arm the control's five. His hardware symptom
("save on bank 1 reloads clean, others corrupt") is unmeasured here. (A
bisect that landed on `0x40087d44` and a PR to him built on it were
retracted.)

## The loader

`tools/remix/loader.S`, derived from Em's Octakit loader with attribution:
a stub at `0x4010fdf0` (the byte after the OS image) that the boot site's
`jsr 0x40001e50` is redirected into by octabam's three-byte poke. It
replays the boot-continue call, then for each payload in its table: copies
the staged blob (4-byte signature + `GKA3` stream) to its persistent stage
through the uncached alias, hash-gates the packed stream (rolling ×33, the
same function her OS-resident helper computes), checks the `GKA3` header,
depacks with the firmware's own aPLib routine at `0x400e0aca`, hash-gates
the result, and copies a backup if asked. Any mismatch hangs the boot
visibly. octabam's runtime is the one payload today (Octakit's runtime was
another until 6 Oct 2026).

`tools/verify/verify_dram_boot.py` (in `make verify`) boots the built image
under the port and checks that the loader ran once, never hit its hang,
and that every window reads back equal to its linked image except the
bytes a runtime writes about itself.

## Shared sites: the bridges

In the free ROM, SCALE QUANTIZER's 2,916 B unit beside REPITCH's 576 B
leaves CC MAP's 724 B cave no run (measured 28 Sep 2026), so `mods`
carries REPITCH and CC MAP without the quantizer.

A stock site claimed by two mods is refused by the ledger unless a bridge
carries it. A bridge is a stub that does what both hooks did, in an order
that respects each protocol, declared through `schema.Override` so the
build skips the overridden detour.

Until 6 Oct 2026 three bridges carried Octakit's shared sites:
`scenes-kits` (the MIDI CC dispatch entry `0x400d64a0`, CC MAP's cave in
front of her handler), `scenes-p2-kits` (the two page-2 editor entries)
and `kits-reload` (OKMS1 trapped on the first Part Reload: her
replacement of the stock reload validated its caller's return address and
midisc's `reload` stub substitutes it; the ledger carried the class as
`Runtime.pinned_returns` against `Detour.subst_return`). KITS leaves the
stock Part routines and the CC dispatch as stock, so none is needed (`git show 2063370f:modules/kits-reload/README.md`).

## Open

- The reserve is what the remix claims (MEMORY); the ledger refuses
  claims that leave fewer than 2,048 pages. The route that costs no sample memory (a remix with
  the stock DELAY off both choosers detouring its frame routine
  `0x400031a0` so the eight rings are never written, 10.8 MB) is
  unmeasured; whether the routine has duties beyond the delay is the
  question.
- `0x46000000..0x47502c10`: measure with samples loaded and the recorder
  running before placing there.

## PERKY4S shared-program boundary reservation

The [native-clock CF placement measurement](../../modules/perky/hybrid/CF_PLACEMENT_FEASIBILITY.md)
prices all 81 requested algorithm layouts with the existing renderer bodies.
The WT/WT escape route overruns a real combined modeled ISR with four active
stock STATIC tracks and retained FX. CF remainder costs favor investigating
V4 on DSP-A, but removal of CF work is not a replacement DSP memory/cycle
ledger. Neither the private-P recovery below nor the measured CF fallbacks
establish the complete layout.

The [split Noise Hat prototype](../../modules/perky/hybrid/NOISE_HAT_OFFLOAD.md)
places 1,453 words of DSP-A service/kernel code with 584 shared P words free.
Its 4,805-sample ring remains in CF RAM. Exact voice tests pass locally, but
blocking HI08 exchange makes WT/WT + Slap + Hat slower than its same-image
CF control, and the pulse row loses stock post-FX audio. Code/data fit is
measured; complete workload feasibility is rejected for this prototype.

The [cooperative follow-up](../../modules/perky/hybrid/NOISE_HAT_ASYNC.md)
uses byte-identical DSP uploads, with 324 bytes of CF transaction state,
80 bytes of CF coordinator state and 24 bytes of queue/split state. It
finishes the tested requests during other CF rendering without using its
cleanup wait path. All three modes pass source/state and stock audio gates,
but the peak combined ISR is 494.034 us and private-stack use reaches 1,596
of 4,096 bytes. This does not admit a new production placement.

The opt-in [20 October DSP-B specialization experiment](../../modules/perky/hybrid/DSP_B_FEASIBILITY.md)
also tests appended **ordinary private P** records. They remain exclusive to
the addressed core; only records in the physically shared window are unioned
across uploads. B's candidate `0x1d9f..0x2000` tail overlaps A's live stock
program and must never be copied into A's private P. The experiment's 557-word
relocation passes local execution/readback checks, but its paired oscillator
cost exceeds the existing allowance. The default placement and the physical
qualification of the new private boundary remain separate.

The four-engine PERKY profile reserves the last six mapped shared-P words,
0x3fffa..0x3ffff, for explicit NOP uploads on both cores. Executable placement
uses 2398 shared words; the six guard words fill the 2404-word physical tail
capacity. Private P remains 770/774 words per core. Full physical startup-clear
spans remain unchanged; only the four-engine placement solver's usable bound
shrinks. No stock FX or additional donor is removed.

The original R T1 frame ended at 0x3fffe and stalled physical playback at the
first sound trigger. The guarded P4RPG6 image passes the user's reported T1/T5,
all-algorithm, Dark Reverb cases; normal PERKY4S reproduces that MAIN OS exactly.
Instruction prefetch beyond mapped memory is the suspected mechanism, not an
emulated or measured exact fetch depth. The permanent boundary gate rejects
the frozen unsafe R placement. See [the release record](../../modules/perky/PERKY4S_RELEASE.md).

The [resident-state experiment](../../modules/perky/hybrid/NOISE_HAT_RESIDENT.md)
keeps Noise Hat's classic and pulse dynamic histories on A. CF retains control
smoothing, the large ring and rational clock. Commands use the existing T6
source record's padding; native results use otherwise discarded low bytes in
the existing A readback, cleared before stock CF audio processing. It adds no
host command or DMA payload words and no new CF IPL7 reservation. All three 4,096-frame
rows pass source/state, all-track audio and program readback, but peak CF ISR
cost is 380.530 µs versus 362.812 µs available. Added source latency is a
stable 48 samples. The separate full-renderer/rational-clock witness confirms
the delayed source stream; AMP/FX event alignment and the complete voice map
remain unqualified.


The subsequent [current-source tap-DMA prototype](../../modules/perky/hybrid/NOISE_HAT_TAPS.md)
moves Noise Hat delay arithmetic and exact rational resampling to A. CF owns
the 4,805-sample ring and emits five taps per native classic sample; scheduled
readback carries feedback writes only. This removes the additional 48-sample
source queue without adding host commands, DMA words or CF interrupt holds.
A uses 1,940 P words; shared P is 2,308/2,404, A private P 761/774, private X
513/616 and low Y 2,093/2,139. All twelve retained FX remain byte-exact.
The production tap guard refuses 573 or more pending writes; the tested
largest pending count at a read is 52. Current source PCM, state, feedback,
clock and committed ring match the original renderer in all three 4,096-frame
rows. Pulse meets the modeled CF deadline at 358.504 µs with zero misses;
white/metallic still exceed it at 370.841/372.485 µs. This is a bounded local
feasibility result; full all-mode timing and hardware admission remain open.


The [profiled control-settling follow-up](../../modules/perky/hybrid/NOISE_HAT_CONTROLS.md)
keeps that DSP placement and transport byte-identical. Complete CF frame
profiles identify sixteen repeated Noise Hat control derivations as the
avoidable overrun cost (13,987/14,005 cycles on the white/metallic maxima).
Batched exact smoothing retains the penultimate PARAM2 attack input, final
sixteenth derivation and trigger/seventeenth ordering. A full pre/post raw
ColdFire control witness checks the original routine independently. All
three 4,096-frame combined rows meet the 362.812 µs modeled deadline at
324.841/327.299/316.902 µs, with zero misses and no exactness or stock-audio
failures. Same-image unbatched controls separate batching from CF outlining
and layout changes. No additional DSP memory is used; hardware timing,
lifecycle and other family combinations remain unqualified.

The [lifecycle follow-up](../../modules/perky/hybrid/NOISE_HAT_LIFECYCLE.md)
keeps PKNHE1 and its memory placement unchanged. Actual STOP/START, Part 1→3→1
and playing Bank A→B→A preserve the tested continuing source contract across
49,565 source frames, peaking at 327.943 µs with zero modeled misses. All six
directed mode changes pass separately. Three live DSP→CF→DSP round trips fail
with six target transport errors, although their 354.000 µs maximum meets the
budget. Resident state, outstanding ring writes and both clocks need a coherent
ownership handoff; the existing enable toggle supplies none. The dynamic audio
oracle stops at that departure. Stateless CF arithmetic passes independently
but cannot establish migration. Product Part/generation semantics and hardware
qualification remain open; fixed-mode full-workload timing is reproduced.


The [PKNHF7 handoff and CF synthesis experiment](../../modules/perky/hybrid/NOISE_HAT_HANDOFF.md)
resolves the enable-toggle failure in the model and profiles the remaining CF
work. CF WT/WT and Slap plus resident A Hat pass eighteen backend transitions
and both-backend STOP/START, Part and playing Bank changes. The worker mirrors
inner state and the retained native sample without waiting in the audio ISR.
CF resumes with its logical ring cursor, and old DMA writes retire into their
original positions before a 573-sample tap can reach them. Ordered source DMA
imports return ownership to A after dirty limbs and old jobs drain.

A uses 2,023 P words; shared P is 2,381/2,404 and A private P plus startup clear
is 771/774. X/Y residency is unchanged. Both DSP uploads are identical to
PKNHF1; all 2,414 B portfolio words still match PKNHE1. CF text/data/BSS are
1,059,870/580/997,584 bytes: +53,404/+16/+650,812 from PKNHE1, including the
638,976-byte bounded queue. F7 adds 6,056 text bytes over F6 and no data/BSS;
private stack peaks at 1,716/4,096 bytes. The original exact resampler remains
in assembly. The serial Slap delay assembly is unchanged from F6. A typed-int16
classic Hat delay specialization checks every tap/gain word and cursor on every call;
other metadata uses the original C recurrence. The ring remains little-endian; no DMA, latency or interrupt-mask cost is added.
The explicit author-proven PIO first-sector fix remains byte-identical.

All three 16,384-frame workload rows pass with peaks
320.379/324.890/312.102 µs. The worst overall frame is 345.379 µs, leaving
4,602.313 modeled cycles / 17.433 µs. CF calibration is 28 cycles above F6,
while the switching regression is fixed: 339.830→331.110 µs, below F5's
334.356 µs. Panel peaks at 336.489 µs. Both candidate read-only profiles
reproduce normal frame and cycle totals. Persistent Hat exactness and
actual-call Slap PCM, full raw-state/ring and RNG differentials pass. The CF
direct gate covers 96,880 cases including altered-metadata fallbacks. Hardware,
B-tail silicon remain unqualified. That F7 evidence does not qualify production
Part/generation resets; G3 below supplies the scoped local proof. This is not
a flash release.

The subsequent [G3 production reset candidate](../../modules/perky/hybrid/PRODUCTION_LIFECYCLE.md)
integrates staged family-local selectors and real Bank/Part generations.
Resident DSP, CF ring/control/clock and the interruptible shadow reset at the
same event; pending feedback is checked and retired by generation. All-mode
16,384-frame stock/FX rows, CF-only and DSP-enabled lifecycle, and actual
encoder/SAVE PROJECT/cold reload pass exact Hat/Slap audio and timing locally.
Eighteen rapid handoffs with cycling production MODE locks also pass.
Peak 349.439 µs leaves 13.372 µs, versus G2's 4.903 µs (2.7× reserve).
Read-only actual-reset profiles reproduce normal frame/cycle totals exactly
for G2 and G3: the global worst frame occurs 400 frames after the Bank reset.
Boot-derived sparse raw-state restores lower generations 2–5 restoration
from 18,652–18,673 to 7,681–7,709 cycles; worst later reset falls from
350.174 to 301.019 µs. Templates use 6,176 extra BSS bytes with a guarded
dense-initializer fallback. Direct source records, identical zero clearing
and exact reciprocal resampling reduce common CF overhead without changing
synthesis. Linked text/data/BSS is 1,061,870/588/1,138,484 bytes. The A service uses 1,946 P words, shared P uses
2,306/2,404, and private A X uses 564/616 including packed initializer records.
Register preservation and reset/import gates run on the final program.
B-owned code/data and both CF synthesis assembly bodies stay exact to F7;
both complete uploads are identical to G2 (shared P differs from F7).
G2's passing baseline, G1's failed audio/timing admission and F7's continuing-history evidence remain
preserved. This is local WT/WT + Slap + Hat admission; physical timing and V4
alternative source dispatch remain unqualified. No flash release is produced.


### Complete-map PKFM6 candidate

**Subsequent performance screen: FAIL.** Same-instrument replays of the exact
PERKY4S image and reported working one-CF configuration establish an operating
target of 158.212 us steady ISR mean, 166.780 us ISR p99 and 189.298 us total
playback CF work/frame. PKFM6 metallic Hat measures 232.879 / 242.208 / 299.144 us.
All five tested full-workload alternatives exceed the target. The
[budget record](../../modules/perky/hybrid/EMULATOR_BUDGET.md) retains the full
vector, historical overlap and measurement limits. This is a provisional
working-envelope policy; no scalar hardware slowdown or safe voice limit is
established. Nominal deadline passes below are not performance admission.

The subsequent [PKFM11 CF optimization campaign](../../modules/perky/hybrid/CF_BUDGET_OPTIMIZATION.md)
retains this placement and both DSP uploads. WT block sizing, fixed-tap and
Slap filter assembly, sparse controls and a transposed background Hat renderer
reduce metallic ISR/total means to 222.407/281.344 us. All five sustained
alternatives still fail the unchanged working-envelope target. This candidate
is held for further performance work; no physical admission is claimed.

The [PKFM15 state handoff campaign](../../modules/perky/hybrid/STATE_HANDOFF_QUALIFICATION.md)
replaces that continuous CF Hat renderer with a requested coherent DSP snapshot
and interruptible CF catch-up. DSP-A keeps rendering until CF is ready. Its
190-word payload and cursor reuse 191 retired A low-Y wave words at
07a5..0863; envelope/clock tables and the overall low-Y reservation are unchanged.
Snapshot fragments occupy only spare words in the existing 24-halfword
scheduled feedback transfer. Shared custom P is 2,312/2,404 words (92 free),
with no added private-P donor or X allocation. Normal DSP ownership executes
zero CF Hat inner renders or replay jobs. Metallic total CF mean falls to
248.054 us while ISR mean remains 222.128 us; all five full-workload rows
still fail the unchanged performance target. This is not physical admission.

The [PKFM17 CF synthesis/ISR campaign](../../modules/perky/hybrid/CF_SYNTHESIS_QUALIFICATION.md)
retains those DSP uploads byte-for-byte and optimizes CF oscillator arithmetic,
native block handling, control settling, resampling, tap gathering, packet
publication and guarded stock sample-position loops. Actual CF ELF text grows
3,756 bytes; data and BSS sizes are unchanged. There is no new DSP allocation,
DMA word count or source latency. Metallic ISR/total means fall to
210.117/235.939 us. All five sustained rows retain exact original-reference
audio and still fail six of the seven frozen budget ceilings. The worst
Noise/Tone means among these Slap-based rows need a further 28.5% ISR and
23.4% total-CF reduction; no physical performance admission is claimed.

The subsequent [sustained Resonant screen](../../modules/perky/hybrid/RESONANT_WORKLOAD_QUALIFICATION.md)
corrects that campaign's missing dedicated Snare/Bass workload. Eight matched
32,768-block runs use WT/WT, Slap or Resonant, metallic DSP-A Hat or CF Noise/Tone,
four active stock sample tracks and all fourteen FX. Snare/Bass and sequenced
MODE-lock ISR means are 205.566–205.612 us with Hat and 216.536–217.005 us with
Noise/Tone; every row fails six of seven frozen timing ceilings. The prior
selector sweep did not establish these sustained means. Current local Resonant
means are slightly below Slap while peaks are higher, which does not settle the
reported greater Resonant burden on hardware. Firmware, DSP allocation, native
clocks and budget are unchanged. Dedicated sustained Snare, Bass and MODE-lock
rows with actual selection witnesses are required for future four-voice
performance claims; no physical admission is established.

The [PKFM20 remaining-CF campaign](../../modules/perky/hybrid/REMAINING_CF_QUALIFICATION.md)
adds exact twenty-sample Resonant chunks, an authoritative unchanged-control
preparation path after production generation observation, and a 558-byte
assembly replacement for the fixed stock source-mixing block. The latter
preserves all data/MAC ordering and binds its independently executed bytes to
the packaged and booted image. Public preparation remains a real `noinline`
boundary for the frozen source observer. CF text is 577,292 bytes, 4,084 less
than PKFM17; data/BSS and both DSP uploads are unchanged. There is no new DSP
allocation, DMA word count or source latency. Eight matched full workloads
improve Resonant ISR means by 4.526–5.600 us and Slap by 2.764–3.305 us; all
still fail six of seven fixed budget ceilings. Individual peaks do not improve
uniformly. The worst mean remains Slap/CF Noise-Tone at 218.918 us ISR and
244.643 us total CF; this placement remains held for performance work.

The [PKFM21 stock/CF campaign](../../modules/perky/hybrid/STOCK_CF_QUALIFICATION.md)
adds a 974-byte zero-ramp stock DELAY mixer, exact signed interpolation,
bounded packet loops and Slap ring spans. Every executed helper proof is bound
to the final code and actual loader readback. CF text is 578,396 bytes, 1,104
more than PKFM20; data/BSS, both DSP uploads, DMA words and latency are unchanged.
The segment trace frame shrinks 100→80 bytes; Slap's span helper uses 44 extra
private stack bytes locally. The actual selector sweep observes a 1,244-byte
private peak within the existing 4,096-byte capacity. All eight matched full
workloads improve sustained means and peaks, but still fail six of seven
fixed timing ceilings. Worst means remain 214.982 us ISR / 240.727 us total CF
against 158.212/189.298 us targets. Functional and lifecycle gates pass; this
placement remains held for performance work and has no physical admission.

The [full-map record](../../modules/perky/hybrid/FULL_MAP_QUALIFICATION.md)
separates the logical T1/T2/T5/T6 contract from source placement. Both WT voices
and the Fold/Simple/Complex/Resonant/Slap/Karplus/Noise-Tone/Acoustic alternatives
use CF; Noise Hat histories, delay arithmetic and conversion use A, with its
ring/control shadow on CF. Current-frame mixed PCM/Hat segments share the
existing scheduled DMA transport. Shared per-voice RNG and all original engine
histories survive ALGO changes; resets and pending retirement are generation-aware.

Measured assembled custom P is 2,220/2,404 shared words (184 free), with no
private-P donor or upper-tail use. The unused B oscillator portfolio is removed;
B resumes stock source handling. Both Plate and Compressor are restored, bringing
the candidate to all fourteen stock effects. A private X is 564/616 and low Y
2,093/2,139. Upload identity, loaded custom/private program readback and active FX
workloads are separate gates; the compact qualification receipt records their
actual completion and timing.

The card wrapper measures 934,480 bytes. Exact Acoustic PCM moves to a versioned,
CRC-pinned `/PERKYAH.DAT` file (452,124 bytes), read in bounded UI-task chunks.
All source access waits for readiness; repeated boot invalidates that loaded
cookie before clearing the buffers. PK/2 signatures prevent silent reuse of
legacy selector meanings. This is an opt-in final-map candidate. Performance
work against the empirical target is required before its pending physical
MKII acceptance; it has no hardware qualification or silicon timing bound.

Final local PKFM6 qualification passes 160,096 layout-sweep frames and 247,902
mode-corner frames, five 16,384-frame full-workload rows, and a 53,189-frame
production lifecycle capture with 22 handoffs. Exact source/state/RNG/clock and
feedback counters stay zero. The observed maximum is 93,809 cycles / 355.337 µs,
leaving 7.475 µs in the CF264/PIT132 model. That thin ISR reserve is not a physical
WCET bound or 20% whole-CPU margin. The later empirical performance gate fails;
another nominal deadline pass does not supersede that verdict.
