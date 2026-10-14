#!/usr/bin/env python3
"""Reject expensive/unbounded operations from final Perky per-sample renderers."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
RENDERERS = ("cf_fold.c", "cf_karplus.c", "cf_noise_tone.c", "cf_wavetable.c", "cf_resonant.c")


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*?$", "", text, flags=re.M)


def main() -> None:
    for name in RENDERERS:
        text = strip_comments((PERKY / name).read_text())
        if name == 'cf_wavetable.c':
            # Unsigned division/remainder by the pinned power-of-two table
            # stride are shifts/masks, not runtime division. The target-code
            # gate also rejects emitted div/rem instructions and helpers.
            header = (PERKY/'cf_wavetable.h').read_text()
            match = re.search(r'^#define PK_CF_WT_BANK_STRIDE (0x[0-9a-fA-F]+)u$', header, re.M)
            if not match or (stride := int(match[1],16)) == 0 or stride & (stride-1):
                raise AssertionError('WT bank stride is no longer an unsigned power of two')
            text = re.sub(r'([/%])\s*PK_CF_WT_BANK_STRIDE\b', ' SHIFT_OR_MASK_CONSTANT ', text)
        # The final render files intentionally use shifts/multiply helpers only.
        # Division/modulo in these files would place a high-latency operation in
        # or adjacent to a 44.1-kHz hot path and must be reviewed explicitly.
        if re.search(r"(?<![/*])/=(?!=)|(?<![/*])/(?![/*=])", text):
            raise AssertionError(f"{name}: division operator leaked into renderer")
        if re.search(r"%=|%(?!=)", text):
            raise AssertionError(f"{name}: modulo operator leaked into renderer")
        for bad in ("malloc(", "calloc(", "realloc(", "free(", "memcpy(", "memmove(", "memset("):
            if bad in text:
                raise AssertionError(f"{name}: libc/heap call leaked into renderer: {bad[:-1]}")

    nt = strip_comments((PERKY / "cf_noise_tone.c").read_text())
    shared = nt[nt.index("int pk_cf_nt_shared_render"):]
    loop = shared.index("for(i=0;i<n;i++)")
    for setup in ("osc_fast_init", "noise_fast_init", "filt_fast_init"):
        if shared.find(setup) < 0 or shared.find(setup) > loop:
            raise AssertionError(f"Noise/Tone fast setup {setup} is not outside sample loop")
    for slow in ("findwave(", "osc_fast_init(", "noise_fast_init(", "filt_fast_init("):
        body = shared[loop:shared.index("noise_fast_store", loop)]
        if slow in body:
            raise AssertionError(f"Noise/Tone sample loop contains slow setup/search: {slow[:-1]}")

    print(
        "PERKY CF hot loops: PASS "
        "(no runtime renderer div/mod/heap/libc; Noise/Tone wave/filter/noise setup outside sample loop)"
    )


if __name__ == "__main__":
    main()
