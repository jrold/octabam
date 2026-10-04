"""PERKY milestone-0 source canary.

This is deliberately NOT the final PERKY machine yet.  In the isolated
``perky-probe`` remix it replaces FLEX's source-render callback with a tiny
record writer, then hooks the hardware-proven Analog-BD DSP source seam.  A
real trig must emerge as one +0.5 stereo impulse at the stock event offset and
then continue through the stock AMP -> FX1 -> FX2 path.

Keeping this as its own module/remix gives us one falsifiable result before the
Noise/Tone renderer and the full machine browser are allowed into the image.
"""
from remix.schema import (
    ArenaReserve,
    Category,
    Claims,
    DspHook,
    DspRange,
    DspSection,
    Gate,
    Kind,
    Linked,
    Module,
    Proof,
    SymbolRef,
)

MODULE = Module(
    name="perky",
    key="PERKY PROBE",
    kind=Kind.HYBRID,
    category=Category.MACHINES,
    author="jrold",
    author_url="https://github.com/jrold",
    proof=Proof.CHECK,
    proof_note="development source-seam canary; hardware flash still pending",
    doc="Development canary: FLEX trig -> PERKY transport record -> DSP impulse before AMP/FX.",

    linked=(Linked("pkprobe", "modules/perky/probe_cf.s"),),
    symbol_refs=(
        SymbolRef(
            0x400D6438,
            0x40004008,
            "pkprobe",
            "pk_probe_render",
            note="isolated canary: replace FLEX renderer with PK/Y1 record writer",
        ),
    ),
    arena=ArenaReserve(pages=242, where="bottom"),
    claims=Claims(dsp_ranges=(
        DspRange("x", 0x3800, 236, "PERKY compact voice state + envelope caches + RNG"),
        DspRange("x", 0x38EC, 1, "PERKY source event-offset staging"),
        DspRange("x", 0x3900, 64, "PERKY shared source-render scratch"),
        DspRange("y", 0x0795, 0x1000 - 0x0795, "PERKY packed Noise/Tone tables"),
    )),
    dsp=DspSection(
        asm="modules/perky/probe_glue.asm",
        priority=90,
        hooks=(
            DspHook(
                site={"A": 0x0039C, "B": 0x001A2},
                stock=(0x567000, 0x00020E),
                label="pk_probe_source",
                note="source prepare seam: replay x:$20e setup, inspect PK/Y1 record",
            ),
        ),
        subst={
            "A": {"@CONT@": "$000426"},
            "B": {"@CONT@": "$000221"},
        },
    ),
    conflicts=((
        "ANALOG BD",
        "both replace the FLEX source callback and hook the same DSP source seam",
    ),),
    pressure_blocker=(
        "development source-machine canary; source work is outside the FX pressure pricer"
    ),
    gates=(
        Gate("tools/verify/verify_perky_probe.py", remix_arg=False),
        Gate("tools/verify/verify_perky_synth_seam.py", remix_arg=False),
        Gate("tools/verify/verify_perky_preboot_reserve.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_tone_ref.py", remix_arg=False),
        Gate("tools/verify/verify_perky_dsp_word_model.py", remix_arg=False),
        Gate("tools/verify/verify_perky_compact_voice.py", remix_arg=False),
        Gate("tools/verify/verify_perky_compact_packed.py", remix_arg=False),
        Gate("tools/verify/verify_perky_voice_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_voice_packed_wave_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_voice_packed_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_voice_xstate_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_sources.py", remix_arg=False),
        Gate("tools/verify/verify_perky_table_extractor.py", remix_arg=False),
        Gate("tools/verify/verify_perky_memory_plan.py", remix_arg=False),
        Gate("tools/verify/verify_perky_runtime_memory.py", remix_arg=False),
        Gate("tools/verify/verify_perky_packed_tables.py", remix_arg=False),
        Gate("tools/verify/verify_perky_envelope_cache.py", remix_arg=False),
        Gate("tools/verify/verify_perky_envelope_cursor.py", remix_arg=False),
        Gate("tools/verify/verify_perky_table_payload.py", remix_arg=False),
        Gate("tools/verify/verify_perky_image_tables.py", remix_arg=False),
        Gate("tools/verify/verify_perky_synthetic_fixtures.py", remix_arg=False),
        Gate("tools/verify/verify_perky_synthetic_render.py", remix_arg=False),
        Gate("tools/verify/verify_perky_math_source.py", remix_arg=False),
        Gate("tools/verify/verify_perky_math_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_filter_source.py", remix_arg=False),
        Gate("tools/verify/verify_perky_filter_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_oscillator_source.py", remix_arg=False),
        Gate("tools/verify/verify_perky_oscillator_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_oscillator_packed_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_envelope_source.py", remix_arg=False),
        Gate("tools/verify/verify_perky_envelope_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_envelope_packed7_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_mix_source.py", remix_arg=False),
        Gate("tools/verify/verify_perky_mix_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_wave_unpack_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_envelope_unpack7_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_probe_port.py", remix_arg=False, stage="image"),
    ),
)
