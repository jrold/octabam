#!/usr/bin/env python3
"""Generate wave.asm: constants computed here, the four voices unrolled.
--check refuses a stale wave.asm.

Every label is `wv` plus two digits, so no label is a prefix of another
(dsp_asm resolves labels by prefix, AGENTS.md)."""
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def q(v):
    """Q23, as the assembler's 24-bit hex."""
    n = int(round(v * 2 ** 23))
    if not -2 ** 23 <= n < 2 ** 23:
        raise ValueError(f"{v} is outside Q23")
    return f"$%06x" % (n & 0xFFFFFF)


# ---- the r7 instance block (X), $00..$67 -----------------------------------
BASE, GEN, SX, SY, LPH, LP, HP, LPY, HPY, POS, E1, E2, PREV, CNT, FLAST, INCC, VPH = range(17)
VOICE = 0x11                       # five words a voice: phase, b0, b1, h0, h1
INC = 0x25                         # $25..$28: the voices' increments, per block
POST, CUT, RES, FDEP, FINC, VDEP, VINC, LEVL = range(0x29, 0x31)
FBL, FBH, GAIN, MORPH, RA, RB, SUM, VMUL, XN, ROOT = range(0x31, 0x3b)
CHORD = 0x40                       # 8 shapes x 3 ratios, /4
RATE = 0x58                        # 16 LFO increments
TOP = 0x68

AMP = 0.45                         # table amplitude: a step between neighbours stays below 1.0
CHORDS = [(0, 0, 0), (12, 0, 12), (7, 12, 19), (4, 7, 12),
          (3, 7, 12), (4, 7, 11), (3, 7, 10), (5, 7, 12)]
CHORD_NAMES = ("UNI", "OCT", "5TH", "MAJ", "MIN", "MAJ7", "MIN7", "SUS4")
# CHOMPI's LFO rate law, .14 (65.41 / .14)^amount Hz, at 16 steps
RATE_HZ = [.14 * (65.41 / .14) ** (k / 15) for k in range(16)]
RATE_INC = [round(hz * 2 ** 24 / 44100) for hz in RATE_HZ]
RATE_LABELS = tuple(("%.2g" % hz).lstrip("0") if hz < 1 else "%.2g" % hz for hz in RATE_HZ)
# voice gain: CHOMPI's .2 a voice, at 1/16 inside the filters, from an
# envelope of mean |sine| (2/pi of the carrier's peak)
GAIN_K = math.pi / 2 * (0.2 / 16) / AMP
DETUNE = [-1.5, -0.5, 0.5, 1.5]   # x DETN x .0234: up to +-60 cents on the outer voices

lines = []
labels = iter(range(10, 100))


def L():
    return f"wv{next(labels):02d}"


def emit(*xs):
    lines.extend(xs)


def x(slot):
    return f"x:(r7+${slot:02x})"


# ---- init --------------------------------------------------------------------
def init():
    z = L()
    emit("init:",
         "        move    #>$ffffff,m4",
         "        move    r7,r4",
         "        clr     a",
         f"        do      #${TOP:02x},>{z}",
         "        move    a,x:(r4)+",
         f"{z}:",
         "        nop",
         "        move    x:>$213,r4                  ; the allocator's FX2 buffer base",
         "        move    x:(r4),a",
         f"        move    a,{x(BASE)}",
         f"        move    #>{q(AMP)},a",
         f"        move    a,{x(SY)}",
         "        move    #>$040000,a                 ; 1/(1-0), /32",
         f"        move    a,{x(LPY)}",
         f"        move    a,{x(HPY)}",
         "        move    #>$001000,a                 ; 4096: the first crossing only stamps",
         f"        move    a,{x(CNT)}",
         "        move    r7,r4",
         f"        move    #>${CHORD:02x},n4",
         "        move    (r4)+n4")
    for shape in CHORDS:
        for s in shape:
            emit(f"        move    #>{q(2 ** (s / 12) / 4)},x0", "        move    x0,x:(r4)+")
    for inc in RATE_INC:
        emit(f"        move    #>${inc:06x},x0", "        move    x0,x:(r4)+")
    emit("        rts", "")


# ---- table generation: 256 samples a call until 16,384 -----------------------
def generate():
    gen, done = "wv01", "wv02"
    emit(f"{gen}:",
         f"        move    {x(BASE)},a",
         f"        move    {x(GEN)},x0",
         "        add     x0,a",
         "        move    a1,r4",
         "        move    #>$ffffff,m4",
         f"        move    {x(GEN)},a",
         "        asr     #$b,a,a                     ; frame",
         "        move    a1,n4")
    frames = [L() for _ in range(8)]
    for k in range(1, 8):
        emit("        move    n4,a", f"        move    #>${k:06x},x0", "        cmp     x0,a",
             f"        beq     {frames[k]}")
    # frame 0: sine, the magic circle, x += e y; y -= e x
    send = L()
    emit(f"{frames[0]}:",
         f"        move    #>{q(2 * math.sin(math.pi / 2048))},y1",
         f"        do      #$100,>{send}")
    emit(f"        move    {x(SX)},a",
         "        move    a,y:(r4)+",
         f"        move    {x(SY)},x0",
         "        mac     x0,y1,a",
         f"        move    a,{x(SX)}",
         "        move    a,x0",
         f"        move    {x(SY)},b",
         "        mac     -x0,y1,b",
         f"        move    b,{x(SY)}",
         f"{send}:",
         "        nop",
         f"        bra     {done}")
    # frames 1..7 from the index i = GEN & 2047 (r5 counts it)

    def sample_loop(lbl, body):
        end = L()
        emit(f"{lbl}:",
             f"        move    {x(GEN)},a",
             "        and     #>$0007ff,a",
             "        move    a1,r5",
             f"        do      #$100,>{end}",
             "        move    r5,a                        ; i",
             *body,
             "        move    a,y:(r4)+",
             "        move    (r5)+",
             f"{end}:",
             "        nop",
             f"        bra     {done}")

    # triangle: i/512 rising, (1024 - i)/512, (i - 2048)/512; x 2 AMP after /2
    t1, t2, t3 = L(), L(), L()
    sample_loop(frames[1], [
        "        move    #>$000200,x0",
        "        cmp     x0,a",
        f"        blt     {t1}",
        "        move    #>$000600,x0",
        "        cmp     x0,a",
        f"        blt     {t2}",
        "        sub     #>$000800,a",
        f"        bra     {t1}",
        f"{t2}:",
        "        move    a,x0",
        "        move    #>$000400,a",
        "        sub     x0,a",
        f"{t1}:",
        "        asl     #$d,a,a                     ; t / 1024: half scale",
        "        move    a,x0",
        f"        move    #>{q(2 * AMP)},y1",
        "        mpy     x0,y1,a",
    ])
    # saw: i < 1024 ? i : i - 2048, / 1024
    s1 = L()
    sample_loop(frames[2], [
        "        move    #>$000400,x0",
        "        cmp     x0,a",
        f"        blt     {s1}",
        "        sub     #>$000800,a",
        f"{s1}:",
        "        asl     #$c,a,a                     ; t / 2048: half scale",
        "        move    a,x0",
        f"        move    #>{q(2 * AMP)},y1",
        "        mpy     x0,y1,a",
    ])
    # square and the zero-mean pulses: i < W ? AMP : -AMP w / (1 - w)
    for k, w in ((3, .5), (4, .25), (5, .125), (6, .0625), (7, .03125)):
        hi, lo = L(), L()
        sample_loop(frames[k], [
            f"        move    #>${int(2048 * w):06x},x0",
            "        cmp     x0,a",
            f"        blt     {hi}",
            f"        move    #>{q(-AMP * w / (1 - w))},a",
            f"        bra     {lo}",
            f"{hi}:",
            f"        move    #>{q(AMP)},a",
            f"{lo}:",
        ])
    zero = L()
    emit(f"{done}:",
         f"        move    {x(GEN)},a",
         "        add     #>$000100,a",
         f"        move    a,{x(GEN)}",
         "        clr     a",
         f"        do      n7,>{zero}",
         "        move    a,x:(r0)+",
         "        move    a,x:(r0)+",
         f"{zero}:",
         "        nop",
         "        rts", "")


# ---- reciprocal, inline: b = x in [2^-23, 1), a = the value shifted with it
# Normalises b to [.5, 1) in a counted DO (at most 23 doublings) and doubles
# a alongside; then y1 = (1/xn) / 2 by a seed and three Newton steps. a comes
# out in the slot `keep`. dsp_asm encodes no backward branch and no long
# jmp/jsr, and cycle_count prices a counted DO and a forward skip, so it is
# written inline with those alone.
def recip(keep):
    skip, end = L(), L()
    emit("        move    #>$400000,x0",
         f"        do      #$17,>{end}                 ; normalise: at most 23 doublings",
         "        cmp     x0,b",
         f"        bge     {skip}",
         "        asl     #$1,b,b",
         "        asl     #$1,a,a",
         f"{skip}:",
         "        nop",
         "        nop",
         f"{end}:",
         f"        move    a,{x(keep)}",
         f"        move    b,{x(XN)}                  ; xn",
         "        move    b,x1",
         f"        move    #>{q(1.4571 / 2)},a",
         "        asl     #$1,a,a",
         "        sub     x1,a                        ; the seed, 1.4571 - xn",
         "        move    a,y1")
    for _ in range(3):
        emit(f"        move    {x(XN)},x0",
             "        mpy     x0,y1,b                     ; xn y/2",
             "        move    #>$400000,a",
             "        sub     b,a",
             "        add     #>$400000,a                 ; 1 - xn y/2",
             "        move    a,x0",
             "        mpy     x0,y1,a",
             "        asl     #$1,a,a",
             "        move    a,y1")


# ---- a rising zero crossing, inline: x1 = this sample (halved) ---------------
def crossing():
    reject = L()
    emit(f"        move    x1,{x(SUM)}                  ; this sample, while x1 is in use",
         f"        move    {x(PREV)},a",
         "        neg     a                           ; num = -prev",
         f"        move    {x(SUM)},b",
         f"        move    {x(PREV)},x0",
         "        sub     x0,b                        ; den = cur - prev >= num")
    recip(GAIN)                                       # num 2^s parked in GAIN
    emit(f"        move    {x(GAIN)},x0",
         "        mpy     x0,y1,a",
         "        asl     #$1,a,a                     ; f = num / den (1.0 saturates)",
         "        move    a,x0",
         f"        move    {x(CNT)},a",
         "        asl     #$8,a,a                     ; CNT x 256",
         "        move    x0,b",
         "        asr     #$f,b,b",
         "        add     b,a",
         f"        move    {x(FLAST)},b",
         "        asr     #$f,b,b",
         "        sub     b,a                         ; T x 256",
         f"        move    x0,{x(FLAST)}",
         f"        move    {x(CNT)},b",
         "        move    #>$001000,x0",
         "        cmp     x0,b",
         f"        bge     {reject}",
         "        move    #>$000200,x0",
         "        cmp     x0,a",
         f"        ble     {reject}",
         "        move    a,b",
         "        move    #>$000001,a                 ; 2^-23, doubled with the normalisation")
    recip(ROOT)                                       # 2^(s-23) parked (ROOT is per block, free here)
    emit(f"        move    {x(ROOT)},x0",
         "        mpy     x0,y1,a",
         "        asl     #$a,a,a                     ; inc = 2^32 / (T x 256)",
         f"        move    a,{x(INCC)}",
         f"{reject}:",
         "        clr     a",
         f"        move    a,{x(CNT)}",
         f"        move    {x(SUM)},x1")


# ---- one voice ---------------------------------------------------------------
def voice(k):
    s = VOICE + 5 * k
    emit(f"; voice {k}",
         f"        move    {x(s)},a",
         "        lsr     #$d,a",
         "        move    a1,n2",
         "        move    a1,n3",
         f"        move    {x(s)},b",
         "        and     #>$001fff,b",
         "        asl     #$a,b,b",
         "        move    b1,y1                       ; frac",
         f"        move    {x(RA)},r2",
         "        move    (r2)+n2",
         "        move    y:(r2)+,b",
         "        move    y:(r2),x0",
         "        move    x0,a",
         "        sub     b,a",
         "        move    a,x0",
         "        mac     x0,y1,b                     ; frame A",
         "        move    b,y0",
         f"        move    {x(RB)},r3",
         "        move    (r3)+n3",
         "        move    y:(r3)+,b",
         "        move    y:(r3),x0",
         "        move    x0,a",
         "        sub     b,a",
         "        move    a,x0",
         "        mac     x0,y1,b                     ; frame B",
         "        move    y0,a",
         "        sub     a,b",
         "        move    b,x0",
         f"        move    {x(MORPH)},y1",
         "        mac     x0,y1,a                     ; A + morph (B - A)",
         "        move    a,x0",
         f"        move    {x(GAIN)},y1",
         "        mpy     x0,y1,a                     ; x envelope",
         # DjFilter: BasicMMF low-pass, then high-pass
         "        move    a,x1",
         f"        move    {x(s + 1)},a",
         f"        move    {x(s + 2)},x0",
         "        sub     x0,a",
         "        move    a,x0",
         f"        move    {x(FBL)},y1",
         "        mpy     x0,y1,b",
         "        asl     #$5,b,b",
         "        add     x1,b",
         f"        move    {x(s + 1)},x0",
         "        sub     x0,b",
         "        move    b,x0",
         f"        move    {x(LP)},y1",
         f"        move    {x(s + 1)},a",
         "        mac     x0,y1,a",
         f"        move    a,{x(s + 1)}",
         f"        move    {x(s + 2)},b",
         "        sub     b,a",
         "        move    a,x0",
         "        mac     x0,y1,b",
         f"        move    b,{x(s + 2)}",
         "        move    b,x1",
         f"        move    {x(s + 3)},a",
         f"        move    {x(s + 4)},x0",
         "        sub     x0,a",
         "        move    a,x0",
         f"        move    {x(FBH)},y1",
         "        mpy     x0,y1,b",
         "        asl     #$5,b,b",
         "        add     x1,b",
         f"        move    {x(s + 3)},x0",
         "        sub     x0,b",
         "        move    b,x0",
         f"        move    {x(HP)},y1",
         f"        move    {x(s + 3)},a",
         "        mac     x0,y1,a",
         f"        move    a,{x(s + 3)}",
         f"        move    {x(s + 4)},b",
         "        sub     b,a",
         "        move    a,x0",
         "        mac     x0,y1,b",
         f"        move    b,{x(s + 4)}",
         "        move    x1,b",
         f"        move    {x(s + 3)},x0",
         "        sub     x0,b",
         f"        move    {x(SUM)},x0",
         "        add     x0,b",
         f"        move    b,{x(SUM)}",
         # phase += increment x vibrato
         f"        move    {x(INC + k)},x0",
         f"        move    {x(VMUL)},y1",
         "        mpy     x0,y1,b",
         "        asl     #$1,b,b",
         "        move    b1,x0",
         f"        move    {x(s)},a",
         "        add     x0,a",
         f"        move    a1,{x(s)}")


def clamp(acc, lo_zero, hi):
    a, b = L(), L()
    emit(f"        tst     {acc}",
         f"        bge     {a}",
         f"        clr     {acc}",
         f"{a}:",
         f"        move    #>{q(hi)},x0",
         f"        cmp     x0,{acc}",
         f"        ble     {b}",
         f"        move    x0,{acc}",
         f"{b}:")


def tri(phase_slot, inc_slot, depth_slot):
    """DaisySP WAVE_TRI x depth into a, the phase advanced."""
    emit(f"        move    {x(phase_slot)},a",
         f"        move    {x(inc_slot)},x0",
         "        add     x0,a",
         f"        move    a1,{x(phase_slot)}",
         f"        move    {x(phase_slot)},a",
         "        add     #>$800000,a",
         "        move    a1,x0",
         "        move    x0,a",
         "        abs     a",
         "        sub     #>$400000,a",
         "        asl     #$1,a,a",
         "        move    a,x0",
         f"        move    {x(depth_slot)},y1",
         "        mpy     x0,y1,a")


def proc():
    emit("proc:",
         f"        move    {x(GEN)},a",
         "        move    #>$004000,x0",
         "        cmp     x0,a",
         "        blt     wv01",
         # ---- per block: the knobs
         "        move    x:(r6),a",
         "        and     #>$7f0000,a",
         "        move    a1,x0",
         f"        move    #>{q(7 / 8 * 128 / 127)},y1",
         "        mpy     x0,y1,a                     ; FRAM -> frames 0..7, /8",
         f"        move    a,{x(POST)}",
         "        move    x:(r6+$1),a",
         "        and     #>$7f0000,a",
         f"        move    a1,{x(CUT)}",
         "        move    x:(r6+$2),a",
         "        and     #>$7f0000,a",
         "        move    a1,x0",
         f"        move    #>{q(.99 * .95 * 128 / 127)},y1",
         "        mpy     x0,y1,a                     ; RES: setMasterResonance x .95",
         f"        move    a,{x(RES)}",
         "        move    x:(r6+$5),a",
         "        and     #>$7f0000,a",
         f"        move    a1,{x(LEVL)}",
         "        move    x:(r6+$c),a",
         "        and     #>$ff0000,a",
         f"        move    a1,{x(FDEP)}",
         "        move    x:(r6+$c),a",
         "        and     #>$00ff00,a",
         "        asr     #$8,a,a",
         "        move    r7,b",
         f"        add     #>${RATE:06x},b",
         "        add     a,b",
         "        move    b1,r4",
         "        nop",
         "        move    x:(r4),a",
         f"        move    a,{x(FINC)}",
         "        move    x:(r6+$d),a",
         "        and     #>$ff0000,a",
         f"        move    a1,{x(VDEP)}",
         "        move    x:(r6+$d),a",
         "        and     #>$00ff00,a",
         "        asr     #$8,a,a",
         "        move    r7,b",
         f"        add     #>${RATE:06x},b",
         "        add     a,b",
         "        move    b1,r4",
         "        nop",
         "        move    x:(r4),a",
         f"        move    a,{x(VINC)}")
    # the root: the carrier's increment >> (4 - OCT)
    emit(f"        move    {x(INCC)},a",
         "        move    x:(r6+$4),b",
         "        and     #>$7f0000,b                 ; the companion byte is not the knob",
         "        asr     #$10,b,b                    ; OCT, b0 clean",
         "        move    #>$000004,x0",
         "        cmp     x0,b",
         "        tgt     x0,b                        ; OCT clamped to 0..4",
         "        sub     x0,b",
         "        neg     b                           ; octaves down",
         "        move    b1,n3",
         "        tst     b")
    sh = L()
    emit(f"        beq     {sh}",
         f"        do      n3,>{sh}",
         "        asr     #$1,a,a",
         f"{sh}:",
         f"        move    a,{x(ROOT)}                 ; root increment")
    # chord row: r4 = r7 + CHORD + 3 CHRD
    emit("        move    x:(r6+$3),a",
         "        and     #>$7f0000,a",
         "        asr     #$10,a,a",
         "        move    a,b",
         "        asl     #$1,a,a",
         "        add     b,a",
         "        move    r7,b",
         f"        add     #>${CHORD:06x},b",
         "        add     a,b",
         "        move    b1,r4",
         "        move    x:(r6+$e),a",
         "        and     #>$ff0000,a",
         "        move    a1,x1                       ; DETN")
    for k in range(4):
        emit(f"        move    {x(ROOT)},x0")
        if k:
            emit("        move    x:(r4)+,y1",
                 "        mpy     x0,y1,a",
                 "        asl     #$2,a,a                     ; root x 2^(s/12)",
                 "        move    a,x0")
        else:
            emit("        move    x0,a")
        emit(f"        move    #>{q(DETUNE[k] * 0.0234)},y1",
             "        move    x1,b",
             "        move    b,x0",
             "        mpy     x0,y1,b",
             "        move    b,y1")
        if k:
            emit("        move    a,x0")
        else:
            emit(f"        move    {x(ROOT)},x0")
        emit("        mac     x0,y1,a                     ; x (1 + spread)",
             f"        move    a,{x(INC + k)}")
    emit("        move    #>$0007ff,m2",
         "        move    #>$0007ff,m3",
         "        move    #>$000001,n0",
         "        do      n7,>wv98")
    # ---- per sample
    emit("        move    x:(r0),a",
         "        move    x:(r0+n0),x0",
         "        add     x0,a",
         "        asr     #$2,a,a                     ; mono, halved again for the crossing arithmetic",
         "        move    a,x1",
         # envelope: |m| through two one-poles, 2 ms each
         "        abs     a",
         f"        move    {x(E1)},b",
         "        sub     b,a",
         "        asr     #$7,a,a",
         "        add     b,a",
         f"        move    a,{x(E1)}",
         f"        move    {x(E2)},b",
         "        sub     b,a",
         "        asr     #$7,a,a",
         "        add     b,a",
         f"        move    a,{x(E2)}",
         # the crossing counter, saturating at 4096
         f"        move    {x(CNT)},a",
         "        add     #>$000001,a",
         "        move    #>$001000,x0",
         "        cmp     x0,a")
    c1, nc = L(), L()
    emit(f"        ble     {c1}",
         "        move    x0,a",
         f"{c1}:",
         f"        move    a,{x(CNT)}",
         f"        move    {x(PREV)},a",
         "        tst     a",
         f"        bge     {nc}",
         "        move    x1,b",
         "        tst     b",
         f"        blt     {nc}",
         f"        move    {x(E2)},a",
         "        move    #>$001000,x0",
         "        cmp     x0,a",
         f"        blt     {nc}")
    crossing()
    emit(f"{nc}:",
         f"        move    x1,{x(PREV)}")
    # filter LFO, the control, the coefficients
    tri(LPH, FINC, FDEP)
    emit(f"        move    {x(CUT)},x0",
         "        add     x0,a                        ; c = cutoff + LFO",
         "        move    a,b",
         "        asl     #$1,b,b",
         f"        add     #>{q(.01)},b")
    clamp("b", True, .98)
    emit("        move    b,x0",
         "        move    b,y1",
         "        mpy     x0,y1,b",
         "        move    b,x0",
         "        mpy     x0,y1,b                     ; lp target, (.01 + 2c)^3",
         "        move    a,x0",
         f"        move    #>{q(.95)},y1",
         "        mpy     x0,y1,a",
         "        asl     #$1,a,a",
         "        sub     #>$400000,a",
         "        sub     #>$400000,a                 ; 1.9c - 1")
    clamp("a", True, .9)
    emit("        move    a,x0",
         "        move    a,y1",
         "        mpy     x0,y1,a",
         "        move    a,x0",
         "        mpy     x0,y1,a                     ; hp target",
         f"        move    #>{q(.0002)},y1")
    for tgt, slot in (("b", LP), ("a", HP)):
        emit(f"        move    {x(slot)},x0",
             f"        sub     x0,{tgt}",
             f"        move    {tgt},x0",
             f"        mpy     x0,y1,{tgt}",
             f"        move    {x(slot)},x0",
             f"        add     x0,{tgt}",
             f"        move    {tgt},{x(slot)}                 ; fonepole .0002")
    for slot, ys, fb in ((LP, LPY, FBL), (HP, HPY, FBH)):
        emit("        move    #>$7fffff,a",
             f"        move    {x(slot)},x0",
             "        sub     x0,a",
             "        move    a,x0",
             f"        move    {x(ys)},y1",
             "        mpy     x0,y1,b",
             "        move    #>$040000,a",
             "        sub     b,a",
             "        move    a,x0",
             "        mpy     x0,y1,a",
             "        asl     #$5,a,a",
             "        add     y1,a",
             f"        move    a,{x(ys)}                 ; Newton: 1/(1-f), /32",
             "        move    a,y1",
             f"        move    {x(RES)},x0",
             "        mpy     x0,y1,a",
             "        move    x0,b",
             "        asr     #$5,b,b",
             "        add     b,a",
             f"        move    a,{x(fb)}                 ; feedback /32: res + res/(1-f)")
    # the frame position, smoothed; A and B frame bases; the morph
    emit(f"        move    {x(POST)},a",
         f"        move    {x(POS)},b",
         "        sub     b,a",
         "        asr     #$8,a,a",
         "        add     b,a",
         f"        move    a,{x(POS)}",
         "        move    a,b",
         "        and     #>$0fffff,b",
         "        asl     #$3,b,b",
         "        move    b1,x0",
         f"        move    x0,{x(MORPH)}",
         "        asr     #$14,a,a",
         "        asl     #$b,a,a",
         f"        move    {x(BASE)},x0",
         "        add     x0,a",
         f"        move    a1,{x(RA)}",
         "        add     #>$000800,a",
         f"        move    a1,{x(RB)}")
    # vibrato: 2^(lfo/6) / 2 = .5 + y/2 + y^2/4, y = lfo ln2 / 6
    tri(VPH, VINC, VDEP)
    emit("        move    a,x0",
         f"        move    #>{q(math.log(2) / 6)},y1",
         "        mpy     x0,y1,a",
         "        move    a,x0",
         "        move    a,y1",
         "        mpy     x0,y1,b",
         "        asr     #$2,b,b",
         "        asr     #$1,a,a",
         "        add     b,a",
         "        add     #>$400000,a",
         f"        move    a,{x(VMUL)}",
         # the voices' gain: the envelope x K
         f"        move    {x(E2)},x0",
         f"        move    #>{q(GAIN_K)},y1",
         "        mpy     x0,y1,a",
         f"        move    a,{x(GAIN)}",
         "        clr     a",
         f"        move    a,{x(SUM)}")
    # an envelope that has reached zero: the voices' states cleared, silence
    # out. mpy truncates toward -inf, so a filter with no input settles on a
    # small offset rather than zero (736 LSB of DC at the output, measured).
    sil, end = L(), L()
    emit(f"        move    {x(E2)},a",
         "        tst     a",
         f"        beq     {sil}")
    for k in range(4):
        voice(k)
    emit(f"        move    {x(SUM)},x0",
         f"        move    {x(LEVL)},y1",
         "        mpy     x0,y1,a",
         "        asl     #$4,a,a                     ; x 8 at LEVL 64",
         "        move    a,x:(r0)+",
         "        move    a,x:(r0)+",
         f"        move    {x(E2)},a",
         "        tst     a",
         f"        bne     {end}                       ; sounding: past the silence path",
         f"{sil}:",
         "        clr     a")
    for k in range(4):
        for j in range(1, 5):
            emit(f"        move    a,{x(VOICE + 5 * k + j)}")
    emit("        move    a,x:(r0)+",
         "        move    a,x:(r0)+",
         f"{end}:",
         "        nop",
         "wv98:",
         "        nop",
         "        move    #>$ffffff,m2",
         "        move    #>$ffffff,m3",
         "        rts", "")


HEADER = f"""; CYCLES_FORWARD_BRANCHES
; WAVE -- a 4-voice wavetable synth as an FX2 effect: a port of CHOMPI
; WAVE's voice (CHOMPI-Club/CHOMPI a73d732, MIT; LICENSE-CHOMPI) onto the DSP.
; Generated by generate.py; edit that.
;
; The track plays a sine (the carrier). Its period, from the interpolated
; rising zero crossing, sets the voices' root (OCT octaves down); its level,
; through two 2 ms one-poles, is the envelope. So PTCH, the CHROMATIC keys,
; SCALE QUANTIZER, p-locks and AMP play the synth.
;
; The FX2 buffer (Y, 16,384 words) holds eight 2,048-sample frames, written
; 256 samples a call after init (sine, triangle, saw, square, pulses 1/4 ..
; 1/32, zero-mean, peak {AMP}); the output is silent until they are done.
;
; r7 block: $00 base, $01 generated, $02/$03 sine state, $04 filter LFO
; phase, $05/$06 lp/hp, $07/$08 1/(1-f)/32, $09 frame position, $0a/$0b
; envelope, $0c previous sample, $0d samples since the crossing, $0e its
; fraction, $0f carrier increment, $10 vibrato phase, $11..$24 voices
; (phase, b0, b1, h0, h1), $25..$28 increments, $29..$30 knobs, $31..$3a
; per-sample values, $40..$57 chord ratios / 4, $58..$67 LFO increments.
"""


def build():
    init()
    proc()
    generate()
    return HEADER + "\n" + "\n".join(lines) + "\n"


def main():
    body = build()
    out = HERE / "wave.asm"
    if "--check" in sys.argv:
        if not out.exists() or out.read_text() != body:
            raise SystemExit(f"stale: {out}")
        print("wave.asm matches generate.py")
    else:
        out.write_text(body)
        print(f"wrote {out}: {body.count(chr(10))} lines")


if __name__ == "__main__":
    main()
