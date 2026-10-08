#!/usr/bin/env python3
"""Reject expensive/unbounded operations from final Perky per-sample renderers."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
RENDERERS = ("cf_fold.c", "cf_karplus.c", "cf_noise_tone.c")


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*?$", "", text, flags=re.M)


def main() -> None:
    for name in RENDERERS:
        text = strip_comments((PERKY / name).read_text())
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
        "(no renderer div/mod/heap/libc; Noise/Tone wave/filter/noise setup outside sample loop)"
    )


if __name__ == "__main__":
    main()
