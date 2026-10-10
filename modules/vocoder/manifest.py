"""VOCODER -- a ten-band channel vocoder after the Roland VP-330.

A per-track insert. The track's audio is the modulator (a voice); the carrier
is the built-in 8' and 4' sawtooths at NOTE (p-lock NOTE on the steps to play a
melody), or the track's right channel with MODE EXT (a THRU track with the
voice on input A and a synth on input B). Ten bands at the VP-330's centres,
each a 4th-order pair on both sides, so the formants stay apart and the words
come through. modules/vocoder/DESIGN.md has the law and the reasons;
vocoder_ref.py is the float reference.
"""
import sys as _sys
from pathlib import Path as _Path

from remix.schema import (BusRole, Category, DspSection, Formatter, Gate, Harness,
                          Kind, MenuEntry, Module, Param, Proof, YBase)

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import vocoder_law as _ref  # noqa: E402  (numpy-free: the build runs on plain python3)


def _q23(v):
    """Q23, two's complement in 24 bits, held at the largest positive value."""
    return min(round(v * (1 << 23)), 0x7FFFFF) & 0xFFFFFF


# P table, 172 words, read through the ptable literal:
#   +0   BAND[10] x {f1, f2, W/2, f1, f2}  in the order the band loop reads them
#   +50  NINC[61]   NOTE step k (C1 + k) -> the phase increment, a cycle 2^24
#   +111 NIDT[61]   1/(du 2^11), du = NINC / 2^24, for the polyBLEP
BAND = tuple(_q23(v) for f1, f2, w in _ref.band_coefs() for v in (f1, f2, w, f1, f2))
NINC = tuple(_ref.note_inc(k) for k in range(61))
NIDT = tuple(_q23(_ref.note_idt(k)) for k in range(61))

NOTE_LABELS = tuple(_ref.note_name(k) for k in range(61))
_P = Formatter.PLAIN
_BLANK = Param(b"", 0)

MODULE = Module(
    name="vocoder",
    key="VOCODER",
    kind=Kind.DSP_EFFECT,
    category=Category.TRACK, author="Ignorato", author_url="https://github.com/Ignorato",
    proof=Proof.HARDWARE, proof_note="Ignorato's MKII, 4-5 Oct 2026, by ear: OCTABAM12 at the earlier positions T1 T2 T5 T6, stable on all eight tracks; this build at T2 T3 T6 T7 not flashed; those positions heard clean on the 0.2 code only (OCTABAM20, branch vocoder-0.2 at f83463c8)",
    doc="Ten-band vocoder after the Roland VP-330: the track's voice, a built-in carrier at NOTE or input B. FX2 of tracks 2, 3, 6 and 7 only.",
    menu=MenuEntry(
        fx2_id=0x1a,
        donor_desc=0x400d58b8,        # DARK REV
        abbr=b"VOCO",
        fullname=b"VOCODER",
        build_tag=False,
    ),
    params=(
        Param(b"NOTE", 24, 61, active=True, formatter=Formatter.WIDE_STEPPED, labels=NOTE_LABELS,
              doc="the built-in carrier's pitch, C1 to C6; p-lock it to play a melody"),
        Param(b"CONS", 48, 128, active=True, formatter=_P,
              doc="consonants: the voice above 4 kHz passed through, as the VP-330 does"),
        Param(b"DRY", 0, 128, active=True, formatter=_P,
              doc="the dry voice mixed in"),
        Param(b"LEVL", 100, 128, active=True, formatter=_P,
              doc="output level: 127 = unity"),
        _BLANK, _BLANK,
        Param(b"MODE", 0, 2, active=True, formatter=Formatter.STEPPED, labels=("INT", "EXT"),
              doc="carrier: INT the built-in sawtooths at NOTE; EXT the right channel (input B)"),
        _BLANK, _BLANK, _BLANK, _BLANK, _BLANK,
    ),
    mode_slot=6,
    dsp=DspSection(
        asm="modules/vocoder/vocoder.asm",
        ptable=BAND + NINC + NIDT,
        priority=19,
        bus_role=BusRole.NONE,        # an insert
        ybase=YBase.NEVER,            # no buffers, nothing in the shared window
        r7_latch_slot=None,
        gate_label=None,
    ),
    harness=Harness(layout_char="X", is_server=False, render_r7=5),   # runs at 0x6500/0x6800 only
    gates=(Gate("tools/verify/verify_vocoder.py", remix_arg=False),),
    dear={"NOTE": 60, "CONS": 127, "DRY": 127, "LEVL": 127, "MODE": 1},
)
