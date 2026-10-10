#!/usr/bin/env python3
"""Lossless Rice coder for the Perkons PCM that has to live inside the OS image.

The card OS upgrade refuses an ELUP `.bin` whose payload exceeds 1 MiB
(`0x4007f748` computes `filesize - 12` and compares it with `0x100000`; over
that it returns the error that prints "LENGTH ERROR").  PerkyMachines' firmware
assets -- the 48-table Wavetable bank and Acoustic Hats' closed/open/ride --
are 648,716 bytes of effectively incompressible PCM, and aPLib gets ~nothing on
them, so the payload went to 1.2 MB and the card path stopped working.

This coder is a FLAC-style fixed-predictor + Rice residual stream: order 2
within a 4096-sample block, a per-block Rice parameter, 16-bit output exactly.
It is deliberately trivial to decode in freestanding ColdFire C (see
modules/perky/cf_pcm_rice.h) and it is lossless -- the gate
`verify_perky_cf_pcm_rice.py` round-trips every byte of all four assets.

Container (little-endian):

    "PKR1"            4 bytes
    u32               asset count
    per asset:  u32   sample count
                u16   sample[0]            (raw)
                u16   sample[1]            (raw)
                blocks of up to 4096 samples:  u8 k, then Rice(u - pred)
"""
from __future__ import annotations

import struct

MAGIC = b"PKR1"
BLOCK = 4096


def _zigzag(v: int) -> int:
    return (v << 1) if v >= 0 else ((-v << 1) - 1)


def _unzigzag(u: int) -> int:
    return (u >> 1) ^ -(u & 1)


class _Bits:
    def __init__(self) -> None:
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, value: int, bits: int) -> None:
        self.acc = (self.acc << bits) | (value & ((1 << bits) - 1))
        self.n += bits
        while self.n >= 8:
            self.n -= 8
            self.out.append((self.acc >> self.n) & 0xFF)

    def put_unary(self, q: int) -> None:
        while q >= 32:
            self.put(0, 32)
            q -= 32
        self.put(0, q)
        self.put(1, 1)

    def flush(self) -> bytes:
        if self.n:
            self.out.append((self.acc << (8 - self.n)) & 0xFF)
            self.n = 0
        return bytes(self.out)


class _Reader:
    """MSB-first bit reader with an exact absolute bit position."""

    def __init__(self, data: bytes, bit: int = 0) -> None:
        self.d = data
        self.bit = bit

    def get(self, bits: int) -> int:
        v = 0
        while bits:
            byte_index = self.bit >> 3
            avail = 8 - (self.bit & 7)
            take = bits if bits < avail else avail
            byte = self.d[byte_index] if byte_index < len(self.d) else 0
            v = (v << take) | ((byte >> (avail - take)) & ((1 << take) - 1))
            self.bit += take
            bits -= take
        return v

    def get_unary(self) -> int:
        q = 0
        while self.get(1) == 0:
            q += 1
        return q


def _align8(bit: int) -> int:
    return (bit + 7) & ~7


def _encode_asset(samples: list[int]) -> bytes:
    return _encode_asset_np(samples)


def _decode_asset(data: bytes, byte_off: int, count: int):
    """Decode one asset; returns (samples, next byte offset)."""
    reader = _Reader(data, byte_off * 8)
    if count == 0:
        return [], byte_off
    if count == 1:
        return [_s16(reader.get(16))], _align8(reader.bit) // 8
    samples = [_s16(reader.get(16)), _s16(reader.get(16))]
    while len(samples) < count:
        k = reader.get(8)
        n = min(BLOCK, count - len(samples))
        for _ in range(n):
            q = reader.get_unary()
            r = _unzigzag((q << k) | (reader.get(k) if k else 0))
            pred = 2 * samples[-1] - samples[-2]
            samples.append(_s16((pred + r) & 0xFFFF))
    return samples, _align8(reader.bit) // 8


def _s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def encode(assets: list[bytes]) -> bytes:
    out = bytearray(MAGIC)
    out += struct.pack("<I", len(assets))
    for blob in assets:
        out += _encode_asset_np(list(struct.unpack("<%dh" % (len(blob) // 2),
                                                   blob[:len(blob) // 2 * 2])))
    return bytes(out)


def _encode_asset_np(samples: list[int]) -> bytes:
    """Same bitstream as the reference encoder, with the k search vectorised."""
    try:
        import numpy as np
    except ImportError:                                   # pragma: no cover
        return _encode_asset_ref(samples)
    out = bytearray(struct.pack("<I", len(samples)))
    if len(samples) == 0:
        return bytes(out)
    bits = _Bits()
    bits.put(samples[0] & 0xFFFF, 16)
    if len(samples) > 1:
        bits.put(samples[1] & 0xFFFF, 16)
    xs = np.asarray(samples, dtype=np.int64)
    for start in range(2, len(samples), BLOCK):
        seg = xs[start:start + BLOCK]
        pred = 2 * xs[start - 1:start - 1 + len(seg)] - xs[start - 2:start - 2 + len(seg)]
        d = seg - pred
        r = np.where(d >= 0, d << 1, ((-d) << 1) - 1)
        best_k, best_cost = 0, None
        for k in range(0, 17):
            cost = int(((r >> k) + 1 + k).sum())
            if best_cost is None or cost < best_cost:
                best_k, best_cost = k, cost
        bits.put(best_k, 8)
        for value in r.tolist():
            bits.put_unary(value >> best_k)
            if best_k:
                bits.put(value, best_k)
    out += bits.flush()
    return bytes(out)


def _encode_asset_ref(samples: list[int]) -> bytes:
    out = bytearray(struct.pack("<I", len(samples)))
    if len(samples) == 0:
        return bytes(out)
    bits = _Bits()
    bits.put(samples[0] & 0xFFFF, 16)
    if len(samples) > 1:
        bits.put(samples[1] & 0xFFFF, 16)
    for start in range(2, len(samples), BLOCK):
        chunk = samples[start:start + BLOCK]
        res = []
        for i, x in enumerate(chunk):
            p = start + i
            res.append(_zigzag(x - (2 * samples[p - 1] - samples[p - 2])))
        best_k, best_cost = 0, None
        for k in range(0, 17):
            cost = sum((v >> k) + 1 + k for v in res)
            if best_cost is None or cost < best_cost:
                best_k, best_cost = k, cost
        bits.put(best_k, 8)
        for v in res:
            bits.put_unary(v >> best_k)
            if best_k:
                bits.put(v, best_k)
    out += bits.flush()
    return bytes(out)


def decode_all(packed: bytes) -> list[bytes]:
    """Reference decoder: mirrors modules/perky/cf_pcm_rice.h exactly."""
    if packed[:4] != MAGIC:
        raise ValueError("not a PKR1 stream")
    count = struct.unpack("<I", packed[4:8])[0]
    o, out = 8, []
    for _ in range(count):
        n = struct.unpack("<I", packed[o:o + 4])[0]
        o += 4
        samples, o = _decode_asset(packed, o, n)
        out.append(struct.pack("<%dh" % n, *samples))
    return out


def main() -> None:
    import pathlib
    import sys

    sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1])]
    root = pathlib.Path(__file__).resolve().parents[2]
    from extract_noise_tone_tables import find_m7, parse_container

    img = open(sys.argv[1] if len(sys.argv) > 1 else
               r"C:\Users\Jason\Downloads\perkons_both_v1.2.1-0-gbcccfd0.img", "rb").read()
    seg = find_m7(parse_container(img)[1])
    assets = [seg.read(0x080327CC + k * 0x1000, 4096) for k in range(48)]
    assets.append(seg.read(0x080222A0, 4096))
    assets.append(seg.read(0x080CBEF0, 20202))
    assets.append(seg.read(0x080A1BF0, 172800))
    assets.append(seg.read(0x080627CC, 259106))
    raw = sum(len(a) for a in assets)
    packed = encode(assets)
    import struct as _s
    count = _s.unpack("<I", packed[4:8])[0]
    o, back, ok = 8, [], True
    for i in range(min(6, count)):
        n = _s.unpack("<I", packed[o:o + 4])[0]
        o += 4
        samples, o = _decode_asset(packed, o, n)
        got = _s.pack("<%dh" % n, *samples)
        back.append(got)
        ok = ok and got == assets[i]
    print(f"raw {raw:,} -> packed {len(packed):,} ({len(packed)/raw:.3f}); "
          f"first-{len(back)} round-trip {'exact' if ok else 'MISMATCH'}")
    if not ok:
        for i, (a, b) in enumerate(zip(assets, back)):
            if a != b:
                print(f"  asset {i}: first difference at "
                      f"{next(k for k in range(min(len(a), len(b))) if a[k] != b[k])}")


if __name__ == "__main__":
    main()
