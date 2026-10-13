#!/usr/bin/env python3
"""Prove the two-voice light PERKY machine's SRC page 1 -- by EXECUTION.

The implementation under test is ``modules/perky/control_light2_candidate.c``.
It is the translation unit ``tools/perky/build_light2_machine_canary.py`` hands
to ``modules/perky/generate.py`` (m68k-elf-gcc) as ``control.s``.  This gate
does not read that file's text for its verdict: it builds the SAME translation
unit for the host, maps the fixed Octatrack addresses
``tools/harness/perky_cf/production_sim.c`` and
``tools/verify/verify_perky_cf_production_render.py`` already use, and calls the
real ``pk_track_page``, ``pk_admit_track`` and ``pk_render``.

WHAT IS PROVEN

  1. exactly six controls are visible on SRC page 1, and they are
     ``TUNE, DECAY, ALGO, PAR1, PAR2, MODE`` in that order.  Both facts are
     read out of the descriptor ``pk_track_page`` actually built (names at
     P+0x16, six-byte fields; value counts at P+0x9a).
     NOTE: a first-page name field is 6 bytes -- FIVE characters plus a NUL --
     so ``PARAM1``/``PARAM2`` are spelled ``PAR1``/``PAR2``; the gate asserts
     the field is always NUL-terminated inside its six bytes.
  2. all six are staged through the normal parameter path: the descriptor's
     first-page enable bitmap (P+0x18e for slots 0-7, P+0x18a for 8-11, one
     nibble per slot, bit 0 = "drawn by the generic renderer and staged by the
     firmware") enables EXACTLY slots 0..5 and nothing else -- the words are
     the exact 0x00111111 / 0x00000000 pair and no nibble carries the link bit
     or the PLAYBACK-only flag bits.
  3. all six are p-lockable.  MECHANISM: per docs/firmware/PARAM_PAGES.md
     section 3b (read from our own image, all 31 stock descriptors), the
     firmware's staging writer ``FUN_400326d4`` and the knob drawer
     ``FUN_40037590`` both gate on that same bitmap through ``FUN_400a6994`` --
     so a slot the bitmap enables is a slot p-lock/LFO delivery can write.
     The gate then EXECUTES the delivery: it writes each of the six staged
     page words (exactly what that writer leaves there, low byte included) and
     requires the value to appear in the record the DSP gets, for all six.
  4. MODE is bounded to the engine's valid modes: the descriptor count for
     slot 5 (PAGE order: F) is 3, and an out-of-range staged MODE is clamped
     to 2 in the transport (executed).
  5. ALGO is bounded to the real pool: the descriptor count for slot 2 is 4 and
     no executed case -- ALGO 0..3, 4, 5, 7, 127, 255, with or without the
     dirty low byte an LFO leaves -- ever put an engine byte outside
     {0, 3, 2, 10} in the record.
  6. ALGO is INDIRECT.  The four light engines do not occupy ids 0..3, so the
     descriptor's ALGO value is resolved through one table.  Executed:
     ALGO 0 -> 0 (Fold Drum 1), 1 -> 3 (Fold Drum 2), 2 -> 2 (Simple Drum),
     3 -> 10 (Noise/Tone); every out-of-range value clamps to ALGO 0.
  7. base ALGO selects the track's engine, and ALGO -- not the persisted hidden
     engine slot -- is the authority: with the hidden slot poisoned (2 or 10)
     the record still carries ALGO's engine.
  8. an ALGO p-lock changes the engine for ONE trig: base -> locked -> unlocked
     over three trigged events yields engine 0 -> 3 -> 0 (and 2 -> 10 -> 2).
  9. the following unlocked trig returns to base ALGO, and the render never
     writes back to the staged page words or the persisted parameter block.

THE BYTE THAT IS ASSERTED IS THE BYTE THE DSP DISPATCHES ON.  ``pk_render``
packs its twelve parameter bytes into record words 4..9; DSP word 19 (0x13) is
p[11], the engine byte.  The composed DSP source reads precisely that word --
``move x:(r4+$13),a / and #>$ff,a`` -- and routes 0/3/2/10 to the Fold1/Fold2/
Simple/Noise-Tone entries.  Both are pinned below against the tracked composer
sources (``tools/perky/build_multi_synth_source.py``,
``tools/perky/build_fold_candidate.py``), so a record the gate accepts is a
record the DSP dispatch can act on.  The engine byte's ADDRESS is re-derived by
the gate, not trusted: every case also requires the record magic 0x504B0000 and
the trig word 0x59310000|trig at the production slot
``0x80001c90 + (ping&1)*0xa80 + 336*track``, so a wrong readback address cannot
pass.

WHAT THIS GATE CANNOT SEE (stated rather than implied)

  * The unit executes m68k.  This gate EXECUTES a host build of the same C, and
    separately requires the ColdFire build of the same file to compile with
    generate.py's exact flags.  It does not execute m68k machine code; a
    compiler bug that changed ColdFire behaviour only would not be visible.
  * The p-lock/LFO machinery inside the Octatrack OS is not run: the gate
    writes the staged page word (what ``FUN_400326d4`` leaves there) and reads
    the render's record.  The link "bitmap -> that writer" is the documented
    objdump result of PARAM_PAGES.md section 3b, not something re-derived here.
  * Requirement 4 also needs a value count that cannot index past the select;
    the count is read from the built descriptor.  The DRAW of a 3-way select
    (tick widget) is checked for shape only: this machine carries stock SPRING
    TYPE's three-position widget (0x40047424) for MODE, and ALGO carries no B
    widget.  ``tools/verify/verify_menu.py``'s generic rule for count < 128
    wants 0x40047254 (stock CHORUS.TAPS, a five-position widget) whenever
    count <= 5; that rule never sees this descriptor, because the light page is
    built only by the in-memory light2 image build.  The gate therefore records
    the observed widget values in its output and does not assert them beyond
    "the A formatter is stock's stepped select and P+0x12a is zero".
  * Everything here is about the ColdFire CONTROL side.  It says nothing about
    whether a given engine renders correctly, and nothing about timing.

Exit status: 0 when every claim above holds.  A missing toolchain is a printed
SKIP line and not a failure -- the host half is skipped when no host C compiler
exists at all, and the shipping-artifact half when m68k-elf-gcc is absent; the
final summary says which ran.  Set ``PERKY_LIGHT2_CONTROL`` to another C file to
run the same gate against a variant -- that is how the teeth of this gate are
demonstrated.
"""
from __future__ import annotations

import base64
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROL = Path(os.environ.get("PERKY_LIGHT2_CONTROL", ROOT / "modules/perky/control_light2_candidate.c"))
WORK = ROOT / "out/perky/light2-src-page"

DESC_SIZE = 0x1CA
RECORD_BASE = 0x80001C90
PING_BYTES = 0xA80
SLOT_BYTES = 336
CURSOR = 0x80010000

# Descriptor field offsets, P-relative (PARAM_PAGES.md section 5b: P = E+0x38).
P_NAMES, P_DEFAULTS, P_COUNTS = 0x16, 0x5E, 0x9A
P_FMT_A, P_FMT_B, P_FMT_12A = 0x0CA, 0x0FA, 0x12A
P_ENABLE_LO, P_ENABLE_HI = 0x18E, 0x18A
DESC_BASE = 0x38

# The shipping engine pool, in ALGO order (control_light2_candidate.c).
ALGO_ENGINE = (0, 3, 2, 10)
ENGINE_NAMES = {0: "Fold Drum 1", 3: "Fold Drum 2", 2: "Simple Drum", 10: "Noise/Tone"}
MODE_COUNT, ALGO_COUNT = 3, 4
LABELS = ("TUNE", "DECAY", "ALGO", "PAR1", "PAR2", "MODE")
# Page-slot indices of the six SRC controls, left to right. These are the
# Part page slots; the engine ABI order is different and the control source
# remaps between them (pk_light2_src_to_transport).
SLOT_TUNE, SLOT_DECAY, SLOT_ALGO, SLOT_PAR1, SLOT_PAR2, SLOT_MODE = range(6)
SLOT_COUNT = 6
STEPPED_FORMATTER_A = 0x4003C718   # stock enumerated select: prints value+1
MODE_TICK_WIDGET = 0x40047424      # stock SPRING TYPE three-position ticks


def note(line: str) -> None:
    print(line)


def fail(message: str) -> None:
    raise SystemExit("verify-perky-light2-src-page: " + message)


# --------------------------------------------------------------------------
# The generated host driver: the REAL pk_render in a fixed Octatrack map.
# --------------------------------------------------------------------------
DRIVER = r'''
/* Generated by tools/verify/verify_perky_light2_src_page.py; do not edit.
 *
 * Fixed-address Octatrack fixture for the light PERKY control source.  Calls
 * the shipping pk_track_page / pk_admit_track / pk_render, exactly as
 * tools/harness/perky_cf/production_sim.c does for the 3-algo machine.
 *
 * Case rows: track part ping trig dirty hidden r0 r1 r2 r3 r4 r5
 *   r0..r5 = the six SRC page slots, in page order.
 */
#include <sys/mman.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define U8(a)  (*(volatile uint8_t  *)(uintptr_t)(a))
#define U16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))

#define L2_CURSOR        0x80010000u
#define L2_FP            0x80008000u
#define L2_FP_PTR        0x800062a8u
#define L2_CURSOR_PTR    0x80001c80u
#define L2_RECORD        0x80001c90u
#define L2_PING_BYTES    0xa80u
#define L2_SLOT_BYTES    336u
#define L2_TRIG          0x46104d0cu
#define L2_HIDDEN        0x80000810u
#define L2_HIDDEN_STRIDE 72u
#define L2_BANK          0x46c82456u
#define L2_PART_IDX      0x100b14cfu
#define L2_PART_OFF      0x8ed80u
#define L2_PART_STRIDE   0x18b2u
#define L2_DESC_SIZE     0x1cau
#define L2_NEVER         0x0badf00du
#define L2_STOCK_RENDER  0x40004008u

extern int pk_render(unsigned, unsigned, unsigned, unsigned);
extern unsigned pk_admit_track(const volatile uint8_t *, unsigned);
extern uint32_t pk_track_page(const volatile uint8_t *);
extern uint32_t pk_desc_p;
extern void pk_ui_tick(void);

/* The stock FLEX renderer is never supposed to run from this gate. */
void pk_stock_pool_open(void) { abort(); }
int pk_stock_validate(void *part) { (void)part; return 0; }

static void l2_map(uintptr_t at, unsigned size, int prot)
{
    void *p = mmap((void *)at, size, prot, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
    if (p != (void *)at) { perror("mmap"); exit(2); }
}

static unsigned l2_hidden(unsigned track, unsigned slot)
{
    return (unsigned)(L2_HIDDEN + L2_HIDDEN_STRIDE * track + 0x20u + slot);
}

int main(int argc, char **argv)
{
    if (argc != 2) { fprintf(stderr, "usage: %s <cases>\n", argv[0]); return 2; }
    l2_map(0x10000000u, 0x200000u, PROT_READ | PROT_WRITE);
    l2_map(0x40000000u, 0x1000000u, PROT_READ | PROT_WRITE | PROT_EXEC);
    l2_map(0x46000000u, 0x4000000u, PROT_READ | PROT_WRITE);
    l2_map(0x80000000u, 0x1000000u, PROT_READ | PROT_WRITE);

    /* If admission ever let a stock path through, it would jump here: make it
     * return a sentinel so the gate can see that instead of executing zeros. */
    ((uint8_t *)(uintptr_t)L2_STOCK_RENDER)[0] = 0xb8u;             /* mov imm32,%eax */
    { uint32_t never = L2_NEVER;
      memcpy((uint8_t *)(uintptr_t)(L2_STOCK_RENDER + 1u), &never, 4); }
    ((uint8_t *)(uintptr_t)(L2_STOCK_RENDER + 5u))[0] = 0xc3u;       /* ret */

    U32(L2_FP_PTR) = L2_FP;
    U32(L2_CURSOR_PTR) = L2_CURSOR;
    U32(L2_BANK) = 0x48000000u;
    U8(L2_PART_IDX) = 0u;

    /* Four parts, each carrying the PK/1 signature on tracks 0 and 4 only. */
    for (unsigned part = 0; part < 4u; ++part) {
        volatile uint8_t *base = (volatile uint8_t *)(uintptr_t)
            (0x48000000u + L2_PART_OFF + part * L2_PART_STRIDE);
        for (unsigned t = 0; t < 8u; ++t) {
            base[0x22u + t] = (t == 0u || t == 4u) ? 1u : 0u;
            base[60u + 30u * t + 0u] = 'P';
            base[60u + 30u * t + 1u] = 'K';
            base[60u + 30u * t + 2u] = 1u;
        }
    }
    for (unsigned t = 0; t < 8u; ++t)
        for (unsigned k = 0; k < 6u; ++k)
            U8(l2_hidden(t, k)) = 0u;

    /* The descriptor, through the entry the unit reaches it by. */
    const volatile uint8_t *part0 = (const volatile uint8_t *)(uintptr_t)
        (0x48000000u + L2_PART_OFF);
    const uint32_t page = pk_track_page(part0 + 0x22u);
    printf("DESC_PTR %08x %08x\n", (unsigned)page, (unsigned)pk_desc_p);
    const uint8_t *desc = (const uint8_t *)(uintptr_t)(page - 0x38u);
    printf("DESC ");
    for (unsigned i = 0; i < L2_DESC_SIZE; ++i) printf("%02x", desc[i]);
    printf("\n");

    /* The other admitted voice (T5, zero-based 4) and the UI tick must hand out
     * the same page: one light machine, two tracks. */
    printf("DESC4_PTR %08x\n", (unsigned)pk_track_page(part0 + 0x22u + 4u));
    pk_ui_tick();
    printf("UI_TICK %08x\n",
           (unsigned)U32(0x400d5f38u + 5u * 4u));   /* PERKY_ROW 5 */

    printf("ADMIT");
    for (unsigned t = 0; t < 8u; ++t)
        printf(" %u", pk_admit_track(part0, t));
    printf("\n");

    FILE *f = fopen(argv[1], "r");
    if (!f) { perror("cases"); return 2; }
    unsigned track, part, ping, trig, dirty, hidden, r[6];
    unsigned idx = 0, fallback = 0;
    while (fscanf(f, "%u %u %u %u %u %u %u %u %u %u %u %u",
                  &track, &part, &ping, &trig, &dirty, &hidden,
                  &r[0], &r[1], &r[2], &r[3], &r[4], &r[5]) == 12) {
        U8(L2_PART_IDX) = (uint8_t)part;
        U8(l2_hidden(track, 5u)) = (uint8_t)hidden;
        /* Stage the six page slots LITERALLY, in page order. All slot semantics
         * (which control lives where, and how it maps onto the engine ABI) live
         * in the Python half, so there is one description of the layout, not
         * two that can drift apart. */
        for (unsigned s = 0; s < 6u; ++s)
            U16(L2_FP + 2u * s) = (uint16_t)((r[s] << 8) | dirty);
        for (unsigned t = 0; t < 8u; ++t) U8(L2_TRIG + t) = 0u;
        U8(L2_TRIG + track) = trig ? 16u : 0u;
        U32(L2_CURSOR_PTR) = L2_CURSOR;

        const int rc = pk_render(track, ping, 0u, 16u);
        if (rc == (int)L2_NEVER) ++fallback;

        const volatile uint32_t *rec = (const volatile uint32_t *)(uintptr_t)
            (L2_RECORD + (ping & 1u) * L2_PING_BYTES + L2_SLOT_BYTES * track);
        printf("CASE %u %u %u %u %d", idx, track, part, ping, rc);
        for (unsigned w = 0; w < 10u; ++w) printf(" %08x", (unsigned)rec[w]);
        printf("\n");
        ++idx;
    }
    fclose(f);

    printf("FALLBACK %u\n", fallback);
    printf("AFTER");
    for (unsigned k = 0; k < 6u; ++k) printf(" %04x", (unsigned)U16(L2_FP + 2u * k));
    for (unsigned t = 0; t < 8u; ++t)
        for (unsigned k = 0; k < 6u; ++k)
            printf(" %02x", (unsigned)U8(l2_hidden(t, k)));
    printf("\n");
    return 0;
}
'''


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------
class Case:
    __slots__ = ("name", "track", "part", "ping", "trig", "algo", "mode",
                 "knobs", "dirty", "hidden")

    def __init__(self, name, *, track=0, part=0, ping=0, trig=1, algo=0,
                 mode=1, knobs=(64, 64, 64, 64), dirty=0, hidden=0):
        self.name, self.track, self.part, self.ping = name, track, part, ping
        self.trig, self.algo, self.mode = trig, algo, mode
        self.knobs, self.dirty, self.hidden = knobs, dirty, hidden

    def slots(self) -> tuple[int, ...]:
        """The six SRC page values this case presents, in PAGE order.

        `knobs` is the four continuous controls in ENGINE-ABI order
        (TUNE, DECAY, PAR1, PAR2); ALGO and MODE are separate fields. The page
        order is a product choice and differs from the ABI order, so the mapping
        lives here once and the C driver just stages what it is given.
        """
        k = self.knobs
        out = [0] * SLOT_COUNT
        out[SLOT_TUNE], out[SLOT_DECAY] = k[0], k[1]
        out[SLOT_ALGO] = self.algo
        out[SLOT_PAR1], out[SLOT_PAR2] = k[2], k[3]
        out[SLOT_MODE] = self.mode
        return tuple(out)

    def row(self) -> str:
        return " ".join(str(v) for v in (
            self.track, self.part, self.ping, self.trig, self.dirty, self.hidden,
            *self.slots()))

    def staged(self) -> list[int]:
        """The six staged page words this case leaves in the fixture."""
        return [(v << 8) | self.dirty for v in self.slots()]


def target(value: int) -> int:
    """pk_light2_target(): the Noise/Tone full-resolution transport."""
    value &= 0x7F
    return 4095 if value == 127 else value << 5


def pair(value: int) -> int:
    """record[4+i] = (p[2i] << 16) | p[2i+1] for one 16-bit prepared value."""
    return ((value >> 8) & 0xFF) << 16 | (value & 0xFF)


def noise_tone_record(case: Case) -> list[int]:
    """The exact record pk_render must write for ALGO 3 (Noise/Tone).

    pk_light2_full_prepare() reads the transport words p[0..3], which
    pk_light2_src_to_transport() fills from the PAGE slots
    TUNE(slot 0), DECAY(slot 1), PARAM1(slot 3), PARAM2(slot 4) -- the page
    order is not the ABI order -- maps each through pk_light2_target() and
    publishes them as the four prepared pairs, with MODE clamped to 2 in p[8]
    and the engine byte (10) in p[11].
    """
    k = case.knobs
    ordered = (target(k[0]), target(k[1]), target(k[2]), target(k[3]))
    mode = min(case.mode, 2)
    record = [0x504B0000, 0x59310000 | case.trig, 0, 0]
    record += [pair(v) for v in ordered]
    record += [(mode << 16), 10]
    return record


def build_cases() -> list[Case]:
    cases: list[Case] = []
    # (a) Noise/Tone is the one engine whose record is fully computable, so it
    # is the exact oracle for slot order, the 7-bit knob law, MODE clamping and
    # the LFO dirty low byte.
    cases += [
        Case("nt_endpoints", part=0, ping=0, algo=3, mode=1, knobs=(0, 127, 64, 100)),
        Case("nt_two_ends", part=1, ping=1, algo=3, mode=2, knobs=(127, 0, 127, 64)),
        Case("nt_mask7", part=2, ping=0, algo=3, mode=0, knobs=(200, 128, 63, 255)),
        Case("nt_mode_clamp3", part=3, ping=0, algo=3, mode=3, knobs=(64, 100, 33, 7)),
        Case("nt_mode_clamp127_dirty", part=0, ping=0, algo=3, mode=127,
             knobs=(96, 96, 96, 96), dirty=0x7D),
    ]
    # (b) the pool map and the clamp for every out-of-range ALGO
    for algo in (0, 1, 2, 3):
        cases.append(Case(f"engine_algo{algo}", part=algo, algo=algo))
    for algo in (4, 5, 7, 127, 255):
        cases.append(Case(f"engine_oob{algo}", part=0, algo=algo))
    # (c) one-trig ALGO p-lock, twice, plus the dirty low byte an LFO leaves
    cases += [
        Case("lock_base", part=3, algo=0),
        Case("lock_held", part=3, algo=1),
        Case("lock_released", part=3, algo=0),
        Case("lock_base_2", part=0, algo=2),
        Case("lock_held_2", part=0, algo=3),
        Case("lock_released_2", part=0, algo=2),
        Case("lock_held_dirty", part=1, algo=1, dirty=0x7D),
        Case("lock_released_dirty", part=1, algo=0, dirty=0x7D),
    ]
    # (d) ALGO, not the persisted hidden engine slot, is the authority
    cases += [
        Case("algo_beats_hidden_fold1", part=2, algo=0, hidden=2),
        Case("algo_beats_hidden_simple", part=2, algo=2, hidden=10),
    ]
    # (e) both admitted tracks, the second ping slot, and a non-admitted track
    #     is never rendered (only pk_admit_track is asked about it)
    cases += [
        Case("track4_algo1", track=4, part=1, ping=1, algo=1),
        Case("track4_algo3", track=4, part=2, ping=0, algo=3, mode=2),
        Case("track0_final", track=0, part=0, ping=0, algo=0, mode=1),
    ]
    return cases


# --------------------------------------------------------------------------
# Host execution
# --------------------------------------------------------------------------
def host_arch() -> tuple[list[str], list[str]]:
    """Same 32-bit-address fixture recipe the sibling CF gates use."""
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return ["-arch", "x86_64"], ["-Wl,-pagezero_size,0x1000"]
    return [], []


def run(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        fail(f"{what} failed (exit {result.returncode}):\n"
             + result.stdout[-4000:] + result.stderr[-2000:])
    return result


def execute(cases: list[Case]) -> dict[str, object]:
    if shutil.which("cc") is None or shutil.which("c++") is None:
        note("[SKIP] no host C compiler (`cc`/`c++`): the EXECUTED half of this gate did not run")
        return {}

    WORK.mkdir(parents=True, exist_ok=True)
    arch, link = host_arch()
    cflags = [*arch, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
              "-I", str(ROOT / "modules/perky")]
    driver_c, driver_o = WORK / "light2_fixture.c", WORK / "light2_fixture.o"
    control_o, exe = WORK / "light2_control.o", WORK / "light2_src_page"
    driver_c.write_text(DRIVER)
    run(["cc", *cflags, "-c", str(CONTROL), "-o", str(control_o)],
        f"host compile of {CONTROL.name}")
    run(["cc", *cflags, "-c", str(driver_c), "-o", str(driver_o)],
        "host compile of the fixed-address fixture")
    run(["c++", *arch, str(driver_o), str(control_o), *link, "-o", str(exe)],
        "host link of the fixture")

    case_file = WORK / "cases.txt"
    case_file.write_text("\n".join(case.row() for case in cases) + "\n")
    result = run([str(exe), str(case_file)], "execution of the real pk_render")

    desc = None
    admit: list[int] = []
    rows: dict[int, dict[str, object]] = {}
    after: dict[str, object] = {}
    fallback = None
    page = page4 = ui_tick = None
    for line in result.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "DESC_PTR":
            page = int(fields[1], 16)
            if page != int(fields[2], 16):
                fail(f"pk_track_page returned 0x{page:08x} but pk_desc_p is "
                     f"0x{int(fields[2], 16):08x}")
            desc = bytes.fromhex(fields[3]) if len(fields) > 3 else None
        elif fields[0] == "DESC":
            desc = bytes.fromhex(fields[1])
        elif fields[0] == "DESC4_PTR":
            page4 = int(fields[1], 16)
        elif fields[0] == "UI_TICK":
            ui_tick = int(fields[1], 16)
        elif fields[0] == "ADMIT":
            admit = [int(v) for v in fields[1:]]
        elif fields[0] == "CASE":
            idx = int(fields[1])
            rows[idx] = {"track": int(fields[2]), "part": int(fields[3]),
                         "ping": int(fields[4]), "rc": int(fields[5]),
                         "words": [int(v, 16) for v in fields[6:16]]}
        elif fields[0] == "FALLBACK":
            fallback = int(fields[1])
        elif fields[0] == "AFTER":
            after = {"fp": [int(v, 16) for v in fields[1:7]],
                     "hidden": [int(v, 16) for v in fields[7:]]}
    if desc is None or len(desc) != DESC_SIZE:
        fail("the fixture did not report a whole descriptor")
    if len(admit) != 8 or len(rows) != len(cases) or fallback is None or not after:
        fail(f"incomplete fixture output ({len(rows)}/{len(cases)} cases)")
    if page4 is None or page4 != page:
        fail(f"the second admitted voice (T5, zero-based 4) was handed a "
             f"different page pointer (0x{page4} vs 0x{page:08x})")
    if ui_tick is None or ui_tick != page:
        fail(f"pk_ui_tick published 0x{ui_tick} for the PERKY row, not the "
             f"descriptor page 0x{page:08x}")
    note(f"MEASURED page identity: pk_track_page(T1) == pk_track_page(T5) == "
         f"0x{page:08x}, and pk_ui_tick publishes that same pointer for the "
         f"PERKY row")
    return {"desc": desc, "admit": admit, "rows": rows, "after": after,
            "fallback": fallback}


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
def be32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 4], "big")


def nibble(lo: int, hi: int, slot: int) -> int:
    word = lo if slot < 8 else hi
    return (word >> (4 * (slot if slot < 8 else slot - 8))) & 0xF


def check_descriptor(desc: bytes) -> None:
    base = DESC_BASE
    labels = []
    for i in range(12):
        field = desc[base + P_NAMES + 6 * i: base + P_NAMES + 6 * i + 6]
        if len(field) != 6 or field[5] != 0 or b"\0" not in field:
            fail(f"descriptor name field {i} is not NUL-terminated inside its "
                 f"six bytes: {field!r} (a five-character name plus a terminator "
                 f"is the whole field)")
        labels.append(field.split(b"\0")[0].decode("ascii", "replace"))
    if tuple(labels[:6]) != LABELS:
        fail(f"SRC page-1 controls are {labels[:6]!r}, expected {list(LABELS)!r} "
             f"(slots 0..5, in that order)")
    counts = [be32(desc, base + P_COUNTS + 4 * i) for i in range(12)]
    defaults = [desc[base + P_DEFAULTS + i] for i in range(12)]

    # The enable bitmap, read the way tools/verify/verify_menu.py and
    # tools/panel/panel_server.py read it (bit 0 of each nibble).
    lo, hi = be32(desc, base + P_ENABLE_LO), be32(desc, base + P_ENABLE_HI)
    enabled = {i for i in range(12) if nibble(lo, hi, i) & 1}
    visible = {i for i in enabled if counts[i] >= 2}
    if (lo, hi) != (0x00111111, 0x00000000):
        fail(f"staging mask is (P+0x18e, P+0x18a) = (0x{lo:08x}, 0x{hi:08x}); "
             f"expected (0x00111111, 0x00000000) -- exactly slots 0..5")
    if enabled != set(range(6)):
        fail(f"the staging bitmap enables slots {sorted(enabled)}, expected "
             f"[0, 1, 2, 3, 4, 5] and nothing else")
    if visible != set(range(6)):
        fail(f"visible slots (enabled and adjustable) are {sorted(visible)}, "
             f"expected [0, 1, 2, 3, 4, 5]; counts={counts}")
    stray = {i for i in range(12) if nibble(lo, hi, i) & 0xC}
    if stray:
        fail(f"nibbles {sorted(stray)} carry bits 2/3 (stock PLAYBACK-only "
             f"flags); the light page must leave them zero")
    linked = {i for i in range(12) if nibble(lo, hi, i) & 2}
    if linked:
        fail(f"nibbles {sorted(linked)} carry the left-neighbour link bit; the "
             f"six light controls are independent")
    continuous = (SLOT_TUNE, SLOT_DECAY, SLOT_PAR1, SLOT_PAR2)
    got_cont = [counts[i] for i in continuous]
    if got_cont != [128, 128, 128, 128]:
        fail(f"the four continuous controls (slots {sorted(continuous)} = "
             f"TUNE/DECAY/PAR1/PAR2) must be 128-position knobs, got {got_cont!r}")
    if counts[SLOT_MODE] != MODE_COUNT:
        fail(f"MODE (slot {SLOT_MODE}) count is {counts[SLOT_MODE]}, expected "
             f"{MODE_COUNT} (the light engines have three modes)")
    if counts[SLOT_ALGO] != ALGO_COUNT:
        fail(f"ALGO (slot {SLOT_ALGO}) count is {counts[SLOT_ALGO]}, expected "
             f"{ALGO_COUNT} (the shipping pool has four engines); a larger count "
             f"would let the panel ask for an engine the pool does not contain")
    if counts[6:] != [0] * 6:
        fail(f"slots 6..11 must stay empty, got counts {counts[6:]!r}")
    want_defaults = [64, 64, 0, 64, 64, 0]
    if defaults[:6] != want_defaults:
        fail(f"seeded first-page defaults are {defaults[:6]!r}, expected "
             f"{want_defaults!r}")
    for i in enabled:
        if not 0 <= defaults[i] < counts[i]:
            fail(f"slot {i} default {defaults[i]} is outside its count {counts[i]}; "
                 f"an out-of-range default is used as an index")

    # Formatter shape: a count < 128 slot is drawn as a select, so its A
    # formatter is stock's stepped select and P+0x12a must be zero.
    fmt = {}
    for i in range(12):
        fmt[i] = (be32(desc, base + P_FMT_A + 4 * i),
                  be32(desc, base + P_FMT_B + 4 * i),
                  be32(desc, base + P_FMT_12A + 4 * i))
    for i in continuous:
        if fmt[i] != (0, 0, 0):
            fail(f"continuous control slot {i} ({labels[i]}) carries formatter "
                 f"words {fmt[i]!r}; a plain dial must carry none")
    for i in (SLOT_ALGO, SLOT_MODE):
        if fmt[i][0] != STEPPED_FORMATTER_A or fmt[i][2] != 0:
            fail(f"slot {i} ({labels[i]}, count {counts[i]}) must carry stock's "
                 f"stepped-select A formatter 0x{STEPPED_FORMATTER_A:08x} with "
                 f"P+0x12a zero, got 0x{fmt[i][0]:08x}/0x{fmt[i][2]:08x}")
    if fmt[SLOT_MODE][1] != MODE_TICK_WIDGET:
        fail(f"MODE must carry the three-position tick widget "
             f"0x{MODE_TICK_WIDGET:08x}, got 0x{fmt[SLOT_MODE][1]:08x}")

    note("MEASURED descriptor: visible slots 0..5 = "
         + " / ".join(f"{i} {labels[i]} (count {counts[i]}, default {defaults[i]})"
                      for i in range(6)))
    note(f"MEASURED staging bitmap P+0x18e/P+0x18a = 0x{lo:08x}/0x{hi:08x} "
         f"-> enabled {sorted(enabled)} (nothing else)")
    note(f"MEASURED select widgets: MODE A/B/0x12a = "
         f"0x{fmt[SLOT_MODE][0]:08x}/0x{fmt[SLOT_MODE][1]:08x}/0x{fmt[SLOT_MODE][2]:08x}; "
         f"ALGO A/B/0x12a = "
         f"0x{fmt[SLOT_ALGO][0]:08x}/0x{fmt[SLOT_ALGO][1]:08x}/0x{fmt[SLOT_ALGO][2]:08x}")
    if fmt[SLOT_ALGO][1] == 0 and counts[SLOT_ALGO] <= 5:
        note("NOTE (INFERRED, not asserted): verify_menu.py's generic rule for "
             "count <= 5 asks for the tick widget 0x40047254; ALGO carries 0. "
             "Stock's count-4 selects are not otherwise evidenced in this tree, "
             "so the gate records this rather than blessing it.")


def check_admission(admit: list[int]) -> None:
    if admit != [1, 0, 0, 0, 1, 0, 0, 0]:
        fail(f"pk_admit_track admits {admit} for tracks 0..7; expected exactly "
             f"[1,0,0,0,1,0,0,0] -- T1 and T5, one PERKY voice per DSP core")
    note("MEASURED admission: pk_admit_track = [1,0,0,0,1,0,0,0] (T1 and T5 only)")


def record_words(rows: dict[int, dict[str, object]], index: int, case: Case) -> list[int]:
    name = case.name
    row = rows[index]
    words = row["words"]
    assert isinstance(words, list)
    if row["rc"] != 0:
        fail(f"case {name}: pk_render returned {row['rc']} (the stock FALLBACK "
             f"path ran; the fixture sentinel exists precisely to catch this)")
    if words[0] != 0x504B0000 or words[1] != (0x59310000 | case.trig):
        fail(f"case {name}: no PK/Y1 record at the production slot "
             f"0x{RECORD_BASE:08x} + ping*0x{PING_BYTES:x} + 336*track "
             f"(word0=0x{words[0]:08x}, word1=0x{words[1]:08x}, trig={case.trig}); "
             f"the record address or the writer drifted")
    if words[2] != 0 or words[3] != 0:
        fail(f"case {name}: record words 2/3 are not zero: "
             f"0x{words[2]:08x}/0x{words[3]:08x}")
    return words


def engine_of(words: list[int]) -> int:
    return words[9] & 0xFF


def check_dispatch(cases: list[Case], data: dict[str, object]) -> None:
    rows = data["rows"]
    assert isinstance(rows, dict)
    by_name = {case.name: i for i, case in enumerate(cases)}
    engines: dict[str, int] = {}
    pool = set(ALGO_ENGINE)

    for i, case in enumerate(cases):
        words = record_words(rows, i, case)
        engine = words[9] & 0xFFFF
        if engine not in pool:
            fail(f"case {case.name}: engine byte 0x{engine:04x} (DSP word 19) is "
                 f"not in the shipping pool {sorted(pool)}; ALGO={case.algo}")
        engines[case.name] = engine

    # (a) The exact Noise/Tone oracle: the whole record, so slot order, the
    #     7-bit transport law, MODE clamping and the dirty low byte are pinned
    #     arithmetically rather than by comparison.
    for case in cases:
        if not case.name.startswith("nt_"):
            continue
        words = rows[by_name[case.name]]["words"]
        want = noise_tone_record(case)
        if words[:10] != want:
            offset = next((k for k in range(10) if words[k] != want[k]), None)
            fail(f"case {case.name}: record word {offset} (DSP words "
                 f"{2*offset}/{2*offset+1}) is 0x{words[offset]:08x}, expected "
                 f"0x{want[offset]:08x}. knobs={case.knobs} mode={case.mode} "
                 f"dirty=0x{case.dirty:02x}; the transport maps PAGE slot "
                 f"0->TUNE, 1->DECAY, 3->PARAM1, 4->PARAM2, 5->MODE (clamped to "
                 f"2), 2->engine -- the page order is not the engine ABI order.")
    note("MEASURED Noise/Tone exact record: 5 cases, every one of the 10 record "
         "words matches the independent Python oracle (slot order, 127->4095 "
         "endpoint, 7-bit mask, MODE clamp, LFO dirty low byte ignored)")

    # (b) The pool map.
    for algo, engine in enumerate(ALGO_ENGINE):
        got = engines[f"engine_algo{algo}"]
        if got != engine:
            fail(f"ALGO {algo} selected engine {got}, expected {engine} "
                 f"({ENGINE_NAMES[engine]}); ALGO must be resolved through the "
                 f"engine table, not used as an engine id directly")
    note("MEASURED ALGO -> engine byte: "
         + ", ".join(f"{a}->{engines[f'engine_algo{a}']}"
                     for a in range(ALGO_COUNT)))

    # (c) Out-of-range ALGO.
    for algo in (4, 5, 7, 127, 255):
        got = engines[f"engine_oob{algo}"]
        if got != ALGO_ENGINE[0]:
            fail(f"out-of-range ALGO {algo} selected engine {got}; an "
                 f"out-of-range value must clamp to {ALGO_ENGINE[0]}, never "
                 f"reach a non-pool engine")
    note("MEASURED out-of-range ALGO 4/5/7/127/255 -> engine "
         f"{ALGO_ENGINE[0]} every time")

    # (d) One-trig p-lock, twice, dirty low byte included.
    for base, held, released in (("lock_base", "lock_held", "lock_released"),
                                 ("lock_base_2", "lock_held_2", "lock_released_2")):
        sequence = [engines[base], engines[held], engines[released]]
        if sequence[1] == sequence[0]:
            fail(f"the ALGO p-lock case {held} did not change the engine "
                 f"(both {sequence[0]})")
        if sequence[2] != sequence[0]:
            fail(f"the unlocked trig did not return to base ALGO: "
                 f"{base}={sequence[0]}, {held}={sequence[1]}, "
                 f"{released}={sequence[2]}")
        note(f"MEASURED one-trig ALGO p-lock: base {base}={sequence[0]} -> "
             f"locked {held}={sequence[1]} -> unlocked {released}={sequence[2]}")
    if engines["lock_held_dirty"] != engines["lock_held"]:
        fail(f"an LFO dirty low byte changed the engine: clean "
             f"{engines['lock_held']} vs dirty {engines['lock_held_dirty']}")
    if engines["lock_released_dirty"] != engines["lock_base"]:
        fail("with the dirty low byte present the unlocked trig did not return "
             "to base ALGO")
    note("MEASURED LFO dirty low byte (0x7d in the staged words): ALGO p-lock "
         "and its release are unaffected (the render keeps bits 8..15 only)")

    # (e) ALGO beats the persisted hidden engine slot.
    if engines["algo_beats_hidden_fold1"] != ALGO_ENGINE[0]:
        fail(f"with the hidden engine slot poisoned to 2, ALGO 0 selected "
             f"{engines['algo_beats_hidden_fold1']}; ALGO must be the authority")
    if engines["algo_beats_hidden_simple"] != ALGO_ENGINE[2]:
        fail(f"with the hidden engine slot poisoned to 10, ALGO 2 selected "
             f"{engines['algo_beats_hidden_simple']}; ALGO must be the authority")
    note("MEASURED ALGO authority: hidden engine slot poisoned with 2 (ALGO 0) "
         "and 10 (ALGO 2) changes nothing; the record carries ALGO's engine")

    # (f) Both admitted tracks and both ping slots.
    t4a1 = engines["track4_algo1"]
    t4a3 = engines["track4_algo3"]
    if (t4a1, t4a3) != (ALGO_ENGINE[1], ALGO_ENGINE[3]):
        fail(f"track 5 (zero-based 4) did not publish the expected engines: "
             f"ALGO 1 -> {t4a1} (want {ALGO_ENGINE[1]}), ALGO 3 -> {t4a3} "
             f"(want {ALGO_ENGINE[3]})")
    if rows[by_name["track4_algo1"]]["ping"] != 1:
        fail("the ping-1 record slot was not exercised")
    note("MEASURED T5 (track 4, core A) publishes the same ALGO->engine map, at "
         "the ping-1 record slot: ALGO 1 -> 3, ALGO 3 -> 10")

    # (g) The render writes back nothing.
    after = data["after"]
    assert isinstance(after, dict)
    last: dict[int, Case] = {}
    for case in cases:
        last[case.track] = case
    final = last[0]
    if after["fp"] != final.staged():
        fail(f"the render rewrote the staged page words: left {after['fp']}, "
             f"expected the last case's {final.staged()}")
    hidden = after["hidden"]
    for track, case in last.items():
        if hidden[track * 6 + 5] != case.hidden:
            fail(f"the render rewrote track {track}'s persisted engine slot: "
                 f"{hidden[track * 6 + 5]}, expected {case.hidden}")
    for i, value in enumerate(hidden):
        if i % 6 != 5 and value != 0:
            fail(f"the render wrote the persisted parameter block at hidden "
                 f"index {i} (value {value})")
    note("MEASURED non-mutation: after every case the six staged page words "
         "still hold what was staged and the persisted parameter block is "
         "untouched (a one-trig p-lock does not become a new default)")

    if data["fallback"] != 0:
        fail(f"the stock FLEX fallback ran {data['fallback']} time(s): "
             f"admission let a non-PERKY track reach the renderer")


# --------------------------------------------------------------------------
# The shipping ColdFire artifact and the DSP-side dispatch byte
# --------------------------------------------------------------------------
def check_shipping_artifact() -> None:
    spec = importlib.util.spec_from_file_location(
        "perky_generate_light2", ROOT / "modules/perky/generate.py")
    if spec is None or spec.loader is None:
        fail("cannot import modules/perky/generate.py")
    generate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = generate
    spec.loader.exec_module(generate)
    if shutil.which("m68k-elf-gcc") is None:
        note("[SKIP] m68k-elf-gcc is not installed: the shipping-artifact compile "
             "half did not run")
        return
    try:
        text = generate.generate_text(CONTROL)
    except subprocess.CalledProcessError as exc:
        fail("the SHIPPING ColdFire compile (generate.py, m68k-elf-gcc) rejected "
             "the control source:\n" + (exc.stderr or "")[-4000:])
    for label in LABELS:
        if f'.string\t"{label}"' not in text:
            fail(f"the shipping ColdFire assembly does not carry the control "
                 f"label {label!r}")
    if "0x111111" not in text and "1118481" not in text:
        fail("the shipping ColdFire assembly does not carry the 0x00111111 "
             "staging-mask immediate")
    note("MEASURED shipping artifact: generate.py compiles "
         f"{CONTROL.name} with m68k-elf-gcc -Wall -Wextra -Werror; the emitted "
         "assembly carries the six labels and the 0x00111111 mask immediate")
    table = asm_table_bytes(text, "ALGO_ENGINE", len(ALGO_ENGINE))
    if table is None:
        note("NOTE: could not decode ALGO_ENGINE's initializer from the m68k "
             "assembly text; the executed host build already pinned the table")
    elif tuple(table) != ALGO_ENGINE:
        fail(f"the shipping assembly's ALGO_ENGINE is {tuple(table)}, expected "
             f"{ALGO_ENGINE}")


def asm_table_bytes(text: str, label: str, count: int) -> list[int] | None:
    """Decode a constant array's initializer from m68k-elf-gcc's assembly.

    Best effort: gas writes small constant arrays as ``.byte``/``.base64``/
    ``.string`` and this only needs to understand those.  A directive it does
    not know ends the array, and an empty result means "not decodable" (the
    executed host build has already pinned the table's content).
    """
    match = re.search(rf"(?m)^{label}:\n((?:\t\.[a-z0-9.]+.*\n)+)", text)
    if not match:
        return None
    out: list[int] = []
    for line in match.group(1).splitlines():
        line = line.strip()
        b64 = re.match(r'\.base64\s+"([^"]*)"', line)
        if b64:
            out += list(base64.b64decode(b64.group(1)))
            continue
        raw = re.match(r"\.(?:byte|short|word|long)\s+(.*)", line)
        if raw:
            out += [int(v, 0) for v in raw.group(1).split(",") if v.strip()]
            continue
        text_lit = re.match(r'\.(?:string|ascii)\s+"([^"]*)"', line)
        if text_lit:
            out += list(text_lit.group(1).encode("latin1"))
            continue
        break
    return out[:count] or None


def check_dsp_dispatch() -> None:
    """Pin the record byte this gate measures to the DSP dispatch that reads it.

    ``pk_render`` packs p[11] into record word 9's low half, which is DSP word
    19 (0x13).  The composed DSP source reads exactly ``move x:(r4+$13),a`` and
    masks it with ``and #>$ff,a`` before routing 0/3/2/10.  Those instructions
    are inserted by the tracked composers: build_multi_synth_source.py holds
    them in a triple-quoted template (real newlines), while
    build_fold_candidate.py builds its insertions from single-quoted literals
    with escaped newlines -- so the two files are searched in their own
    spelling.
    """
    synth = (ROOT / "tools/perky/build_multi_synth_source.py").read_text()
    fold = (ROOT / "tools/perky/build_fold_candidate.py").read_text()
    escaped = "\\n        "   # build_fold_candidate.py's literals
    for needle in ("move x:(r4+$13),a", "and #>$ff,a",
                   "cmp #>$a,a\n        bne pks_silence"):
        if needle not in synth:
            fail(f"the composed DSP source no longer reads and routes the engine "
                 f"byte the way this gate assumes: {needle!r} is missing from "
                 f"tools/perky/build_multi_synth_source.py")
    for needle in ("tst a" + escaped + "beq pks_fold_entry",
                   "cmp #>$3,a" + escaped + "beq pks_fold2_entry",
                   "cmp #>$2,a" + escaped + "beq pks_simple_entry"):
        if needle not in fold:
            fail(f"the composed DSP dispatch no longer routes one of the light "
                 f"engines: {needle!r} is missing from "
                 f"tools/perky/build_fold_candidate.py")
    note("MEASURED DSP tie-in: the composed DSP source reads DSP word 0x13 "
         "(= record word 9 low half = p[11]) with `move x:(r4+$13),a / and "
         "#>$ff,a` and routes engines 0/3/2/10 to Fold1/Fold2/Simple/Noise-Tone")


# --------------------------------------------------------------------------
def main() -> None:
    if not CONTROL.is_file():
        fail(f"missing control source {CONTROL}")
    cases = build_cases()
    data = execute(cases)
    if data:
        check_descriptor(data["desc"])
        check_admission(data["admit"])
        check_dispatch(cases, data)
    check_shipping_artifact()
    check_dsp_dispatch()
    print()
    print("PERKY light two-voice SRC page 1: PASS")
    if data:
        print("  exactly six controls, in order: TUNE / DECAY / ALGO / PAR1 / PAR2 / MODE")
        print("  staged through the normal path: P+0x18e/P+0x18a = 0x00111111/0x00000000")
        print("  p-lockable: all six staged words reach the record; MODE has 3 "
              "positions, ALGO has 4")
        print("  ALGO indirect: 0->Fold1(0), 1->Fold2(3), 2->Simple(2), 3->Noise/Tone(10)")
        print("  one-trig ALGO p-lock: 0->3->0 and 2->10->2 in the DSP dispatch byte (word 19)")
        print(f"  executed: host build of {CONTROL.name} + the real pk_render, "
              f"{len(cases)} cases")
    else:
        print("  NOT EXECUTED: no host C compiler; only the artifact and DSP "
              "tie-in checks ran")


if __name__ == "__main__":
    main()
