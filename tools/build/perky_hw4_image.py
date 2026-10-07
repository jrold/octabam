#!/usr/bin/env python3
"""HW4-only PERKY upload extension for reclaimed local-Y state/rings.

Stable PERKY2/PERKY4 packaging remains in perky_image.py.  This wrapper consumes
that exact private-X/table layout, then appends audition-only Y initializers from
layout.json.  Currently the only accepted form is a zero-filled local Karplus
ring at Y:$1000..$17ff, emitted only after the Karplus builder verified that the
selected original ARM pre-trigger fixture has an all-zero ring.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/build'))

import ab_records
import perky_image as base

LOCAL_Y_MIN = 0x1000
LOCAL_Y_MAX = 0x3F00              # exclusive; avoid stock-init clear at $3f00+
KARPLUS_BASE = 0x1000
KARPLUS_WORDS = 0x800


def die(message):
    raise SystemExit('perky-hw4-image: ' + message)


def extra_y_init(layout):
    rows = layout.get('extra_y_init') or []
    out = []
    claimed = []
    for row in rows:
        if not isinstance(row, dict):
            die('extra_y_init entry must be an object')
        name = str(row.get('name', 'unnamed'))
        addr = int(row.get('base_word', -1))
        words = int(row.get('words', 0))
        fill = int(row.get('fill', -1))
        if fill != 0:
            die(f'{name}: only exact zero-fill is supported for first HW4 audition')
        if words <= 0 or not LOCAL_Y_MIN <= addr < LOCAL_Y_MAX or addr + words > LOCAL_Y_MAX:
            die(f'{name}: Y:{addr:04x}+{words} is outside reclaimed local Y:{LOCAL_Y_MIN:04x}..{LOCAL_Y_MAX-1:04x}')
        if any(base._overlap(addr, words, other, count) for other, count in claimed):
            die(f'{name}: overlaps another HW4 Y initializer')
        out.append((name, addr, [0] * words))
        claimed.append((addr, words))
    if out:
        if len(out) != 1 or out[0][1] != KARPLUS_BASE or len(out[0][2]) != KARPLUS_WORDS:
            die('first HW4 image accepts only the qualified 2K Karplus ring geometry')
    return out


def extend_upload(img, tag, y_words, x_words, extra_x, extra_y):
    c = base.PAY[tag]
    records, term = ab_records.records(img, *c['payload'])
    base._check_y_free(records, len(y_words), tag)
    base._check_space_free(records, 1, base.X_BASE, len(x_words), tag, 'state-init')

    claimed_y = [(base.Y_BASE, len(y_words))]
    for name, addr, values in extra_y:
        if any(base._overlap(addr, len(values), other, count) for other, count in claimed_y):
            die(f'payload {tag}: {name} overlaps packed PERKY tables or another initializer')
        base._check_space_free(records, 2, addr, len(values), tag, name)
        claimed_y.append((addr, len(values)))

    p0 = c['payload'][0] - ab_records.BASE
    extra = ab_records.ot_record(1, base.X_BASE, x_words)
    claimed_x = [(base.X_BASE, len(x_words))]
    for addr, values in extra_x:
        if any(base._overlap(addr, len(values), other, count) for other, count in claimed_x):
            die(f'payload {tag}: extra X initializer overlaps another PERKY initializer')
        base._check_space_free(records, 1, addr, len(values), tag, 'HW4 extra X')
        extra += ab_records.ot_record(1, addr, values)
        claimed_x.append((addr, len(values)))

    extra += ab_records.ot_record(2, base.Y_BASE, y_words)
    for _name, addr, values in extra_y:
        extra += ab_records.ot_record(2, addr, values)
    raw = bytes(img[p0:term]) + extra + bytes(img[term:p0 + c['payload'][1]])
    return raw


def integrate(img: bytes | bytearray, table_dir: Path):
    from remix import platform_build, runtime_build

    y_words, layout = base.load_tables(table_dir)
    x_words = base.load_state_init(table_dir, layout)
    extra_x = base.extra_state_init(layout)
    extra_y = extra_y_init(layout)
    pres, pokes, log = [], [], []

    for tag, c in base.PAY.items():
        raw = extend_upload(img, tag, y_words, x_words, extra_x, extra_y)
        packed = (
            runtime_build.PACKED_MAGIC
            + len(raw).to_bytes(4, 'big')
            + runtime_build.pack(raw, platform_build.MAX_CANDIDATES)
        )
        dst, stage = base.PRE[tag]
        if len(raw) > 0x40000 or 4 + len(packed) > 0x40000:
            die(f'payload {tag}: HW4 upload outgrows 256 KiB preboot scratch')
        pres.append(dict(
            name=f'perky HW4 payload {tag}', blob=platform_build.SIGNATURE + packed,
            stage=stage + ab_records.UNCACHED, dst=dst + ab_records.UNCACHED,
            rawlen=len(raw), rhash=platform_build.roll(raw),
        ))
        pokes.append((
            c['pointer'], c['payload'][0].to_bytes(4, 'big'),
            (dst + ab_records.UNCACHED).to_bytes(4, 'big'),
            f'DSP boot: payload {tag} reads PERKY HW4 extended upload',
        ))
        ydesc = ', '.join(
            f'{name}=Y:{addr:04x}..{addr+len(values)-1:04x}'
            for name, addr, values in extra_y
        ) or 'no extra Y'
        log.append(
            f'PERKY HW4 {tag}: X init {len(x_words)} words; packed tables {len(y_words)} Y words; '
            f'{ydesc}; upload {len(raw):,} B, packed {len(packed):,} B'
        )
    return pres, pokes, log, layout
