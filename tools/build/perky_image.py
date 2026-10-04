#!/usr/bin/env python3
"""PERKY Noise/Tone table injection into the two finalized OT DSP uploads.

This pass is intentionally table-only.  Generic ``build_bus.py`` has already
placed PERKY's source hook/code in each DSP payload.  Here we append one Y-data
record containing the exact packed Noise/Tone tables and return replacement
uploads for Octabam's established pre-boot loader.

The destination is hardware-measured private Y:0x0795..0x0fff on both cores
(`docs/firmware/CHIP.md`).  The pass checks the finalized payload's existing Y
records before claiming any word.  It never assumes that "not in the static
map" means free.

Input ``table_dir`` is the output of ``tools/perky/build_noise_tone_payload.py``.
The firmware-derived table bytes remain an external build input; this file
contains no PĒRKONS data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/build"))

import ab_records  # noqa:E402

Y_BASE = 0x0795
Y_END = 0x1000                 # exclusive: FX1 allocation begins here
Y_WORDS = Y_END - Y_BASE       # 2,155 hardware-measured private words

PRE = {
    "A": (0x40B00000, 0x40B80000),
    "B": (0x40B40000, 0x40BC0000),
}
PAY = {
    "A": dict(payload=ab_records.PAYLOAD_A, pointer=0x40001E8E),
    "B": dict(payload=ab_records.PAYLOAD_B, pointer=ab_records.B_POINTER),
}


def die(message: str) -> "NoReturn":
    raise SystemExit("perky-image: " + message)


def read_words24(path: Path) -> list[int]:
    raw = path.read_bytes()
    if len(raw) % 3:
        die(f"{path}: {len(raw)} bytes is not a whole number of 24-bit words")
    return [
        raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
        for i in range(0, len(raw), 3)
    ]


def load_tables(table_dir: Path) -> tuple[list[int], dict]:
    layout_path = table_dir / "layout.json"
    binary_path = table_dir / "tables.bin"
    if not layout_path.exists() or not binary_path.exists():
        die(f"{table_dir}: expected layout.json and tables.bin")
    try:
        layout = json.loads(layout_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"{layout_path}: {exc}")
    if layout.get("schema") != "perky-noise-tone-dsp-tables-v1":
        die(f"{layout_path}: unsupported schema {layout.get('schema')!r}")

    words = read_words24(binary_path)
    if layout.get("total_words") != len(words):
        die(f"layout says {layout.get('total_words')} words, binary has {len(words)}")
    if len(words) > Y_WORDS:
        die(
            f"packed tables need {len(words)} Y words, private interval "
            f"Y:{Y_BASE:04x}..{Y_END-1:04x} holds only {Y_WORDS}"
        )
    digest = hashlib.sha256(binary_path.read_bytes()).hexdigest()
    if layout.get("sha256") != digest:
        die(f"tables.bin sha256 {digest} != layout {layout.get('sha256')}")
    return words, layout


def _overlap(a: int, n: int, b: int, m: int) -> bool:
    return a < b + m and b < a + n


def _check_y_free(records, words: int, tag: str) -> None:
    for space, address, count, _off in records:
        if space == 2 and _overlap(Y_BASE, words, address, count):
            die(
                f"payload {tag}: existing Y record Y:{address:05x}.."
                f"{address + count - 1:05x} overlaps PERKY table destination "
                f"Y:{Y_BASE:05x}..{Y_BASE + words - 1:05x}"
            )


def extend_upload(img: bytes | bytearray, tag: str, words: list[int]) -> tuple[bytes, int]:
    """Return one payload upload with the PERKY Y record inserted.

    This helper is pure enough for a synthetic record-stream gate: the only
    image-specific operation is ``ab_records.records``/the payload extent.
    """
    c = PAY[tag]
    records, term = ab_records.records(img, *c["payload"])
    _check_y_free(records, len(words), tag)
    p0 = c["payload"][0] - ab_records.BASE
    raw = (
        bytes(img[p0:term])
        + ab_records.ot_record(2, Y_BASE, words)
        + bytes(img[term:p0 + c["payload"][1]])
    )
    return raw, term


def integrate(img: bytes | bytearray, table_dir: Path):
    """Return (preboot_payloads, pointer_pokes, log, layout)."""
    from remix import platform_build, runtime_build

    words, layout = load_tables(table_dir)
    pres, pokes, log = [], [], []
    for tag, c in PAY.items():
        raw, _term = extend_upload(img, tag, words)
        packed = (
            runtime_build.PACKED_MAGIC
            + len(raw).to_bytes(4, "big")
            + runtime_build.pack(raw, platform_build.MAX_CANDIDATES)
        )
        dst, stage = PRE[tag]
        if len(raw) > 0x40000 or 4 + len(packed) > 0x40000:
            die(
                f"payload {tag}: upload {len(raw):,} B / packed {len(packed):,} B "
                "outgrows its 256 KiB preboot scratch"
            )
        pres.append(dict(
            name=f"perky payload {tag}",
            blob=platform_build.SIGNATURE + packed,
            stage=stage + ab_records.UNCACHED,
            dst=dst + ab_records.UNCACHED,
            rawlen=len(raw),
            rhash=platform_build.roll(raw),
        ))
        pokes.append((
            c["pointer"],
            c["payload"][0].to_bytes(4, "big"),
            (dst + ab_records.UNCACHED).to_bytes(4, "big"),
            f"DSP boot: payload {tag} reads PERKY's extended upload",
        ))
        log.append(
            f"PERKY {tag}: Y:{Y_BASE:05x}..{Y_BASE + len(words) - 1:05x} "
            f"{len(words)} packed table words; upload {len(raw):,} B, "
            f"packed {len(packed):,} B"
        )

    return pres, pokes, log, layout
