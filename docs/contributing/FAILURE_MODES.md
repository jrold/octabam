# Hardware failure modes: the register

Symptom → cause (measured, inferred or open) → fix. Add an entry the moment
a mode is seen on hardware.

Each entry's full investigation: `git show 666b6154:docs/remixer/FAILURE_MODES.md`.

## PERKY was SILENT on the unit and in the port: the record header's count byte ✅ measured, fixed (10 Oct 2026)

- **Seen:** Perky selected on T1/T2/T5/T6 with trigs, the CF rendering (the frame interrupt grows by 186.8 us over a stock baseline of 97.1 us, measured with CF METER, `out/perky-cfmeter`), the record in the slot correct -- and no sound on the unit and none in the port.
- **Cause (measured):** the published source record's first header long carries the segment's sample count in its LOW byte as well as above it: a stock FLEX record's header long 4 is `0x00001010` for a 16-sample segment (16 above, 16 below). This encoder wrote only `n << 8` = `0x00001000`, because its shape was taken from ANALOG BD, which writes a magic word (`0xab090000`) in that long instead of a stock header. With the low byte zero the stock chain played nothing: the per-track post-FX2 **read-back** was **zero** for the Perky tracks while the stock FLEX tracks on the same run were full audio.
- **Why every gate missed it for a whole session:** they all checked the RECORD -- the bytes the ColdFire publishes -- and never the chain's output. The record was perfect (147,866 significant samples, 32,510 distinct) and the track was silent. `tools/verify/verify_perky_cf_userpath.py` now also requires the per-track read-back (`require_readback`) and runs the emulator WITHOUT `--dsp-dirty` (a dirtied DSP seeds the read-back, which hides exactly this).
- **Fix:** `d[0] = (n << 8) | n` in `cf_perky4.c`'s `pk4_encode_stock_segment`. One line. All four voices then produce real chain output (peak 4.2-7.8 M, 12k-32k distinct samples), and the full qualification, both user-path gates and the wrapper round-trip pass.
- **Ruled out on the way (each changed the chain output not at all):** making the source read position match stock (`d[1] = k<<4`, `d[3] = k<<30`); trimming the published PCM by 12 dB; and the frame budget (the meter shows 283.9 us of a 362.8 us frame). Copying a stock FLEX record byte-for-byte into a Perky slot DID sound, which is what proved the delivery, slot and routing were fine and the contents were the whole problem.

## PERKY: briefly sounds, then the sequencer stalls ✅ the ColdFire outruns its frame 🔴 open on the unit

- **Seen:** the CF-only Perky Machines images (PK4DIAG2 silent, PK4TONE1 "faint pop at the trig, then no audio and the sequencer will not advance"). Same family as PERKY1/PERKY2.
- **Cause (measured in the model):** the ColdFire's per-16-sample-frame work does not fit the 362.8 us frame. `tools/verify/verify_perky_cf_realtime_budget.py` prices it at 260.6 us/frame of MODEL cycles against the 181.4 us the gate allows (frame / 2). The vendored core prices each instruction with cache hits and zero-wait-state operand accesses, and the project's own hardware reading (`modules/cfmeter/README.md`: the stock frame prices at 126 us in the model against 213.5 us on the unit, image 92, Sam's MKII) says that is ~1.7x low -- so the unit's real cost is ~443 us/frame: the frame never completes before the DSP's next boundary and the exchange desynchronises.
- **Why the lock-step port could not see it:** ot_emu's whole machine, DSP included, is slaved to the ColdFire's instruction stream, so the ColdFire can never be "late" -- a slow frame is absorbed (the frame edge is a latch and the missed edges are dropped). Measured 9 Oct 2026: the production image renders four independent PERKY records for 12000 frames, no fault, even at `--ips 800`.
- **The firmware's own overrun paths (read from the image, 9 Oct 2026):** the frame handler at `0x4000aad0` reads the DSP's bank id with no ready check (`0x4000aafa  movew 0x2000001c,%d0`, sign-extended into `0x800000e0`) and then **halts if it is not 0 or 1** (`0x4000ab38  cmpl #1,0x800000e0 / bccs / 0x4000ab40 halt`). That is the fatal path O9b saw with a free-running frame timer, and it is the one an overrun would reach. There is also a re-entrancy guard (`0x46104d4e`, set `0x4000ab32`, cleared `0x4000d9a0`) whose entry test `0x4000aae0 tstl / beq / 0x4000aae8 halt` looks like the overrun detector -- but it is UNREACHABLE: the frame source is priority 5 (`0xfc048041` written at `0x4001fc30`) and the handler lowers SR to `0x2500` (mask 5, `0x4000aeca`), so the source cannot preempt its own handler. Measured under the port: with the overrun edge delivered, every frame ack still sees the guard clear, and no halt follows.
- **Neither fatal path is reachable by a late frame ✅ measured 9 Oct 2026.** The bank-id read is not stale either: `OT_DEADLINE_TRACE=1` shows the read (pc `0x4000ab00`, i.e. `0x4000aafa`) returning 0 or 1 in **every** frame, with the DSP's RX FIFO empty right after each take -- the port is host-paced in both directions (the ColdFire's reads drive `DspPair::catchUp`, and the DSP's frame loop waits for the host take at `P:0x97`), so the two sides cannot drift. That holds even with the overrun delivered every frame. The only other reads of `0x2000001c` are the boot's DSP-upload handshake (pc `0x40001ba6`, values 0-2) and these are not range-checked. So the halt O9b saw came from a *free-running* timer putting a second, out-of-phase edge inside one DSP frame -- a modelling artefact, not the overrun's consequence.
- **What is left:** the ColdFire simply falls behind (one frame's work costing more than one frame period, every frame), so the sequencer position, advanced per ColdFire frame, stops tracking the audio clock. `ot_emu --cf-cycles-clock 1.7` now expresses that: the audio clock is driven by the ColdFire's cycles instead of the fitted `1/--ips` per instruction, so the frame period really is 16 samples of 96,505 cycles and the ColdFire can be late. Measured 9 Oct 2026, 400 frames: the Perky image's frames take **22.5 samples** each against the 16-sample frame, the stock image's 18.9 -- a **3.6-sample (~22 %) gap**, which is the Perky synthesis cost and agrees with the budget gate's 22 % over. The stock side is 18.9 rather than 16 because the model's DSP pacing (`--dsp-ips`) adds its own constant, so only the DELTA is trustworthy; a genuinely independent DSP clock means `--dsp-rt`, which still cannot start on native Windows (see `tools/emu/README.md`, the `--dsp-rt` bullet: the vendored MMU helper's reservation blocks the shared-window alias).
- **Fix:** open, and the first pass is in (9 Oct 2026): two bit-exact invariant hoists (`cf_fold.c`'s pitch term, `cf_karplus.c`'s filter coefficients) took the frame 260.6 -> 256.2 us. That is the honest size of this class of change -- the renderers' cost is the arithmetic plus the byte-wise state traffic, not recomputed invariants; `-O2` and dropping `-funroll-loops` are both worse. The one big lever left is typed state access, which needs the state base provably 4-aligned (a ColdFire address errors otherwise) and is worth maybe another 8-10%.
- **⚠️ THE 1.7 CALIBRATION IS A STOCK NUMBER AND MAY NOT APPLY TO THE RENDERERS.** It comes from cache-inhibited traffic: `CACR`'s `DDCM_P` plus an `ACR0` that covers only `0x40000000..0x47ffffff`, so the delay rings (through the uncached alias `0x4f502c10`) and the shared RAM (`0x80000000`) are the expensive part of the stock frame. The Perky renderers live entirely inside `ACR0` (`0x40a9b230..0x40a9e000`, state small and sequential), so their real cost should be close to the model's. Re-pricing only the uncached pieces puts the frame at ~360 us against a 362.8 us frame -- **right at the limit**, not 22% over, which fits "briefly sounds then stalls" better than either extreme. One reading of the `cfmeter` module in a PERKY build settles it.
- **Check:** `ot_emu --cf-frame-deadline 1.7 --dsp --sequencer ...` reports the overrun live ("the frame handler was still in its exchange 390.3 us after the frame began") and delivers the late edge; the stock image reports none under the same flag, and `--cf-frame-deadline 1.0` (the model at face value) reports none either -- which is exactly the blindness this entry is about. `OT_DEADLINE_TRACE=1` prints the per-frame guard/mask state.

## Three Perky machines on a unit: stutter, audio cut-out, then the transport sits on step 1 ✅ measured in the model, 10 Oct 2026

- **Seen:** Sam's unit, 10 Oct 2026, image PK4AH2 (all twelve algorithms, the
  card-size fix). Two Perky machines played; **adding a third** made the
  sequence stutter and the audio cut out. Stopping and playing again left the
  trig lit on step 1 with no playback. The project was saved and handed over
  as `PRESETS MKII/PROJECT 261010`.
- **The project, read back:** bank A part 1 has exactly three Perky machines --
  **T1 (FLEX slot 129 = R1), T3 (131 = R3), T4 (132 = R4)**; everything else on
  the part is STATIC. The pattern is intact (T1 steps 1/7/11, T3 steps
  5/8/11/13, T4 step 8), so nothing was lost on save; the trig LEDs lighting
  with no playback is a *transport* state, not an empty pattern.
- **Cause (measured in the model): the ColdFire's frame handler overruns the
  362.8 us frame once the Perky voices trig.** Same project, only the number of
  Perky machines changed, run under the unit's own deadline
  (`ot_emu --cf-frame-deadline 1.7 --sequencer --dsp --dsp-dirty 123`):

  | Perky machines | overrun |
  |---|---|
  | 0 (stock tracks only) | none |
  | 1 (T1) | none |
  | 2 (T1, T3) | **404.7 us late** |
  | 3 (T1, T3, T4) | **375.1 us late** |

  and the average frame cost rises with each machine:
  `--cf-frame-budget-us` 120.5 -> 151.2 -> 195.7 -> 221.3 us/frame of 362.8.
- **It is the EVENT frames, not the per-frame rendering ✅ measured.** The same
  three machines with every trig mask erased: **no overrun**. So the frames
  that overrun are the ones carrying a trig -- the first-event engine creation,
  the control settle (16-18 smoother passes) and the trigger, all inside the
  audio callback.
- **Why the symptom is a permanent stall and not just dropouts:** an overrun
  desynchronises the CF/DSP exchange, and the frame handler at `0x4000aad0`
  reads the DSP bank id with no ready check and **halts if it is not 0 or 1**
  (`0x4000ab38`). "The firmare halted ... its own frame-handler guard" is the
  path the emulator prints as `cf stall`; it did not trip in these runs (the
  port is host-paced, see the entry above), so the model shows the *cause* and
  the unit shows the *hang*.
- **Confidence:** the model says the frame does not fit; the project's own
  calibration for that model (x1.7) is a STOCK number and the entry above warns
  it may not apply to the renderers, whose state is cached. One `cfmeter`
  reading from a PERKY build settles the real per-frame cost.
- **Fix:** open, and it is the frame-cost work, not the algorithms: every
  engine's hand-off in this table is still bit-exact against the firmware. The
  next lever is the event frame -- hoisting the one-time engine creation and
  the control settle out of the audio callback -- plus the typed state access
  named in the entry above.
- **Check:** `C:\temp4495\perky-deepseek-20261009-072423\octabam\work\budget_variants.py`
  (3->2->1->0 machines, budget and deadline modes) and
  `work/notrigs.py` (the no-trig control).

## Pops and clicks from T1 with BusDelay when T1 plays its own trigs 🔴 open
- **Seen:** Discord, Arcdmd_, 29 Sep 2026. Image, unit model, T1's machine and trig pattern not stated.
- **Cause:** open. The rig is tested with T1 and T5 as THRU tracks without trigs. The one earlier test with a trig on every T1 step (21 Sep 2026) gave clicks and no wash. A trig splits the host's block into two dispatcher calls; the delay's glides run on the first call only since 21 Sep 2026 (`modules/busdelay/README.md`).
- **Fix:** open. To find out: the reporter's image, machine and trig pattern; whether the clicks land on T1's trigs; whether they follow the delay (FX2 = SEND on T1, same trigs) or the machine (a THRU host with a trig every step clicks from the THRU's re-open); the same test on T5 with BusVerb.

## Every FX1/FX2 page-2 knob turn halts under Octakit with SCENES P2 (bottleservice) ✅ measured under the port

- **Seen:** under the port, 28 Sep 2026. Image 88 carried the twelve-byte build; the halt was not reported from the unit.
- **Cause (measured):** SCENES P2's entry detours at `0x4003a9dc` / `0x4003abe4` displaced twelve bytes and nopped the third stock instruction (`moveal %sp@(32),%a2`, the slot argument). Octakit's trampoline replays eight bytes and continues at entry+8, so a2 held a stale code address, the body took its slot>5 exit, and `validate_result` reported corrupt: `illegal` at `gk_track_setup_byte_fatal` (`0x45d28e98` in bottleservice's runtime). kits (Octakit alone) takes the same turn.
- **Fix:** the detours displace eight bytes (`pad_to=8`), the stubs continue at entry+8 (`modules/scenes-p2`), 28 Sep 2026.
- **Check:** `verify_modedefaults` and `verify_scenesp2` run their editor calls under bottleservice (Octakit SKIPs removed).

## Junk on main R for one frame, from T1 with BusDelay, about twice a minute ✅ measured, fixed (image 43)

- **Seen:** images 32-38, 25 Sep 2026. BusDelay on T1 (STATIC, hard left): 16-24 samples of random full-scale words on main R about 0.5/min, at one phase of the 4-second pattern cycle.
- **Cause (measured):** core 1's frame start reads core 0's bank word (`P:0x57-0x7a`, payload B), picks the read-back buffer (`X:$2600` or `X:$4600`, `X:$206`) and patches the host handlers' masks (`P:$371`/`P:$380`): one read-back buffer per frame, and the ColdFire's pull (DMA channel 1, armed at `P:0x37c`) must finish before the first FX2 copy overwrites it. The ISR pulls core 0, the ESAI, then core 1; on the unit core 1's pull reaches T1's 64 words ~4.5 samples after T1's proc entry (the port models +0.26), jittering with pattern position. BusDelay on core 1 copied inside the pull. A NOP burn after the loop: +0 cycles 1266 runs/min, +256 16/min, +512 1.4/min over 10 min.
- **Fix:** image 43 (branch `padfix`): 8,192 NOPs (two samples, 11 % of the frame) after the loop, before the rts. 10-minute take: 0 junk (baseline 5). Costs two samples of core 1's budget every frame. Polling DSR1 / DCR1.DE (images 37, 38) and a frame-end detour (images 39-42, PR #405: core 1 wedged at project load; the idle at `P:0x57` is the last instruction of `do #16`, a word-by-word handshake with core 0) did not work.
- **Check:** `tools/harness/burst_census.py` on a `tools/rec` take (built from `tools/hw/rec.swift`); only 10-minute takes count (a 90 s take shows nothing 47 % of the time at 0.5/min).

## A white-noise wash from a sample host with trigs on it ✅ measured, fixed (image 43)

- **Seen:** Sam's MKII, 21 Sep 2026, images 39-42. BusDelay on T3 STATIC with a trig every step washes from the second pass; T2 THRU with a trig every step at once. LEVEL 0 silences it; FDBK, WET and STOP do not remove it; PLAY or a reload clears it until the next full loop. T1 as host: clicks, no wash. The port shows nothing (lock-step cores).
- **Cause (🟡 inferred):** each bus participant rebuilt the second call's frame offset from a flag and split stashed by the first call in its block (`$65/$66`). If the stash does not survive a trig between the two calls, the second call runs as a first: at position 0 the rotation tracker advances twice and keeps a lead of one. The stash was never measured on the unit.
- **Fix:** image 43: the offset comes from `r0` (0 on a first call, 2 × split on the second; the port: `r0 = $e` for a trig at frame 7), in SEND, BusDelay and BusVerb. Measured: T3 STATIC with a trig every step clean through eight loops and a reload. PR #344's init stores (removed in 42), the `$84..$88` relocation (#346) and once-per-block glides (#345) were not the cause.

## Sequencer stuck on step 1 at the first play: images 44 and 45 🟡 two causes inferred, fix built (image 46)

- **Seen:** images 44 and 45, 21 Sep 2026: flash, load, play, stuck on step 1; power-cycle and reload recover.
- **Cause (🟡 inferred):** (1) image 44's housekeeper stamp clear used one-word displaced Y stores (`move a,y:(r3+$1)`), a form with no stock site; image 45 used `move a,y:(r3)+` and wedged the same way, so the form was not (or not only) it. (2) The tracker's check read the client's last write offset from its slot as an address; an FX1 NONE slot runs SEND at an r7 below `$6200`, which ROTINIT never seeds, so on the unit the read went to a wild Y address (peripheral registers live in Y). The port zeroes RAM.
- **Fix:** image 46 masks the value (`and #>$30`) before it becomes an address.
- **Check:** the gate chain runs the port with `--dsp-dirty` on the trig-host fixtures.
- **Lesson:** no address from a word init did not seed, unmasked. A DSP form with no stock precedent in `tools/build/dsp_disasm_all.py` output does not ship without a hardware probe.

## A white-noise wash from a THRU host past position 0 with a trig every step; bleed into the bus with every SEND at 0 🟡 lead measured (image 47), cause inferred, fix built (images 48, 49)

- **Seen:** BusDelay on T2 THRU with a trig every step, images 40-43 and 46; on 46 audio also reached the bus with every SEND at 0. T1 as host: clicks, no wash. The port (`verify_set`, `out/OCTABAM89_t2thru`) shows nothing.
- **Cause:** ✅ image 47 (a marker-tone probe): the core-1 tracker sits one step ahead permanently on plain play. 🟡 Inferred (`modules/send/README.md` "An FX1 slot is not a client"): FX1 NONE is id 0 = SEND, which ran on every empty FX1 slot at r7 0x6100/0x6400/0x6700/0x6a00 (measured, PC watch). The 0x6100 call sent from an unseen page byte (the bleed) and, on core 1, ran the tracker compare before position 0's advance; a flip landing before it leaves `T == R + 1` for good. Under the port the flip lands late in core 1's frame every frame.
- **Fix:** image 48: SEND returns at proc entry on an FX1 r7; the self-check removed. Image 49 (structural): eight accumulator and chain buffers, a server reads three back, the housekeeper clears two on, a core-1 client counts its own blocks from a seed read at init, checked against the rotation with a tolerance of one (`modules/send/README.md`). Costs one more block (48 samples) of latency.
- **Check:** the port's two-core gate is bit-identical to the one-core control under every skew. Falsified by any wash or static on 49 that a host position, trig pattern or load changes.

## Audio engine wedged, sequencer alive: the master loop ✅ measured

- **Seen:** 5-6 Sep 2026 (tag-93 rig). Sequencer runs, no audio, sample preview silent, record meters B/C/D lit. Distinct from the DSP hang (sequencer frozen).
- **Cause (measured 6 Sep 2026):** T8's station (Character, return role) sent into the reverb bus it returns: T8 FX1 -VRB at 71 in bank02's parts; turning it to 0 brought audio back. Why the loop reads as silence is not established.
- **Fix:** stations have no sends; SEND is refused at track 8's dispatch position on payload A whatever its knob. The refusal outlived the T8 return (20 Sep 2026): with MASTER TRACK on, T8's input includes the hosts' wet.
- **Check:** `tools/verify/verify_onebus.py`.

## The audio engine wedges with only BusVerb + the return 🔴 open (the return removed 20 Sep 2026)

- **Seen:** image 94, 13 Sep 2026, `tools/hw/ot_soak.py`: T5 FX2 = BusVerb, T8 FX1 = Character as return. Output drops to the noise floor while the transport runs; a transport restart recovers.
- **Cause:** open. 3-minute soaks: return alone clean; BusVerb with return at 0 clean twice; BusVerb + return at 127 silent at 131.5 s once, clean on a repeat and on a 9-minute run. Rate ~one freeze in 15 minutes. Not the cycle wall.
- **Fix:** open. Next: soak `BusVerb + return` against `BusDelay + return` for tens of minutes each.

## BusDelay silent with its knobs locked: the MODE formatter wrote over the minimum table ✅ measured

- **Seen:** OCTABAM86. No delay; TONE, PING and MIX pinned and immovable; cleared by a reboot, back when page 2 was drawn.
- **Cause (measured, emulator write watch, 13 Sep 2026):** `tools/build/mode_names.py` wrote renames at `P + 0x4e + 6·slot` where the names live at `E + 0x4e` and `P = E + 0x38`, landing in the minimum-value table (`P + 0x6a + 4·slot`): GRAIN's names set `min[3..5]` to 0x4d444550 / 0x4d524154. Character's SAT view and Modulation's COMB view had the same fault.
- **Fix:** `NAMES_AT = 0x16` (P-relative); the project re-stamped from the manifests (OCTABAM87) measured clean on the ladder.
- **Check:** `verify_modenames` reads the names from the corrected offset (it had read back from the same wrong one).
- **Lesson:** an autocorrelation of the mix that "measured TIME inert" was reading the material's own eighth and quarter (248 / 496 ms at 121 BPM) and is retracted; measure a delay time from the repeats' spacing after the source stops.

## CC MAP (CC PAGE 2 until 25 Sep 2026) did not write on hardware ✅ fixed (image 96)

- **Seen:** CC 62-67 changed nothing on the panel, stopped or running.
- **Cause (measured):** the cave used the PLAYBACK page-2 editor's stores (`0x4003a474`), corrupting the track's PLAYBACK page-2 byte. The FX2 editor's stores are Part `+0x8f084`, shadow `0x100a51d2`, lane +0x38.
- **Fix:** the cave uses the FX2 stores; image 96: CC 63 on channel 5 moved SHMR and raised the tail's 2-8 kHz bands 5-8 dB. Every page-2 sweep taken over the old cave is void.
- **Check:** `verify_ccmap` proves the write against the FX2 editor.

## BusDelay's SEND knob drew TIME's division labels ✅ measured

- **Seen:** on the unit, 15 Sep 2026: the first knob printed `1/8`-style labels.
- **Cause (measured):** `modules/tempo-sync` registered the TIME formatter on slot 0; TIME has been slot 1 since the one-aux re-slot (7 Sep 2026). The published value was the knob's.
- **Fix:** registered on slot 1. The same day the knob became `SEND` on every track (was `AUX`), and the engines' `MIX` became an add-only `WET` (the crossfade had faded the delay out; measured on an impulse, 15 Sep 2026).

## A generated project shows as modified and RELOAD refuses ✅ measured

- **Seen:** a project written by `tools/hw` loads marked modified; RELOAD PROJECT does nothing.
- **Cause (measured):** the saved state is the `.strd` twin of every `.work` file; the tools wrote `.work` only.
- **Fix:** `ot_project.py stored <project>` writes the twins; `rigproj` and `delaytest` write them. A SAVE PROJECT on the unit does the same.

## Re-selecting an effect zeroes the bus ⚠️

- **Seen:** a rig that measures dead after panel work.
- **Cause (measured):** a re-select loads manifest defaults, and BusVerb's SEND defaults to 0 (a non-zero default registers every idle host as a client); Character's RET also defaulted to 0.
- **Fix:** assert SEND `CC 40` per track over MIDI immediately before every measurement (and, until 20 Sep 2026, RET `CC 38` on the master's channel).

## A station "at its defaults" was running its default mode's view ✅ measured

- **Seen:** a station documented as bit-exact passthrough at defaults changed T5's level by −2.5 dB on the ladder.
- **Cause (measured):** `ot_project.module_defaults` applied the ModeView of the defaults' MODE (Modulation's CHOR: MIX 64, RATE 30), so `rigproj` and `stamp-defaults` wrote a half-mix chorus into every T5.
- **Fix:** a view applies only when MODE is given explicitly. Re-stamp.

## PARSE ERROR loading a generated project ✅ measured

- **Seen:** LOAD PROJECT on a project from our tooling stops with "PARSE ERROR".
- **Cause (measured):** every PART record carries its own index in byte 8 (parts 1-4 hold 0-3, mirrors 5-8 repeat 0-3); a whole-record copy keeps the donor's. Also: `project.work` edited in text mode loses its CRLF.
- **Fix:** write `p % 4` into byte 8 after any whole-record copy (`ot_ladder.PART_INDEX_OFF`); the generator's read-back checks every record.
- **Check:** under the port the firmware logs `Couldn't read bank file '...bank01.work' ('PARSE ERROR')` to the card's `LOG 000000.txt` (`verify_set`, `ot_emu --card-out`).

## The set went silent after a test flash: the firmware reset the project 🟡

- **Seen:** after flashing a test image whose remix omitted Character; silent back on the rig image.
- **Cause:** ✅ the card's bank records had every part reset (FX1 id 4 with FILTER's page-2 bytes, FX2 = stock delay, T1/T2 no longer THRU, T8 = FX1 NONE / FX2 COMPRESSOR 0x18). 🟡 Inferred: the firmware sanitises part records whose FX ids are not in the running image and writes the .work files back. Not reproduced by LOAD PROJECT under the port (15 Sep 2026, OCTABAM88 bank B under `bus`), so the rewrite happens on another action.
- **Fix:** never load the set under a test image. Recovery: save a copy of the card's project; regenerate (`ot_project.py rigproj … + lfo-clear … all`), copy the banks over in place, keep the project's own `project.work` (a foreign `OS_VERSION` tag gave PARSE ERROR, inferred from the diff).

## The master compressor collapses one channel above COMP ~40 ✅ measured

- **Seen:** 13-14 Sep 2026. Character on T8 with COMP above ~40: R drops 40+ dB, L holds; scales with WDTH; only with the stations loaded.
- **Cause (measured 14 Sep 2026):** T4's Spectrum generated near-full-scale DC from state: init cleared `$00..$17` only; filter B's two HP poles at cHP = 0 were frozen and `hp2 = yB − h2` subtracted a stale h2 every sample (−0.5 FS on silence from a block pre-filled with 0x400000, under `dsp_host`). The makeup clipped DC + audio on the channel with the larger offset. Track LEVEL 0 on T4 cleared it; AMP VOL 0 did not.
- **Fix:** every persistent slot zeroed at init (Spectrum `$00..$3f`, Modulation's LFO values, Character's counters, phase and grace). Image 8: bank G's master at COMP 40 / 80 / 127 reads R−L −0.4 / −0.1 / −0.6 dB (was −44 at COMP 80).
- **Check:** `tools/verify/verify_dirtystate.py` (in `make verify`) renders every module from a garbage block on silence and refuses output above −100 dBFS.
- **Lesson:** a channel-asymmetric failure in channel-symmetric code is a data asymmetry; an AC-coupled capture cannot see DC.

## A diagnostic image silenced every bank with stations; the port played them 🔴 open

- **Seen:** OCTABAM5 (Character 189 words shorter) played banks A, B, E and was silent on F and G (the station layouts), DSP not hung. Image 4 and the shipping image play G.
- **Cause:** open. Under the port image 5 plays F and G and runs no instruction image 4 did not. Left: placement (Modulation moved down, A 0x1c1b, B 0x193c; stock COMB code and dispatch kept on payload B). Image 6 = image 5's Character plus 189 nop words plays F and G. Not bisected.
- **Fix:** workaround: pad a diagnostic module to a placement known to play.

## Sequencer stuck on step 1 at project load: an init that moved r1 ✅ measured

- **Seen:** image 99, 13 Sep 2026, every project loading a Spectrum on FX1.
- **Cause (measured, the port's last-PC ring):** the FX1 dispatcher keeps the effect id in r1 across `jsr init` and indexes the proc table with it (`P:0x4c8..0x4d7`). Spectrum's init returned r1 = r7+24; `jsr (r2)` landed on P:0. `dsp_host` calls init and proc itself and cannot see it.
- **Fix:** init zeroes through r5. Recovery: power-cycle and a project without the module.
- **Check:** `tools/verify/verify_initregs.py` (in `make check`) refuses an init that writes r1/n1/m1.

## Sequencer stuck on step 1: cycle overrun or a wild value

- **Seen:** step 1 solid, no audio.
- **Cause (measured):** a core cannot finish a block: a cycle overrun (three heavy stations beside an engine at a static 3,106 of 3,120; the counter is a floor, the wall a cliff), or a wild stored value feeding an engine on frame one (an old part's crossed-slot byte after a layout change).
- **Fix:** fit the layout (≤ two heavy stations per core); stamp the project for the current remix before playing.

## The bus return is "less rich / bit-crushed" on the unit, clean under the port ✅ gone with the return (images 35 → 38)

- **Seen:** image 35, up to 20 Sep 2026. One sender, WET 0 on both engines, RET 127 on T8: the return duller and grainier than the dry; worse after knob presses; STOP then PLAY resets it. Present on either core, at any send level, with the sender muted post-FX. Under the port the same path is the aux itself at −109 dB residual, lag 60 samples (`verify_set`).
- **Cause:** in the return path; which part (shared-window per-sample reads, the rotation, the station's add) was not bisected and the code is gone.
- **Fix:** 20 Sep 2026: the return removed (Character has no RET, engines publish no stage output, SEND allowed on T8); each engine's wet leaves through its host (T1 repeats, T5 tail). Image 38 on the unit: the reverb on T5 clean (Sam, 20 Sep 2026).

## A TIME turn on BusDelay crackles for about a second, in both directions ✅ measured, fixed (unflashed)

- **Seen:** Sam, image 38, 20 Sep 2026: TIME or FDBK moves crackle; putting knobs back does not clear it; re-selecting does.
- **Cause (measured, `dsp_host` and the port):** the glide (image 33) stepped its Q8 state once per block, up to ~17 samples a step; the loop's tap, REVERSE's lag floor and GRAIN's read base jumped by the step at every block edge (~1 s of clicks after a big move, then a ~3 s sub-sample tail). The FDBK crackle was TIME's tail.
- **Fix:** the Q8 TIME ramps within the block, a sixteenth of the step per sample; REVERSE and GRAIN re-derive their per-sample lag from it. Spikes per mode 5,228 / 2,676 / 4,483 → 0 / 73 / 896 (the remainder is REVERSE's uninterpolated heads).
- **Check:** `tools/harness/glide_census.py`, `port_click_census.py`.

## The RET/CRSH trap ✅ removed by design

- **Seen:** T8's Character in the old BUS mode with knob 3 at 127: switching SAT to TAPE made the whole mix a full-scale 4-bit crush (the same knob was RET in BUS, CRSH elsewhere).
- **Fix:** no BUS mode. 13-20 Sep 2026 slot 4 was RET on every track; since 20 Sep 2026 slot 4 is empty (`---`) and the return is gone. DRV 0 skips the saturator (bit-exact).

## An FX1 station's page 2 does not reach the DSP on a bus host ✅ fixed (image 24)

- **Seen:** 15 Sep 2026. Character on T1 (THRU, FX1) ran TAPE whatever the panel said (−47 dBFS hash at knob 3 = 127). T3 (STATIC) and T8 (FLEX) took page-2 edits; T1 did not. T2 (THRU, FX2 = SEND) kept its page 2; T1 (FX2 = BusDelay) lost it.
- **Cause (measured, `ot_emu --watch-mem` on T1's DSP record):** the tempo cave (`modules/tempo-sync`, in the voice-record writer for FX2 ids 6/7) stored tempo24, clock period, fader+1 and note into record halfwords 18-21 (`+0x24..+0x2a`) every frame after the copier put FX1 page-2 bytes in 18-20 (`0x400d7550`, `0x400d755e`, `0x400d7522`). Halfwords 18-20 are also `r6_FX1+$c..$e`. Every FX1 effect on a delay or reverb host had run page 2 on tempo bytes since 24 Aug 2026.
- **Fix:** the cave publishes only the note, into the low byte of BusDelay's TIME halfword (`+0x1b`, `r6+$1` bits 8-15); BusDelay reads tempo24 from stock's record word (halfword 31, `r6+$13`, `0x40004d6a`) and derives the period on the DSP. Under the port a live SAT edit on T1 lands (`0x7f01`); 120 BPM snaps TIME to 11,025 samples (1/8). Image 24 (15 Sep 2026): sends into the delay work on the unit.

## Static that stays after knob moves with both engines live 🔴 open

- **Seen:** image 26, OCTABAM89 C02, 15 Sep 2026. Knob moves on BusDelay or BusVerb (times, sizes) sometimes bring static that stays, most reliably with the reverb host's SEND and both WETs up; a transport restart clears it. Not reproducible on demand after. One 10 s capture (`out/hw/voicing25/noise_now.wav`): HF above 8 kHz −77 dB against −85..−91 dB after CC toggles, no clean A/B.
- **Cause:** open. Under the port (ONEAUX fixture and OCTABAM89 C02 for 2,400 frames, `out/crackle/c02_recipe.midi`) a knob turn costs no extra cycles (delay 3,754 → 3,754, REVRS 3,914, reverb 16,710 ± 14) and no output rails or jumps above 0.25 FS. The port models no stall; C02 prices ~2,950 (core 1) and ~2,994 (core 0) against 3,120 usable, with the counter ~270 low on the reverb, so an overrun that desynchronises the frame handshake fits (🟡 inferred).
- **Fix:** open. To find out: with the static going, take one station off the core (T2's FX1 to NONE); or `make burn` on C02, stepping the burn until it appears.

## A DC thump every 10.59 s at idle, from track 6 ✅ source measured

- **Seen:** every ladder rung, including the one with no module of ours; transport stopped. DC step +0.23 FS L / +0.46 R, two-sample rise, ~35 ms decay through the output DC blocker. LEVEL 0 on T6 removes it; AMP VOL 0 does not.
- **Cause (measured):** T6 LFO 2: destination 16 (AMP BAL), triangle, speed 18, depth 21, FREE; period 64 steps at 121 BPM with a 3/4X scale; the pulse rate follows LFO speed. A plain BAL move over CC 8 never pulses.
- **Fix:** every LFO depth cleared in OCTABAM87 and the ladder (`lfo-clear all`). Open: whether a balance LFO pulses on stock 1.40C (the port with a fast LFO fixture decides it); a 593.5 Hz tone at −75 dBFS after STOP on OCTABAM87 only.

## Spectrum VOWL went silent with RES up 🟡 seen once

- **Seen:** image 96, T3 soloed, FREQ/RES over CC, MODE set at the panel: VOWL at RES 100 with FREQ ≤ 96, and RES 127 at FREQ 64, output −102 dBFS; other modes bounded.
- **Cause:** 🟡 not reproduced (`dsp_host`; image 97 with MODE over CC 69, both knob orders). The one difference: T3's FX1 page 2 was on screen during the page-1 CCs (the editor's refresher `0x40027e00` runs there). CC 35 with page 2 on screen landed on RES, which falsifies routing by displayed page.
- **Fix:** the two-peak VOWL is gone (image 98: a three-formant resonator bank, bounded at RES 127). If it recurs, capture before touching anything.

## A one-sample tick on an exact 2048-sample grid at idle 🔴 open

- **Seen:** image 93, sequencer stopped: a common-mode one-sample downward spike, −45 dBFS, every few hundred ms; present with the reverb's track muted.
- **Cause:** open. Measured: 23 / 24 ticks per 30 s on a 2048.050 / 2048.049-sample grid (residual 0.29 / 0.25 samples over 631 periods); +24 ppm says the unit generates it; 4 % of wraps spike. Ruled out: the capture rig, Character, the stored project (a reload gave zero ticks), the input path, BusVerb page 1. Page 2 untested (the CC MAP fault). Candidates for 2048: BusVerb's 2048-word modulo buffers (`m5 = $7ff`), Modulation's `buffer_words=2048`, the PCM-pool block (`0x800` in the recorder's table at `0x80003c20`).
- **Fix:** open. When bisecting by hand, take slots to a stock effect, not NONE (id 0 is SEND). `tools/rec` (built from `tools/hw/rec.swift`) must be the HAL recorder.

## Sequencer stuck on step 1 with every effect turned off: id 0 is SEND

- **Seen:** image 85B (the first rig-burn image): every FX1 NONE and every FX2 SEND. Second instance, image 32B, 16 Sep 2026: two projects with every stored page byte zero.
- **Cause:** ✅ id 0 is aliased to SEND and FX1 NONE is id 0, so SEND's proc runs on every FX1 NONE slot with r6 on a page whose bytes the last effect left; the burn read a stale slot-1 byte on four extra slots per core. The emulator never instantiates an FX1-NONE slot. Second instance: 🔴 7,111 burn loop iterations at "0" and the frame never finished; the loop count's cause is open. ❌ Retracted (22 Sep 2026): "the firmware computes page-1 slot 1's word" (`0x378f00` was the previous instruction's `a`; a port page dump shows every slot raw, knob << 16).
- **Fix:** anything in SEND that reads a knob and can cost cycles or write the bus gates on the slot being FX2. Since image 48 SEND keys the refusal on r7 (0x6100/0x6400/0x6700/0x6a00, measured under the port; X:$213 is stale at proc time) and returns before touching state. The burn reads page-2 slot 6 (`$c`, CC 62), unflashed. The stamper writes SEND's defaults into every id-0 slot, FX1 and FX2.
- **Check:** `verify_burn.py` check 5 (`dsp/burn_send.inc`).

## Line-F exception on [PROJ]: a cave pinned in OS .bss

- **Seen:** tag 91: PROJECT throws an exception and wedges.
- **Cause (measured):** a cave at `0x40108800`, in the OS image's last ~30 KB: a zero run at rest that is the PROJECT subsystem's RAM.
- **Fix:** `build_bus.SAFE_CAVE_CEIL` (0x400d8000) refuses any cave above the decoded free region.

## Garbled audio straight after an OS upgrade: the warm-up tag

- **Seen:** right after OS UPGRADE, audio garbled (worse for the delay); not after a reboot.
- **Cause (🟡 inferred):** an upgrade rewrites program memory without clearing DSP state RAM; an engine skips warm-up when its tagged counter holds a valid tag at full count (BusVerb `$2c0000` at `r7+$82`, BusDelay `$2e0000`).
- **Fix:** power-cycle after every upgrade before judging anything.

## A module mistuned on tracks 1-4 only: an absolute stock-table address ✅ measured

- **Seen:** Bryan T's LOFI2 low-pass three times too bright on tracks 1-4.
- **Cause (measured):** the payloads are linked separately: the 6,305-word curve bank is `X:0x438` in A and `X:0x42b` in B; Y tables shift by 16. A bare literal is right on A (tracks 5-8) and 13 words off on B. The single-payload audition render dumps payload A.
- **Fix:** declare stock X/Y table addresses so the build rewrites them per payload, or read through a build-supplied base.
- **Check:** audit any stock-table read on both payloads with `rig_render.py`.

## Self-oscillating squeal: a page-2 value out of range, or deep overrun

- **Cause:** (1) a wild page-2 value: BusVerb DIFF stamped to 127 self-oscillates the tank (the +0x325/+0x331 stamp-offset bug, also flash 4's "the stock DELAY wedges the unit on part load": T4's DELAY row landed on T5's BusVerb). (2) Deep cycle overrun (the high-pitch squeal, `docs/firmware/CHIP.md`).
- **Fix:** re-stamp the project (1); fit the layout (2).

## "Z" screen / won't boot: corrupt OS

- **Fix:** Startup Menu recovery: power off; hold [FUNC], power on; [TRIG 3] MIDI UPGRADE; send a good `.syx` (`make midi-flash PORT=A SYX=…`, or a SysEx app). [`docs/guide/BUILDING.md`](../guide/BUILDING.md) section 7.

## Cross-core bus glitch: the accumulators' race ✅ mechanism measured, fixed

- **Seen:** a tear, stutter or hash on wet audio crossing cores, often smeared into a reverb tail.
- **Cause (measured under the port, `git show 3ceba41:docs/history/COLDFIRE_PORT.md` O12; [`modules/send/README.md`](../../modules/send/README.md)):** core 0's housekeeping flips the rotation word mid-way through core 1's frame; clients read the word directly, so a frame's sends split across two buffers.
- **Fix:** four ACC buffers and one rotation tracker per core (`build_bus.py` ROTLATCH, payload B); eight buffers since image 49 (above). No local test is evidence: `dsp_host` runs the cores lock-step or under a guessed interleave.

## CONTROL menu shows its stock six rows though the image carries eight 🔴

- **Seen:** tag 16: the bus screen's appended rows absent; the image held row count 8 at 0x400cbd54 and the repointed row pointer.
- **Cause:** unknown; the rows are read from somewhere the patch does not reach.
- **Fix:** the module is out of the tree. Navigate to CONTROL in the ColdFire emulator's own menu before any flash that appends rows again.

## The one-aux return never reached T8 ✅ measured under the port

- **Seen:** flash 6: wet out of T1 and T5 (the engines' hosts), nothing at T8.
- **Cause (measured):** the station pinned the return to track 8 by `r7 & 0xff00` against `$6700/$6800` (the harness's two-per-track model). The stock dispatcher bumps r7 three times per track (the third unconditional at P:0x51e), so T8's FX1 runs at `$6a00`.
- **Fix:** pin `$6a00/$6b00`; the harness's r7 model corrected. Confirmed on flash 7.
- **Lesson:** `verify_onebus` was green on exactly this property; dispatcher facts are measured under the port.

## The port reports a wrong bank/pattern for an image that detours `0x40087d44`: the instrument

- **Seen:** under `ot_emu --sequencer`, an image hooking the BANK= store at `0x40087d44` plays bank 0 pattern 0 after LOAD PROJECT (`saved_bank: -1`). A 38-site bisect and a PR to midisc's author (withdrawn) were built on it.
- **Cause (measured):** `rtos.cpp` learned the saved bank from a write watch on `BANK_PTR` (`0x46c82456`) accepting only the stock store's PC; a detour stores from a cave.
- **Fix:** the watch follows a `jsr (abs).l` at the site and accepts the detour's store; `--bank N` overrides.
- **Lesson:** a port watch keyed on a stock PC is blind to any module that detours that PC.

## A send that ignores its knob, a track loud into the bus at SEND 0, different per track 🟡 two causes, both project data

- **Seen:** image 32, OCTABAM89 and its no-effects copy, 16 Sep 2026: T5 and T7 loud through BusDelay at SEND 0; T3 quiet; T2 leaking with a dead knob. CLEAR PATTERN fixed it.
- **Cause 1 (measured):** stale parameter locks: one lock byte per slot per trig (`tools/hw/ot_bank.py`: 64 steps × 32 slots; FX1 = 18-23, FX2 = 24-29; `0xff` = none). Every slot move since 7 Sep left locks on whatever knob sits there now. OCTABAM89 carried 962 FX1 and 6 FX2 lock bytes, one on T5's FX2 knob A.
- **Cause 2 (🟡 inferred):** an FX2 stored as id 0 aliases to SEND; the firmware delivers no page for it, so SEND reads whatever the DSP page word holds. Not measured under the port; the falsifier is a stamped project that still leaks.
- **Fix:** `ot_bank.py strip` clears a page's locks in every pattern; `stamp-defaults` and `clean` store SEND (id 9) with a zero page in every empty FX2 slot.

## Freeze without an exception screen as ColdFire delay-routine work grows 🟡 open

- **Seen:** Jannik Aßfalg (repeat98)'s unit, Tape Echo (PR #357, runs in the stock delay's frame routine, [`docs/firmware/COLDFIRE_DELAY.md`](../firmware/COLDFIRE_DELAY.md)): OCTACLID3 froze on a TIME edit with three instances, OCTACLID4 editing the sixth, the PR's candidate at seven; always during control edits.
- **Cause (🟡 inferred):** the routine's per-frame deadline. Port instruction meter per eight-track frame: stock DELAY 7,628; eight instances ~23,000 settled, up to 32,355 moving (after the 23 Sep 2026 EMAC rewrite: 15,283 / 16,459 / 21,547, `modules/tapeecho/README.md` "Measured", unflashed). Frame period 363 µs, ~95,800 CPU cycles at 264 MHz, shared. The meter prices an uncached SDRAM access at one cycle. State is a fixed 1,600 B; nothing is allocated. Stock spins at `0x40003780` on DMA status `0xfc0450be` before the commit: a silent hang on overrun. Falsified by a freeze at the same count with the work halved, or with settled controls.
- **Fix:** open; the ColdFire's per-frame budget for the routine is not measured. Any reverb or granular on the ColdFire prices above the seven-instance point (BusVerb ~18,000 DSP cycles per frame, four-grain GRAIN ~28,400).

## Bursts of garbage on the reverb host's frame while the delay runs on core 1 🔴 open

- **Seen:** Sam, image 58 on, 23-24 Sep 2026 (heard as intermittent clicks since image 26). BusDelay on T1 with a sample playing, BusVerb on T5, nothing sent: 23-53 samples of near-full-scale garbage on T5's side about 3.5 times per six minutes. Stock 1.40C does not burst (Sam).
- **Cause:** open. Measured:
  - The bursts need the delay's DSP code running on T1 past its preamble: image 95 (proc returns at its first instruction) and 96 (stops after the preamble) read 0 in 12 minutes; every other delay image burst. T1 AMP VOL 0 read 0.
  - Ruled out on the unit: the ColdFire side of id 6, CPU load on core 1, the reverb, the frame write-back, the role lock alone, absolute-address stores into the shared window, words written by both cores, which half of the shared window holds the bus scratch (images 91-99), and the delay's per-sample shared accesses (image 91 take 5: none, same rate).
  - 9 of 12 bursts start 14-18 ms after the loud transient in T1's sample, and follow T1's trigs when those move against the beat.
  - The aligned-copy census: T1's own print deviates in the same 16-sample block in 29 of 32 bursts (0.03-0.35 FS); the same T1 audio instant gives the same burst waveform (12 copies of one cluster across images 91-99), so the content is a function of T1's audio. The junk is in T1's stereo block, full scale on the side T1 is panned away from, before the main mix (CUE shows it), and not T5's block (T5 LEVEL 0 changes nothing).
  - The dispatcher re-sets r0, r1, n1, r3, x1 and y1 before the read-back packer (`P:0x303-0x35e` on B); m0-m6 were saved on image 83 and it still burst.
  - Rates: a six-minute 0 occurs by chance 5-9 % of the time, a twelve-minute 0 about 0.1 %; the earlier two-minute table read 0 by chance ~37 % and separates nothing.
- **Fix:** open: where between T1's audio block after proc and the read-back words at `X:0x2600` the junk appears, and which part of the delay's per-block decodes or sample loop it needs. Branches `diag91`..`diag98`, `core1scratch99`, `nolock94`, `fix97`; captures `out/hw/v9*.wav` (machine-local). The "dead words at 0x360d3-5" (send_client.asm) are unexplained.
- **Check:** `tools/harness/burst_census.py` with the aligned-copy check on a `tools/rec` take (T1 BAL hard left, T5 hard right). `tools/rec` needs the device name as its third argument (without it, it looks for EVO4 and exits).

## USB audio: a burst of reordered samples in the first 1.5 s of every host stream, clean after 🔴 open

- **Seen:** image 64, 25 Sep 2026, macOS recording all sixteen USB channels: four of five takes have one cluster of sample-step events 0.75-1.5 s after stream open, on several channels, none after 2 s (60 s, 60 s, 300 s, and 120 s under a 7,170-message/s USB-MIDI flood with panel work). Device counters (vendor request 0xc0/0x55): 0 underruns, 0 overruns, no bank-duplicate movement. Image 69 (24-bit, four packets queued at a 250 µs poll): still present, 0.51-0.76 s after open, only on the right channel of each pair, in runs 124-380 frames off phase.
- **Cause:** open. Measured: short runs out of order (−11.6, +10.3, −41 frames off the tone's phase), long-window phase agrees to 0.1 frame, so nothing is lost or repeated. Candidates: the device's packet queue on the first primes after alt 1 (the controller's add-dTD tripwire, not modelled by the port's bench), or the host's stream start. 🟡 Right-only on image 69 points at the host's stream assembly: each USB frame carries a track's L and R in one packet. Likely octemu's "some crackles" (sox opens a fresh stream per run).
- **Fix:** none. Workaround: discard the first two seconds of every take, or hold the stream open in a DAW. A stream held open across two recordings, or a sequence counter in the packets, decides the cause.

## PERKY1 briefly sounded, then froze the sequencer — timing defect measured locally

- **Seen:** user's Octatrack, 6 Oct 2026: brief sound, sequencer stops.
- **Cause:** the generated limb renderer measures 79,000–84,000 nominal cycles
  per 16-sample default block, exceeding the ~72,512-cycle hardware deadline
  before stock audio work. This is a concrete defect; the exact hardware halt
  PC is unavailable. The normal full emulator schedules instructions and did
  not reproduce the stall even over 32,000 frames.
- **Fix built:** PERKY2 native arithmetic/direct state, exact synthetic curve
  specialization, and one admitted PERKY voice per core. Excess signed tracks
  receive a cleared source block. FX NONE is the qualified development layout.
- **Check:** independent PCM/state/RNG parity, `verify_perky_realtime_budget.py`
  (2x decoded opcode cost plus the stock reserve), and mandatory project-loaded
  `verify_perky_synth_port.py` with dirty memory and later trigs. On 6 Oct 2026,
  the user reported that PERKY2 works on their Octatrack after the failed
  PERKY1 test. No duration or extended stress results were supplied; emulator
  timing remains a conservative local model, not a hardware burn sweep.
