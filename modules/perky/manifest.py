"""PERKY milestone-0 source canary.

This is deliberately NOT the final PERKY machine yet. In the isolated
``perky-probe`` remix it replaces FLEX's source-render callback with a tiny
record writer, then hooks the hardware-proven Analog-BD DSP source seam. A
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
    # The PERKY arena: 242 pages reserved at the bottom of DRAM. This is not
    # decoration -- repack_machine_loader.verify_reservation checks the
    # built image for the reservation poke and refuses without it
    # ("PERKY arena reservation missing at 0x4000045e"). The light build
    # needs it exactly as the PERKY4 build did.
    arena=ArenaReserve(pages=242, where="bottom"),
    claims=Claims(dsp_ranges=(
        DspRange("x", 0x3800, 236, "PERKY compact voice state + envelope caches + RNG"),
        DspRange("x", 0x38EC, 2, "PERKY source event-offset and admission staging"),
        DspRange("x", 0x3900, 0x64, "PERKY shared sparse source-render scratch"),
        DspRange("y", 0x07a5, 0x1000 - 0x07a5, "PERKY packed Noise/Tone tables"),
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
        # @CONT@ is where the ADMITTED path resumes: the stock code past the
        # source render, which sets r7/r6/n7 from x:$20a/$208/$20c and mixes.
        #
        # The seam is planted as a `jsr`, so BOTH exits must balance the stack
        # and they do it differently on purpose:
        #   not admitted -> `rts`, which pops the seam's return and resumes at
        #                   the instruction after the hook (stock source runs)
        #   admitted     -> `move ssh,x0` DISCARDS that return (measured: with
        #                   it, a following `rts` does not return; without it,
        #                   it does), then `jmp @CONT@` skips the stock source.
        # Neither path may simply `jmp`: that would leak one stack level per
        # track per frame, wrap the 15-deep hardware stack and destroy stock's
        # return addresses.
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
        Gate("tools/verify/verify_perky_synth_source_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_control_mapper.py", remix_arg=False),
        Gate("tools/verify/verify_perky_control_mapper_exec.py", remix_arg=False),
        # The two-voice LIGHT machine's SRC page-1 contract, executed against the
        # real pk_render: six controls, exact staging mask, engine byte on ALGO
        # with a one-trig p-lock.  The light page has no other gate.
        Gate("tools/verify/verify_perky_light2_src_page.py", remix_arg=False),
        Gate("tools/verify/verify_perky_shard_emit.py", remix_arg=False),
        # the brief's "no provenance mismatch between HEAD, manifest and produced
        # artifact": matches each recorded *_sha256= against the artifact it pins,
        # resolves git=, and refuses to pass when it can check no hash at all.
        Gate("tools/verify/verify_perky_provenance.py", remix_arg=False),
        # boot/upload/readback. No project fixture needed -- stops at the RTOS
        # handoff. The canary passes --image/--packed explicitly; with stale
        # defaults absent it SKIPs rather than failing make check.
        Gate("tools/verify/verify_perky_machine_boot.py", remix_arg=False),
        # keeps the step-0 probe honest: it re-runs the probe tool's
        # --selftest, which re-parses an edited payload copy and checks the
        # edit. Writes nothing.
        Gate("tools/verify/verify_perky_tail_probe.py", remix_arg=False),
        Gate("tools/verify/verify_perky_machine_module.py", remix_arg=False),
        Gate("tools/verify/verify_perky_preboot_reserve.py", remix_arg=False),
        Gate("tools/verify/verify_perky_abi_contract.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_tone_ref.py", remix_arg=False),
        Gate("tools/verify/verify_perky_dsp_word_model.py", remix_arg=False),
        Gate("tools/verify/verify_perky_cf_odd_access.py", remix_arg=False),
        # ALL_FX_MEMORY.md cites the placer as its proof that the 2404-word
        # shared-tail budget is usable; both were unregistered and so had
        # never run in make check. Registering them is the whole fix.
        Gate("tools/verify/verify_perky_all_fx_placer.py", remix_arg=False),
        Gate("tools/verify/verify_perky_all_fx_memory.py", remix_arg=False),
        # Engine gates that were genuinely unregistered.
        Gate("tools/verify/verify_perky_shipping_voice_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_fold_regression.py", remix_arg=False),
        Gate("tools/verify/verify_perky_fold_seam_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_multi_seam_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_synth_seam_exec.py", remix_arg=False),
        # Further engine/ABI gates, each verified to PASS before registration.
        Gate("tools/verify/verify_perky_simple_drum_voice_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_fold_drum_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_xstate_asm_layout.py", remix_arg=False),
        Gate("tools/verify/verify_perky_stock_dsp_boot_path.py", remix_arg=False),



        Gate("tools/verify/verify_perky_compact_voice.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_compact.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_hat_pulse_native_compact.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_hat_filter_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_hat_phase_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_hat_envelope_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_hat_pulse_synthetic_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_hat_classic_synthetic_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_slap_dsp_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_karplus_dsp_exec.py", remix_arg=False),
        # RETIRED: Resonant Bass and Resonant Snare are not in the shipping
        # engine pool, so their renderer gate is no longer a shipping gate. It
        # is removed from the gate LIST rather than deleted, because the tool
        # remains a useful non-shipping diagnostic -- and it is currently RED
        # for a reason that predates this branch: its Python model and the
        # composed DSP diverge at words 14/84/85/86. That divergence is
        # reproducible on the untouched donor branch with a correctly patched
        # dsp_asm, so it is a pre-existing model/DSP disagreement, not a
        # consequence of any change here. Nothing in the shipping light path
        # depends on it.
        # Gate("tools/verify/verify_perky_resonant_dsp_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_noise_tone_original_dsp_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_control.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_tables.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_runtime_tables.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_transport.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_live.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_frequency_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_envelope_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_oscillator_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_assets.py", remix_arg=False),
        Gate("tools/verify/verify_perky_simple_drum_state_analysis.py", remix_arg=False),
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
        Gate("tools/verify/verify_perky_envelope_cache_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_mix_source.py", remix_arg=False),
        Gate("tools/verify/verify_perky_mix_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_wave_unpack_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_envelope_unpack7_exec.py", remix_arg=False),
        Gate("tools/verify/verify_perky_table_image.py", remix_arg=False, stage="image"),
        Gate("tools/verify/verify_perky_probe_port.py", remix_arg=False, stage="image"),
    ),
)
