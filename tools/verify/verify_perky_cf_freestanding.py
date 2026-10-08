#!/usr/bin/env python3
"""Source gate for the final no-libgcc/no-libc ColdFire Perky core."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "modules/perky"
FILES = (
    "control_cf_final.c", "cf_perky4.c", "cf_fold.c", "cf_karplus.c", "cf_noise_tone.c"
)
FORBIDDEN_SOURCE = re.compile(r"\b(?:u?int64_t|memset|memcpy|memmove)\b")

for name in FILES:
    text = (P / name).read_text()
    hits = sorted(set(FORBIDDEN_SOURCE.findall(text)))
    if hits:
        raise SystemExit(f"verify-perky-cf-freestanding: {name}: forbidden {hits}")

math = (P / "cf_math.h").read_text()
for symbol in ("pk_cf_mul_hi_u32", "pk_cf_mul_hi_s32", "pk_cf_mul_lo_u32"):
    if symbol not in math:
        raise SystemExit(f"verify-perky-cf-freestanding: missing {symbol}")

print("PERKY CF freestanding source: PASS (32-bit-only math; no libc memory calls)")
