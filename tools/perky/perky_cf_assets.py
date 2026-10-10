#!/usr/bin/env python3
"""Hash-pin and embed the exact PĒRKONS v1.2.1 assets used by Perky CF.

No firmware bytes are tracked. During a real Octabam build ``asset_inc`` reads
``PERKONS_FIRMWARE``, verifies the complete update-image SHA-256, then verifies
each exact M7 table independently before emitting assembler ``.byte`` rows.
The per-asset hashes are the same bytes used by the native PCM differential
suite, so the packaged runtime cannot silently use different tables.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/perky"))
from extract_noise_tone_tables import find_m7, parse_container  # noqa:E402

FIRMWARE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"

# label, M7 address, byte count, SHA-256
ASSETS = (
    ("pk_asset_pitch",      0x080202A0, 8192, "142684ed785eea7e2fe30a0b2db5fa710e2c4b6bb024226fcab46adb12ba3266"),
    ("pk_asset_chromatic",  0x08030ECC,   24, "f3eca592b65c72371c7417f361d946fe09429fd960833ca3dc4d425bf7d3c139"),
    ("pk_asset_envelope1",  0x08022EA0, 4096, "ca168bb45a7d175619eed89344d80ca8035e0fa817f825c5284a4d10082ebb40"),
    ("pk_asset_envelope2",  0x080236A2, 4096, "8320184a4d522919090620d48835a6300a9efd156782645148126d4d843ea39f"),
    ("pk_asset_wave0",      0x080222A0,  512, "5a744b7d4b801d00a934203e47528cfa83d85457da9c7a2c29800b1cffe8ff39"),
    ("pk_asset_wave1",      0x080224A0,  512, "53a131adc557a633b618010ee4b97e53df5201013b43bad2eef8a94ae1fa1522"),
    ("pk_asset_wave2",      0x080226A0,  512, "3511b74fa21d0c3430b7e1ddb0bbd8d76b1fd0dbc2272dfb32867b0e5412e697"),
    ("pk_asset_wave3",      0x080228A0,  512, "9cc8eeff587490a75dc669b0b9f462dd39d777061a9be6bf18658062909ece69"),
    ("pk_asset_m1_wave",    0x080310E0, 4096, "9b8d2fbf72195a55a915225d355b89337cf26fb13dead58a4573d5fb37e3e17a"),
    # Resonant Drums' two 257-entry interpolation tables.
    ("pk_asset_res_interp_a", 0x0803237C, 514, "005cdcef1e936228a92e8b513872bbffd3435cc81882c8d0fbd939e4630b16a7"),
    ("pk_asset_res_interp_b", 0x08032178, 514, "5fa9df6f7f2a46a70716329ea966ea931b0460a1a2c8afb93f7d36bc5a180e72"),
    # Wavetable Drum: the primary oscillator's own 2048-entry table (the shared
    # 256-entry wave views are only its first 256 samples) and the contiguous
    # 48-table secondary crossfade bank the panel PARAM1 walk indexes.
    ("pk_asset_wt_base",     0x080222A0, 4096, "cd152c38143fd71b7d465a6f62abfb723a454a314cb94ef09384204925102b7c"),
    ("pk_asset_wt_bank",     0x080327CC, 196608, "98bbb3e2622d3e11b255537d53245f6631d82431dea08c3857ef1f77ff102937"),
    # Acoustic Hats' three hat samples, selected by PANEL MODE.
    ("pk_asset_ah_closed",   0x080CBEF0, 20202, "d9caeb79cc5c105bd13dd2b58dccde5bef3e1e17e15d2efeb34d15af6ed463be"),
    ("pk_asset_ah_open",     0x080A1BF0, 172800, "0cffaca235777f058c065567b420143b506b62f07b3fdd13f87fe5f4623f893c"),
    ("pk_asset_ah_ride",     0x080627CC, 259106, "0803c1873d5c255dd334c1e775f2d86e17e8d1a337bebcef2508160a5454f29f"),
)


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def firmware_path() -> Path:
    value = os.environ.get("PERKONS_FIRMWARE")
    if not value:
        raise SystemExit(
            "PERKY CF: set PERKONS_FIRMWARE to perkons_both_v1.2.1-0-gbcccfd0.img"
        )
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"PERKY CF: PĒRKONS firmware does not exist: {path}")
    return path


def extract(path: Path | None = None) -> dict[str, bytes]:
    path = path or firmware_path()
    raw = path.read_bytes()
    got = _sha(raw)
    if got != FIRMWARE_SHA256:
        raise SystemExit(
            f"PERKY CF: firmware sha256 {got}, expected exact v1.2.1 {FIRMWARE_SHA256}"
        )
    _product, segments = parse_container(raw)
    m7 = find_m7(segments)
    result: dict[str, bytes] = {}
    for label, address, size, expected in ASSETS:
        blob = m7.read(address, size)
        actual = _sha(blob)
        if actual != expected:
            raise SystemExit(
                f"PERKY CF: {label} sha256 {actual}, expected {expected} "
                f"at M7 0x{address:08x}"
            )
        result[label] = blob
    return result


def _byte_rows(blob: bytes, width: int = 16) -> list[str]:
    return [
        "        .byte " + ",".join(f"0x{x:02x}" for x in blob[i:i + width])
        for i in range(0, len(blob), width)
    ]


# The five big firmware assets are carried as ONE lossless PKR1 stream
# (tools/perky/pcm_rice.py) instead of raw image rodata.  The card OS upgrade
# refuses an ELUP .bin whose payload exceeds 1 MiB, and these 652,812 bytes are
# effectively incompressible PCM: they cost the image ~1:1 and pushed the
# payload to 1.2 MB.  The stream is 368,895 bytes and is decoded at boot into
# .bss buffers (pk_pcm_*) by modules/perky/cf_pcm_rice.h.
PCM_ASSETS = (
    ("pk_asset_wt_base",   0x080222A0, 4096),
    ("pk_asset_wt_bank",   0x080327CC, 196608),
    ("pk_asset_ah_closed", 0x080CBEF0, 20202),
    ("pk_asset_ah_open",   0x080A1BF0, 172800),
    ("pk_asset_ah_ride",   0x080627CC, 259106),
)
PCM_SYMBOLS = (
    ("pk_pcm_wt_base",   4096),
    ("pk_pcm_wt_bank",   196608),
    ("pk_pcm_ah_closed", 20202),
    ("pk_pcm_ah_open",   172800),
    ("pk_pcm_ah_ride",   259106),
)
PCM_STREAM_LABEL = "pk_asset_pcm_rice"

_PCM_LABELS = {label for label, _a, _s in PCM_ASSETS}
IMAGE_ASSETS = tuple(a for a in ASSETS if a[0] not in _PCM_LABELS)


def pcm_stream(blobs: dict[str, bytes]) -> bytes:
    """The PKR1 stream, in PCM_ASSETS order (the decoder's target order)."""
    import pcm_rice  # noqa:E402  (tools/perky on sys.path)

    return pcm_rice.encode([blobs[label] for label, _a, _s in PCM_ASSETS])


def assembly_text(path: Path | None = None) -> str:
    blobs = extract(path)
    rows = [
        "| Generated at build time from SHA-pinned PĒRKONS v1.2.1; do not commit firmware bytes.",
        "        .balign 4",
    ]
    for label, address, size, _expected in IMAGE_ASSETS:
        blob = blobs[label]
        rows += [
            "        .balign 4",
            f"        .global {label}",
            f"{label}:",
            f"        | original M7 0x{address:08x}, {size} bytes",
            *_byte_rows(blob),
            f"        .global {label}_end",
            f"{label}_end:",
        ]
    stream = pcm_stream(blobs)
    rows += [
        "        .balign 4",
        f"        .global {PCM_STREAM_LABEL}",
        f"{PCM_STREAM_LABEL}:",
        f"        | PKR1 stream over {len(PCM_ASSETS)} assets, "
        f"{sum(s for _l, _a, s in PCM_ASSETS)} raw bytes",
        *_byte_rows(stream),
        f"        .global {PCM_STREAM_LABEL}_end",
        f"{PCM_STREAM_LABEL}_end:",
        "",
        "| The decode destination: never loaded (BSS), filled once at boot.",
        "        .section .bss",
        "        .balign 4",
    ]
    for label, size in PCM_SYMBOLS:
        rows += [
            f"        .global {label}",
            f"{label}:",
            f"        .space {size}",
            f"        .global {label}_end",
            f"{label}_end:",
        ]
    rows.append("        .text")
    return "\n".join(rows) + "\n"


def asset_inc(_modules) -> str:
    """Linked.include callback used by the platform runtime build."""
    return assembly_text()


def main() -> None:
    path = firmware_path()
    blobs = extract(path)
    total = 0
    print(f"PERKY CF assets: {path.name} sha256={FIRMWARE_SHA256}")
    for label, address, size, expected in ASSETS:
        blob = blobs[label]
        total += len(blob)
        print(
            f"  {label:20s} 0x{address:08x} {len(blob):5d} B "
            f"sha256={expected}"
        )
    print(f"  total {total:,} bytes")


if __name__ == "__main__":
    main()
