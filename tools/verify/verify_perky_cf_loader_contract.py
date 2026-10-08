#!/usr/bin/env python3
"""Gate the final Perky platform-loader DSP continuation contract.

The platform loader intentionally replaces the stock call site at 0x4000050c so
it can unpack DRAM runtimes. For final ColdFire-only Perky it must still call the
unchanged stock DSP boot routine at 0x40001e50 before loading the normal platform
runtime, and the generic platform builder must continue to guard the original
six-byte call before redirecting it.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
loader = (ROOT / "tools/remix/loader.S").read_text()
platform = (ROOT / "tools/remix/platform_build.py").read_text()

required_loader = (
    ".set    BOOT_CONTINUE, 0x40001e50",
    "jsr     (BOOT_CONTINUE).l",
    "lea     table(%pc),%a2",
)
for needle in required_loader:
    if needle not in loader:
        raise AssertionError(f"platform loader contract drifted: missing {needle!r}")
if loader.index("jsr     (BOOT_CONTINUE).l") > loader.index("lea     table(%pc),%a2"):
    raise AssertionError("platform runtime is unpacked before stock DSP boot continuation")

required_platform = (
    'boot_poke = (0x4000050C, bytes.fromhex("4eb940001e50")',
    'b"\\x4e\\xb9" + LOADER_AT.to_bytes(4, "big")',
    '"boot -> octabam loader"',
)
for needle in required_platform:
    if needle not in platform:
        raise AssertionError(f"platform boot redirect drifted: missing {needle!r}")

print(
    "PERKY CF loader contract: PASS "
    "(guard stock jsr 0x40001e50 at 0x4000050c; redirect caller only; "
    "loader invokes untouched stock DSP boot before normal Perky DRAM runtime)"
)
