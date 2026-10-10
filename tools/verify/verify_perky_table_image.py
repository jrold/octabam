#!/usr/bin/env python3
"""Build and verify PERKY's complete table-loaded development image.

This image-stage gate starts from the normal perky-probe image, generates the
explicit synthetic Noise/Tone assets, builds the packed X/Y payload, runs the
real preboot-loader post-processor, then independently proves:

* both extended DSP uploads contain exact X:$3800/236 and Y:$07a5/1975 records;
* the loader's emitted preblob0/1 bytes are byte-identical to independently
  packed A/B extended uploads;
* the final image redirects both DSP upload pointers to the PERKY preboot dsts;
* the stock boot JSR is redirected to Octabam's loader at LOADER_AT;
* the appended bytes in the final image equal the loader build's append.bin.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "tools"),
    str(ROOT / "tools/build"),
    str(ROOT / "tools/perky"),
]

import ab_records  # noqa:E402
import build_perky_tables  # noqa:E402
import perky_image  # noqa:E402
from remix import pack, platform_build  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_table_image_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
payload_builder = load_module(
    "perky_table_image_payload",
    ROOT / "tools/perky/build_noise_tone_payload.py",
)

BASE_IMAGE = ROOT / "out/mainos_bus.bin"
WORK = ROOT / "out/platform-perky-tables"


def fail(message: str) -> None:
    raise AssertionError("PERKY table image: " + message)


def read24(raw: bytes, off: int) -> int:
    return raw[off] | (raw[off + 1] << 8) | (raw[off + 2] << 16)


def parse_upload(raw: bytes):
    """Parse one standalone Elektron DSP upload into (space,addr,words)."""
    p = 0
    if raw[p] == 3:
        p += 6
    if raw[p] == 4:
        p += 6
    records = []
    while p + 3 <= len(raw):
        space = read24(raw, p)
        if space > 2:
            return records
        if p + 9 > len(raw):
            fail("truncated DSP upload record header")
        address = read24(raw, p + 3)
        count = read24(raw, p + 6)
        end = p + 9 + count * 3
        if end > len(raw):
            fail("truncated DSP upload record body")
        words = [read24(raw, p + 9 + i * 3) for i in range(count)]
        records.append((space, address, words))
        p = end
    fail("DSP upload has no terminator")


def image_slice(img: bytes, address: int, size: int) -> bytes:
    off = address - ab_records.BASE
    if off < 0 or off + size > len(img):
        fail(f"0x{address:08x}..0x{address+size:08x} outside image")
    return img[off:off + size]


def exact_record(records, space: int, address: int, words: list[int], tag: str) -> None:
    hits = [data for sp, at, data in records if sp == space and at == address]
    if len(hits) != 1:
        fail(f"payload {tag}: expected one {'PXY'[space]}:{address:05x} record, got {len(hits)}")
    if hits[0] != words:
        fail(
            f"payload {tag}: {'PXY'[space]}:{address:05x} record differs "
            f"({len(hits[0])} words vs expected {len(words)})"
        )


def main() -> None:
    if not BASE_IMAGE.exists():
        fail("missing out/mainos_bus.bin; build REMIX=perky-probe before image-stage checks")

    base = BASE_IMAGE.read_bytes()
    with tempfile.TemporaryDirectory(prefix="perky-table-image.") as td:
        td = Path(td)
        source = td / "source"
        packed = td / "packed"
        output = td / "mainos_perky_tables.bin"
        fab.emit_tables(source)
        payload_builder.build(source, packed)

        y_words, layout = perky_image.load_tables(packed)
        x_words = perky_image.load_state_init(packed, layout)
        if len(y_words) != 1975 or len(x_words) != 236:
            fail(f"fixture geometry drifted: X={len(x_words)} Y={len(y_words)}")

        # Independently construct and inspect the exact raw uploads expected to
        # be carried by the loader before asking the image builder to run.
        expected_raw = {}
        expected_blob = {}
        for tag in ("A", "B"):
            raw, _term = perky_image.extend_upload(base, tag, y_words, x_words)
            expected_raw[tag] = raw
            records = parse_upload(raw)
            exact_record(records, 1, perky_image.X_BASE, x_words, tag)
            exact_record(records, 2, perky_image.Y_BASE, y_words, tag)
            packed_stream = (
                pack.PACKED_MAGIC
                + len(raw).to_bytes(4, "big")
                + pack.pack(raw, platform_build.MAX_CANDIDATES)
            )
            expected_blob[tag] = platform_build.SIGNATURE + packed_stream

        build_perky_tables.build(BASE_IMAGE, packed, output)
        final = output.read_bytes()

    if len(final) <= len(base):
        fail("table image did not append the platform loader")

    # The builder leaves the loader work products in the canonical work dir.
    for index, tag in enumerate(("A", "B")):
        emitted = (WORK / f"preblob{index}.bin").read_bytes()
        if emitted != expected_blob[tag]:
            fail(f"loader preblob{index} is not the independently expected payload {tag}")

    append = (WORK / "append.bin").read_bytes()
    append_off = platform_build.LOADER_AT - ab_records.BASE
    if final[append_off:] != append:
        fail("final image append does not match platform loader append.bin")

    boot_expected = b"\x4e\xb9" + platform_build.LOADER_AT.to_bytes(4, "big")
    if image_slice(final, 0x4000050C, 6) != boot_expected:
        fail("stock boot JSR is not redirected to the Octabam loader")

    for tag in ("A", "B"):
        pointer = perky_image.PAY[tag]["pointer"]
        dst = perky_image.PRE[tag][0] + ab_records.UNCACHED
        got = int.from_bytes(image_slice(final, pointer, 4), "big")
        if got != dst:
            fail(f"payload {tag} pointer is 0x{got:08x}, expected 0x{dst:08x}")

    build_perky_tables.verify_reservation(final)

    print(
        "PERKY table-loaded image: PASS "
        "(A+B exact X:3800/236 + Y:07a5/1975 uploads; preblobs exact; "
        "boot -> loader; DSP pointers -> extended uploads; append exact)"
    )


if __name__ == "__main__":
    main()
