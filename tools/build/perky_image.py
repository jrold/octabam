#!/usr/bin/env python3
"""PERKY development source-machine integration.

Milestone 0 deliberately installs only ``modules/perky/probe_glue.asm``.  A
signed PERKY track renders an impulse at the stock trig offset; every unsigned
track takes the untouched stock source path.  This proves the source seam and
ColdFire record before the Noise / Tone engine is added.

The placement follows the hardware-qualified ANALOG BD route:

* assemble into the beginning of harvested SPRING REV P code on both DSPs;
* point SPRING REV's dispatch at the stock null stub;
* replace the measured source seam with a JSR to our glue;
* repack each final DSP upload as a pre-boot payload and repoint the boot upload
  pointer through the platform loader.

Unlike ANALOG BD, the probe is intentionally constrained to the words BEFORE
SPRING's shared 35-word reverb helper.  We therefore do not relocate that
helper yet.  The real Noise / Tone engine must either fit this smaller budget or
adopt the same helper relocation (or a different placement) explicitly.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/analog-bassdrum"))
sys.path.insert(0, str(ROOT / "tools/build"))

import ab_records  # noqa: E402
import dsp909  # noqa: E402

BASE = ab_records.BASE
UNCACHED = ab_records.UNCACHED
GLUE = ROOT / "modules/perky/probe_glue.asm"
OUT = ROOT / "out/perky/image"

SPRING_ID = 0x15
PAY = {
    # payload (virtual address, byte length), boot pointer, SPRING P start,
    # stock null init/proc, source seam, stock continuation
    "A": dict(
        payload=ab_records.PAYLOAD_A,
        pointer=0x40001E8E,
        spring=0x01252,
        null=(0x7C8, 0x7C9),
        seam=0x39C,
        cont=0x426,
    ),
    "B": dict(
        payload=ab_records.PAYLOAD_B,
        pointer=ab_records.B_POINTER,
        spring=0x01012,
        null=(0x588, 0x589),
        seam=0x1A2,
        cont=0x221,
    ),
}

SPRING_WORDS = 1063
# ANALOG BD measured the stock helper at SPRING + 0x334.  The probe must stop
# before it so this first integration changes no helper/caller topology.
PROBE_WORDS = 0x334

# Same hardware-qualified pre-boot staging/destination windows as ANALOG BD.
PRE = {
    "A": (0x40B00000, 0x40B80000),
    "B": (0x40B40000, 0x40BC0000),
}


def die(message: str) -> None:
    raise SystemExit(f"perky-image: {message}")


def assemble(org: int, cont: int, tag: str):
    source = GLUE.read_text().replace("@CONT@", f"${cont:x}")
    if "@CONT@" in source:
        die(f"payload {tag}: unresolved @CONT@")

    OUT.mkdir(parents=True, exist_ok=True)
    binary = OUT / f"perky_probe_{tag}.bin"
    symbols, _listing = dsp909.assemble(org, {}, binary, source)
    blob = binary.read_bytes()
    if len(blob) % 3:
        die(f"payload {tag}: dsp_asm produced {len(blob)} bytes, not 24-bit words")

    words = [
        blob[i] | (blob[i + 1] << 8) | (blob[i + 2] << 16)
        for i in range(0, len(blob), 3)
    ]
    if len(words) > PROBE_WORDS:
        die(
            f"payload {tag}: probe is {len(words)} words; only {PROBE_WORDS} "
            "words precede SPRING's shared helper"
        )
    if "pk_probe_source" not in symbols:
        die(f"payload {tag}: assembler emitted no pk_probe_source symbol")
    return words, symbols


def integrate(img: bytearray, stock_img: bytes):
    """Install the PERKY integration probe.

    Returns ``(preboot_payloads, pointer_pokes, report_lines)`` in the same
    shape as ``ab_image.integrate`` so ``build_bus.py`` can feed the platform
    loader without giving PERKY a second loader design.
    """
    from remix import platform_build, runtime_build

    preboots: list[dict] = []
    pokes: list[tuple[int, bytes, bytes, str]] = []
    log: list[str] = []

    for tag, cfg in PAY.items():
        records, _term = ab_records.records(img, *cfg["payload"])
        stock_records, _stock_term = ab_records.records(stock_img, *cfg["payload"])
        words, symbols = assemble(cfg["spring"], cfg["cont"], tag)

        # 1. Plant only the probe words over pristine SPRING code.
        for i, word in enumerate(words):
            address = cfg["spring"] + i
            offset = ab_records.word_at(records, 0, address)
            stock_offset = ab_records.word_at(stock_records, 0, address)
            got = ab_records.rd(img, offset)
            expected = ab_records.rd(stock_img, stock_offset)
            if got != expected:
                die(
                    f"payload {tag}: P:{address:05x} is no longer stock "
                    f"SPRING REV ({got:06x} != {expected:06x})"
                )
            ab_records.wr(img, offset, word)

        # 2. A stored SPRING id must never enter our probe code.
        for table, stub in ((0x215, cfg["null"][0]), (0x235, cfg["null"][1])):
            offset = ab_records.word_at(records, 1, table + SPRING_ID)
            got = ab_records.rd(img, offset)
            if not (
                cfg["spring"] <= got < cfg["spring"] + SPRING_WORDS
                or got == stub
            ):
                die(
                    f"payload {tag}: X:{table + SPRING_ID:05x} holds "
                    f"{got:06x}, not SPRING's entry/null stub"
                )
            ab_records.wr(img, offset, stub)

        # 3. Divert every source record through the signature probe.  Unsigned
        # records return and execute the stock renderer; signed records skip it.
        ab_records.patch(
            img,
            records,
            0,
            cfg["seam"],
            (0x567000, 0x00020E),
            (0x0BF080, symbols["pk_probe_source"]),
            f"{tag} source seam -> jsr PERKY probe",
            log,
        )

        # 4. Repack this already-final payload.  No extra X/Y record is needed
        # for the impulse canary, so its raw upload length stays unchanged.
        payload_va, payload_len = cfg["payload"]
        p0 = payload_va - BASE
        raw = bytes(img[p0 : p0 + payload_len])
        packed = (
            runtime_build.PACKED_MAGIC
            + len(raw).to_bytes(4, "big")
            + runtime_build.pack(raw, platform_build.MAX_CANDIDATES)
        )

        destination, stage = PRE[tag]
        if len(raw) > 0x40000 or 4 + len(packed) > 0x40000:
            die(
                f"payload {tag}: upload {len(raw):,} B / packed "
                f"{len(packed):,} B outgrows its 256 KiB scratch"
            )

        preboots.append(
            dict(
                name=f"PERKY probe payload {tag}",
                blob=platform_build.SIGNATURE + packed,
                stage=stage + UNCACHED,
                dst=destination + UNCACHED,
                rawlen=len(raw),
                rhash=platform_build.roll(raw),
            )
        )
        pokes.append(
            (
                cfg["pointer"],
                payload_va.to_bytes(4, "big"),
                (destination + UNCACHED).to_bytes(4, "big"),
                f"DSP boot: payload {tag}'s upload reads the PERKY probe",
            )
        )
        log.append(
            f"  PERKY probe {tag}: {len(words)} words at "
            f"P:{cfg['spring']:05x} (before SPRING helper); id "
            f"0x{SPRING_ID:02x} -> null {cfg['null'][0]:05x}/{cfg['null'][1]:05x}; "
            f"source seam P:{cfg['seam']:05x} -> "
            f"P:{symbols['pk_probe_source']:05x}; upload {len(raw):,} B, "
            f"packed {len(packed):,}"
        )

        (OUT / f"upload_{tag}.bin").write_bytes(raw)
        (OUT / f"perky_probe_{tag}.sym").write_text(
            "".join(
                f"{name} {address:06x}\n"
                for name, address in sorted(symbols.items(), key=lambda item: item[1])
            )
        )

    return preboots, pokes, log
