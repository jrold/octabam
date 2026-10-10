"""Construct the final ColdFire-only Perky Machines module declaration.

Unlike the historical HW4/DSP audition builders, this architecture renders
PĒRKONS PCM on the ColdFire and publishes ordinary FLEX-compatible source
segments.  The stock DSP image, source preparation, AMP, FX1 and FX2 code/data
are therefore left completely untouched.
"""
from __future__ import annotations

import dataclasses

from remix.schema import Claims, Gate, Kind, Linked, Proof, SymbolRef
import perky_machine_module as legacy
import perky_cf_assets


def build(original, *, generated_dir: str = "out/perky/cf-final"):
    if original.key != "PERKY PROBE":
        raise ValueError(f"expected PERKY PROBE, got {original.key!r}")

    # Reuse only the already-measured ColdFire machine chooser/detour surface.
    # The DSP argument is discarded below; this just obtains the qualified
    # machine/UI patch set without duplicating it here.
    base = legacy.build(
        original,
        control_source=f"{generated_dir}/pkcontrol.s",
        dsp_source="modules/perky/probe_glue.asm",
    )

    linked = (
        Linked("pkmachine", "modules/perky/machine.s", dram=True),
        Linked("pkassets", "modules/perky/cf_assets.s", dram=True,
               include=perky_cf_assets.asset_inc),
        Linked("pkfold", f"{generated_dir}/pkfold.s", dram=True),
        Linked("pkkarplus", f"{generated_dir}/pkkarplus.s", dram=True),
        Linked("pknoise", f"{generated_dir}/pknoise.s", dram=True),
        Linked("pkresonant", f"{generated_dir}/pkresonant.s", dram=True),
        Linked("pknoisehat", f"{generated_dir}/pknoisehat.s", dram=True),
    Linked("pksimpledrum", f"{generated_dir}/pksimpledrum.s", dram=True),
    Linked("pkcomplexdrum", f"{generated_dir}/pkcomplexdrum.s", dram=True),
        Linked("pkcore", f"{generated_dir}/pkcore.s", dram=True),
        Linked("pkcontrol", f"{generated_dir}/pkcontrol.s", dram=True),
    )
    refs = tuple(
        SymbolRef(r.addr, r.expect, r.unit, r.symbol, note=r.note)
        for r in base.symbol_refs
    )

    return dataclasses.replace(
        base,
        kind=Kind.CF_PATCH,
        linked=linked,
        symbol_refs=refs,
        # Locked all-FX property: no replacement, hook, allocation or reserve
        # exists anywhere in DSP P/X/Y.  The ordinary stock source record is
        # consumed by the unmodified DSP path.
        dsp=None,
        claims=Claims(),
        arena=None,
        gates=(
            Gate("tools/verify/verify_perky_cf_final_control.py", remix_arg=False),
            Gate("tools/verify/verify_perky_cf_freestanding.py", remix_arg=False),
            Gate("tools/verify/verify_perky_cf_machine_module.py", remix_arg=False),
            Gate("tools/verify/verify_perky_cf_final_remix.py", remix_arg=False),
            Gate("tools/verify/verify_perky_cf_final.py", remix_arg=False),
            Gate("tools/verify/verify_perky_stock_dsp_identity.py", remix_arg=False, stage="image"),
        ),
        proof=Proof.CHECK,
        proof_note=(
            "ColdFire PĒRKONS source renderer; stock DSP/AMP/FX1/FX2 untouched; "
            "four-track PCM/control/source-record gates required"
        ),
        doc=(
            "Four-track Perky Machines: Tune/Decay/Algo/Prm1/Prm2/Mode on "
            "SRC A-F; ColdFire synthesis into stock source/AMP/FX1/FX2 chain."
        ),
        pressure_blocker=(
            "ColdFire source synthesis is outside the DSP FX pressure pricer; "
            "qualified by Perky PCM/control/source-record gates"
        ),
    )
