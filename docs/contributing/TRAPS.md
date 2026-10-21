# The trap register

The traps that have already cost real work, moved here from `AGENTS.md` on
14 Oct 2026. `AGENTS.md` keeps a one-line index with a link into each entry.
`docs/contributing/FAILURE_MODES.md` is the register of hardware failures on
a unit (symptom -> cause -> fix); this is the register for the code, the
build, the emulators, the harness and the measurement instrument. Each entry
states the symptom, what it cost, the fix, and what now gates it.

Add a new trap here the moment it costs real work, and add its one-line
index entry in `AGENTS.md`'s trap index.

## Traps that have already cost real work

<a name="trap-asm"></a>

### The assembler mis-encodes instructions, silently

**The assembler mis-encodes instructions, silently.** `dsp_asm` encodes
`tfr a,b` as `rnd b`, and **any `mpy` operand order it doesn't know as
`mpysu`** — found with `mpy x0,y0`, confirmed 9 Aug 2026 for `mpy x1,y1`
and `mpy x0,x1` too (every shipping site is audited safe because its second
operand is always positive, which is the only reason the engine works; the
sites are counted per module in `build_bus.MPYSU_AUDITED`, and since 23 Sep
2026 every `assemble()` round-trips its bytes through the disassembler and
stops on any other mismatch or on a count that differs from the table). `mpysu` treats the SECOND operand as unsigned, so
a negative multiplier there is silently corrupted. `mpy x0,y1` and
`mpy y0,x0` encode signed. Both assemble clean and do the wrong thing.
**Disassemble what you assemble** when a result surprises you — and always
for a new `mpy` whose second operand can go negative. A related family bit
us in shipping code: `cmp a,b` had encoded as `max a,b`, which updates only
the C bit while `blt` tests N^V. **Until 4 Oct 2026 it had no encoding
for a data-ALU op with two parallel moves** (XY, X:R, R:Y, class II):
`clr`/`add`/... with one were InvalidInstruction, and `mpy`/`mac` fell
to the non-parallel `mpysu`/`macsu` with both moves dropped (`mac
x1,y0,b x:(r1)+,x1 y:(r7)+,y0` -> `0126a6`; the chip word is `f4f9ea`).
`move x:(r1)-n1,x0 y:(r7)+,y0` encoded `(r1)` (`f0e100`): the XY form
has no `(Rn)-Nn`. Against the stock payloads (A+B) the old `dsp_asm` got
0 of 688 ALU+XY lines right (605 wrong, 83 refused) and 0 of 258 X:R/R:Y
lines; the patch makes all 946 the stock word and leaves the result for
the other 12,079 stock lines unchanged. A move token with no encoding is now
InvalidInstruction, and the round-trip compares every operand field,
parallel moves included. **And until 14 Sep 2026 it emitted only
the TWO-WORD displaced move**: `move x:(r7+$15),a` assembled to
`0a77ce 000015` where the chip (and every Elektron payload, 533 sites in A)
has the one-word `0257de` for displacements −64..63 with a data-ALU
register. `tools/patches/dsp56300.patch` adds the one-word form; every
word or cycle number recorded for a displaced move before that date is 2
where the assembler now emits 1 (the emulator's own cycle table prices the
forms 3 and 2; hardware timing of the one-word form under OUR code is
unmeasured — stock runs it every frame). **THE BINARY IS NOT THE SOURCE:**
the encoder lives in the vendored `assembler.cpp` behind that patch, and
a `dsp_asm` built before it silently emits the two-word form for every
site — five images (8–12, 14 Sep 2026) and every price quoted with them
were ~800 words / ~500 cycles heavier than the tree said, found only when
another session's FREE table did not match. After any change under
`tools/patches/`: `make dsp-repatch` (`scripts/setup.sh` does not
re-patch a built tree; it stops when the tree lacks the current patch),
then `make emu-cf`; after one under `tools/harness/dsp_host/`:
`scripts/setup.sh`. `make check-asm` expects `0257de` for `move
x:(r7+$15),a` and `f4f9ea` for `mac x1,y0,b x:(r1)+,x1 y:(r7)+,y0`.

<a name="trap-a0"></a>

### Reading `a0` exposes the fractional left shift that reading `a1` hides

**READING `a0` EXPOSES THE FRACTIONAL LEFT SHIFT THAT READING `a1` HIDES.**
`mpy` aligns the Q46 product into Q47, so `a1` is the plain fractional
product — which is why "mpy does not double here" is true, and stays true,
for every module that reads a1 (all of them until 29 Aug 2026). Read the LOW
word instead — the idiom for turning an integer product into a wrapping
ramp — and you see the RAW 48-bit content, shift included, so the effective
integer scale is **2× your multiplier**. Nimbus's grain window is one
`mpy phase,2^(23-k)` plus `abs`; written with the arithmetically obvious
`2^(24-k)` it assembled, rendered, and made a perfectly plausible granular
noise while running the window at DOUBLE RATE, which put the two grains of
each pair in phase instead of interleaving. Found by a DC gate, not by ear
and not by any existing check: two triangle windows a half period apart sum
to exactly 1, so **DC in must come back flat** — it came back with 2×-DC
ripple, and went flat (−122 dB) when the multiplier was halved. If you use
a0 for anything, pin it with a test whose arithmetic you can predict exactly.

<a name="trap-asr-a0"></a>

### `asr #n,a,a` shifts the low bits into `a0`, and Z is set only when all 56 bits are zero

**`asr #n,a,a` SHIFTS THE LOW BITS INTO a0, AND Z IS SET ONLY WHEN ALL 56
BITS ARE ZERO.** A ramp step written as `sub x0,a / asr #6,a,a / teq y1,b`
("a step that rounds to 0 snaps the run value onto its target") never
snapped: a1 was 0, a0 held the shifted-out remainder, Z stayed clear, and
every ramp sat up to 63 LSB under its knob for good (26 Sep 2026, found
by `make verify-onebus`: a host's send at 100 was not bit-identical to a
SEND's at 100). The same a0 remainder breaks `add x0,a / cmp x0,a / teq`
(a 56-bit compare). Reload the step clean before testing it — `move a,x1 /
move x1,a / tst a` — the one-word `move a,x1` drops a0. Sister of the
"reading a0" trap above: the low word carries what a1 hides.

<a name="trap-a2-stale"></a>

### A logical op on an accumulator leaves the extension byte stale, and the next store saturates

**A logical op (`and`/`or`/`not`/`asr`-as-mask) on an accumulator leaves the
extension byte (A2/B2) STALE, and the next `move a,x:` SATURATES to full
scale.** Building a sign mask with `move a,b / asr #$17,b,b / not b` and
storing the result writes `0x7FFFFF`, not the bits you computed — the
store's limiter sees A2 inconsistent with A1's sign and clamps. This cost a
long session on the gated-reverb envelope: a branchless mask-select looked
correct and disassembled correctly but pinned the gate open, because every
masked value saturated on store. **Fix: don't hand-roll sign masks. Use the
conditional-transfer ops** — `tmi x0,a` (floor to 0 if negative), `teq x0,a`,
`tpl`/`tge` — which move a CLEAN register into the accumulator, so no A2
staleness. A plain `move #imm,reg` does NOT disturb the condition codes, so
the `sub`/`tst` that sets the flag survives to the Tcc. (This is also why the
sample loop stays branch-free: Tcc replaces the branch AND avoids the trap.)

<a name="trap-tcc-pair"></a>

### A Tcc pair that shares one compare is broken by any arithmetic between them

**A Tcc pair that shares ONE compare is broken by ANY arithmetic between
them — and nothing at the second site looks wrong.** The branch-free idiom
here is `cmp`/`tst` once, then several `Tcc`s that all read the same
condition codes, relying on the fact that MOVES do not disturb them. That
holds until someone inserts real work in the middle. GRAIN's two scatter
latches (line L, line R) shared one wrap flag; adding a density gate
containing `clr b` and `tst a` between them left line R testing garbage, so
it re-latched a random read position EVERY SAMPLE instead of once per grain.
That is broadband noise, and it was audible as a hiss **on the right channel
only** — found by ear (13 Aug), not by any check, because `make check` and
the bit-identity gate were both green: the code was deterministic and every
mode still assembled. Fix: park the compare's RESULT in a scratch slot and
restore the flag with `tst` before each Tcc that needs it. **When you add
anything to a block, check what the code BELOW it assumed about the
condition codes** — the dependency is invisible at the point you edit, and
`clr`, `and`, `abs`, `tst` and every arithmetic op all set them. Same family
as the A2-staleness trap: legal instructions, correct-looking source, wrong
machine behaviour.

<a name="trap-move-tfr"></a>

### An accumulator-to-accumulator `move a,b` limits; `tfr a,b` moves all 56 bits

**AN ACCUMULATOR-TO-ACCUMULATOR `move a,b` LIMITS; `tfr a,b` MOVES ALL 56
BITS.** A parallel `tfr x1,a  a,x:(r3)+` written to replace `move a,x:(r3)+ /
move a,b` differed on the bit-identity gate whenever `a` exceeded 24 bits
(23 Sep 2026, Modulation's LINE loop; encodings confirmed by disassembly,
found by bisecting one item). The two are interchangeable only when the
source is known to fit.

<a name="trap-tcc-operands"></a>

### `Tcc` takes a register source, never an accumulator, and `clr` takes an accumulator, never a register

**`Tcc` takes a REGISTER source, never an accumulator, and `clr` takes an
accumulator, never a register.** `tpl b,a` and `clr x0` are both
InvalidInstruction — caught at assembly, which is the cheap case, but they
look plausible enough to write repeatedly. Move the value through `x0`.

<a name="trap-lua"></a>

### `lua (rN+d),rM` takes d in −64..63, and `dsp_asm` wraps anything larger silently

**`lua (rN+d),rM` TAKES d IN −64..63, AND `dsp_asm` WRAPS ANYTHING LARGER
SILENTLY.** `lua (r7+$46),r5` assembled to `0x042765`, the same word as
`lua (r7-$3a),r5`, and the round-trip disassembly cannot object (a `lua`
is a `lua`): Modulation's TONE glide read and wrote 58 words BELOW its
block for one build (26 Sep 2026, caught by `verify_modulation`'s
reference gates, not by the build). Past ±63 use `move r7,r5 / move
#$46,n5 / move (r5)+n5`, the form the streams already use.

<a name="trap-label-prefix"></a>

### `dsp_asm` resolves labels by prefix, so no new label may have an existing label as its prefix

**`dsp_asm` resolves labels by PREFIX, so no new label may have an existing
label as its prefix.** Adding a loop labelled `warmz2` next to the existing
`warmz` assembled to

```
do #<$40,>$13632     ; 064080 013631      (should have been 001374)
```

— `warmz`'s address `0x1363` with the leftover `2` appended. The loop branched
into hyperspace and `dsp_host` SIGSEGVed with no diagnostic. Same family as the
three above: clean assembly, wrong machine code. Found 9 Aug 2026, after three
wrong guesses (emulator memory limits, buffer alignment, a stale modulo) that
were all *reasoned about* rather than disassembled. **Disassembling first would
have cost one step instead of four** — the rule above is not advice.

<a name="trap-markers"></a>

### Build-time markers and base literals count when they appear in comments

**Build-time markers and base literals count when they appear in COMMENTS.**
`build_bus.py` census-checks the number of `$30000` literals in the delay
source and requires exactly one `; DMODE_OVERRIDE` / `; DINT_OVERRIDE`
marker — and the substitution is a blanket text replace over the whole file.
Writing *about* either in a comment trips the guard: both happened while
documenting stage 5/6 (a comment explaining why mode 3's immediate must be
decimal spelled the hex out; another explaining the override marker spelled
the marker out). The build refuses, loudly, which is the guard working —
describe them in prose instead of spelling them. The same goes for
`; ROTLATCH` and `; ROTINIT`: the build substitutes a body at the FIRST
occurrence, and on 21 Sep 2026 a housekeeping comment that said "the
ROTLATCH check" took the tracker body while the real marker stayed a
comment -- no client on either payload resolved its write offset, and
`verify-bus` read it as every server's client count changing.
`_marker_once` refuses a second occurrence of `; ROTLATCH`, `; ROTINIT` and
`; XBUS_GATE`; the `; HOSTGUARD`, mode-override and delay-override markers are
counted to exactly one before they are replaced.

<a name="trap-chip-form"></a>

### An instruction form the chip has never run is not proven by the port

**AN INSTRUCTION FORM THE CHIP HAS NEVER RUN IS NOT PROVEN BY THE PORT.**
The assembler encodes it, the vendored emulator decodes it the same way, and
the chip may not: image 44 (21 Sep 2026) wedged on its first block on four
one-word displaced Y stores (`move a,y:(r3+$1)`), a form with no site in
either stock payload; the X form has 533. Before using a form, grep it in
`out/dsp/payload_*.asm` (`tools/build/dsp_disasm_all.py`); no precedent means
a hardware probe first, or the form everything else uses.

<a name="trap-rep-dma"></a>

### No `rep` in an effect's `init` or `proc`, and no dense X work in a DMA's 8K block

**NO `rep` IN AN EFFECT'S `init` OR `proc`, AND NO DENSE X WORK IN A DMA'S
8K BLOCK.** Neither stock payload contains a `rep`. A `rep` cannot be
interrupted, and the host-command handlers that arm the ColdFire's DMA must
answer at once: JamCones' BBD delay on T1 crackled core B and then silenced
tracks 1-4 (11 Oct 2026), and Zac's MKI voice tore the read-back and wrote
ColdFire RAM out of place; `do #n,>l / div x0,a / l:` is bit-identical and
fixed both. Separately, core work that hammers the memory partition a DMA
channel uses stalls the DMA (core 0: `X:$0000-$1cf`, `$2000` and `$4000`
host buffers, `$8000` ESAI): a muted track leaking into MAIN, outputs stuck
one-sided. The port models neither. `docs/contributing/FAILURE_MODES.md`
has both entries; `tools/build/norep.py` makes the build refuse a `rep` in any DSP source.

<a name="trap-spec-xbus"></a>

### `SPEC=1` requires `XBUS=1`

**`SPEC=1` requires `XBUS=1`.** Without it the accumulators stay in core-private
memory and each half of the tracks can reach only its own core's server — worse
than today, **and it still makes sound.** The build guards this. Do not ungate it.

<a name="trap-track-core"></a>

### The track↔core mapping is inverted from old assumptions

**The track↔core mapping is INVERTED from old assumptions**: payload A serves
**tracks 5-8** (BusVerb), payload B serves **tracks 1-4** (BusDelay).
Measured 10 Aug 2026 via the MrkVerb32 marker flash, after the assumption cost
two flashes and a session chasing "R13 is dead" (it was alive on tracks 5-8).
Kept deliberately: delay on low tracks, reverb downstream. Test the reverb on
**track 5**, not track 1.

<a name="trap-send-knobs"></a>

### SEND's `DEL` and `REV` are separate knobs

**SEND's `DEL` and `REV` are separate knobs**: `x:(r6+0)` and `x:(r6+1)`
(again since 25 Sep 2026; one knob from 6 Sep). Driving the wrong one
renders silence, which reads as a broken algorithm.

<a name="trap-formatter"></a>

### A descriptor's display formatter overrides its value count, and a cloned descriptor inherits the donor's

**A DESCRIPTOR'S DISPLAY FORMATTER OVERRIDES ITS VALUE COUNT, and a cloned
descriptor inherits the DONOR's.** A slot can carry a correct count, default,
name and enable bit and still draw as something else entirely — or as nothing
at all. Found on the 17 Aug flash: BusDelay clones SPRING REV, the formatter
fix-up in `build_bus.py` was gated to the reverb, and three of six page-2
slots drew wrong. WOW inherited SPRING TYPE's word-label renderer whose table
has THREE entries, was asked to draw 0..127, and **drew no knob at all**;
MODE inherited SPRING BAL's bipolar pair and drew as a balance dial reading
−64…−60 instead of a 5-way select. Every existing check passed, because every
field they checked was right. `verify_menu` now checks the renderer against
the count (`count < 128` → the enumerated pair with `0x12a` zero; `128` → both
formatters zero). **The general form: when you clone a descriptor, every field
you did not explicitly write is the donor's, and some of them outrank the ones
you did.** Same family as "a slot can draw a knob and publish nothing" — the
panel and the DSP are separate mechanisms and neither validates the other.

<a name="trap-unicorn-frac"></a>

### Stock Unicorn halves every ColdFire fractional-mode multiply and adds where `msac` subtracts

**STOCK UNICORN HALVES EVERY ColdFire FRACTIONAL-MODE MULTIPLY AND ADDS
WHERE `msac` SUBTRACTS, and the firmware runs its EMAC in fractional mode
(`MACSR = 0x20`).** Unicorn 2.1.4 computes `macl`/`macw` under `F/I = 1` as
an UNSIGNED product `>> 32` where the MCF5445x does a SIGNED product `>> 31`
(the 2.62 product shifted left one bit, upper 40 bits accumulated), and it
reads the MAC/MSAC bit from the opcode word where ColdFire keeps it in the
extension word, so every `msac` accumulated with the wrong sign (the
sequencer's frame builder is one). One defect, three symptoms that were each
investigated as firmware behaviour for a day (7 Sep 2026, RTOS_FORK
section 10.16): the recorder length converter wrote 10,336 for Bryan's 20,672
(explained away as "2-sample units"), the recorder's block walk stalled at
3,072 samples ("needs a DSP position feed"), and the sequencer's per-frame
timing byte advanced 8 per 16-sample frame, which dropped half the tempos'
recorder trigs ("nothing re-locks the step clock", plus a compensation
lever). The firmware's own reciprocal tables (`0x80003c20`: 2^31 / block
size) said which side was wrong. `emu_bringup.emac_selftest` pins the
semantics; `scripts/build_unicorn.sh` builds the fixed
library (`tools/patches/unicorn_emac_fractional.patch`). The general rule is the
same as "disassemble what you assemble": when firmware arithmetic comes out
exactly 2× or ½ off, suspect the INSTRUMENT before inventing a unit, and
find a site in the firmware whose constants only make sense one way.

<a name="trap-unicorn-macload"></a>

### Stock Unicorn's MAC-with-load decode has three defects, which is why tier-0 shims it per site

**STOCK UNICORN'S MAC-WITH-LOAD DECODE HAS THREE DEFECTS, WHICH IS WHY
TIER-0 SHIMS IT PER SITE RATHER THAN THE FORM BEING ABSENT.** Found 22 Sep
2026 by reading markandrus/octemu's independent fix against QEMU 11.1 and
confirming the identical lines are present, verbatim, in Unicorn 2.1.4's
own vendored QEMU 5.0.1 `target/m68k/translate.c`. In `DISAS_INSN(mac)`:
(1) `rx = (ext & 0x8000) ? AREG(ext, 12) : DREG(insn, 12)` reads Rx from
the OPCODE word instead of the extension word; (2)
`dual = ((insn & 0x30) != 0 && (ext & 3) != 0)` reads Ry's own register
field (ext bits 3-0, ANY MAC-with-load) as a dual-accumulate flag, and
`cfv4e` has no `M68K_FEATURE_CF_EMAC_B`, so this `disas_undef`s an ordinary
multiply into an illegal-instruction trap whenever Ry's low bits are set;
(3) the EMAC address MASK register resets to zero instead of CFPRM's
all-ones, and MAC-with-load ANDs its effective address with it, so every
load reads address 0 regardless of the real operand. **Fixing (3) in
`cpu.c`'s `m68k_cpu_reset` does nothing under Unicorn**: `src/uc.c` never
calls `cc->reset()`, only `uc->reg_reset()` (`unicorn.c`), a separate,
minimal function that clears `aregs`/`dregs`/`pc` and nothing else — found
by a `UC_ERR_READ_UNMAPPED` on a `macl ...,%a0@,...` whose `a0` was a
valid mapped address (the AND with a zeroed mask folded it to 0 first).
The fix belongs in `unicorn.c`'s `reg_reset`, not `cpu.c` (kept there too,
for documentation, since a future Unicorn version might wire up the real
reset path). All three are in `tools/patches/unicorn_emac_fractional.patch`;
`emu_bringup.emac_selftest` gained cases for them (fails on stock, passes
fixed). The MAIN OS has zero true dual-accumulate instructions
(`maaac`/`masac`/`msaac`/`mssac`), so forcing `dual = 0` is unconditionally
safe for it. The per-site shim (`emu_bringup._emac_load_shim`) stays:
the only differential against native decode ran route A with no project
on the card, which executes none of the 435 hooked sites (0 shim calls
either way), and route A was retired on 26 Sep 2026.

<a name="trap-macsr"></a>

### MACSR S/U is bit 6, and in fractional mode it selects 16-bit rounding on the accumulator read-out

**MACSR S/U IS BIT 6, AND IN FRACTIONAL MODE IT IS NOT SIGNED/UNSIGNED:
it selects 16-BIT ROUNDING ON THE ACCUMULATOR READ-OUT.** The ColdFire port
had S/U as bit 4 (that is R/T) and returned every `movclrl` as `ACC[39:8]`;
the firmware's level chain at `0x4000ccae` runs at MACSR `0x60` and keeps the
LOW words of two reads as a voice record's mode:level, which the CFPRM's
pseudocode (`OMC,S/U == 01`: `ACC[39:24]` rounded into `Rx[15:0]`, upper half
zero) puts there and a plain `>> 8` leaves at zero — every voice rendered
silent for a whole session (8 Sep 2026, O9b). The self-test never exercised
S/U. Read the CFPRM's MOVCLR pseudocode before touching `accRead`. The ACCext
registers have two layouts as well (fractional: eight extension + eight
low bits per accumulator; integer: sixteen extension bits), and the frame
ISR saves and restores them in INTEGER mode every frame (`0x4000ac96`,
`0x4000d968`); the port's write knew only the fractional layout until 23
Sep 2026 and put the saved word's low byte into ACCn[7:0] on every restore
-- invisible to a stock A/A (deterministic), found by Jannik Aßfalg's A/B/A
of a ColdFire patch. `test_emac.cpp` holds both layouts now.

<a name="trap-agu-modulo"></a>

### The vendored DSP AGU left a modulo buffer on a pre-decrement from its base

**THE VENDORED DSP AGU LEFT A MODULO BUFFER ON A PRE-DECREMENT FROM ITS
BASE.** `x:-(r2)` with r2 = 0 and m2 = 0x3f gave `0xffffbf` where the chip
gives `0x3f`, the next sixteen sample writes walked the peripheral registers,
a timer interrupt came alive whose vector in payload B is `move x0,y:(r4)+`,
and the corruption surfaced as a 196,608-iteration voice loop thirteen frames
after the first trig. Found with a one-word write watch, a DSP PC watch with
registers and an interrupt-vector histogram (O9b); fixed in `agu.h`. It is
the eleventh vendored-emulator defect and `dsp_host` renders every effect on
that AGU — `make check`'s bit-identity gates are the audit.

<a name="trap-trampoline"></a>

### A rewritten trampoline is not retranslated

**A REWRITTEN TRAMPOLINE IS NOT RETRANSLATED.** The ColdFire emulator's
EMAC-with-load shim ran every shimmed instruction from one scratch address,
rewriting its bytes each time; in a long-running Unicorn the address kept
its first translation, so the trampoline executed whichever instruction had
been translated there LAST — `msacl ..,%acc1` ran as the previous `msacl
..,%acc0` and corrupted the sequencer's timing byte (RTOS_FORK section 10.16.2,
7 Sep 2026). Fresh-Uc micro-tests could not show it; a per-instruction
trace of the real run did. Rule: never rewrite emulated code in place — give
each distinct instruction its own slot (`r.emac_slots`), and when a
micro-test disagrees with the running emulator, the difference is state,
so trace the running emulator.

<a name="trap-blind-instrument"></a>

### A measurement can be structurally blind to the thing you are using it to rule out

**A MEASUREMENT CAN BE STRUCTURALLY BLIND TO THE THING YOU ARE USING IT TO
RULE OUT — and it will report "clean" with total confidence.** Two instances,
both on 17 Aug 2026, both costing hours:
- `send_probe`'s THD metric sums harmonics **2f..9f of a 438 Hz tone**. A
  block-rate discontinuity (~2940 Hz) is not a harmonic of 438 Hz, so the
  metric cannot see it. It reported −45 dB ("clean") on audio that hardware
  measurement later showed carrying +22 to +31 dB of inharmonic hash. Every
  "no change" conclusion drawn from it that day was worthless.
- XBUS step 3 concluded "synchronisation not needed" from a cross-core send
  measured **through the reverb** — the one consumer that smears per-sample
  damage into a multi-second tail. It shipped a cross-core race for months.
**Before trusting a null result, ask what the instrument physically cannot
see.** A reverb cannot show you a discontinuity. A harmonic metric cannot show
you an inharmonic one. A lock-step emulator cannot show you a race between
two cores — `dsp_host` boots both payloads since 7 Sep 2026 and `-skew` can
interleave them, but that is a fuzz of the hardware's timing, not the
timing, so a local "clean" is still NOT evidence a bus timing defect is
gone (a local red IS a defect). When local says clean and hardware says
broken, believe the hardware and go looking for what the harness omits.

PERKY private-stack qualification, 15 Oct 2026, found another instance:
a before-instruction observer sees the same PC again when a higher interrupt
preempts it. Counting the first private instruction or RTE at every observation
double-counted switches/returns. Check the CPU's pending-interrupt mask before
counting execution. The private observer calibrates five switch windows in both
stepping modes, including IRQ arrival immediately before RTE; complete model
ISR time must equal executed cycles excluding the interrupted task instruction.

On 21 Oct 2026, PKFM18's smaller unchanged-control preparation path was
inlined into some `pk_nhr_frame` branches. Direct source calls passed 5,355
exact frames, but the frozen observer's public `placement_prepare` PC was
bypassed during real playback; both full workloads aborted at its missing-event
assertion before producing valid timing. Preserve an instrumented event boundary
explicitly with `noinline` when optimizing its caller/body, inspect actual call
sites, and retain full runtime selection/coverage checks. The aborted captures
are development failures, not performance receipts; the measuring binary and
budget stay unchanged. Source/archive evidence is retained under
`out/perky/hybrid/full-map-remaining-cf-v1/DEVELOPMENT_REJECTION.json`.

PERKY optimization, 15 Oct 2026, exposed a separate initial-condition trap:
`ot_emu` starts frame exchange at PLAY by default; hardware exchanges frames
since boot (`tools/emu/ot_emu/main.cpp`, O14). A raw old/new block comparison
failed on six DSP readback/mix records in the first two cold frames, while
all source/control records and every later record matched. Running both
images with 40 frame exchanges **before PLAY** produced 20,490 identical
post-priming records, with active audio on all four synthesis tracks.
`tools/verify/verify_perky_hybrid_block_identity.py` keeps the raw failure
visible, restricts its exact locations, and requires the complete primed
post-PLAY comparison. It never discards arbitrary frames after PLAY or changes
the shipping firmware. Compare initialized pipeline states before attributing
startup readback differences to synthesis; hardware startup remains unqualified.

The same campaign found that `Rtos::ticks()` counts vector 0x60 only in
`m_acks`, whose capture stops after 100,000 total interrupts. In the 4,096-frame
external-clock run the printed prefix was 1,862 ticks; the uncapped observer
counted 4,059, and all 4,056 supplied MIDI clock bytes were consumed. Do not
reuse a literal tick total from a shorter run as an acceptance condition.
Bind clock delivery and the uncapped observer to the actual run. Interactive
`run <ms>` can also stop inside an ISR: after the final STOP, stop releasing
test frames and drain the current exception before asserting balanced
switch/return counts. Never relabel a partial capture as a completed return.

<a id="trap-sustained-algorithm-coverage"></a>

### Selector coverage does not establish sustained algorithm timing

**21 Oct 2026, PKFM17 workload omission.** The sequence matrix exercised
Resonant Snare and Bass, but the sustained four-voice rows fixed the third
voice to Slap. Aggregate ALGO/MODE coverage and those sustained Slap timings
did not establish a sustained Resonant performance envelope. Feasibility
optimization had proceeded without measuring the algorithm the user had
identified as the largest ColdFire burden on hardware.

Require matched sustained Slap controls, Resonant Snare, Resonant Bass and
sequenced Snare/Bass MODE-lock rows. Hold the image, observer, native clocks,
duration, other voices, stock tracks and FX workload constant within each
comparison, and apply the frozen calibrated budget without relaxing its limits.
Run long enough to cover the complete pattern. Verify the final card's locks
and the actual runtime algorithm/mode combinations, with active source and
post-FX audio witnesses and independent exact-audio checks. A mode bitmask
alone proves neither the sequence order nor sustained residence in each mode.

`tools/verify/measure_perky_resonant_workload.py` supplies the focused rows;
`tools/verify/qualify_perky_resonant_workload.py` binds their selection, audio,
timing and input identities for admission. Preserve earlier hash-bound reports
as historical evidence for the workloads they actually measured; do not
relabel their Slap timings as Resonant qualification. Passing these local rows
still does not establish physical Octatrack timing.

<a name="trap-source-return"></a>
### A DSP source harness can return before its second voice executes

**Symptom (20 Oct 2026):** the first paired DSP-B experiment reported exactly
the first solo voice's cycle count and PCM. The second context never advanced.
The production source continuation reads `ssh` to discard the seam's JSR
return before jumping to stock AMP/FX. A simple test `jsr seam` followed by
a synthetic continuation `rts` therefore returns straight to the host sentinel.

**Cost:** the first paired measurement attempt was invalid. Its separate
second-channel PCM/state assertions caught the missing execution before any
timing result was accepted.

**Fix:** reproduce the real stack shape with a separate call thunk. The seam
discards the inner call return; the synthetic stock continuation then returns
to the paired dispatcher, which executes the second source and restores the
first context.

**Gate:** `tools/verify/verify_perky_dsp_b_pair.py` compares both PCM channels
and all 142 words of each context against independent solo calls, including
active interior transitions. A single aggregate meter is insufficient.

<a name="trap-native-block-clock"></a>

### A native sample block is not an OT audio block

The 20 October 2026 PERKONS placement campaign measured the existing CF
oscillator fallbacks at their original 48 kHz rate, including rational
conversion to 44.1 kHz and source packing. Earlier costs for rendering
16 native samples do not price a 16-sample OT block: native count, phase,
carry and event splits must be included. Correctness is checked separately
against the original renderers and the rational clock oracle. The integrated
WT/WT + Slap + Noise Hat row reaches 406.26 modeled us against 362.812 us,
despite small solo oscillator costs.

An initial diagnostic version also stored every native sample on the timed
target, charging unshipped observer work to the candidate. That version was
discarded; final timing disables target sample tracing and validates the
native shadow's trace independently. `verify_perky_cf_native_clock.py` covers
all phases/segment lengths; `measure_perky_cf_placement.py` checks target
PCM/state and native counts; `measure_perky_cf_placement_integrated.py`
measures the combined stock ISR. See the
[placement receipt](../../modules/perky/hybrid/CF_PLACEMENT_FEASIBILITY.md).
None of these local gates qualifies physical cache/card contention.

<a name="trap-hybrid-receipts"></a>

### A probe builder's success label is not qualification

PERKY Goal 2 recovery, 14 Oct 2026: the inherited builder wrote
`LOCAL_PROBE_QUALIFIED_HARDWARE_PENDING` into its notes before the workload
gates ran. The aggregate verifier required a TIMING file but did not inspect
its contents, skipped the retained-FX gate, and did not bind reports to the
generated image or recorded source commit. The existing DTIM3 counter used
88 MHz instead of the qualified 132 MHz, summed only PERKY callbacks, and
counted 60,630 groups during 27,563 real frames. Its zero misses could not
qualify whole-frame timing. The recovery initially called an ACK-to-ACK
measurement (98,632 modeled CF cycles, 370.797 us) an ISR duration. That
interpretation is **retracted**: `rtos.frameCycles()` also includes intervening
task work. New independent ISR entry/tail instrumentation, using the corrected
cycle clock and 132 MHz DTIM3, did reproduce a true overrun before optimization
(368.167 us). Two bit-exact CF control iterations reduced that same short case
to 315.871 us; the proposed 80% margin still fails. These are model observations,
not MKII timing or a complete workload bound.

The on/off comparison also exposed two instrument limitations. The port's
`--poke-before-play` takes **one byte and C integer syntax**, whereas a step's
`poke` takes a hex byte string. A four-byte switch needs four explicit byte
writes; verify the effective switch and resulting counter activity. Clearing
only the high byte leaves the loaded low-byte one enabled. Also, a PC watch
before the CPU step misses most first instructions entered by an interrupt in
that step. Watch the next instruction, establish one matched pair per frame,
and account for the omitted instructions. Never accept a zero overhead result
until both controls and coverage are observed.

Gate report contents, durations, active audio, source commit, image/tool
hashes, lifecycle and timer/export qualification before issuing a success
status. `verify_perky_hybrid_evidence_selftest.py` checks refusal of smoke,
stale-image, missing-audio, skipped-FX, missing-lifecycle, wrong-clock,
uncommitted-source and corrupted-artifact receipts. The hybrid remains
unqualified; those negative tests do not replace its missing positive gates.

The PKFM21 stock/CF pass also required binding what a standalone runner
actually loads. An ELF hash alone did not pin the Slap runner's `target.bin`
and `target.nm`. `verify_perky_slap_span_binding.py` reconstructs both from
the pinned ELF, privately replays the 2,880-frame / 76,880-case proof, then
checks the final helper relocation, caller and real boot readback. The packet
and stock DELAY bindings follow the same executed-binary rule. Their final
qualification refuses missing bindings; newly named profile buckets are summed
with their original owner before a stock saving is reported.

<a name="trap-bus-zero-client"></a>

### A bus client that registers but contributes nothing steals everyone else's level

**A BUS CLIENT THAT REGISTERS BUT CONTRIBUTES NOTHING STEALS EVERYONE ELSE'S
LEVEL.** The auto-gain divides the accumulator by the number of registered
clients, so a writer that registers unconditionally and then writes zero
dilutes the real senders by N/(N+1) — **−6 dB with a single sender.** Two
instances found the same day, 17 Aug: BusVerb registered for its `→DEL` send
even when `→DEL` was off (since gated on the knob, measured −6.02 → +0.00 dB;
the send itself was later retired), and BusDelay's own `IN` knob would have
done it too if its default
had stayed non-zero on a return track with no audio to send. **Gate the
registration on the knob, and remember the level knob is usually decoded
LATER in the block than the registration runs** — read it from `r6` directly,
or use the previous block's value and accept one block of latency. Symptom to
watch for: a level that is flat across sender count in one layout and drifts
in another. It surfaced as an "unexplained residual" in a completely
different effect's send level, and the effect being blamed was innocent.

<a name="trap-r7-scratch"></a>

### r7 scratch `$00..$83` is the per-instance block; `$84+` hangs the unit

**r7 scratch `$00..$83` is the per-instance block; `$84+` hangs the unit**
(a host track's own state lives there between calls, images 39–42). Each
module's header maps its own block; a slot census of the source is the
truth, not the map (23 Sep 2026: BusVerb's map said full and 14 slots had
no reference; BusDelay's map listed nine slots the code never touches, and
one it used twice — the PITCH decode's park on grain 3's scatter record).
New per-track state goes in a free slot of the module's own block or the
Y state table. (Do not scan for these with `"\$$s"` in a shell — it expands.)

<a name="trap-dump-alias"></a>

### A dump can resolve a perfectly plausible dispatch entry for an effect it does not contain

**A dump can resolve a perfectly plausible dispatch entry for an effect it
does not contain.** `SPEC=1` (which `make render` sets) aliases the absent
server's id to the SEND client — deliberately, so a wrong chooser pick
becomes a send. Locally that alias renders a dry passthrough: silence over
the bus, dry in a `--direct` control, no error anywhere. This produced the
12 Aug "BusDelay outputs nothing in any config" session — the delay was
never instantiated; every measurement ran a SEND. Delay work needs the
hatch (`make render-delay`), and `send_probe.py` now dies when a D layout's
DELAY entry equals SEND's. The general rule: before believing a *negative*
result, check which code the dispatch entry actually points at — same
family as "disassemble what you assemble".

<a name="trap-shared-window"></a>

### In the shipping remix, payload A's half of the shared window is fully owned

**IN THE SHIPPING REMIX, payload A's half of the shared window is FULLY
OWNED** (a remix without the reverb frees it, which is how the insert
collection has room to stack): stock's staging at `0x30000-0x30047`,
BusVerb's buffers at `0x30800-0x357FF` (its `Claims.dsp_ranges`),
stock's core 1 -> core 0 mailbox at `0x37F00-0x37F0F` (moved there from
`0x38000` by every build; `docs/firmware/DSP.md` section 5), bus
scratch at `0x36000-0x36157`
(grew 12 Aug for the DELAY send counts + reciprocal table, 17 Aug when the
accumulators went to FOUR buffers for the cross-core race fix, and 22 Sep
2026 to EIGHT buffers plus the chain at `0x360d8..`).
There is no free ground in it for delay lines — the DEV build places the
delay at its shipping base `0x38000` (payload B's half) for exactly this
reason. A delay based at `0x30000` sweeps the rotation word, all four ACC
buffers and both role locks every 16,384 samples and blows up any
multi-server layout (found 12 Aug, RDS full-scale garbage).

<a name="trap-fx2-id"></a>

### An FX2 id is also an FX1 id: the DSP dispatch tables are indexed by the raw id and shared by both menus

**AN FX2 ID IS ALSO AN FX1 ID: the DSP dispatch tables are indexed by the
raw id and shared by both menus.** A module on a stock effect's id replaces
that effect's code wherever it is selected, FX1 included, and a remix that
omits the module then aliases the id to SEND and takes the stock effect
away from FX1 too. Rungs sat on EQUALIZER's `0x0c` and Nimbus on DJ EQ's
`0x0d` from 29 Aug to 2 Sep 2026, in every local image, unflashed. The
schema now refuses `STOCK_FX2_IDS`; the stock effects themselves are kept
in a chooser by listing them in the remix (`tools/remix/stock.py`). The
same table makes FX1's NONE (id 0) run the FALLBACK's code: SEND ran on
every empty FX1 slot at r7 0x6100/0x6400/0x6700/0x6a00, sent from an
unseen page byte and, on core 1, compared the rotation tracker before
position 0's advance — one step ahead for good on the unit (images 40–47,
21 Sep 2026; `modules/send/README.md` "An FX1 slot is not a client"). A client keys its slot on r7, never
on X:$213 (stale at proc time), and `dsp_host` places FX2 slots at
0x6200 + 0x300·pos (`verify_twocore` had 0x200·pos until image 48).

<a name="trap-audio-block"></a>

### `dsp_host`'s default audio block (X:0x80) sits inside the scratch the stock effects use

**`dsp_host`'S DEFAULT AUDIO BLOCK (X:0x80) SITS INSIDE THE SCRATCH THE
STOCK EFFECTS USE.** On hardware the dispatcher passes `r0 = 0`: the audio
block is at X:0 and stock code scratches X:0x20–0xff every block. Our
modules never touch low X, so the default was harmless for months and then
made the stock FLANGER render as Nyquist-rate hash and five other stock
effects 5–17 dB dirtier while passing as "credible" (2 Sep 2026). Eight
instruction probes were spent clearing the emulator first. `send_probe`
passes `-audio 0` for a stock render; if a stock effect sounds wrong
locally, suspect the harness before the effect.

<a name="trap-stock-tables"></a>

### An absolute stock-table address is right in payload A and 13 words off in B, and the audition render cannot show it

**AN ABSOLUTE STOCK-TABLE ADDRESS IS RIGHT IN PAYLOAD A AND 13 WORDS OFF IN
B, AND THE AUDITION RENDER CANNOT SHOW IT.** The payloads are linked
separately: the 6,305-word curve bank is `X:0x438` in A and `X:0x42b` in B
(the block below it is 23 words on A and 10 on B), and the Y tables shift by
16. Stock code carries a different extension word per payload; a module is
one source assembled into both, so a bare literal into a stock table is
correct on tracks 5–8 and mistuned on 1–4, and past the end of the relocated
table it reads garbage. Bryan T's LOFI2 shipped that way through a week of
renders and several flashes (13 Sep 2026, `docs/firmware/TABLES.md`
"Payload-relative addresses";
measured here from our own image). `send_probe`'s single-payload render dumps
payload A. Declare stock table addresses so the build rewrites them per
payload, or read through a build-supplied base; and audit any stock-table
read on BOTH payloads under `rig_render.py`. Our own modules were scanned
14 Sep 2026 and read none.

<a name="trap-lfo-word"></a>

### A knob word under an LFO is not a clean word: bits 8-15 are non-zero, and no local render writes them

**A KNOB WORD UNDER AN LFO IS NOT A CLEAN WORD: BITS 8-15 ARE NON-ZERO, AND
NO LOCAL RENDER WRITES THEM.** Each ColdFire halfword is one DSP word `<< 8`,
and the firmware's LFO store (`movew %d0,%a1@` at `0x4000d07a`,
`docs/firmware/LFO.md` section 5) writes the modulated value with its low byte
free. Measured under the port (`ot_emu --watch-pc 0x4000d07a`, bottleservice
with `tools/harness/stress_project.py`, 24 LFOs per part, depth 18-28 on
FX1/FX2 knobs, 900 frames, 5 Oct 2026): 21,088 stores, 21,011 with a
non-zero low byte (e.g. `d0 = 0x22fe` for knob 34); 147 stores had knob
byte 0 and all 147 carried a non-zero low byte (largest knob byte seen
0x7d), so a knob at 0 under an LFO is not a zero word. The gate project at
LFO depth 0: 19,843 stores, all with a zero low byte. A knob at rest is
clean; `dsp_host -params` takes 0..127 and writes clean words, so no render
shows it. Two modules read the raw word: WAVE's `asr #$10` on OCT left a
remainder in b0, `neg b` borrowed from b1 (one octave off at any OCT) and at
OCT 4 `do n3` ran with LC = 0xffff (65,535 `asr` a block); SEND's
registration `tst` on the raw DEL/REV word counted a track at knob 0 as a
sender (N/(N+1) dilution of every other sender, -6.02 dB with one). Rule:
mask a page word with `and #>$7f0000` before any shift, compare, select or
`tst` use (the form the servers, Spectrum and BusVerb use); the
`asr` then leaves a clean low word. After `and`, store from `a1`/`b1`
(`move a1,x:`), not `move a,x:` (the A2-staleness trap above). The
`dsp_host -pword k:off=hex` option writes a raw word after `-params`, and
`verify_wave` / `verify_onebus` render dirty words.

<a name="trap-name-nul"></a>

### A descriptor name that exactly fills its field leaves no NUL, and the crash lands somewhere else entirely

**A DESCRIPTOR NAME THAT EXACTLY FILLS ITS FIELD LEAVES NO NUL, AND THE
CRASH LANDS SOMEWHERE ELSE ENTIRELY.** `abbr` is a 5-byte field holding FOUR
characters plus a terminator; `fullname` is 13 bytes holding TWELVE (and the
build tag is appended after your string). A 5-character abbr assembled,
built, drew correctly on the panel and behaved normally under manual knob
use — and threw a line-F exception (VEC:0B) the moment a parameter was
**LFO-MODULATED**, faulting PC `0x48454C4C` = `"HELL"`. It presented as
"custom effects can't be modulated", which points at the clone mechanism,
not at a string. Found 2 Sep 2026 by Bryan T contributing `modules/hello/`,
after the build accepted it silently. A faulting PC made of the field's own
ASCII is a smashed return address, so the copy destination is fixed-size —
INFERRED, the copy is not located; the rule itself is measured (all 30 stock
page descriptors are ≤4 chars with byte 5 zero). `schema.MenuEntry` now
refuses both over-lengths and `build_bus.py` re-checks the string it writes,
tag included — which caught two diagnostic delay names (`BusDlyRPLY`,
`BusDlyNOCF`) that had been filling all 13 bytes since 24 Aug 2026.

<a name="trap-part-layout"></a>

### A part saved under an older slot layout feeds the new layout its old bytes, and the sequencer stalls on the first play

**A PART SAVED UNDER AN OLDER SLOT LAYOUT FEEDS THE NEW LAYOUT ITS OLD
BYTES, AND THE SEQUENCER STALLS ON THE FIRST PLAY.** Moving MODE from slot 7
to slot 6 (4 Sep 2026) passed every local check and both hardware claims —
then pressing play went 1, 2, 1 and froze, because every other track's part
still held a 0–127 SHMR/MDEP byte in what was now a count-3 select, the
"value outside its count is used as an index" trap in stored form. The
schema cannot see stored data. Re-selecting the effect on the track you are
looking at is NOT enough; the sequencer runs every track of the part. After
any change to a slot's count, position or meaning: `tools/hw/ot_project.py
stamp-defaults <project> <remix>` on the card BEFORE play, and say so in the
flash notes. (Cause inferred from the symptom and a refreshed project
running clean; not measured.) Measured against it under the port (6 Oct
2026): stock's Part validator `0x40002318` rewrites every FX page byte
outside its descriptor's `[min, min + count - 1]` to the nearer end during
the load, in all 16 banks x 8 Parts (`tools/verify/verify_brain.py`, "stock
clamps"), so a stored byte loaded from the card does not reach play outside
its count; and with such bytes stamped, the page drawn and the DSPs
running, the sequencer advanced as on a clean project. What stalled the
unit is open; the stamp before play stays the rule.

<a name="trap-otemu-part"></a>

### The part the emulated load applies is not the part that plays

**THE PART THE EMULATED LOAD APPLIES IS NOT THE PART THAT PLAYS.** `ot_emu`'s
load applies bank 1 part 1; its transport start re-applies the SAVED bank's
pattern part and the refresher at `0x4000c19c` rewrites the live lane from
it. A fixture that edited "part 1 and its saved copy" measured a track whose
FX2 was still SEND — for a whole O9c session (8 Sep 2026): "the THRU monitor
is pre-FX2", "the page-2 select never crosses" and "X:0x2c0 is the FX2
instance" were all this one fixture, and the last was `stamp-slot` landing in
the track's FX1 (it stamps both slots). Write fixtures into EVERY part of
EVERY bank (`ot_project.py set-fx`, `stamp-slot`), and before believing a
DSP-side "byte-identical" between two cards, run both with `--block-dump`
and `tools/harness/blockdump.py diff`: if no host-port block differs, the
cards did not differ where it matters.

<a name="trap-dispatcher-model"></a>

### The harness's model of the dispatcher is not the dispatcher

**THE HARNESS'S MODEL OF THE DISPATCHER IS NOT THE DISPATCHER.** `dsp_host`
handed every effect r7 = 0x6100 + 0x100·(2·pos + fx−1); the stock
dispatcher bumps r7 THREE times per track (the third unconditional, after
FX2), so from position 1 on every r7 the harness used was wrong, and two
modules that pinned a track by its r7 (the one-aux return on T8, the
track-8 send refusal) matched in the harness and never on the unit — flash
6's "the return never reaches T8", with `make verify-onebus` green on
exactly that property. Found 8 Sep 2026 by running the shipping image from
the card under the ColdFire port (`git show 3ceba41:docs/history/COLDFIRE_PORT.md` O11). Any module
logic keyed on a dispatcher fact (r7, r6, X:0x213, instance blocks) is
measured under the port (`ot_emu --dsp-pcwatch`), never modelled in
`dsp_host`; and a hardware failure the lock-step harness cannot show goes to
the port before it goes to a guess.

<a name="trap-init-r1"></a>

### An effect's `init` must preserve r1: the FX1 dispatcher keeps the effect id there across the init call

**AN EFFECT'S `init` MUST PRESERVE r1: THE FX1 DISPATCHER KEEPS THE EFFECT
ID THERE ACROSS THE INIT CALL.** `P:0x4c8..0x4d7`: `move b,r1`, `jsr
INIT_TABLE[r1]`, then `move x:(r1+$235),r2 / jsr (r2)` for proc — so an init
that returns with r1 moved sends the proc call through a garbage word to
P:0 = the reset vector, and the core dies AT PROJECT LOAD, before a frame.
Image 99 (13 Sep 2026) did this on every core that loaded a Spectrum on FX1:
its new init zeroed 24 state slots with `move a,x:(r1)+`. It looked like the
step-1 DSP hang and was found under the ColdFire port's last-PC ring in an
hour; `dsp_host` cannot see it because it calls init and proc itself and
never reads r1 between them. Proc may use r1 (the dispatcher reloads it
after proc). `tools/verify/verify_initregs.py` refuses an init that writes
r1/n1/m1 and runs in `make check`. Zero through r5.

<a name="trap-knob-publish"></a>

### A parameter slot can draw a knob and publish nothing

**A parameter slot can draw a knob and publish nothing.** The page descriptor
and the DSP-side read are separate mechanisms; `dsp_host` pokes r6 directly, so
everything looks live locally even when the real unit would publish nothing.
See `docs/firmware/PARAM_PAGES.md`.

<a name="trap-flash"></a>

### Flash cycles are expensive

**Flash cycles are expensive** — each one is a manual firmware write. Render
locally and measure instead of guessing. This is why the emulator path exists.

<a name="trap-failure-modes"></a>

### When the unit misbehaves, check `docs/contributing/FAILURE_MODES.md` first

**When the unit misbehaves, check `docs/contributing/FAILURE_MODES.md` first** — the
register of hardware failure modes (symptom -> cause -> fix). Add any new one
the moment it is seen; do not let it live only in a commit message.

<a name="trap-dirty-state"></a>

### A persistent slot that init does not clear holds whatever the effect before ours left in the block

**A PERSISTENT SLOT THAT INIT DOES NOT CLEAR HOLDS WHATEVER THE EFFECT
BEFORE OURS LEFT IN THE BLOCK — AND NO LOCAL RENDER CAN SEE IT, BECAUSE THE
PORT AND `dsp_host` BOOT ZEROED RAM.** Spectrum's init cleared `$00..$17`;
filter B's two HP poles at `$38/$39` (`$3c/$3d` R) sat at cHP = 0 on the
passthrough stamp, FROZEN, and `hp2 = yB − h2` subtracted a stale h2 from
every sample forever: up to a full-scale DC on a station's output. An
AC-coupled capture cannot see DC, so it surfaced as something else entirely
— "the master compressor collapses the RIGHT channel above COMP 40" (the
makeup clipped DC + audio to a constant on the channel whose offset was
larger) — and cost 13–14 Sep 2026: three diagnostic images and 40 hardware
taps rewriting a compressor block that was correct. Found by a LEVEL bisect
across the tracks (post-FX mute cleared it, pre-FX mute did not: the station
made it from state), then reproduced in one run once the instance block was
pre-filled with garbage. Rules: (1) init zeroes EVERY slot the sample loop
reads before it writes — `tools/verify/verify_dirtystate.py` (in `make
verify`) renders each module from a garbage block on silence and refuses any
output; (2) a channel-asymmetric failure in channel-symmetric code is a DATA
asymmetry — go looking for what the instrument cannot see (DC, ultrasonics)
before rewriting the code; a limiter ladder (×2/×4/×8 with the limiting
store) makes DC visible through an AC-coupled capture; (3) when "which knob"
does not localise a fault, "which TRACK" (LEVEL 0 per track, then AMP VOL vs
MUTE) does.

## Traps on the ColdFire / DRAM side (the platform work, 9–10 Sep 2026)

<a name="trap-watch-alias"></a>

### A write-watch on cached addresses is blind to a clear through the uncached alias

**A WRITE-WATCH ON CACHED ADDRESSES IS BLIND TO A CLEAR THROUGH THE UNCACHED
ALIAS.** The port mapped `0x4F...` as separate memory, so a watch on
`0x477...` reported "8.8 MB free at 0x47700000" — the region is the stock
delay's eight rings, cleared via the alias ~38 M instructions after the boot
detour returns (Bryan's write-up had the ring base as `0x4F502C10` all
along). Retracted; `machine.h` now folds the alias. The general rule is the
instrument-blindness one: before trusting a null result, ask what the
instrument physically cannot see, and check whether a second reading
(here, Bryan T's delay write-up, `docs/firmware/COLDFIRE_DELAY.md`) already
contradicts it.

<a name="trap-boot-verifier"></a>

### The boot verifier booted the wrong image

**THE BOOT VERIFIER BOOTED THE WRONG IMAGE.** `make verify` runs after the
selftest, which builds every remix in turn and leaves the LAST one at
`out/mainos_bus.bin`; the first in-pipeline run booted `warped` looking for
midi-scenes' loader and reported "loader ran 0x". `verify_dram_boot` now
rebuilds its remix first. Any verifier that reads `out/` must know who wrote
it last.

<a name="trap-pipe-exit"></a>

### `make … | grep | tail` reports tail's exit code, not make's

**`make … | grep | tail` reports tail's exit code, not make's.** Capture
with `> log; echo $?`.

<a name="trap-gnu-as"></a>

### Matching an author's bytes with GNU as

**Matching an author's bytes with GNU as:** a same-unit label makes `lea`
assemble PC-relative (write `lea SYM:l`); small `move.l #imm` becomes
`moveq`; a `-Ttext` that is 2 mod 4 gets a leading `nop`. All correct code,
all oracle failures.

<a name="trap-cf-live-alignment"></a>

### ColdFire alignment padding can execute as zero halfwords

**A live `.balign 4` broke an otherwise exact Slap delay loop (21 Oct 2026).**
The current m68k GNU assembler inserted `0x0000` at a fallthrough between a
conditional branch and the intended loop. Assembly and linking succeeded;
the native/ColdFire PCM comparison failed. This occurred only in the rejected
isolated `slap-fixed-v4` experiment, never in PKFM16/PKFM17.

Use explicit instruction fill, `.balignw 4,0x4e71`, when execution can cross
the padding, and inspect the final disassembly. The corrected v5 passes
2,880 native PCM/full-state frames and 38,440 ring/ABI cases, but its measured
cycle regression still excludes it from the candidate. The negative log and
disassembly remain at `out/perky/hybrid/slap-fixed-v4/`; the actual execution
gate is `tools/verify/verify_perky_slap_fixed.py`.

<a name="trap-loader-regs"></a>

### A loader draft clobbered d0 across its copy loop and reused a0 after the hash

**A loader draft clobbered d0 across its copy loop and reused a0 after the
hash.** Register discipline in a boot stub is not checkable by anything but
the port: `verify_dram_boot` watches the loader's entry and its `fatal` hang.

<a name="trap-tmp-race"></a>

### Two builds on one machine corrupted each other through fixed `/tmp` names

**TWO BUILDS ON ONE MACHINE CORRUPTED EACH OTHER THROUGH FIXED `/tmp`
NAMES (10 Sep 2026).** `build_bus.assemble()` wrote `/tmp/build_bus_src.asm`,
`.bin` and `.sym` by fixed name, so two sessions' `make check` — or the
selftest's per-remix builds beside anyone else's build — read each other's
assembler output: "STREAMZ overruns the region (2883 > 2724 words)",
"selprobe dsp_asm exit 1", a different remix each time, on a clean checkout
too. Found by a peer session. Scratch is `tempfile.mkdtemp` per process now
(`verify_hello` likewise). A failure that moves between remixes across runs
is a shared-scratch race before it is anything else; and a `make check`
result taken while another build was running is not a result.

<a name="trap-stock-callee"></a>

### A module that replaces a stock routine can make every other caller of it a halt

**A MODULE THAT REPLACES A STOCK ROUTINE CAN MAKE EVERY OTHER CALLER
OF IT A HALT.** Em's Octakit (in octabam until 6 Oct 2026) repointed the
three stock calls to the page-1 writer `0x40054cd8` at her wrapper and
made the writer's dirty store check a token above its arguments; TEMPO
BUS and MODE DEFAULTS called the writer bare, so `bottleservice` halted
under the port at frame 40 of `verify_set` on the first CC 68 (26 Sep
2026; never flashed). Before calling a stock routine from a module, diff
the routine and its callers against stock in the built image
(`tools/build/where.py`): another module may own it.

<a name="trap-fork-shm"></a>

### A forked port shares its DSP memory with its siblings unless it is unshared

**A FORKED PORT SHARES ITS DSP MEMORY WITH ITS SIBLINGS UNLESS IT IS
UNSHARED.** The vendored DSP memory is a `shm` object mapped `MAP_SHARED`
several times (the bridged X/Y/P views, `dsp56kBase/mmuhelper.cpp`), so
`fork()` gives every child the same DSP memory: the first `--scenario`
run (29 Sep 2026) faulted a core in two of three children, PC outside P,
while the third ran clean. `unshareRanges` in `tools/emu/ot_emu/main.cpp`
copies each backing object into a private one after the fork. Anything
new the port maps shared (a window, a ring for the host) needs the same
treatment, or the children interfere and the failure moves between runs.

<a name="trap-rosetta"></a>

### The port ran under Rosetta in every shard, and nothing said so

**THE PORT RAN UNDER ROSETTA IN EVERY SHARD, AND NOTHING SAID SO.** `make
reach` and `check_shards.py` run under `python3`; on this machine that is
Intel Homebrew's (`/usr/local/bin`), and under it `uname -m` and
`os.uname().machine` both say `x86_64`, so cmake built an x86_64 `ot_emu`
that ran translated: 1.27x slower to the handoff, 1.75x on DSP frames
(6 Oct 2026, both binaries side by side under the same load). The
Makefile's `HOST_ARCH` and `check_shards.host_arch()` ask the kernel
(`sysctl -n hw.optional.arm64`, the same answer under Rosetta; Linux keeps
`uname -m`). `file out/emu/ot_emu` is the check; `make check-asm` prints
the binaries' architecture.

<a name="trap-report-api"></a>

### The report is API, and it prints paths

**The report is API, and it prints paths.** Moving a tool changed the build
report (the hints name `tools/harness/send_probe.py`), which refhash
correctly flagged with every artifact identical. Re-save only after proving
the artifact lines match.

<a name="trap-cf-engine-invariants"></a>

### A CF optimization assumed initialization values never change

On 14 Oct 2026, the hybrid foundation's unchanged Resonant reference gate
failed at snare sample 1. Commit `77b2cadf` removed bypass handling because
init wrote zero, but the control updater writes bypass from DECAY. Commit
`2f4f324e` similarly removed signed decay handling, although the trigger writes
three nonzero signs. Restoring both behaviors passed 1,536 continuation samples
and 3,072 fresh/continuation samples plus 24 state stages. Trace all control,
trigger and render writers before declaring a field invariant. The original
firmware captures and hashes stayed unchanged; `verify_perky_cf_resonant_dsp.py`
executes both gates. These are CF renderer fixes, independent of frozen PERKY4S. The
broader original-ARM gate also caught an omitted WT mode flag, four constructor
words and one new-target update; a retained snare noise floor on the finite
DECAY branch; and separate Resonant control caches where the original shares
one history across three objects initialized at note 63. Mode changes must run
the original old-mode and new-mode updates before committing targets.
`verify_perky_hybrid_original_profiles.py` checks control grids, mode/family
retention and long release tails against the original executable, preserving
its capture hashes. A renderer-only snapshot test cannot detect preparation
or wrapper-history defects.

<a name="trap-cf-inline-options"></a>

### GCC option scopes can outline every sample-loop primitive

On 16 Oct 2026, the current hybrid's target disassembly contained calls to
endian loads, multiply-low, shifts and sign casts inside each sample loop.
GCC 16.2.0's `-fopt-info-inline-missed` identified `optimization level attribute
mismatch`: local `no-unswitch-loops` scopes gave callers different options from
their helpers. Native host speedups had not established ColdFire improvement.
Moving or removing the conflicting scopes restored inlining without changing
the arithmetic. In a matched 4,096-frame snare/snare fixture, the first corrected
candidate reduced executed full-ISR maximum from 85,902 to 73,599 modeled cycles
at 264 MHz (325.386 to 278.784 us). Those are emulator observations, not silicon
bounds. The frozen PCM/state/RNG stream and 22,270 target edge calls stayed exact.

`tools/verify/verify_perky_hybrid_inline.py` now compiles the actual WT/Resonant
translation units and rejects option-mismatch diagnostics, with a deliberately
conflicting scope as a negative control. The campaign's raw target disassembly,
compiler diagnostics, matrix and edge receipts are under
`out/perky/hybrid/campaign-20261016/`. Removing the mismatch does not prove every
remaining out-of-line function is undesirable; retain measured function splits.

<a name="trap-cf-pcm-endian"></a>

### Native-endian decoded PCM is not an ARM table

The PKR1 decoder returned native `int16_t` samples, but the WT renderer reads
ARM little-endian table bytes. A host round-trip passed; execution on ColdFire
found 199,516 differing bytes out of 200,704, all explained by swapping each
sample's two bytes. `pk_cf_rice_unpack_le` now serializes successful decoder
output explicitly. The target foundation gate compares all decoded bytes to
the SHA-pinned original assets. Neither the stream nor the reference changed.

<a name="trap-cf-ready-bss"></a>

### A BSS readiness flag can skip initialization

The platform loader does not zero BSS. `static uint8_t pk_final_pcm_ready`
was emitted as `.comm` even with `-fno-zero-initialized-in-bss`; an arbitrary
nonzero boot value could skip WT decoding. The CF adapter now uses a nonzero
loaded `.data` COLD cookie, sets READY only after successful decoding, and
refuses rendering on decode failure. The target probe poisons BSS before
initialization. The compiler also disproved the old generic-engine arithmetic:
actual m68k layout is 118,096 bytes, not the inferred 118,200. The old 256-byte
stack ceiling was unsupported. The initial two-voice diagnostic observed 456
bytes; the completed transition-aware probe observes 460. Neither observation
is a full-machine stack ceiling.

The hybrid's loaded cookies did not initialize inherited native control BSS.
A stale valid smoother with matching Bank/Part and engine family bypassed lazy
invalidation and changed the first split native record. The hybrid boot initializer
now clears that control/prefix/trigger/UI history before RTOS handoff; native
arithmetic and DSP bytes stay frozen. `verify_perky_hybrid_cold_safety.py` injects
poison at the real loader-to-initializer call, including a matching stale tuple,
then compares native records, initialized state and all decoded PCM to clean boot.
The failing pre-fix receipt remains in the post-closeout safety evidence.

On 16 Oct 2026, the complete BSS scrub exposed the inverse problem on repeated
boot initialization: decoded PCM was zeroed while its loaded `.data` cookie
remained READY. The baseline and optimized image both lost all 199,191 nonzero
PCM bytes on a second call. Invalidate the loaded PCM/runtime cookies before
scrubbing BSS, then decode and publish readiness again. The runtime gate now
compares all 200,704 PCM bytes across repeated initialization. This was measured
under Unicorn; it is not evidence for the cause of a physical first-boot hang.

<a name="trap-cf-odd-base"></a>

### An odd displacement can have an even effective address

The Goal 1 narrow CF benchmark hoisted `lea voices+679,%a3`; a subsequent
`move.w` at `935(%a3)` accesses `voices+1614`, which is even. Applying the
production conservative odd-displacement gate to this different translation
unit falsely rejected valid code. The production audit remains required.
The diagnostic gate additionally calibrates both word/long read and write
watches with even and deliberately odd addresses, then rejects any actual
odd effective access during target calls. Readback outside target execution
is excluded. This proves the exercised paths, not unseen compiler paths;
never equate displacement parity with effective-address parity without
establishing the base alignment.

<a name="trap-static-fixture-markers"></a>

### A STATIC fixture can play a tiny region without streaming

The 16 Oct 2026 PERKY footprint probe initially reused the FLEX marker offset
when staging STATIC slot 1. The file contains 136 FLEX records before the 128
STATIC records; the untouched zero STATIC record became a 64-sample region.
All three stock tracks emitted audio, so a nonzero-audio check passed, but no
ATA reads occurred after PLAY. That run does not qualify STATIC streaming.
`verify_repitch.py` already encoded the correct offset. The hybrid fixture now
uses it, reports source activity in successive windows, and records ATA logs
before and after playback. Its corrected seven-track 4096-frame probe issued
411 playback READ commands / 1236 sectors and sustained stock source audio.
This exercises unchanged stock code; the immediate-response PIO card model
still cannot qualify silicon card/DMA/cache contention.

<a name="trap-automap-read-watch"></a>

### Auto-grown emulator pages bypass data read watches

The standalone CF benchmark loaded assets at `0x44000000`, outside its initial
declared mappings. Auto-growth supplied correct bytes, but `read*Slow` called
the read watchers only for declared regions. An all-address watcher therefore
reported zero asset reads while table synthesis worked. Explicitly map the
benchmark asset region before loading it. The resource observer calibrates
all three access widths and a line-crossing access, then requires unchanged
PCM/state/RNG and every modeled cycle/instruction/stack row against the frozen
unobserved run. Also separate reads within executable text: this instrument
observes instruction-stream words too. These are architectural requests and
address working sets, not measured cache misses or SDRAM transactions.

<a name="trap-observer-timer-read"></a>

### A host timer observation can change emulator scheduling

The 16 Oct 2026 full-IRQ observer first read DTIM3 through `Machine::read*`.
These reads did not alter target RAM, but set the peripheral-touch flag used
by the run loop's batching decisions. The raw firmware profiler dump differed
from the unobserved run. Such an observer is not passive timing evidence.
`observeDtim3` now whitelists only the three const DTIM3 registers and bypasses
target touch flags and trace logs. Synthetic controls cover both stepping
paths, nested IRQs, elapsed idle, invalid timer mode and unsupported addresses.
The corrected seven-track 4096-frame comparison matches raw profiler bytes,
all decoded profiler counters, ACK CPU/DSP metrics and playback card reads.

The same audit found a separate scope error: the original port enabled cycle
time after `startTransportLive`, while IRQ/profiler/ACK counters also counted
startup audio. Requested transport frames therefore differ from total IRQs;
their totals must agree independently, rather than use an assumed offset.
The opt-in `--cf-cycles-clock-before-transport` enables cycle time before audio
starts. Default behavior remains exact against the saved pre-change binary.
Earlier startup-inclusive timing maxima retain this clock-transition caveat.

<a name="trap-shared-predictor"></a>

### Two target instances can share branch-predictor history

The retained MCF5445x model's BHT/BTB arrays and counters are globals outside
`m68ki_cpu_core`. The first two-image PERKY callback comparator alternated
machines without switching that history. A same-image control disagreed on
cycles in 24,717 of 25,600 callbacks. Profiler-off instruction counts matched;
248 profiler-on callbacks also differed because diagnostic maximum-update
branches respond to the timing. Exact synthesis/state/RNG remained equal.
Those paired timing claims were withdrawn. Single-target synthesis benchmarks
and single-Machine full-OS processes were unaffected.

Keep independent predictor arrays and counters per compared target, restoring
them before execution and saving them afterwards. Calibrate cold and trained
states, require every same-image cost/resource/branch row to agree, and require
an image's cost rows to remain identical with a different comparison partner.
This repairs host measurement state; it neither changes firmware nor models
physical cache or SDRAM latency.

<a name="trap-panel-cycle-clock"></a>

### An interactive run can accept an inactive cycle-clock flag

The 16 Oct 2026 second-CF admission probe found that `--cf-cycles-clock`
and `--cf-cycles-clock-before-transport` are applied in the sequencer batch
branch. Merely passing them to an interactive panel session does not activate
that clock. Earlier panel captures remain useful for state, audio and stack
ownership; their firmware-timer values are not uniform-cycle timing evidence.
Executed CPU work counts retain their stated input/cadence scope.

The checked workaround is `--sequencer --frames 1` before interactive control,
with the startup-clock flag. Require the actual activation line from stdout.
`PortProc` retains stdout in its log deque; its `log_path` receives stderr.
The positive first-admission captures and the interactive-only negative
control are under `out/perky/hybrid/footprint-20261016/`. The reusable panel
activation probe checks clock activation before accepting timing results.
This changes local test setup, not stock firmware or default port behavior.

<a name="trap-source-control-record"></a>

### DSP source records contain controls, not rendered PCM

The same campaign's first panel audio checker treated T1/T5 source records
like CF PCM and reported silence. Their native DSP producer sends control
records; the DSP generates the waveform. Check post-FX read-back for DSP
voices. For CF and sampler voices check both source PCM and post-FX output.
The retained panel probe validates all seven tracks with the appropriate
instrument; no audio work was omitted to satisfy the check.

<a name="trap-panel-quit-reports"></a>

### A panel's quit reply precedes its final reports

`MenuPort.__exit__` receives `ok` before the child closes observer streams.
An immediate read can therefore report missing stack JSON even after a
successful capture. This cost a second admission-probe analysis attempt.
Wait for normal child exit, then require complete reports and matching
frame/return/private-switch totals. Preserve and revalidate an already
completed capture instead of executing the UI sequence again.

<a name="trap-long-irq-peripherals"></a>

### A long DSP interrupt can stop the emulator's peripheral clock

The 20 October Noise Hat offload first stalled after one host reply word.
The interpreter switches long-interrupt dispatch to `dspExecNop`, so the
normal peripheral service does not run until RTI. A real peripheral keeps
running while the core polls HTDE. The isolated observer explicitly invokes
the existing timed peripheral callback during long interrupts; the default
port and vendor sources remain unchanged. A negative control disables this
callback and must stall on the same request that passes with it enabled.
This repairs progress in the instrument; it does not qualify DSP wall time
or physical transfer latency. See the [prototype receipt](../../modules/perky/hybrid/NOISE_HAT_OFFLOAD.md).

<a name="trap-hi08-halfword"></a>

### An HI08 halfword also writes the preceding byte lane

The same prototype initially truncated packet high bytes. On the stock
16-bit host bus, the halfword addressed to TXM covers TXH:TXM and the one
addressed to TXL covers TXM:TXL. Write `value >> 8` followed by `value`, each
as a halfword; a CVR write must also preserve its adjacent ICR byte. The
stock level-6 transfer ISR shares GPIO selection and this host port: preserve
the selector/ICR, mask competing transfers, and return an already pending
stock HOTX word before releasing ownership. The executable IRQ-wire gate
checks nonzero high bytes, both pending-word states and all saved registers;
the combined stock audio gate remains necessary and catches the pulse-row
regression despite exact Noise Hat output. Watching the IRQ's entry PC was
also blind because interrupt dispatch consumes that instruction internally;
the integrated gate watches the next instruction at entry + 2.

<a name="trap-dsp-lazy-ccr"></a>

### Raw DSP SR storage can contain unresolved condition flags

The 20 October pulse investigation first reported N changing across an IRQ
whose renderer/register wire checks passed. The interpreter defers condition
code calculation: `regs().sr` can contain an old N bit. Compare `getSR()` at
both architectural boundaries before accusing the firmware. The corrected
live witness sees zero register changes; the old N-change claim is retracted.
This resolves interpreter bookkeeping without adding target instructions.

<a name="trap-amp-dropout"></a>

### Stock source PCM can disappear before FX despite exact synthesis

The blocking Noise Hat pulse row had active sampler source PCM, exact Noise
Hat state/PCM and preserved loaded P, yet T4/T7/T8 failed post-FX audio.
Live DSP taps place the loss between source and FX1, in stock AMP. Clearing
all DSP RAM removes it; clearing the four AMP phase words or even their
32-word blocks does not fully remove it. Dirty AMP history alone is therefore
not a proven root cause. Keep the failed counterfactuals and the open startup
question, and require all source/AMP/FX paths instead of weakening the audio
gate. The [cooperative follow-up](../../modules/perky/hybrid/NOISE_HAT_ASYNC.md)
passes its tested dirty-start rows but does not establish arbitrary startup
or silicon acceptance.

<a name="trap-host-dma-upper-byte"></a>

### Stock host DMA words retain a nonzero upper byte

The first resident Noise Hat parser rejected every live marker although its
isolated clean-word gate passed: the target received `0x034e52`, not `0x004e52`.
HI08's retained upper lane survives the stock DMA. Mask every 16-bit field,
including markers, lengths, patch addresses and values. A high byte on an
address can redirect an otherwise private write into the shared window.
The persistent parser gate now poisons the upper byte of every packet word
and executes a control patch before comparing original ARM PCM and state.
The failed live run does not establish a bank-handshake defect; that initial
attribution is retracted. See [resident evidence](../../modules/perky/hybrid/NOISE_HAT_RESIDENT.md).

<a name="trap-delayed-source-split"></a>

### Delayed PCM must still match the current source-packet split

A pipelined source packed its delayed audio as one segment while the stock
parameter record retained a changing split. The DSP unpacker consumes the
current split's packet layout. Pack the delayed samples using that current
split, and preserve the historical event boundary separately for synthesis
and clock conversion. Delaying audio does not permit changing the stock
source framing contract. The integrated resident workload retains actual
locks and verifies source plus post-FX audio on every track.

<a id="trap-dma-halfword-a2"></a>
## A masked DMA halfword can keep a stale accumulator extension

**20 Oct 2026, current-frame Noise Hat tap prototype.** Stock source DMA leaves
upper eight bits in its DSP words. Masking a 16-bit patch count with `and`
cleared B1 but retained a negative B2. A following `DO B` consumed the stale
extension. A persistent test with upper-byte poison exposed it before timing
qualification. Reload `move b1,b` after masking a count, and `move a1,a` before
using a masked field as an accumulator operand or comparison. Moving only A1
into an address does not repair later uses of the accumulator. This is the
DMA-parser instance of [the logical-op extension trap](#trap-a2-stale).
`verify_perky_noise_hat_taps.py` poisons every field, varying the upper byte
across frames and both signs, and checks source PCM, state and feedback.

<a id="trap-rational-approximation"></a>
## A fractional interpolation table can differ from rational division

**20 Oct 2026, current-frame Noise Hat tap prototype.** The existing DSP clock
uses `floor(phase*2^23/147)` and a fractional multiply. Its original gate
explicitly permits one source LSB; it is not an exact integer division by 147.
A longer Noise Hat case produced 9023 where the independent rational oracle
requires 9024. Do not promote the old tolerance into a bit-exact claim.

The tap prototype retains the table as a quotient estimate, computes the exact
integer residual `D*phase-147*q`, and corrects the quotient once. Since
`D=32*(b-a)` and both samples are signed16, the estimate error is less than one.
The complete current-source gate now requires equality, with no LSB tolerance.
The shipping adapter and its declared tolerance are unchanged. See
[the experiment](../../modules/perky/hybrid/NOISE_HAT_TAPS.md).

<a id="trap-cf-host-abi"></a>
## Host structure offsets do not describe a ColdFire object

**20 Oct 2026, Noise Hat lifecycle witness.** A new fallback observer used
host `sizeof(pk4_track)` to locate target V4. The host object was 29,548 bytes;
the loaded ColdFire layout record says 29,522. Two-byte target alignment makes
each of thirteen controls two bytes smaller. The observer's ABI guard aborted
before producing a false audio result. This was an instrument defect, not a
firmware failure. Describe target bytes with the target ABI and check against
the loaded layout record. Pointer-width-dependent engine fields must use
target offsets too. The isolated lifecycle offset helper uses two-byte packing
only in its metadata TU; the original host oracle keeps its normal ABI.
ColdFire-only calibration must pass before attributing fallback differences.

<a id="trap-idle-return"></a>
## A detoured idle loop can contain real work

**20 Oct 2026, PKNHF1 handoff.** The background native shadow initially never
ran after project loading. `callAsMain` returned every borrowed call to the
stock `g_mainSpin`, abandoning the image's detoured main loop. Preserving the
actual parked return PC fixes that. The idle detector also included the
prologue's `jsr 0x40098a2c`, allowing main's final initialization to be skipped;
strict boot readback caught descriptor changes. Exclude that known six-byte
call from the idle range. The probe pads the loop's reserved range so following
renderer functions cannot be mistaken for idle code.

A worker loop must not be fast-forwarded while work is published. The isolated
handoff port checks the actual CF producer/consumer words before idle skipping;
it executes every worker instruction and supplies no target writes, virtual
completion or timer charges. Gate boot readback and actual project loading,
then require worker progress, zero queue overflow, bounded sustained backlog
and completed ownership transitions. A timely audio ISR alone cannot prove
that an idle worker keeps up: the first full-delay shadow fell behind in
metallic mode even with zero audio deadline misses.

<a id="trap-event-boundary"></a>
## Frame-entry controls may not be the controls that render

**20 Oct 2026, PKNHF1 continuity oracle.** A persistent original-author witness
computed a complete frame from controls read at source entry. A diagnostic mode
poke could arrive while that callback was in flight, before its real
`prepare_nh` call. The target correctly rendered its suffix with the new mode;
the oracle incorrectly used the old one, then carried the wrong state forward.
This produced large false PCM/state/clock/ring differences at the first live
mode change despite a passing stateless control witness.

Render the oracle's prefix at source entry, sample actual event arguments at
`prepare_nh`, then render its suffix. Never reseed dynamic state at a switch.
Require continuous CF-only calibration through mode changes before interpreting
backend continuity failures. The PKNHF1 campaign checks both CF and DSP output
against this single stream, and models delayed ring commits separately from
logical synthesis state.

<a id="trap-playing-bank"></a>
## The editor bank is not the playing bank latch

**20 Oct 2026, PKNHF1 panel campaign.** An inherited test required
`0x80000002` (editor/working bank) and `0x800065bd` (playing bank) to match after
a live Bank selection. Playback had reached B while the editor still reported
A; rejecting this did not demonstrate a firmware handoff failure. The stock
switch copies the playing bank byte into `0x46c7ff40` at `0x400a465a`; the frame
ISR applies that latch, as recorded in [PARTS.md](../firmware/PARTS.md#3-pattern-changes).
Gate both the requested playing bank and that actual frame-ISR bank latch,
allow the frame application to run, and retain editor and per-track bank bytes
as observations. Do not infer the audio engine's bank from the editor context.
The corrected PKNHF1 panel driver checks real playing A→B→A with both backends;
production Part/generation semantics remain a separate qualification.

<a id="trap-pio-retiming"></a>
## Audio retiming can expose the stock PIO first-sector race

**20 Oct 2026, Noise Hat headroom experiments.** The intermediate PKNHF3
passed exact source/state/clock checks and its switching deadlines, then froze
on the third STOP/START. A second run reproduced it. `cfstatus` stayed at
`0x40015524`, the card handler's DRQ wait; the frame source stayed unmasked,
asserting and pending, with no eDMA completion outstanding. Three further
100 ms runs did not advance frames or the worker. This was not evidence of an
audio mismatch or an unbounded audio callback.

[STEM_REC.md section 11.7](../firmware/STEM_REC.md) already identifies this exact
stock PIO wait and proves the first-sector pointer/count race. The new runs
measured the stopped PC and IRQ state; the precise write-preemption window is
inferred from that prior investigation, not newly traced. A changed audio
cost can land a stock card interrupt in that window. The port advertises a
PIO card, so STOP's normal project writes can expose it without STEM recording.

Do not retry a shorter panel sequence and call it qualified. Retain the failed
run and capture CPU, eDMA and card state. The qualification probe explicitly
reuses Yves Rosius's existing `stems_ata_first`, built first as `REMIX=stems`
against the shared stock image. Its 52 executable bytes must match that
original build after relocation. A preceding author RTS preserves the
standalone reference's four-byte link alignment; the full 54-byte unit is also
pinned with `Linked.reference`. The source witness counts actual entries, and
panel receipts retain PIO mode and card write errors. This fix is an explicit
change to the qualification image; it is not an emulator repair or a hardware
admission for the PERKY hybrid.

<a id="trap-production-generation"></a>
## Diagnostic Part tests bypassed production generation resets

**20 Oct 2026, four-voice production integration.** F7's Part/Bank panel
campaign passed with diagnostic selectors and continuing synthesis histories.
Its dispatcher replaced the production source body, so it did not call the
Bank/Part generation observer or read staged ALGO/MODE. That scoped pass did
not establish production persistence or event-boundary resets.

The opt-in PKNHG1 integration reuses the production observer, staged six-control
ABI and family-local selector table. It resets CF objects from original
pristine initializers at real events. Thirty-two linked selection/validation
cases and an actual encoder-edit/SAVE PROJECT/cold-reload persistence test
pass. The CF-only panel run keeps the original Hat stream exact but misses
one deadline at 392.731 microseconds. The DSP-enabled panel run also reports
363,906 source PCM mismatches. Both observe five generations per voice and
zero stored/actual selector mismatches. The three sustained production rows
also miss deadlines. F7's separate continuing-history campaign still passes.

A CF reset does not reset resident DSP limbs, the interruptible inner shadow,
its clock or the generations of pending feedback. The G1 protocol has
no generation tag. Resetting producer/consumer counters would hide old work,
not retire it correctly. G1 admission needed an event-coherent reset
and old-job retirement contract, with an independent initializer-based audio
witness, and the reset cost inside the full-ISR timing bound. V4's persisted
Noise Tone choice also needs source dispatch beyond the current Hat protocol.

**Fix and gate (PKNHG2):** reset resident limbs/side/native clock through an
existing DMA header bit, reset CF state at the same event, and let the worker
consume a queued half-frame reset in order. Keep monotonic sequence/counter
history; check all returned feedback and commit only the current generation.
The independent original-initializer witness records explicit epoch/index/value
ring writes, including the old prefix. The mixed lifecycle checks and retires
69 old-generation samples without new-ring writes. Both production lifecycle
captures, all three 16,384-frame stock/FX rows and save/cold reload pass exact
Hat/Slap audio and timing; worst 357.909 µs leaves 4.903 µs. Avoiding redundant
startup copies reduces the first-frame reset bucket from 14,425 to 424 cycles;
later restores use a byte/guard/ABI-tested CF copy. The campaign binder now
requires passing current-image receipts, actual epoch retirement, memory fit,
register/reset/import gates, repository checks and identity. G1 remains a
failed historical record; F7 keeps its continuing-history scope. V4 alternative
source dispatch and physical timing remain unqualified. See
[PRODUCTION_LIFECYCLE.md](../../modules/perky/hybrid/PRODUCTION_LIFECYCLE.md).


<a id="trap-reset-profile"></a>
## A worst post-Part frame is not necessarily a reset frame

**20 Oct 2026, PKNHG3 profiling.** G2's lifecycle worst frames occurred 400
frames after a Bank reset. Treating their full cost as reset work would have
misdirected optimization. Actual generations 2–5 spent 18,652–18,673 cycles
in restoration, while the global peaks combined CF metallic synthesis with
stock processing. The first-adoption 424-cycle event bucket did not measure
later restoration and excluded callees.

**Fix and gate:** record real generation entry frames and read-only instruction
attribution separately from the top 64 full ISRs. Require equal frame/return
counts, full cycle sums, maxima and misses against unprofiled captures of the
same image; both G2 and G3 pass. Check that each attributed frame's buckets sum
to its full ISR. G3 boot-derived sparse restores reduce later restoration to
7,681–7,709 cycles; direct packet/clear and exact resampling assembly reduce
non-reset overhead too. The worst later reset is 301.019 µs and the worst
whole campaign frame is 349.439 µs, leaving 13.372 µs versus G2's 4.903 µs.
Sparse/full-engine, packet, clock/EMAC/ABI and independent original-audio
checks gate the changes. These are local instruction/cycle measurements,
not physical timing qualification. See
[PRODUCTION_LIFECYCLE.md](../../modules/perky/hybrid/PRODUCTION_LIFECYCLE.md).

<a id="trap-full-map-clock"></a>
## A backend's clock restoration can undo another algorithm's trigger

**20 Oct 2026, full-map integration.** The resident-Hat adapter saved and restored
the CF clock around prepare. Applying that restoration to Noise-Tone/Acoustic
also undid their actual trigger/ALGO reset. Direct source PCM diverged despite
correct individual renderers. Restore that snapshot only for an unchanged,
non-reset Hat source; CF alternatives retain their own prepare result.
`verify_perky_full_map_sources.py` gates all layouts, event splits and directed
ALGO transitions against independently initialized original streams.

<a id="trap-full-map-worker"></a>
## A missing observer environment can skip a real worker

**20 Oct 2026.** The first complete-map port ran exact source PCM but filled its
1,024-frame shadow queue: the new driver omitted `NHB_PRODUCED/COMPLETED`, and
the isolated port skipped main's detoured idle loop. This was a measurement
configuration failure, not a measured physical worker deficit. Supply both
addresses, execute worker instructions whenever work is pending, and require
positive completion plus zero overflow/clock/transport errors. Failed rows and
their driver remain under `full-map/worker-observer-failure`; final integrated,
matrix and lifecycle drivers bind the worker environment in their receipts.

<a id="trap-full-map-controls"></a>
## A persisted Part edit need not publish to the live source lane

**20 Oct 2026.** Poking the saved Part and its SRAM mirror left the actual
source controls at WT/WT/Slap/Hat. An expected-tuples gate stopped that attempted
matrix. Use real sequencer ALGO/MODE locks and verify the controls observed at
`placement_prepare`; panel navigation must also verify the actual selected
Part/Bank. Large encoder deltas can clamp past an intended enum, and a few small
reports need not reach it. Backend MODE qualification therefore uses actual
sequencer delivery, while encoder SAVE/cold reload has its own explicit gate.
No selector value is repaired downstream to make a row pass.

<a id="trap-full-map-first-hat"></a>
## A first Hat use can occur after the generation event

**20 Oct 2026.** A Part may begin on Noise-Tone, invalidate Hat, and first select
Hat later while CF owns the source. Looking only at `pk_prod_last_reset` misses
that lazy initialization; inactive DSP limbs can retain old state at cutover.
Capture the pre-prepare initialized mask, reset the ordered shadow for a fresh
Hat, and mark all three limbs dirty before backend ownership can change.
The full-map lifecycle gate enters a Part on NT, selects its first Hat through
the actual control publisher, and changes backend without changing generation.
The independent oracle compares all defined resident limbs and clocks after
that first use. Undefined inactive raw bytes are not substituted as expected
initialized state.

<a id="trap-buffered-eof"></a>
## A successful extra buffered read does not prove a trailing file byte

**20 Oct 2026, card asset packaging.** Stock `F_READ` at `0x40016564` fills a
sector buffer and copies from it without a logical file-length test in the
copy loop. Reading one extra byte after an exact Acoustic payload can return
success on sector padding, so an EOF probe falsely rejected the correct file.
Use an explicit version/declared payload length and pinned payload CRC; the
bundle additionally pins the complete file SHA256. Do not infer logical EOF
from that wrapper's successful buffered byte. The native malformed-input gate
and whole-machine comparison of every loaded asset byte cover separate scopes.

<a id="trap-interactive-dsp-peek"></a>
## Batch DSP readback flags do not run after interactive quit

**20 Oct 2026.** `--interactive` returns through `serveInteractive` before the
batch `--dsp-peek` report. Accepting the option does not produce a post-play
program census; a missing-word assertion correctly rejected that attempted
qualification. Read P through live `dsp peek` commands before quitting, then
wait for child exit before reading destructor reports. Fixed noninteractive
rows keep the batch readback path. Both forms compare the actual final upload
and allow only the four known stock packer-mask changes.

<a id="trap-empirical-budget"></a>
## Nominal emulator headroom can admit a historically overloaded design

**21 Oct 2026.** PKFM6 reached exact audio and a 355.337 us modeled ISR peak,
but older two-CF builds had already passed shorter local timing spans and
overloaded the MKII. A nominal 362.812 us pass, or a nominal 20% reserve,
therefore did not constitute a useful hardware admission criterion. Do not
derive a physical multiplier by dividing unmatched hardware/emulator maxima.

The common-observer replay now pins exact PERKY4S/PKH4O2/PKFM6 images,
configuration labels, full ISR distributions and background-inclusive CPU
work. Working/failing shapes overlap, so no tested scalar timing statistic
separates every row. Use the explicit working-envelope engineering target in
`modules/perky/hybrid/EMULATOR_BUDGET.json`, retain the overlap limitation, and
run `tools/verify/qualify_perky_hybrid_budget.py --check`. It deliberately
rejects PKFM6. Parent/new observer controls require identical raw target/audio
dumps and cycle totals. Playback cycle sums divide by transport frames;
startup-inclusive ACK histogram counts are a different denominator.
## An epoch check is not atomic publication
<a id="trap-epoch-publication"></a>

**Source-audited defect, October 2026:** the first on-demand Hat handoff worker
checked its epoch, then published a phase/completion a few instructions later.
An IRQ could cancel between those operations. The IRQ's cancellation also
assigned completion, so the old worker could resurrect the cancelled phase or
increment completion beyond production. This was caught before qualification;
it is not a claimed hardware failure or an instruction-window fault injection.

The successful protocol gives ordinary phase/production updates to the IRQ
and completion/import publication to main. Cancellation invalidates the epoch
without assigning completion. Main retires cancelled jobs, and the IRQ cannot
arm another request until production equals completion. Completion is the
worker's last shared-state publication, following a compiler memory barrier;
all raw synthesis-state accesses finish before it. A separate imported-epoch
tag prevents an old import publication from making a new request ready.

Initialize the epoch deterministically in the quiescent boot reset. Incrementing
an uninitialized BSS epoch can wrap the first request onto the initial import
tag. The direct gate poisons the epoch to `0xfffffffe`, calls the actual reset,
and requires epoch 1 before any audio is produced.

`verify_hat_state_handoff.py` checks actual CF/DSP PCM, full fallback state,
RNG/hold and clocks across snapshot cancellation, wire-sequence wrap and backend
changes. `qualify_hat_state_lifecycle.py` exercises real IRQ/main preemption and
production generations with the fixed observer. These execution gates accompany
the writer-ownership audit; they do not enumerate every possible preemption PC.

**Instrument control:** a later read-only Unicorn `UC_HOOK_CODE` counter probe
changed the first direct-harness CF/DSP audio comparison. The cause remains
unresolved; its claim was withdrawn and the probe removed. The failing source
and log are retained locally at
`out/perky/hybrid/full-map-state-v1/handoff-gate/UC_CODE_HOOK_FAILURE.*`.
The accepted direct gate uses the actual target counter adjacent to the sole
catch-up renderer call and checks continuing PCM/state; the performance runs
retain the unchanged calibration observer binary. The independent DSP Y-memory
read watch has its own actual-DSP-load positive control and paired exact-audio
control. Do not conflate those two instruments.

## A wrapped sequence is not a startup flag
<a id="trap-sequence-startup"></a>

**Source audit, October 2026:** the on-demand Hat candidate allowed an immediate
CF selection when the transport sequence was zero and DSP was disabled. This
was intended for pre-audio startup, but a running 32-bit counter returns to zero
after about 18 days at 16 samples/frame and 44.1 kHz. Requesting CF at that point
could skip the coherent snapshot/catch-up guard and expose stale Hat state.
The full workload passed because it never ran that long; a 16-bit wire-wrap
test did not cover this separate condition.

The inherited DMA extractor used the same sequence-zero guard and skipped a
valid wrapped return. The consumer also treated last-consumed zero as invalid,
so repeating an already consumed sequence-zero mailbox raised a failure. Direct
mail injection alone could not detect the separate DMA extraction defect.

Use an explicitly reset transport-started latch, published with real source
packets, and a separate last-consumed-valid flag. The direct gate seeds counters
before the first source call, crosses the full 32-bit wrap during snapshot
collection, then requests CF at exact sequence zero. DSP must remain the owner
while a fresh request arms. It also checks disabled startup and poisons the
latch and consumer-valid flag before the actual reset. Repeat a valid zero
return and require no second consumption, ring write or snapshot advance.
`verify_hat_state_dma.py` separately executes the actual DMA helper against
both ping banks, including sequence zero, checks all carrier clears and all
surrounding bytes, and positively distinguishes startup from active transport.
Ordinary PCM/state/RNG/clock checks continue through the source trajectory;
no target synthesis state is repaired. Earlier images fail the directed
ownership and repeated-zero controls at their intended boundaries.
