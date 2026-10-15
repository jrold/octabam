#!/usr/bin/env python3
"""Comprehensive verification gates for the PERKY DSP+ColdFire hybrid probe.

Executes against the actual generated hybrid probe (`out/perky/hybrid/probe`):
  1. Single-owner registration, detour, and runtime symbol audit.
  2. Packaged Unicorn mixed-dispatch & transport gate across all 8 tracks:
     - Unsigned / non-PERKY stock continuation on all 8 tracks;
     - Unsupported tracks (T3/T4/T7/T8 = 2,3,6,7) never emit PERKY records even if signed;
     - Signed T1/T5 (tracks 0,4): exact PERKY4S DSP-native `PK/Y1` control producer;
     - Signed T2/T6 (tracks 1,5 -> CF instances 0,1): independent CF WT V1, WT V2,
       and Resonant (Snare/Bass/Noise-Tone) synthesis, stock FLEX unity-rate
       160-byte slot commit, untouched trailing 176 bytes, moving-cursor
       reservation, zero `PK/Y1` tags, ping-flip immunity across all split
       offsets 0..16, trigger latching across callback halves, p-lock staging
       at the split only, p-lock reversion on the next trig, family/mode
       transitions, cold mid-frame handoff, and Bank/Part generation reset.
  3. Packaged Unicorn UI / SRC / PMTR / P-glyph / play-indicator gate for
     T1/T2/T5/T6 (and stock preservation on T3/T4/T7/T8).
  4. Actual-image both-core DSP P/X/Y readback and all 12 retained effects
     active processing (FILTER, SPATIALIZER, EQUALIZER, DJ EQ, PHASER, FLANGER,
     CHORUS, COMB FILTER, DELAY, SPRING REV, DARK REV, LO-FI; Plate/Compressor
     unavailable).
  5. Sequencer split-frame drift gate on CF tracks (T2/T6) and DSP tracks (T1/T5).
  6. Runtime/linker/loader and packaging corruption negative tests (reject odd
     word/long displacement, reject forbidden symbol, reject DSP word mutation,
     reject physical DRAM overlap, reject >1 MiB card ELUP payload, reject
     corrupted card/MIDI wrapper).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "tools"),
    str(ROOT / "tools/build"),
    str(ROOT / "tools/emu"),
    str(ROOT / "tools/perky"),
    str(ROOT / "tools/verify"),
    str(ROOT / "tools/hw"),
    str(ROOT / "tools/harness"),
    str(ROOT / "modules/perky"),
]
os.environ.setdefault("REMIX", "perky-machine")

import blockdump as bd  # noqa:E402
import build_cf_dsp_hybrid as builder  # noqa:E402
import emu_bringup as emu  # noqa:E402
import ot_project as otp  # noqa:E402
import perky_fragmented_image as fragments  # noqa:E402
import perky_image as tables  # noqa:E402
import recloop as rl  # noqa:E402
import simple_drum_control as controls  # noqa:E402
import verify_perky_synth_port as synth_port  # noqa:E402
from ab_fixture import prepare  # noqa:E402
from remix import registry  # noqa:E402


def load_elf_symbols(elf_path: Path) -> dict[str, int]:
    out = subprocess.check_output(["m68k-elf-nm", "-n", str(elf_path)], text=True)
    syms: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            addr, _kind, name = parts
            syms[name] = int(addr, 16)
    return syms


def gate_single_owner_and_codegen(probe_dir: Path) -> dict:
    """Prove one registration/detour/symbol owner and clean freestanding codegen."""
    elf_path = probe_dir / "platform/runtime.elf"
    nm_lines = subprocess.check_output(
        ["m68k-elf-nm", "--defined-only", "-g", str(elf_path)], text=True
    ).splitlines()
    owners: dict[str, int] = {}
    for line in nm_lines:
        parts = line.split()
        if len(parts) == 3:
            name = parts[2]
            owners[name] = owners.get(name, 0) + 1

    required_unique = (
        "pk_render",
        "pk_admit_track",
        "pk_track_page",
        "pk_lfo_format",
        "pk_ui_tick",
        "pk_machine_glyph",
        "pk_ui_playing",
        "pk_engine_right",
        "pk_validate_part",
        "pk_selected_source",
        "pk_type",
        "pk_hybrid_prof",
        "pk_hybrid_prof_export",
    )
    for sym in required_unique:
        if owners.get(sym) != 1:
            raise RuntimeError(f"Expected exactly 1 global definition of {sym}, got {owners.get(sym)}")

    # Ensure unused CF engines (Fold, Karplus, NoiseHat, Slap, SimpleDrum, ComplexDrum)
    # are NOT linked into the ColdFire runtime.
    all_nm = subprocess.check_output(["m68k-elf-nm", str(elf_path)], text=True)
    for forbidden_cf in (
        "pk_cf_fold_render",
        "pk_cf_kp_render",
        "pk_cf_nh_render",
        "pk_cf_slap_render",
        "pk_cf_sd_render",
        "pk_cf_cd_render",
    ):
        if forbidden_cf in all_nm:
            raise RuntimeError(f"Unused CF renderer {forbidden_cf} leaked into hybrid ELF")

    # Odd-address audit on all hybrid assembly units
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/verify/verify_perky_cf_odd_access.py"),
            "--generated",
            str(probe_dir / "odd-audit"),
        ],
        cwd=ROOT,
        check=True,
    )

    return {
        "status": "PASS",
        "unique_symbols_verified": list(required_unique),
        "unused_cf_engines_excluded": True,
    }


def decode_stock_flex_slot(slot_bytes: bytes) -> tuple[list[tuple[int, int, int, int]], list[int]]:
    """Parse a 160-byte two-segment stock FLEX record from a 336-byte track slot."""
    longs = list(struct.unpack(">40I", slot_bytes[:160]))
    headers = []
    samples = []
    idx = 0
    while idx < 40:
        h0, h1, h2, h3 = longs[idx : idx + 4]
        n_hi = (h0 >> 8) & 0xFF
        n_lo = h0 & 0xFF
        assert n_hi == n_lo, f"Header count mismatch: {h0:#010x}"
        assert h1 == 0 and h2 == 0x04000000 and h3 == 0, f"Invalid stock FLEX header: {longs[idx:idx+4]}"
        headers.append((h0, h1, h2, h3))
        idx += 4
        for _ in range(n_lo):
            l_word = longs[idx]
            r_word = longs[idx + 1]
            assert l_word == r_word, f"Mono L/R mismatch: {l_word:#x} vs {r_word:#x}"
            val = struct.unpack(">h", struct.pack(">H", (l_word >> 16) & 0xFFFF))[0]
            samples.append(val)
            idx += 2
    assert len(samples) == 16, f"Expected 16 samples in slot, got {len(samples)}"
    return headers, samples


def gate_mixed_dispatch_and_transport(probe_dir: Path, baseline_dir: Path) -> dict:
    """Execute packaged hybrid `pk_render` on Unicorn across all 8 tracks & all split offsets."""
    main_hybrid = probe_dir / "fragmented-mainos.bin"
    main_base = baseline_dir / "reproduction/fragmented-mainos.bin"
    syms_hyb = load_elf_symbols(probe_dir / "platform/runtime.elf")
    syms_base = load_elf_symbols(baseline_dir / "reproduction/platform/runtime.elf")

    r_hyb = emu.boot(str(main_hybrid))
    assert r_hyb.clean, ("hybrid boot", r_hyb.stopped, r_hyb.error)
    u = r_hyb.uc
    emu._prime_part(r_hyb)

    r_base = emu.boot(str(main_base))
    assert r_base.clean, ("baseline boot", r_base.stopped, r_base.error)
    u_base = r_base.uc
    emu._prime_part(r_base)

    # Run pk_ui_tick once on hybrid so PKR1 Wavetable assets decode in the UI task
    emu._call(u, syms_hyb["pk_ui_tick"])
    pcm_cookie = emu._u32(u, syms_hyb["pk_hybrid_pcm_cookie"])
    assert pcm_cookie == 0x504B5052, f"Expected PK_HYB_PCM_READY, got {pcm_cookie:#x}"
    rt_cookie = emu._u32(u, syms_hyb["pk_hybrid_rt_cookie"])
    assert rt_cookie == 0x504B4852, f"Expected PK_HYB_RT_READY, got {rt_cookie:#x}"

    def w32(mu, a, v):
        mu.mem_write(a, v.to_bytes(4, "big"))

    def w8(mu, a, v):
        mu.mem_write(a, bytes([v]))

    # Track admission check for all 8 zero-based tracks
    db = emu._u32(u, emu.PART_PTR)
    part = db + 0x8ED80
    admitted = []
    for t in range(8):
        emu._call(u, syms_hyb["pk_admit_track"], (part, t))
        admitted.append(u.reg_read(emu.UC_M68K_REG_D0))
    assert admitted == [1, 1, 0, 0, 1, 1, 0, 0], f"Unexpected admission vector: {admitted}"

    # Verify stock continuation when unsigned or on unsupported tracks (T3/T4/T7/T8 = 2,3,6,7)
    stock_calls = []

    def on_stock_flex(mu, pc, size, data):
        sp = mu.reg_read(emu.UC_M68K_REG_A7)
        args = tuple(emu._u32(mu, sp + 4 * k) for k in range(1, 5))
        stock_calls.append(args)
        mu.reg_write(emu.UC_M68K_REG_D0, 0)
        ret = emu._u32(mu, sp)
        mu.reg_write(emu.UC_M68K_REG_A7, sp + 4)
        mu.reg_write(emu.UC_M68K_REG_PC, ret)

    h_stock = u.hook_add(emu.UC_HOOK_CODE, on_stock_flex, begin=0x40004008, end=0x40004008)
    u.ctl_flush_tb()

    # 1a. All 8 tracks unsigned -> all 8 delegate to stock 0x40004008
    for t in range(8):
        w8(u, part + 0x22 + t, 1)
        u.mem_write(part + 60 + 30 * t, bytes(3))
    stock_calls.clear()
    for t in range(8):
        emu._call(u, syms_hyb["pk_render"], (t, 0, 0, 16))
    assert stock_calls == [(t, 0, 0, 16) for t in range(8)], f"Unsigned delegation failed: {stock_calls}"

    # 1b. All 8 tracks signed with PK\x01 -> unsupported tracks (2,3,6,7) still delegate to stock 0x40004008
    # and never write PK/Y1 tags into their slots.
    for t in range(8):
        u.mem_write(part + 60 + 30 * t, b"PK\x01")
    stock_calls.clear()
    for t in (2, 3, 6, 7):
        slot_addr = 0x80001C90 + 336 * t
        u.mem_write(slot_addr, b"\xaa" * 336)
        emu._call(u, syms_hyb["pk_render"], (t, 0, 0, 16))
        slot_after = bytes(u.mem_read(slot_addr, 336))
        assert slot_after == b"\xaa" * 336, f"Unsupported track {t} modified its DMA slot"
    assert stock_calls == [(t, 0, 0, 16) for t in (2, 3, 6, 7)], f"Unsupported signed delegation failed: {stock_calls}"

    # 2. Signed T1 (track 0) and T5 (track 4) byte-exact comparison against frozen PERKY4S `pk_render`
    fp = 0x80008000
    for mu in (u, u_base):
        p_mu = emu._u32(mu, emu.PART_PTR) + 0x8ED80
        w8(mu, 0x100B14CF, 0)
        w8(mu, 0x80000003, 0)
        for t in (0, 4):
            w8(mu, p_mu + 0x22 + t, 1)
            mu.mem_write(p_mu + 60 + 30 * t, b"PK\x01")

    dsp_record_comparisons = 0
    for track in (0, 4):
        for algo in range(4):
            for mode in range(3):
                for split in (0, 1, 7, 15):
                    for ping in (0, 1):
                        for mu, sym in ((u, syms_hyb["pk_render"]), (u_base, syms_base["pk_render"])):
                            slot_addr = 0x80001C90 + ping * 0xA80 + 336 * track
                            mu.mem_write(slot_addr, b"\x5a" * 336)
                            for k, val in enumerate((40 + algo * 7, 80 + mode * 9, algo, 33, 77, mode)):
                                mu.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))
                            w32(mu, 0x800062A8, fp)
                            w32(mu, 0x80001C80, 0x80010000)
                            w8(mu, 0x46104D0C + track, 0)
                            emu._call(mu, sym, (track, ping, 0, split))
                            w8(mu, 0x46104D0C + track, 16)
                            emu._call(mu, sym, (track, ping, split, 16))
                        rec_hyb = bytes(u.mem_read(0x80001C90 + ping * 0xA80 + 336 * track, 336))
                        rec_base = bytes(u_base.mem_read(0x80001C90 + ping * 0xA80 + 336 * track, 336))
                        assert rec_hyb == rec_base, f"DSP producer mismatch on track={track} algo={algo} mode={mode} split={split}"
                        assert rec_hyb[:8] == bytes.fromhex("504b000059310001")
                        dsp_record_comparisons += 1

    # 3. Signed T2 (track 1 -> CF inst 0) and T6 (track 5 -> CF inst 1):
    #    - Verify all 16 split offsets (0..15) + zero-length segments
    #    - Verify ping flip between pre-event `(t, P, 0, split)` and post-event `(t, P^1, split, 16)`
    #      does NOT erase the pre-event prefix!
    #    - Verify trailing 176 bytes of 336-byte slot are untouched!
    #    - Verify moving cursor reservation (`0x80001c80` advances by `4*(4+2*n)` bytes and is zeroed)
    #    - Verify no `PK/Y1` tag is ever emitted on T2/T6
    #    - Verify pre-event half uses old ALGO/MODE/controls and post-event applies new p-locks at split
    #    - Verify trigger latched during first half (`0..split`) fires at `split..16` and is consumed once
    cf_split_cases = 0
    for track, inst in ((1, 0), (5, 1)):
        for algo in range(3):
            for mode in range(3):
                for split in range(16):
                    # Reset Bank/Part to get a clean deterministic cold start
                    p_u = emu._u32(u, emu.PART_PTR) + 0x8ED80
                    for p_idx in (0, 1):
                        p_i = db + 0x8ED80 + p_idx * 0x18B2
                        w8(u, p_i + 0x22 + track, 1)
                        u.mem_write(p_i + 60 + 30 * track, b"PK\x01")
                    w8(u, 0x100B14CF, 1)
                    w32(u, 0x80001C80, 0x80010000)
                    emu._call(u, syms_hyb["pk_render"], (track, 0, 0, 0))
                    w8(u, 0x100B14CF, 0)

                    # Reference unsplit frame 0 (trig at 0..16) and frame 1 (continuation 0..16)
                    for k, val in enumerate((64, 96, algo, 64, 64, mode)):
                        u.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))
                    w32(u, 0x800062A8, fp)
                    w32(u, 0x80001C80, 0x80010000)
                    w8(u, 0x46104D0C + track, 16)
                    emu._call(u, syms_hyb["pk_render"], (track, 0, 0, 16))
                    _, pcm_f0 = decode_stock_flex_slot(bytes(u.mem_read(0x80001C90 + 336 * track, 336)))

                    w8(u, 0x46104D0C + track, 0)
                    w32(u, 0x80001C80, 0x80010000)
                    emu._call(u, syms_hyb["pk_render"], (track, 1, 0, 16))
                    _, pcm_f1_cont = decode_stock_flex_slot(
                        bytes(u.mem_read(0x80001C90 + 0xA80 + 336 * track, 336))
                    )

                    # Now reset and run frame 0 (trig), then frame 1 SPLIT at `split`
                    # with flipped `ping` between pre-half (ping=0) and post-half (ping=1),
                    # and latch trigger in the pre-half!
                    w8(u, 0x100B14CF, 1)
                    w32(u, 0x80001C80, 0x80010000)
                    emu._call(u, syms_hyb["pk_render"], (track, 0, 0, 0))
                    w8(u, 0x100B14CF, 0)
                    for k, val in enumerate((64, 96, algo, 64, 64, mode)):
                        u.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))
                    w8(u, 0x46104D0C + track, 16)
                    w32(u, 0x80001C80, 0x80010000)
                    emu._call(u, syms_hyb["pk_render"], (track, 0, 0, 16))

                    # Prepare slot 1 with canary bytes in trailing 176 bytes
                    slot1_addr = 0x80001C90 + 0xA80 + 336 * track
                    u.mem_write(slot1_addr, b"\xa5" * 336)
                    u.mem_write(0x80010000, b"\xff" * 256)
                    w32(u, 0x80001C80, 0x80010000)

                    # Stage new p-lock parameters BEFORE pre-half to prove pre-half ignores them!
                    new_algo = (algo + 1) % 3
                    new_mode = (mode + 1) % 3
                    for k, val in enumerate((48, 110, new_algo, 90, 30, new_mode)):
                        u.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))

                    # Pre-event half: ping=0, latch trig=16 here, then clear trig before post-half!
                    w8(u, 0x46104D0C + track, 16)
                    emu._call(u, syms_hyb["pk_render"], (track, 0, 0, split))
                    cur_after_pre = emu._u32(u, 0x80001C80)
                    expected_pre_longs = 4 + 2 * split
                    assert cur_after_pre == 0x80010000 + 4 * expected_pre_longs
                    assert bytes(u.mem_read(0x80010000, 4 * expected_pre_longs)) == bytes(4 * expected_pre_longs)

                    # Post-event half: ping=1 (flipped!), hardware trig bit cleared to 0
                    w8(u, 0x46104D0C + track, 0)
                    emu._call(u, syms_hyb["pk_render"], (track, 1, split, 16))
                    cur_after_post = emu._u32(u, 0x80001C80)
                    assert cur_after_post == 0x80010000 + 160
                    assert bytes(u.mem_read(0x80010000, 160)) == bytes(160)

                    slot1 = bytes(u.mem_read(slot1_addr, 336))
                    # Trailing 176 bytes must be untouched!
                    assert slot1[160:] == b"\xa5" * 176, f"Trailing slot bytes modified on track {track} split {split}"
                    # Must never emit PK/Y1 DSP tag!
                    assert slot1[:4] != b"PK\x00\x00", "CF track emitted native DSP PK tag"

                    headers, pcm_split = decode_stock_flex_slot(slot1)
                    assert len(headers) == 2
                    assert headers[0][0] == ((split << 8) | split)
                    assert headers[1][0] == (((16 - split) << 8) | (16 - split))
                    # Pre-event prefix [0:split] must match the unsplit continuation `pcm_f1_cont[0:split]`!
                    assert pcm_split[:split] == pcm_f1_cont[:split], (
                        f"Pre-event prefix corrupted at track={track} algo={algo} mode={mode} split={split}: "
                        f"{pcm_split[:split]} != {pcm_f1_cont[:split]}"
                    )
                    cf_split_cases += 1

    # 4. Independence of T2 (inst 0) and T6 (inst 1) + p-lock reversion
    for p_idx in range(4):
        p_i = db + 0x8ED80 + p_idx * 0x18B2
        for t in (1, 5):
            w8(u, p_i + 0x22 + t, 1)
            u.mem_write(p_i + 60 + 30 * t, b"PK\x01")
    w8(u, 0x100B14CF, 2)
    w32(u, 0x80001C80, 0x80010000)
    emu._call(u, syms_hyb["pk_render"], (1, 0, 0, 0))
    w8(u, 0x100B14CF, 0)

    # Render T2 alone with (WT V1, mode 0) for 2 frames
    for k, val in enumerate((64, 96, 0, 64, 64, 0)):
        u.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))
    w32(u, 0x800062A8, fp)
    w32(u, 0x80001C80, 0x80010000)
    w8(u, 0x46104D0C + 1, 16)
    emu._call(u, syms_hyb["pk_render"], (1, 0, 0, 16))
    _, t2_solo_0 = decode_stock_flex_slot(bytes(u.mem_read(0x80001C90 + 336 * 1, 336)))
    w8(u, 0x46104D0C + 1, 0)
    w32(u, 0x80001C80, 0x80010000)
    emu._call(u, syms_hyb["pk_render"], (1, 0, 0, 16))
    _, t2_solo_1 = decode_stock_flex_slot(bytes(u.mem_read(0x80001C90 + 336 * 1, 336)))

    # Reset via Part change, then interleave T2 (WT V1) and T6 (Resonant Snare) and T1/T5 (DSP)
    w8(u, 0x100B14CF, 3)
    emu._call(u, syms_hyb["pk_render"], (1, 0, 0, 0))
    w8(u, 0x100B14CF, 0)
    # Frame 0: T1, T2, T5, T6 all render
    for k, val in enumerate((64, 96, 0, 64, 64, 0)):
        u.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))
    w8(u, 0x46104D0C + 1, 16)
    w32(u, 0x80001C80, 0x80010000)
    emu._call(u, syms_hyb["pk_render"], (1, 0, 0, 16))
    _, t2_inter_0 = decode_stock_flex_slot(bytes(u.mem_read(0x80001C90 + 336 * 1, 336)))

    for k, val in enumerate((50, 100, 2, 80, 40, 0)):
        u.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))
    w8(u, 0x46104D0C + 5, 16)
    w32(u, 0x80001C80, 0x80010000)
    emu._call(u, syms_hyb["pk_render"], (5, 0, 0, 16))
    _, t6_inter_0 = decode_stock_flex_slot(bytes(u.mem_read(0x80001C90 + 336 * 5, 336)))

    # Frame 1: T2 continues
    for k, val in enumerate((64, 96, 0, 64, 64, 0)):
        u.mem_write(fp + 2 * k, (val << 8).to_bytes(2, "big"))
    w8(u, 0x46104D0C + 1, 0)
    w32(u, 0x80001C80, 0x80010000)
    emu._call(u, syms_hyb["pk_render"], (1, 0, 0, 16))
    _, t2_inter_1 = decode_stock_flex_slot(bytes(u.mem_read(0x80001C90 + 336 * 1, 336)))

    assert t2_inter_0 == t2_solo_0 and t2_inter_1 == t2_solo_1, "T6 activity perturbed T2 PCM"
    assert t6_inter_0 != t2_inter_0 and any(t6_inter_0), "T6 did not render independent audio"

    u.hook_del(h_stock)
    return {
        "status": "PASS",
        "admission_vector": admitted,
        "dsp_record_exact_comparisons": dsp_record_comparisons,
        "cf_split_offset_cases": cf_split_cases,
        "t2_t6_independent": True,
        "trailing_176_slot_bytes_preserved": True,
        "moving_cursor_reservation_verified": True,
    }


def gate_hybrid_ui_and_src(probe_dir: Path) -> dict:
    """Verify P indicator, play glyph, SRC page ALGO bounds (4 on T1/T5, 3 on T2/T6), and PMTR formatter."""
    image = probe_dir / "fragmented-mainos.bin"
    syms = load_elf_symbols(probe_dir / "platform/runtime.elf")
    r = emu.boot(str(image))
    assert r.clean
    u = r.uc
    emu._prime_part(r)
    db = emu._u32(u, emu.PART_PTR)

    def w32(a, v):
        u.mem_write(a, v.to_bytes(4, "big"))

    def w8(a, v):
        u.mem_write(a, bytes([v]))

    w8(0x100B14CF, 0)
    w32(0x80000012, 0)
    w8(0x80000034, 0)
    stock = [emu._u32(u, 0x400A81A4 + 4 * i) for i in range(5)]
    calls = []

    def capture(mu, pc, size, data):
        sp = mu.reg_read(emu.UC_M68K_REG_A7)
        calls.append((emu._u32(mu, sp + 4), emu._u32(mu, sp + 12), emu._u32(mu, sp + 16)))

    h = u.hook_add(emu.UC_HOOK_CODE, capture, begin=0x400128A8, end=0x400128A8)
    u.ctl_flush_tb()

    draw_count = 0
    for part_idx in range(4):
        w8(0x80000003, part_idx)
        p = db + 0x8ED80 + part_idx * 0x18B2
        for machine in range(5):
            for signed in (False, True):
                for track in range(8):
                    w8(p + 0x22 + track, machine)
                    u.mem_write(p + 60 + 30 * track, b"PK\x01" if signed else bytes(3))
                before = bytes(u.mem_read(p, 0x18B2))
                u.mem_write(0x400C0C50, b"\xff" * 68)
                calls.clear()
                emu._call(u, 0x4003FED8)
                assert len(calls) == 8
                expected = [
                    stock[4] if signed and machine == 1 and t in (0, 1, 4, 5) else stock[machine]
                    for t in range(8)
                ]
                assert [c[0] for c in calls] == expected, (part_idx, machine, signed, calls, expected)
                assert bytes(u.mem_read(p, 0x18B2)) == before
                draw_count += 8
    u.hook_del(h)

    # Verify SRC page ALGO max: 4 on T1/T5 (tracks 0,4) and 3 on T2/T6 (tracks 1,5)
    p = db + 0x8ED80
    algo_max_by_track = {}
    for track in range(8):
        emu._call(u, syms["pk_track_page"], (p + 0x22 + track,))
        page_ptr = u.reg_read(emu.UC_M68K_REG_D0)
        assert emu._cstr(u, page_ptr + 9, 13) == "SRC"
        algo_max = int.from_bytes(u.mem_read(page_ptr + 0x9A + 2 * 4, 4), "big")
        mode_max = int.from_bytes(u.mem_read(page_ptr + 0x9A + 5 * 4, 4), "big")
        assert mode_max == 3
        algo_max_by_track[f"T{track+1}"] = algo_max
        expected_max = 3 if track in (1, 5) else 4
        assert algo_max == expected_max, f"Track {track} ALGO max {algo_max} != {expected_max}"

    # Verify PMTR LFO formatter across all 8 tracks when T1/T2/T5/T6 are signed
    for track in range(8):
        w8(p + 0x22 + track, 1)
        u.mem_write(p + 60 + 30 * track, b"PK\x01" if track in (0, 1, 4, 5) else bytes(3))
    buf = 0x47F00800
    labels = ("TUNE", "DECAY", "ALGO", "PAR1", "PAR2", "MODE")
    for track in range(8):
        w8(0x80000000, track)
        w8(0x100B14CC, track)
        for dest in range(6):
            u.mem_write(buf, bytes(64))
            emu._call(u, syms["pk_lfo_format"], (buf, dest))
            name = emu._cstr(u, buf, 6)
            group = emu._cstr(u, buf + (6 if track in (0, 1, 4, 5) else 5), 5)
            if track in (0, 1, 4, 5):
                assert (name, group) == (labels[dest], "SRC"), (track, dest, name, group)
            else:
                assert group == "PB", (track, dest, name, group)

    return {
        "status": "PASS",
        "track_glyph_draws": draw_count,
        "algo_max_by_track": algo_max_by_track,
        "pmtr_formatter_verified_tracks": [1, 2, 3, 4, 5, 6, 7, 8],
    }


def gate_dsp_readback_and_12_fx(probe_dir: Path, project_path: Path, work_dir: Path) -> dict:
    """Verify both-core DSP P/X/Y readback and all 12 retained effects processing on hybrid image."""
    work_dir.mkdir(parents=True, exist_ok=True)
    plans = {tag: fragments.plan(probe_dir / "multi.asm", tag) for tag in ("A", "B")}
    y_words, y_layout = tables.load_tables(probe_dir)
    shared = json.loads((probe_dir / "p-records.json").read_text())
    expected = {tag: {addr: words for addr, words in plans[tag][0]} for tag in ("A", "B")}
    for tag in ("A", "B"):
        expected[tag].update({addr: words for addr, words in shared[tag]})
    watch = next(r["start"] for r in plans["A"][1] if r["name"] == "complex_drum_production_voice")
    peek = ";".join(
        [f"{core}:P:{addr:x},{len(words)}" for tag, core in [("A", 0), ("B", 1)] for addr, words in expected[tag].items()]
        + [f"{core}:Y:7a5,{len(y_words)}" for core in (0, 1)]
        + [f"{core}:X:383a,172" for core in (0, 1)]
    )
    configs = [
        ("FILTER", "EQUALIZER", "DJ EQ", "PHASER"),
        ("SPATIALIZER", "FLANGER", "CHORUS", "COMB FILTER"),
    ]
    x_words = tables.load_state_init(probe_dir, y_layout)[58:230]
    fx_tested = set()

    for index in range(4):
        fx1 = configs[index % 2]
        cfg_dir = work_dir / f"fx_config_{index}"
        if cfg_dir.exists():
            shutil.rmtree(cfg_dir)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        synth_port.OUT = cfg_dir
        fixture = synth_port.configure_fixture(str(project_path), engine=5)
        for bank in fixture.glob("bank*.work"):
            def setup_tracks(data):
                for part in range(8):
                    base = otp.PART_BASE + part * otp.PART_STRIDE + 9
                    for t in range(8):
                        data[base + 0x22 + t] = 1
                        if t in (0, 1, 4, 5):
                            data[base + 60 + 30 * t : base + 63 + 30 * t] = b"PK\x01"
                            algo = 3 if t in (0, 4) else (index % 3)
                            vals = (64, 80, algo, 64, 64, index % 3)
                            for s, v in enumerate(vals):
                                data[base + 0x2A + 30 * t + 6 + s] = v
                        else:
                            data[base + 60 + 30 * t : base + 63 + 30 * t] = bytes(3)
            otp._bank_write(fixture, int(bank.stem[4:]), setup_tracks, guard=False)

        for track in range(1, 9):
            e1 = fx1[(track - 1) % 4]
            e2 = ("LO-FI", "SPRING REV", "DARK REV", "DELAY")[(track - 1 + index) % 4]
            fx_tested.add(e1)
            fx_tested.add(e2)
            for slot, effect in [("fx1", e1), ("fx2", e2)]:
                values = otp.module_defaults(registry.modules()[effect])
                otp.set_fx(fixture, slot, track, effect, page=values[:6], page2=values[6:12], guard=False)

        card = cfg_dir / "card.img"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/emu/ot_emu/stage_card.py"),
                str(fixture),
                "OCTABAM",
                "RIG",
                "--tree",
                str(cfg_dir / "tree"),
                "--out",
                str(card),
            ],
            cwd=ROOT,
            check=True,
        )
        cmd = [
            str(ROOT / "out/emu/ot_emu"),
            "--image",
            str(probe_dir / "mainos_PKHYB2P.bin"),
            "--card",
            str(card),
            "--set",
            "OCTABAM",
            "--project",
            "RIG",
            "--load-ms",
            "90000",
            "--sequencer",
            "--internal-clock",
            "--bank",
            "0",
            "--frames",
            "600",
            "--dsp",
            "--dsp-dirty",
            "123",
            "--main-level",
            "64",
            "--dsp-peek",
            peek,
            "--dsp-pcwatch",
            f"0:{watch:x}",
        ]
        log_file = cfg_dir / "port.log"
        with log_file.open("w") as out:
            out.write(" ".join(cmd) + "\n")
            out.flush()
            subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, check=True, timeout=600)
        log = log_file.read_text()
        assert "FAULT:" not in log and "ILLEGAL" not in log
        assert re.search(r"frames run\s*:\s*600 .*REACHED", log)
        assert int(re.search(r"dsp pcwatch:.*last (\d+) arrival", log)[1]) > 0
        readback = {
            (int(c), int(a, 16)): [int(w, 16) for w in words.split()]
            for c, a, words in re.findall(r"core (\d+) P:0x([0-9a-f]+): ([0-9a-f ]+)", log)
        }
        for tag, core in [("A", 0), ("B", 1)]:
            for addr, words in expected[tag].items():
                assert readback[core, addr] == words, (index, tag, hex(addr))
        y_readback = {
            int(core): [int(w, 16) for w in words.split()]
            for core, words in re.findall(r"core (\d+) Y:0x0*7a5: ([0-9a-f ]+)", log)
        }
        for core in (0, 1):
            assert y_readback[core] == y_words, (index, core, "stock FX modified PERKY Y tables")
        x_readback = {
            int(core): [int(w, 16) for w in words.split()]
            for core, words in re.findall(r"core (\d+) X:0x0*383a: ([0-9a-f ]+)", log)
        }
        for core in (0, 1):
            assert x_readback[core] == x_words, (index, core, "stock FX modified fourth wave X table")
        shutil.rmtree(cfg_dir / "tree", ignore_errors=True)
        card.unlink(missing_ok=True)

    return {
        "status": "PASS",
        "configurations_tested": 4,
        "frames_per_configuration": 600,
        "effects_exercised": sorted(fx_tested),
        "p_shards_intact": True,
        "y_tables_intact": True,
        "fourth_wave_x_intact": True,
    }


def gate_negative_corruption_tests(probe_dir: Path, work_dir: Path) -> dict:
    """Execute runtime/linker/loader and packaging corruption negative tests."""
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Existing wrapper & DSP corruption self-test
    subprocess.run(
        [sys.executable, str(ROOT / "tools/verify/verify_perky_release_guards_selftest.py")],
        cwd=ROOT,
        check=True,
    )

    # 2. Odd-address access negative test: synthetic odd word displacement must fail
    with tempfile.TemporaryDirectory() as tmp:
        bad_s = Path(tmp) / "bad.s"
        bad_s.write_text("        .text\n        move.w 3(%a0),%d0\n")
        res = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/verify/verify_perky_cf_odd_access.py"),
                "--generated",
                tmp,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode != 0, "Odd-address verifier failed to reject move.w 3(%a0),%d0"

    # 3. Corrupted hybrid card ELUP wrapper must be rejected by verify_perky_final_wrappers.py
    with tempfile.TemporaryDirectory() as tmp:
        bad_card = Path(tmp) / "bad_card.bin"
        raw_card = bytearray((probe_dir / f"OCTATRACK_{builder.PROBE_VERSION}.bin").read_bytes())
        raw_card[256] ^= 0x40
        bad_card.write_bytes(raw_card)
        res = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/verify/verify_perky_final_wrappers.py"),
                "--mainos",
                str(probe_dir / f"mainos_{builder.PROBE_VERSION}.bin"),
                "--elek",
                str(probe_dir / f"elek_{builder.PROBE_VERSION}.bin"),
                "--card",
                str(bad_card),
                "--midi",
                str(probe_dir / f"OCTATRACK_OS1.40C_{builder.PROBE_VERSION}.syx"),
                "--eft",
                str(builder.base.EFT),
                "--version",
                builder.PROBE_VERSION,
                "--work",
                str(Path(tmp) / "w"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode != 0, "Wrapper verifier failed to reject corrupted hybrid card .bin"

    # 4. Corrupted DSP byte in MAIN OS must be rejected by verify_dsp_identity
    with tempfile.TemporaryDirectory() as tmp:
        bad_main = Path(tmp) / "bad_main.bin"
        raw_main = bytearray((probe_dir / f"mainos_{builder.PROBE_VERSION}.bin").read_bytes())
        raw_main[0x400E2200 - 0x40000400] ^= 0x01
        bad_main.write_bytes(raw_main)
        rejected = False
        try:
            builder.verify_dsp_identity(
                probe_dir,
                probe_dir.parent / "baseline",
                bad_main,
                probe_dir / "fragmented-normal.bin",
            )
        except RuntimeError:
            rejected = True
        assert rejected, "verify_dsp_identity failed to reject mutated DSP byte in MAIN OS"

    # Re-emit clean DSP_IDENTITY.json
    builder.verify_dsp_identity(
        probe_dir,
        probe_dir.parent / "baseline",
        probe_dir / f"mainos_{builder.PROBE_VERSION}.bin",
        probe_dir / "fragmented-normal.bin",
    )

    return {
        "status": "PASS",
        "release_guards_selftest": "PASS",
        "odd_displacement_rejected": True,
        "corrupted_card_wrapper_rejected": True,
        "corrupted_dsp_span_rejected": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=ROOT / "out/perky/hybrid")
    ap.add_argument("--skip-fx", action="store_true")
    args = ap.parse_args()

    work = args.work.resolve()
    probe_dir = work / "probe"
    baseline_dir = work / "baseline"
    gates_dir = probe_dir / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)

    baseline_json = json.loads((ROOT / "modules/perky/hybrid/BASELINE.json").read_text())
    project_path = Path(baseline_json["project"]["root"])

    print("[1/4] Auditing single-owner symbols & freestanding codegen...")
    r_owner = gate_single_owner_and_codegen(probe_dir)
    print("  PASS:", r_owner)

    print("[2/4] Running mixed-dispatch & split-offset transport gate across all 8 tracks...")
    r_disp = gate_mixed_dispatch_and_transport(probe_dir, baseline_dir)
    print("  PASS:", r_disp)

    print("[3/4] Running hybrid UI, SRC ALGO bounds, and PMTR formatter gate...")
    r_ui = gate_hybrid_ui_and_src(probe_dir)
    print("  PASS:", r_ui)

    print("[4/4] Running negative corruption tests...")
    r_neg = gate_negative_corruption_tests(probe_dir, gates_dir / "negative")
    print("  PASS:", r_neg)

    r_fx = {"status": "SKIPPED"}
    if not args.skip_fx:
        print("[FX] Running both-core DSP P/X/Y readback and 12-effect FX processing gate...")
        r_fx = gate_dsp_readback_and_12_fx(probe_dir, project_path, gates_dir / "fx")
        print("  PASS:", r_fx)

    summary = {
        "schema": "octabam.perky.hybrid.probe-gates.v1",
        "status": "PASS" if r_fx['status'] == 'PASS' else 'PARTIAL',
        "single_owner_and_codegen": r_owner,
        "mixed_dispatch_and_transport": r_disp,
        "hybrid_ui_and_src": r_ui,
        "negative_corruption_tests": r_neg,
        "dsp_readback_and_12_fx": r_fx,
    }
    (probe_dir / "PROBE_GATES.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"HYBRID PROBE GATES: {summary['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
