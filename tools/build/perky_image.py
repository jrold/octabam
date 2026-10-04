#!/usr/bin/env python3
"""PERKY Noise/Tone data injection into the two finalized OT DSP uploads.

Generic ``build_bus.py`` has already placed PERKY's source hook/code in each
DSP payload. This pass appends two data records and returns replacement uploads
for Octabam's established pre-boot loader:

* X:0x3800 -- four compact voices + one 17-word cache each + shared RNG;
* Y:0x0795 -- exact packed Noise/Tone waves/envelopes.

Both destinations are checked against every finalized upload record before a
word is appended. The X interval lies in the Analog-BD-qualified private-X run;
the Y interval is the hardware-measured free 0x0795..0x0fff range.

Input ``table_dir`` is the output of ``tools/perky/build_noise_tone_payload.py``.
Firmware-derived bytes remain an external build input; this file contains no
PĒRKONS table/state data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/build"))

import ab_records  # noqa:E402

X_BASE = 0x3800
X_WORDS = 236
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


def die(message: str) -> NoReturn:
    raise SystemExit("perky-image: " + message)


def read_words24(path: Path) -> list[int]:
    raw = path.read_bytes()
    if len(raw) % 3:
        die(f"{path}: {len(raw)} bytes is not a whole number of 24-bit words")
    return [
        raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
        for i in range(0, len(raw), 3)
    ]


def _load_layout(table_dir: Path) -> dict:
    layout_path = table_dir / "layout.json"
    if not layout_path.exists():
        die(f"{table_dir}: expected layout.json")
    try:
        layout = json.loads(layout_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"{layout_path}: {exc}")
    if layout.get("schema") != "perky-noise-tone-dsp-tables-v1":
        die(f"{layout_path}: unsupported schema {layout.get('schema')!r}")
    return layout


def load_tables(table_dir: Path) -> tuple[list[int], dict]:
    layout = _load_layout(table_dir)
    binary_path = table_dir / "tables.bin"
    if not binary_path.exists():
        die(f"{table_dir}: expected tables.bin")
    words = read_words24(binary_path)
    if layout.get("total_words") != len(words):
        die(f"layout says {layout.get('total_words')} Y words, binary has {len(words)}")
    if len(words) > Y_WORDS:
        die(
            f"packed tables need {len(words)} Y words, private interval "
            f"Y:{Y_BASE:04x}..{Y_END-1:04x} holds only {Y_WORDS}"
        )
    digest = hashlib.sha256(binary_path.read_bytes()).hexdigest()
    if layout.get("sha256") != digest:
        die(f"tables.bin sha256 {digest} != layout {layout.get('sha256')}")
    return words, layout


def load_state_init(table_dir: Path, layout: dict | None = None) -> list[int]:
    layout = layout or _load_layout(table_dir)
    meta = layout.get("x_init")
    if not isinstance(meta, dict):
        die("layout has no x_init metadata")
    if meta.get("base_word") != X_BASE:
        die(f"x_init base {meta.get('base_word')!r} != X:{X_BASE:04x}")
    if meta.get("words") != X_WORDS:
        die(f"x_init has {meta.get('words')!r} words, expected {X_WORDS}")
    path = table_dir / "state_init.bin"
    if not path.exists():
        die(f"{table_dir}: expected state_init.bin")
    words = read_words24(path)
    if len(words) != X_WORDS:
        die(f"state_init.bin has {len(words)} words, expected {X_WORDS}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if meta.get("sha256") != digest:
        die(f"state_init.bin sha256 {digest} != layout {meta.get('sha256')}")
    if any(word > 0x00FFFF for word in words):
        die("state_init.bin contains a word outside the 16-bit compact-state ABI")
    return words


def _overlap(a: int, n: int, b: int, m: int) -> bool:
    return a < b + m and b < a + n


def _check_space_free(records, space: int, base: int, words: int,
                      tag: str, what: str) -> None:
    for rec_space, address, count, _off in records:
        if rec_space == space and _overlap(base, words, address, count):
            label = "X" if space == 1 else "Y"
            die(
                f"payload {tag}: existing {label} record {label}:{address:05x}.."
                f"{address + count - 1:05x} overlaps PERKY {what} destination "
                f"{label}:{base:05x}..{base + words - 1:05x}"
            )


def _check_y_free(records, words: int, tag: str) -> None:
    _check_space_free(records, 2, Y_BASE, words, tag, "table")


def _check_x_free(records, tag: str) -> None:
    _check_space_free(records, 1, X_BASE, X_WORDS, tag, "state-init")


def extend_upload(img: bytes | bytearray, tag: str, y_words: list[int],
                  x_words: list[int] | None = None) -> tuple[bytes, int]:
    """Return one payload upload with PERKY private-X/Y records inserted."""
    c = PAY[tag]
    records, term = ab_records.records(img, *c["payload"])
    _check_y_free(records, len(y_words), tag)
    if x_words is not None:
        if len(x_words) != X_WORDS:
            die(f"payload {tag}: X init is {len(x_words)} words, expected {X_WORDS}")
        _check_x_free(records, tag)
    p0 = c["payload"][0] - ab_records.BASE
    extra = b""
    if x_words is not None:
        extra += ab_records.ot_record(1, X_BASE, x_words)
    extra += ab_records.ot_record(2, Y_BASE, y_words)
    raw = bytes(img[p0:term]) + extra + bytes(img[term:p0 + c["payload"][1]])
    return raw, term


def integrate(img: bytes | bytearray, table_dir: Path):
    """Return (preboot_payloads, pointer_pokes, log, layout)."""
    from remix import platform_build, runtime_build

    y_words, layout = load_tables(table_dir)
    x_words = load_state_init(table_dir, layout)
    pres, pokes, log = [], [], []
    for tag, c in PAY.items():
        raw, _term = extend_upload(img, tag, y_words, x_words)
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
            f"PERKY {tag}: X:{X_BASE:05x}..{X_BASE + X_WORDS - 1:05x} "
            f"{X_WORDS} init words; Y:{Y_BASE:05x}..{Y_BASE + len(y_words) - 1:05x} "
            f"{len(y_words)} packed table words; upload {len(raw):,} B, "
            f"packed {len(packed):,} B"
        )

    return pres, pokes, log, layout
