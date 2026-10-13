#!/usr/bin/env python3
"""Recover the DSP56300 module load map from the MAIN OS image: which bytes
load to which DSP address in which memory space.

The ColdFire boots the DSP twice (GPIO 0xfc0a400c selects 0 then 1), each
time uploading a small bootstrap to P memory and then a self-describing
payload:

    FUN_40001d4c(0x400e21e0, 0x96,  0x31000)   bootstrap A -> P:0x31000
    FUN_40001b18(0x400e2324)                   payload A   (self-describing)
    FUN_40001d4c(0x400e2276, 0xae,  0x32000)   bootstrap B -> P:0x32000
    FUN_40001b18(0x400f59ef)                   payload B   (self-describing)

FUN_40001b18 walks 24-bit little-endian words: an optional 3-header and an
optional 4-header (6 bytes each), then records whose leading word is the
memory space (0/1/2), terminated by a word > 3.

    python3 tools/build/dsp_modmap.py
"""
import pathlib, sys

BASE = 0x40000400
IMG = pathlib.Path("out/raw/section_3_MAIN_OS.bin")
SPACE = {0: "P", 1: "X", 2: "Y", 3: "?"}

PAYLOADS = [("A", 0x400e2324, 0x136cb), ("B", 0x400f59ef, 0x12d05)]
BOOTSTRAPS = [("A", 0x400e21e0, 0x96, 0x31000), ("B", 0x400e2276, 0xae, 0x32000)]


def w24(b, i):
    """24-bit little-endian word, as FUN_40001b18 assembles it."""
    return b[i] | (b[i + 1] << 8) | (b[i + 2] << 16)


def parse(b, order):
    """Walk the records. `order` picks (count,addr) vs (addr,count) -- the
    decompilation did not make the field order unambiguous, so try both and
    keep whichever consumes the blob cleanly."""
    off = 0
    if b[0] == 3:
        off = 6
    if off < len(b) and b[off] == 4:
        off += 6
    mods, guard = [], 0
    while off + 9 <= len(b):
        guard += 1
        if guard > 5000:
            return None, "runaway"
        sp = w24(b, off)
        if sp > 3:
            return mods, f"terminator 0x{sp:06x} at +0x{off:x}"
        f1, f2 = w24(b, off + 3), w24(b, off + 6)
        cnt, addr = (f1, f2) if order == "ca" else (f2, f1)
        if cnt == 0 or cnt > 0x20000:
            return None, f"implausible count {cnt} at +0x{off:x}"
        data = off + 9
        end = data + cnt * 3
        if end > len(b):
            return None, f"record overruns blob at +0x{off:x} (count {cnt})"
        mods.append((sp, addr, cnt, data))
        off = end
    return mods, "ran off the end"


def modules(img, va, ln):
    """Best-effort parse of one payload -> list of (space, addr, count, data_off)."""
    b = img[va - BASE: va - BASE + ln]
    best = None
    for order in ("ca", "ac"):
        mods, _ = parse(b, order)
        if mods:
            consumed = mods[-1][3] + mods[-1][2] * 3
            if best is None or consumed > best[0]:
                best = (consumed, mods)
    return (best[1] if best else []), b


# --- writing the record table -------------------------------------------------
#
# `parse` reads the table; the two functions below change it. They exist because
# a module can need DSP code at an address NO stock record covers -- the "tails"
# -- and a word with no record cannot be written: build_bus._p_off sys.exits.
# So the record has to be created or re-pointed first.
#
# Both shapes are measured against the real image (payload A and B both parse as
# order "ac") and both round-trip through `parse`; see
# modules/perky/FX_RECOVERY_HANDOFF.md rounds 121-142 and the self-test in
# tools/perky/probe_tail_record.py, from which this logic is lifted.

def _w24(v: int) -> bytes:
    """Three-byte little-endian packing, the inverse of `w24`."""
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF])


def _record_header(order: str, space: int, addr: int, count: int) -> bytes:
    if order == "ac":
        return _w24(space) + _w24(addr) + _w24(count)
    if order == "ca":
        return _w24(space) + _w24(count) + _w24(addr)
    raise ValueError(f'order must be "ac" or "ca", not {order!r}')


def repoint(blob: bytes, old_addr: int, new_addr: int, order: str = "ac") -> bytes:
    """Return `blob` with the record at `old_addr` re-pointed to `new_addr`.

    The words do not move and the count does not change -- only the `addr`
    field. This is payload A's operation: the retired effects' records are one
    contiguous run and their space is repurposed rather than extended.
    """
    mods, _ = parse(blob, order)
    for sp, addr, cnt, data in mods:
        if sp == 0 and addr == old_addr:
            out = bytearray(blob)
            hdr = data - 9
            if order == "ac":
                out[hdr + 3:hdr + 6] = _w24(new_addr)
            else:
                out[hdr + 6:hdr + 9] = _w24(new_addr)
            return bytes(out)
    raise KeyError(f"no P record at 0x{old_addr:05x}")


def terminator_offset(blob: bytes, order: str = "ac") -> int:
    """Offset of the terminating record: where a new record must be inserted."""
    mods, _ = parse(blob, order)
    if not mods:
        raise ValueError("no records")
    last = mods[-1]
    return last[3] + last[2] * 3


def append(blob: bytes, space: int, addr: int, words: bytes,
           order: str = "ac") -> bytes:
    """Return `blob` with a record for `addr` inserted before the terminator.

    `words` must be `count * 3` bytes, stored inline. This is payload B's
    operation: it has slack after its table, so a record can be added.
    """
    if len(words) % 3:
        raise ValueError("words must be a whole number of 3-byte DSP words")
    count = len(words) // 3
    at = terminator_offset(blob, order)
    record = _record_header(order, space, addr, count) + words
    return blob[:at] + record + blob[at:]


def extract(img, args):
    """--extract <A|B> <hex dsp addr> <out.bin>  : dump one module's raw words."""
    tag, addr_s, out = args
    addr = int(addr_s, 16)
    for t, va, ln in PAYLOADS:
        if t != tag.upper():
            continue
        mods, b = modules(img, va, ln)
        for sp, a, cnt, data in mods:
            if a == addr:
                blob = b[data: data + cnt * 3]
                pathlib.Path(out).write_bytes(blob)
                print(f"payload {t} {SPACE.get(sp,'?')}:0x{addr:05x}  {cnt:,} words "
                      f"({len(blob):,} B) -> {out}")
                print(f"  disassemble with:")
                print(f"    vendor/dsp56300/build/source/disassemble/dsp56kDisassemble \\")
                print(f"        -in {out} -pc {addr:x} -le")
                return
        sys.exit(f"no module at 0x{addr:05x} in payload {t}")
    sys.exit(f"unknown payload {tag}")


def dumpmem(img, args):
    """--dumpmem <A|B> <out.mem> : flat memory image for the emulator harness.

    Format (little-endian): per module [u8 space][u32 addr][u32 count] then
    count * u32 words. Terminated by space == 0xff.
    """
    import struct
    tag, out = args
    for t, va, ln in PAYLOADS:
        if t != tag.upper():
            continue
        mods, b = modules(img, va, ln)
        with open(out, "wb") as fh:
            for sp, addr, cnt, data in mods:
                fh.write(struct.pack("<BII", sp, addr, cnt))
                for i in range(cnt):
                    fh.write(struct.pack("<I", w24(b, data + i * 3)))
            fh.write(struct.pack("<BII", 0xff, 0, 0))
        n = sum(c for _, _, c, _ in mods)
        print(f"payload {t}: {len(mods)} modules, {n:,} words -> {out}")
        return
    sys.exit(f"unknown payload {tag}")


def main():
    if not IMG.exists():
        sys.exit(f"missing {IMG}")
    img = IMG.read_bytes()

    if len(sys.argv) > 1 and sys.argv[1] == "--extract":
        return extract(img, sys.argv[2:5])
    if len(sys.argv) > 1 and sys.argv[1] == "--dumpmem":
        return dumpmem(img, sys.argv[2:4])

    print("=== bootstraps (address given explicitly by the ColdFire) ===")
    for tag, va, ln, dsp in BOOTSTRAPS:
        print(f"  {tag}: 0x{va:08x} +0x{ln:<6x} -> P:0x{dsp:05x}  ({ln//3} words)")

    for tag, va, ln in PAYLOADS:
        b = img[va - BASE: va - BASE + ln]
        print(f"\n=== payload {tag} @0x{va:08x}  {ln:,} B  ({ln//3:,} words) ===")
        print(f"  first bytes: {b[:12].hex(' ',1)}")
        best = None
        for order in ("ca", "ac"):
            mods, why = parse(b, order)
            if mods:
                consumed = mods[-1][3] + mods[-1][2] * 3
                score = consumed / len(b)
                print(f"  order={order}: {len(mods)} records, consumed "
                      f"{consumed:,}/{len(b):,} ({score:.1%}) -- {why}")
                if best is None or score > best[0]:
                    best = (score, order, mods)
            else:
                print(f"  order={order}: rejected -- {why}")
        if not best:
            print("  !! neither field order parses; the record layout differs")
            continue
        _, order, mods = best
        print(f"\n  --- module map (field order {order}) ---")
        tot = 0
        for sp, addr, cnt, data in mods:
            tot += cnt
            print(f"    {SPACE.get(sp,'?')}:0x{addr:05x}  {cnt:6,} words  "
                  f"(image 0x{BASE+va-BASE+data:08x})")
        print(f"    total {tot:,} words across {len(mods)} modules")


if __name__ == "__main__":
    main()
