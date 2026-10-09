"""REPITCH_REPEAT98_KYOTI -- TSTR RPCH / RPS9 / RPSP: tempo-locked varispeed with S900/S950 and SP-1200 repitch emulations, and QUAN ratios on PTCH.

Source: `upstream/` is Zac Kyoti's repository (Zac-Kyoti/octatrack-kyoti-fw,
submodule, pinned to `329b801`). The declaration is
`upstream/octabam-modules/repitch-repeat98-kyoti/manifest.py`: three DRAM units
(`patch_repitch_kyoti.s`, `rpk_glyphs.s`, `patch_repitch_reload.s`), the first
two re-linked and compared with the author's own bytes (`reference`) every
build, and a DSP section (`rpk_dsp.asm`, reached by two hooks -- the voice
kernel's prologue and the boot memory clear -- with two table blocks). Its source paths are derived from its own directory, so it is executed
here from the source on disk, as the registry does for every manifest, and this
file only re-exports its MODULE. Nothing inside `upstream/` is edited here.
"""

import dataclasses
import pathlib
import runpy

from remix.schema import Category, Proof

_UPSTREAM = pathlib.Path(__file__).resolve().parent / "upstream" / "octabam-modules" / "repitch-repeat98-kyoti" / "manifest.py"

MODULE = runpy.run_path(str(_UPSTREAM), run_name="remix_manifest_repitch_repeat98_kyoti")["MODULE"]
# The module table's fields are octabam's (README.md, `make docs`), so they
# are added here rather than in the author's manifest.
MODULE = dataclasses.replace(
    MODULE, category=Category.MACHINES, author="Zac-Kyoti/octatrack-kyoti-fw", author_url="https://github.com/Zac-Kyoti/octatrack-kyoti-fw",
    proof=Proof.HARDWARE, proof_note="the author's MKI, 5-8 Oct 2026, octabam images with every KYOTI module, REC_TRIG_MUTE and SIDECHAIN_COMPRESSOR, only SPRING REV given up: RPCH/QUAN, RPS9/RPSP, on T5-T8 beside SIDECHAIN, TSTR across a Part reload; four RPSP tracks per core with DARK REV, and up to three DJ EQs on T5-T8")
