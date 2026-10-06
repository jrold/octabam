#!/usr/bin/env python3
"""Qualify the engine-003 Simple Drum PK/Y1 prepared-record transport.

The transport is intentionally tested without committing firmware blobs.  The
three hashes below are the authentic 128-value u16 sweeps captured from a fresh
PĒRKONS v1.2.1 Simple Drum engine.  Driving the byte-record model through the
same physical 0..127 controls must reproduce those hashes exactly.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import simple_drum_transport as transport  # noqa: E402

PREPARED_SHA256 = "b90b3b9b4bd77eb683f83b43114f2b1ef2c0aa3d78cb3c45de89200f3d0b19f1"
DECAY_SHA256 = "c0d3a30b007591185e59db5736106fa14d3af3c87c5374a553544753b62c13e0"
ENV_SHA256 = "6b42105a889ee8fe5f809d266c7c387499e7ad3daf715a291e9351dc00d866b4"
MIX_SHA256 = "8f4770d1a4fd573e544f6c5affcf105d5f59752972e2fc26d45808e97f1eccaf"


def digest_u16(values: list[int]) -> str:
    blob = b"".join(struct.pack("<H", value & 0xFFFF) for value in values)
    return hashlib.sha256(blob).hexdigest()


def sweep(slot: int, key: str) -> list[int]:
    out = []
    for value in range(128):
        raw = [64, 64, 64, 64]
        raw[slot] = value
        state = transport.State.fresh()
        record = state.prepare(tuple(raw), 2, trigger=True)
        decoded = transport.decode(record)
        if decoded["engine"] != transport.ENGINE_INDEX or decoded["mode"] != 2:
            raise AssertionError("Simple Drum record lost engine/mode identity")
        out.append(decoded[key])
    return out


def main() -> None:
    midpoint = transport.decode(
        transport.State.fresh().prepare((64, 64, 64, 64), 0, trigger=True)
    )
    if midpoint != {
        "raw_pitch": 2046,
        "amp_decay": 40,
        "pitch_decay": 99,
        "pitch_env_amount": 1023,
        "mode": 0,
        "engine": transport.ENGINE_INDEX,
    }:
        raise AssertionError(f"Simple Drum midpoint record drifted: {midpoint!r}")

    tune = sweep(0, "raw_pitch")
    decay = sweep(1, "amp_decay")
    env = sweep(2, "pitch_decay")
    mix = sweep(3, "pitch_env_amount")

    if digest_u16(tune) != PREPARED_SHA256:
        raise AssertionError("transport TUNE sweep differs from authentic prepared sweep")
    if digest_u16(decay) != DECAY_SHA256:
        raise AssertionError("transport DECAY sweep differs from authentic v1.2.1 sweep")
    if digest_u16(env) != ENV_SHA256:
        raise AssertionError("transport ENV sweep differs from authentic v1.2.1 sweep")
    if digest_u16(mix) != MIX_SHA256:
        raise AssertionError("transport MIX byte packing/cadence drifted")

    # A non-trigger render after the dirty preparation has exactly the first 16
    # target updates; trigger() contributes the seventeenth update.  Pin that
    # difference explicitly so the CF implementation cannot accidentally move
    # the trigger update to the wrong side of record preparation.
    no_hit = transport.State.fresh()
    before = transport.decode(no_hit.prepare((127, 64, 64, 64), 1, trigger=False))
    hit = transport.State.fresh()
    after = transport.decode(hit.prepare((127, 64, 64, 64), 1, trigger=True))
    if before["raw_pitch"] != 4091 or after["raw_pitch"] != 4092:
        raise AssertionError(
            f"trigger cadence drifted: no-hit={before['raw_pitch']} hit={after['raw_pitch']}"
        )

    # Big-endian u16 packing is deliberate: each adjacent byte pair is packed
    # into one CF long whose high/low halves become consecutive DSP words.
    record = transport.State.fresh().prepare((0, 0, 0, 0), 2, trigger=True)
    if record[8:] != bytes((2, 0, 0, transport.ENGINE_INDEX)):
        raise AssertionError(f"record tail ABI drifted: {record[8:].hex()}")

    print(
        "PERKY Simple Drum transport: PASS "
        "(authentic 128-point TUNE/DECAY/ENV sweeps, MIX packing, "
        "trigger cadence, midpoint and engine/mode ABI)"
    )


if __name__ == "__main__":
    main()
