"""Construct the full PERKY machine module for development builds.

The tracked ``modules/perky/manifest.py`` intentionally remains the tiny
impulse probe. This helper upgrades that declaration in memory only:

* machine.s + generated control.s become DRAM-linked ColdFire units;
* the complete Analog-BD-qualified source-machine detour/poke map is installed;
* FLEX renderer and engine-browser symbol hooks target PERKY control symbols;
* the DSP section points at the generated complete Noise/Tone synth source.

No tracked manifest is mutated by this helper.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from remix.schema import Detour, Linked, Poke, Proof, SymbolRef

H = bytes.fromhex


def build(original, *, control_source: str, dsp_source: str, src_only: bool = False,
          phase2_ui: bool = False):
    if original.key != "PERKY PROBE":
        raise ValueError(f"expected PERKY PROBE, got {original.key!r}")
    if original.dsp is None or original.dsp.asm != "modules/perky/probe_glue.asm":
        raise ValueError("tracked PERKY module is no longer the impulse probe")

    dsp = dataclasses.replace(original.dsp, asm=dsp_source)
    linked = (
        Linked("pkmachine", "modules/perky/machine.s", dram=True),
        Linked("pkcontrol", control_source, dram=True),
    )
    symbol_refs = (
        SymbolRef(
            0x400D6438, 0x40004008, "pkcontrol", "pk_render",
            note="FLEX renderer: signed PERKY tracks publish PK/Y1 source records",
        ),
        SymbolRef(
            0x400CE10E, 0, "pkcontrol", "pk_engine_left",
            note="LEFT from PERKY engine pool to machine chooser",
        ),
        SymbolRef(
            0x400CF714, 0x4007909C, "pkcontrol", "pk_engine_right",
            note="RIGHT on PERKY enters its engine pool",
        ),
    )

    # Same measured source-machine hook sites/guards as ANALOG BD. Only the
    # destination unit/symbol names differ.
    detours = (
        Detour(0x40077B5C, H("7c01bc80650e"), "pkmachine", "pk_pool_title",
               "show the stock right-chevron for the PERKY engine pool"),
        Detour(0x4006D784, H("4fefffe848d73c0c"), "pkmachine", "pk_list_draw",
               "draw the PERKY engine browser in the stock pool layout", pad_to=8),
        Detour(0x400791E4, H("2f0a4ab9460e70e0"), "pkmachine", "pk_pool_open",
               "track double-tap opens the PERKY engine list", pad_to=8),
        Detour(0x400334D8, H("2f02222f0008"), "pkmachine", "pk_machine_name",
               "format machine row 5 as PERKY"),
        Detour(0x4003C928, H("4bf9400a78c8"), "pkmachine", "pk_src_names",
               "point SRC SETUP at six machine names", kind="lea"),
        Detour(0x4003D718, H("41f9400a78c8"), "pkmachine", "pk_name_a",
               "main page name lookup for the signed PERKY track"),
        Detour(0x4004C36A, H("41f9400a78c8"), "pkmachine", "pk_name_b",
               "second main page name lookup for the signed PERKY track"),
        Detour(0x4003C980, H("71104fef0018"), "pkmachine", "pk_setup_row",
               "SRC SETUP row highlights PERKY on a signed FLEX track"),
        Detour(0x400786C8, H("7110b480662e"), "pkmachine", "pk_chooser_row",
               "main chooser row highlights PERKY on a signed FLEX track"),
        Detour(0x400585DC, H("161079034879400bb704"), "pkmachine", "pk_setup_open",
               "SRC SETUP opens on PERKY for the signed track", pad_to=10),
        Detour(0x4005221E, H("4ebaff1c4eb94007e940"), "pkmachine", "pk_tick_hook",
               "publish the PERKY SRC SETUP descriptor", pad_to=10),
        Detour(0x40078886, H("71102f004879460e7386"), "pkmachine", "pk_chooser_open",
               "the track's machine list opens on PERKY for the signed track", pad_to=10),
        Detour(0x40031E74, H("710541f9400d5f386050"), "pkmachine", "pk_resolve_pb",
               "resolve the signed track's PERKY page without changing FLEX tracks", pad_to=10),
        Detour(0x4007981C, H("77101084d081"), "pkmachine", "pk_main_commit",
               "admit PERKY at main chooser commit"),
        Detour(0x4005A616, H("2239460d5c30"), "pkmachine", "pk_src_commit",
               "admit PERKY at SRC SETUP commit"),
        Detour(0x4005A850, H("2239460d5c30"), "pkmachine", "pk_src_commit2",
               "same admission at SRC SETUP second commit path"),
        Detour(0x4003A52E, H("2002e788d4829082"), "pkmachine", "pk_setup_edit6",
               "SETUP editor stores PERKY row in the track FLEX slot", pad_to=8),
        Detour(0x4003CD98, H("2e06e78fdc869e86"), "pkmachine", "pk_setup_draw6",
               "SETUP drawer reads PERKY row from the track FLEX slot", pad_to=8),
        Detour(0x40002318, H("4fefffa048d77cfc"), "pkmachine", "pk_validate",
               "Part validator preserves PERKY source bytes", pad_to=8),
    )

    pokes = (
        Poke(0x40079248, H("48780005"), H("48780006"),
             "machine chooser has six rows, PERKY last"),
        Poke(0x400585FA, H("48780005"), H("48780006"),
             "SRC SETUP selector has six rows"),
        Poke(0x4003C950, H("7204"), H("7205"),
             "SRC SETUP name lookup admits PERKY"),
        Poke(0x40078678, H("7004"), H("7005"),
             "machine chooser draws PERKY"),
        Poke(0x400786CE, H("7004"), H("7005"),
             "machine chooser highlights PERKY"),
        Poke(0x40079904, H("7604"), H("7605"),
             "machine chooser persists PERKY"),
    )

    if src_only:
        widget=Path(control_source).with_name('lfo-widget.s')
        write_lfo_widget(widget)
        linked+=(Linked("pkui",widget.as_posix(),dram=True),)
        symbol_refs=tuple(r for r in symbol_refs if r.symbol in ("pk_render","pk_engine_right"))
        symbol_refs+=(SymbolRef(0x400d38d8,0x4003bf64,"pkcontrol","pk_lfo_format",
                               note="PERKY five-character PMTR names; stock tracks retain stock strings"),
                      SymbolRef(0x400d3908,0x4004661c,"pkui","pk_lfo_widget",
                               note="PERKY PMTR widget has room for DECAY and SRC"))
        detours=tuple(d for d in detours if d.symbol not in
                      ("pk_pool_title","pk_list_draw","pk_pool_open"))

    if phase2_ui:
        assert src_only, 'PERKY4 uses the SRC-only UI'
        linked += (Linked("pkfourui", "modules/perky/machine_four_ui.s", dram=True),)
        detours += (Detour(0x40040132, H("4879400bf10a2f36cce8"),
                          "pkfourui", "pk_four_machine_glyph",
                          "signed PERKY track selects stock P bitmap; internal FLEX type stays intact",
                          pad_to=10),)
        detours += (Detour(0x4004beac, H("4a1066044282600e"),
                          "pkfourui", "pk_four_play_glyph",
                          "PERKY source trig latch feeds stock play glyph; stock player flags stay intact",
                          pad_to=8),)

    return dataclasses.replace(
        original,
        linked=linked,
        symbol_refs=symbol_refs,
        detours=detours,
        pokes=pokes,
        dsp=dsp,
        proof=Proof.CHECK,
        proof_note=("PERKY4 four-engine source; local qualification required; hardware pending" if phase2_ui else
                    "development full Noise/Tone machine; emulator/hardware qualification pending"),
        doc=(
            "Development PERKY Noise/Tone machine: PK/1-signed FLEX donor, "
            "five source controls, engine browser, packed DSP synth source."
        ),
    )


def write_lfo_widget(path):
    """Clone the user's stock widget with a larger, independently terminated name.

    Keep every instruction length and internal branch unchanged. External
    calls are absolute. No Elektron bytes are stored in the repository.
    """
    base,end=0x4004661c,0x400467a2
    stock_path=Path('out/raw/section_3_MAIN_OS.bin').resolve()
    stock=stock_path.read_bytes()
    changes={0x4004661e:(0xffcc,0xffc8),
             0x40046626:(0x38,0x3c),0x4004662a:(0x3c,0x40),
             0x4004662e:(0x44,0x48),0x40046632:(0x48,0x4c),
             0x40046636:(0x4c,0x50),0x4004663a:(0x50,0x54),
             0x400466a4:(0x33,0x34),0x400466a8:(0x2e,0x2f),
             0x400466b6:(0x2f,0x30),0x4004679e:(0x34,0x38)}
    asm='''        .text
        .global pk_lfo_widget
pk_lfo_widget:
        lea -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr pk_selected_source
        tst.l %d0
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea 16(%sp),%sp
        bne.s .lfo_five
        jmp (0x4004661c).l
.lfo_five:
'''
    cursor=base
    for address,(before,after) in sorted(changes.items()):
        off=address-0x40000400
        assert int.from_bytes(stock[off:off+2],'big')==before,('stock LFO widget drift',hex(address))
        if address>cursor:
            asm+=f'        .incbin "{stock_path}", {cursor-0x40000400}, {address-cursor}\n'
        asm+=f'        .word 0x{after:04x}\n';cursor=address+2
    asm+=f'        .incbin "{stock_path}", {cursor-0x40000400}, {end-cursor}\n'
    path.write_text(asm)
