#!/usr/bin/env python3
"""PERKY data injection into the two finalized OT DSP uploads.

Generic ``build_bus.py`` has already placed PERKY's source hook/code in each
DSP payload. This pass appends data records and returns replacement uploads for
Octabam's established pre-boot loader:

* X:0x3800 -- compact voice state / sideband initialization;
* Y:0x07a5 -- exact packed Noise/Tone/Simple static tables;
* optional profile-declared X/Y initializers generated under ``out/``.

The normal PERKY2/PERKY4 path remains restricted to the measured private gaps.
The HW4 audition profile may additionally declare local Y initializers in
$1000..$3eff: this lies in the stock FX1 arena but below the stock Y clear at
$3f00.  Only the dedicated reduced-FX HW4 remix is allowed to rely on those
records; this injector merely validates geometry/checksums and refuses overlap.

Firmware-derived bytes remain external build inputs; this file contains no
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
PRIVATE_X_END = 0x3A68          # measured private-X ceiling, exclusive
Y_BASE = 0x07a5
Y_END = 0x1000                  # exclusive: FX1 allocation begins here
Y_WORDS = Y_END - Y_BASE        # 2,139 hardware-measured private words
EXTRA_Y_BASE = 0x1000
EXTRA_Y_END = 0x3F00            # exclusive: stock boot clear begins here

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
    if layout.get("schema") not in ("perky-noise-tone-dsp-tables-v1", "perky-multi-dsp-tables-v1"):
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
    expected_words = 242 if layout["schema"] == "perky-multi-dsp-tables-v1" else X_WORDS
    if meta.get("words") != expected_words:
        die(f"x_init has {meta.get('words')!r} words, expected {expected_words}")
    path = table_dir / "state_init.bin"
    if not path.exists():
        die(f"{table_dir}: expected state_init.bin")
    words = read_words24(path)
    if len(words) != expected_words:
        die(f"state_init.bin has {len(words)} words, expected {expected_words}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if meta.get("sha256") != digest:
        die(f"state_init.bin sha256 {digest} != layout {meta.get('sha256')}")
    if any(word > 0x00FFFF for word in words):
        die("state_init.bin contains a word outside the 16-bit compact-state ABI")
    return words


def _overlap(a: int, n: int, b: int, m: int) -> bool:
    return a < b + m and b < a + n


def load_extra_y_init(table_dir: Path, layout: dict) -> list[tuple[int, list[int], str]]:
    rows = layout.get("extra_y_init") or []
    if not isinstance(rows, list):
        die("extra_y_init must be a list")
    out: list[tuple[int, list[int], str]] = []
    claimed: list[tuple[int, int, str]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            die(f"extra_y_init[{i}] is not an object")
        try:
            base = int(row["base_word"])
            count = int(row["words"])
            name = str(row["file"])
            expected = str(row["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            die(f"extra_y_init[{i}] malformed: {exc}")
        if Path(name).name != name:
            die(f"extra_y_init[{i}] file must be a basename, got {name!r}")
        if count <= 0:
            die(f"extra_y_init[{i}] has non-positive word count {count}")
        if base < EXTRA_Y_BASE or base + count > EXTRA_Y_END:
            die(
                f"extra_y_init[{i}] Y:{base:04x}..{base+count-1:04x} is outside "
                f"audition arena Y:{EXTRA_Y_BASE:04x}..{EXTRA_Y_END-1:04x}"
            )
        path = table_dir / name
        if not path.exists():
            die(f"extra_y_init[{i}] missing {path}")
        words = read_words24(path)
        if len(words) != count:
            die(f"extra_y_init[{i}] says {count} words, {path} has {len(words)}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            die(f"extra_y_init[{i}] {name} sha256 {digest} != {expected}")
        purpose = str(row.get("purpose") or name)
        for other_base, other_count, other_name in claimed:
            if _overlap(base, count, other_base, other_count):
                die(
                    f"extra_y_init[{i}] {name} overlaps {other_name}: "
                    f"Y:{base:04x}+{count} vs Y:{other_base:04x}+{other_count}"
                )
        claimed.append((base, count, name))
        out.append((base, words, purpose))
    return out


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
                  x_words: list[int] | None = None,
                  extra_x: list[tuple[int, list[int]]] | None = None,
                  extra_y: list[tuple[int, list[int], str]] | None = None) -> tuple[bytes, int]:
    """Return one payload upload with validated PERKY X/Y records inserted."""
    c = PAY[tag]
    records, term = ab_records.records(img, *c["payload"])
    _check_y_free(records, len(y_words), tag)
    if x_words is not None:
        if len(x_words) not in (X_WORDS, 242):
            die(f"payload {tag}: X init is {len(x_words)} words, expected {X_WORDS}")
        _check_space_free(records, 1, X_BASE, len(x_words), tag, "state-init")
    p0 = c["payload"][0] - ab_records.BASE
    extra = b""
    if x_words is not None:
        extra += ab_records.ot_record(1, X_BASE, x_words)
    claimed_x = [(X_BASE, len(x_words))] if x_words is not None else []
    for base, values in extra_x or []:
        if len(values) != 17:
            die("unsupported extra X initialization geometry: expected 17-word cache")
        if base < X_BASE or base + len(values) > PRIVATE_X_END:
            die(
                f"payload {tag}: extra X cache X:{base:04x}..{base+len(values)-1:04x} "
                f"is outside measured private X:{X_BASE:04x}..{PRIVATE_X_END-1:04x}"
            )
        if any(_overlap(base, len(values), b, n) for b, n in claimed_x):
            die(f"payload {tag}: extra X cache at X:{base:04x} overlaps another PERKY initializer")
        _check_space_free(records, 1, base, len(values), tag, "pitch-cache")
        extra += ab_records.ot_record(1, base, values)
        claimed_x.append((base, len(values)))

    extra += ab_records.ot_record(2, Y_BASE, y_words)
    for base, values, purpose in extra_y or []:
        _check_space_free(records, 2, base, len(values), tag, purpose)
        extra += ab_records.ot_record(2, base, values)

    raw = bytes(img[p0:term]) + extra + bytes(img[term:p0 + c["payload"][1]])
    return raw, term


def integrate(img: bytes | bytearray, table_dir: Path):
    """Return (preboot_payloads, pointer_pokes, log, layout)."""
    from remix import pack, platform_build

    y_words, layout = load_tables(table_dir)
    x_words = load_state_init(table_dir, layout)
    extra_y = load_extra_y_init(table_dir, layout)
    pres, pokes, log = [], [], []
    for tag, c in PAY.items():
        raw, _term = extend_upload(
            img, tag, y_words, x_words, extra_state_init(layout), extra_y
        )
        packed_blob = (
            pack.PACKED_MAGIC
            + len(raw).to_bytes(4, "big")
            + pack.pack(raw, platform_build.MAX_CANDIDATES)
        )
        dst, stage = PRE[tag]
        if len(raw) > 0x40000 or 4 + len(packed_blob) > 0x40000:
            die(
                f"payload {tag}: upload {len(raw):,} B / packed {len(packed_blob):,} B "
                "outgrows its 256 KiB preboot scratch"
            )
        pres.append(dict(
            name=f"perky payload {tag}",
            blob=platform_build.SIGNATURE + packed_blob,
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
        extra_desc = ""
        if extra_y:
            extra_desc = "; extra Y " + ", ".join(
                f"{purpose} ${base:04x}+{len(values)}"
                for base, values, purpose in extra_y
            )
        log.append(
            f"PERKY {tag}: X:{X_BASE:05x}..{X_BASE + len(x_words) - 1:05x} "
            f"{len(x_words)} init words; Y:{Y_BASE:05x}..{Y_BASE + len(y_words) - 1:05x} "
            f"{len(y_words)} packed table words{extra_desc}; upload {len(raw):,} B, "
            f"packed {len(packed_blob):,} B"
        )

    return pres, pokes, log, layout


def extra_state_init(layout: dict) -> list[tuple[int, list[int]]]:
    if layout["schema"] == "perky-multi-dsp-tables-v1":
        cache = layout.get("pitch_cache") or {}
        base = int(cache.get("base_word", 0x3964))
        words = int(cache.get("words", 17))
        tag = int(cache.get("initial_tag", 0xffff)) & 0xffff
        if words != 17:
            die(f"pitch_cache declares {words} words; decoder ABI requires 17")
        # Cache tag must not accidentally match a dirty first-block index.
        return [(base, [tag] + [0] * 16)]
    return []
