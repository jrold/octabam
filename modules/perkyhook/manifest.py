"""MINIMAL PERKY HOOK DEBUG -- the hardware-blocker bisect, part one.

See modules/perky/hook_only.asm for what it does and what each outcome means.

It is deliberately NOT a machine: no dispatch entry, no ColdFire side, no Y
tables, no audio. It is the source hook, its site, its admission test and its
two continuations, and nothing else. Flashing it answers exactly one question --
does the hook mechanism wedge the sequencer? -- and it must not be mistaken for
a build of the instrument.
"""
from remix.schema import (  # noqa: F401
    BusRole, Claims, DspHook, DspSection, Kind, Module, YBase,
)

MODULE = Module(
    name="perkyhook",
    key="PERKY HOOKDBG",
    kind=Kind.DSP_CLIENT,
    doc=("Source-hook debug insert: replays the displaced stock instruction, "
         "applies the admission test, and returns to stock (rts, popping the "
         "seam's JSR return) when the event is not ours. Renders nothing."),
    menu=None,
    params=(),
    dsp=DspSection(
        asm="modules/perky/hook_only.asm",
        priority=90,
        payloads=frozenset({"A", "B"}),
        bus_role=BusRole.NONE,
        ybase=YBase.NEVER,
        dev_pin_ybase=None,
        r7_latch_slot=None,
        gate_label=None,
        override_markers=(),
        ptable=(),
        ptable2=(),
        hooks=(
            DspHook(
                site={"A": 0x0039C, "B": 0x001A2},
                stock=(0x567000, 0x00020E),
                label="pk3d_source",
                note=("MINIMAL HOOK DEBUG: admission + both continuations, "
                      "no renderer"),
            ),
        ),
        subst={
            "A": {"@CONT@": "$000426"},
            "B": {"@CONT@": "$000221"},
        },
        max_per_core=None,
    ),
    cf_patches=(),
    # The hook touches no table and claims no private memory: it writes only
    # x:$20e, which the displaced instruction wrote anyway.
    claims=Claims(
        reserved_private_y=(),
        owns_fx2_buffers=False,
        stock_instance_buffer=False,
        buffer_words=None,
        fx1_only=False,
        part_window=(),
        sram=(),
        dsp_ranges=(),
    ),
    harness=None,
    linked=(),
    dram_regions=(),
    detours=(),
    tables=(),
    symbol_refs=(),
    pokes=(),
    keeps=(),
    overrides=(),
    requires=(),
    conflicts=(),
)
