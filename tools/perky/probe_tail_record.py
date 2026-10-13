#!/usr/bin/env python3
"""Build a probe image that answers step 2's one open question.

THE QUESTION
    The stock DSP boot routine reads a payload's record table and writes each
    record's words to its ``addr`` in DSP memory. Step 2 needs records at
    addresses no stock record covers (the "tails"). Does the routine accept
    that, or does it validate ``addr`` and refuse?

    Five measurements say it probably accepts (r127, r133, r134, r135, r136);
    none proves it. This produces the image that settles it in one flash/run.

THE PROBE
    Take payload A. RE-POINT one existing record -- SPRING, at 0x01252, 1063
    words -- to a tail address, and fill its words with a recognisable pattern.
    That is a PURE IN-PLACE edit: no insertion, no growth, no shifting, so the
    only difference from the stock image is the record's ``addr`` and its bytes.

    Re-pointing is the operation payload A needs anyway (r131), so a positive
    result is the real answer, not a synthetic one.

HOW TO READ THE RESULT
    Boot the probe image and peek DSP P memory at the tail address:

        dsp peek <core> P 0x33da3 8

    * the pattern appears  ->  the routine writes wherever ``addr`` says.
                               Step 2's mechanism is sound; proceed with the plan.
    * silence / stock bytes ->  the routine refuses or ignores the record.
                               Stop and read the stock DSP boot routine.

SELF-TEST
    ``--selftest`` performs the edit on an in-memory copy and re-parses it, so
    the file's claim about the format is checked on every run and not assumed.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools' / 'build')]

import dsp_modmap as M  # noqa: E402

# SPRING REV in payload A: 0x01252, 1063 words (modules/perky/MEMORY.md).
# Chosen because it is retired by the milestone's FX priorities, so re-pointing
# it costs nothing the goal wants to keep.
DONOR_ADDR, DONOR_COUNT = 0x01252, 1063
# The first tail span, from all_fx_layout.SAFE_SHARED_P_SPANS.
TAIL_ADDR = 0x33DA3
# A word pattern that cannot be mistaken for stock code: 0xABCDEF little-endian
# in the image's 3-byte packing.
MARKER = bytes([0xEF, 0xCD, 0xAB])


def w24(v: int) -> bytes:
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF])


def rd24(b: bytes, o: int) -> int:
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def find_record(blob: bytes, addr: int):
    mods, _ = M.parse(blob, 'ac')
    for m in mods:
        if m[1] == addr:
            return m, mods
    return None, mods


def probe_payload(blob: bytes) -> bytes:
    """Return a copy of `blob` with SPRING re-pointed to TAIL and marked."""
    rec, mods = find_record(blob, DONOR_ADDR)
    if rec is None:
        raise SystemExit(f'record for 0x{DONOR_ADDR:05x} not found')
    sp, addr, cnt, data = rec
    if cnt != DONOR_COUNT:
        raise SystemExit(f'0x{DONOR_ADDR:05x} has {cnt} words, expected {DONOR_COUNT}')

    out = bytearray(blob)
    hdr = data - 9                       # the record's 9-byte header
    out[hdr + 3:hdr + 6] = w24(TAIL_ADDR)      # addr is the SECOND field ("ac")
    for i in range(cnt):                       # mark every word
        out[data + i * 3:data + i * 3 + 3] = MARKER
    return bytes(out)


def selftest() -> int:
    """Prove the edit round-trips through the parser before anyone builds with it."""
    img = (ROOT / 'out/mainos_bus.bin').read_bytes()
    tag, va, ln = [p for p in M.PAYLOADS if p[0] == 'A'][0]
    blob = img[va - M.BASE: va - M.BASE + ln]

    before, mods_before = find_record(blob, DONOR_ADDR)
    after_blob = probe_payload(blob)
    after, mods_after = find_record(after_blob, TAIL_ADDR)

    checks = [
        ('the donor record exists', before is not None),
        ('the probe record is at the tail', after is not None),
        ('the record count is unchanged', len(mods_before) == len(mods_after)),
        ('the donor address is gone', find_record(after_blob, DONOR_ADDR)[0] is None),
        ('the word count is preserved', after is not None and after[2] == DONOR_COUNT),
        ('the payload length is unchanged', len(blob) == len(after_blob)),
        ('_p_off resolves the tail',
         any(m[0] == 0 and m[1] <= TAIL_ADDR < m[1] + m[2] for m in mods_after)),
        ('the marker is in the image bytes',
         after is not None and after_blob[after[3]:after[3] + 3] == MARKER),
    ]
    ok = True
    for name, good in checks:
        print(f'  [{"ok" if good else "FAIL"}] {name}')
        ok &= good
    if not ok:
        raise SystemExit('selftest: the probe does not round-trip -- do not build with it')
    print(f'  selftest: SPRING 0x{DONOR_ADDR:05x} -> tail 0x{TAIL_ADDR:05x}, '
          f'{DONOR_COUNT} words marked')
    return 0


def emit(image: pathlib.Path, out: pathlib.Path) -> int:
    img = bytearray(image.read_bytes())
    tag, va, ln = [p for p in M.PAYLOADS if p[0] == 'A'][0]
    off = va - M.BASE
    probed = probe_payload(bytes(img[off:off + ln]))
    if len(probed) != ln:
        raise SystemExit('the probe changed the payload length; it must be in-place')
    img[off:off + ln] = probed
    out.write_bytes(bytes(img))
    print(f'  wrote {out} ({len(img):,} B)')
    print(f'  payload A: SPRING 0x{DONOR_ADDR:05x} re-pointed to 0x{TAIL_ADDR:05x}; '
          f'its {DONOR_COUNT} words are now 0xABCDEF')
    print(f'  peek after boot:  dsp peek <core> P 0x{TAIL_ADDR:05x} 8')
    print('    pattern present -> the routine writes wherever addr says')
    print('    stock bytes     -> it refuses; read the stock DSP boot routine')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true',
                    help='prove the edit round-trips through the parser, write nothing')
    ap.add_argument('--image', type=pathlib.Path, default=ROOT / 'out/mainos_bus.bin')
    ap.add_argument('--out', type=pathlib.Path, default=ROOT / 'out/mainos_probe_tail.bin')
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.image.is_file():
        raise SystemExit(f'no image at {args.image} (run `make bus REMIX=perky-machine`)')
    return emit(args.image, args.out)


if __name__ == '__main__':
    raise SystemExit(main())
