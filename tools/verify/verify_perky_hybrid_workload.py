#!/usr/bin/env python3
"""Execute the integrated PERKY DSP+ColdFire hybrid workload and timing matrix.

Measures on the actual built hybrid probe (`out/perky/hybrid/probe/mainos_PKHYB2P.bin`):
  1. Real Octatrack sequencer split-frame drift gate on CF tracks T2 and T6
     (adapted from `verify_perky_cf_seq_drift.py` for zero-based tracks 1 and 5).
  2. Delayed first trigger, Bank/Part handoff, and p-lock reversion under real
     sequencer execution.
  3. Full integrated workload matrix (each row >= 60 simulated seconds = 165,375
     frames, plus worst row for 10 simulated minutes = 1,653,750 frames):
     - Mandatory rows:
       * V1/V1 (`wt_v1` / `wt_v1`)
       * V1/V2 (`wt_v1` / `wt_v2`)
       * V2/snare (`wt_v2` / `res_snare`)
       * V1/bass (`wt_v1` / `res_bass`)
       * snare/snare (`res_snare` / `res_snare`)
       * bass/snare (`res_bass` / `res_snare`)
       * third/third (`res_nt` / `res_nt`)
     - Additional rows (V2/V2, reversed assignments, and Phase 1 heavy corners):
       * V2/V2 (`wt_v2` / `wt_v2`)
       * V2/V1 (`wt_v2` / `wt_v1`)
       * snare/V2 (`res_snare` / `wt_v2`)
       * bass/V1 (`res_bass` / `wt_v1`)
       * snare/bass (`res_snare` / `res_bass`)
       * third/snare (`res_nt` / `res_snare`)
       * snare/third (`res_snare` / `res_nt`)
       * V1M3/third (`wt_v1_m2` / `res_nt`)
  4. Instrumentation overhead comparison (`profiler_enable=1` vs `profiler_enable=0`)
     and CF armed vs disarmed comparison (`cf_arm=1` vs `cf_arm=0`) without
     changing any frozen DSP bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import wave
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
import ot_project as otp  # noqa:E402
import recloop as rl  # noqa:E402
from ab_fixture import prepare  # noqa:E402
from remix import registry  # noqa:E402

EMU = ROOT / "out/emu/ot_emu"
PY = ROOT / ".venv/bin/python3"
SR = 44100
FRAME_SAMPLES = 16
FRAME_PERIOD_US = 16e6 / 44100.0  # 362.81179138321994 us
ADVANCEMENT_MARGIN_US = 0.80 * FRAME_PERIOD_US  # 290.24943310657596 us
CF_CLOCK_HZ = 264_000_000.0
PIT_CLOCK_HZ = 132_000_000.0  # RM 29.3: PCSR.PRE divides the internal bus clock
DTIM3_HZ = 132_000_000.0
RECORDER_BASE = 128
SAMPLE_REL = "AUDIO/HYB_SAMPLER_440.wav"
SAMPLE_FRAMES = SR * 4

# Voice specification map for T2 (CF inst 0) and T6 (CF inst 1):
# (algo, mode, base_tune, base_decay, base_par1, base_par2)
CF_SPEC = {
    "V1": (0, 0, 64, 108, 64, 64),
    "V2": (1, 0, 64, 108, 64, 64),
    "snare": (2, 0, 64, 112, 72, 56),
    "bass": (2, 1, 56, 112, 68, 60),
    "third": (2, 2, 64, 112, 80, 48),
    "V1M3": (0, 2, 64, 112, 96, 32),
}

MANDATORY_ROWS = (
    ("V1/V1", "V1", "V1"),
    ("V1/V2", "V1", "V2"),
    ("V2/snare", "V2", "snare"),
    ("V1/bass", "V1", "bass"),
    ("snare/snare", "snare", "snare"),
    ("bass/snare", "bass", "snare"),
    ("third/third", "third", "third"),
)

EXTRA_ROWS = (
    ("V2/V2", "V2", "V2"),
    ("V2/V1", "V2", "V1"),
    ("snare/V2", "snare", "V2"),
    ("bass/V1", "bass", "V1"),
    ("snare/bass", "snare", "bass"),
    ("third/snare", "third", "snare"),
    ("snare/third", "snare", "third"),
    ("V1M3/third", "V1M3", "third"),
)


def load_elf_symbols(elf_path: Path) -> dict[str, int]:
    out = subprocess.check_output(["m68k-elf-nm", "-n", str(elf_path)], text=True)
    syms: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            addr, _kind, name = parts
            syms[name] = int(addr, 16)
    return syms


def make_tone(path: Path) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = bytearray()
        for n in range(SAMPLE_FRAMES):
            v1 = int(round(10000.0 * math.sin(2.0 * math.pi * 440.0 * n / SR)))
            v2 = int(round(10000.0 * math.sin(2.0 * math.pi * 660.0 * n / SR)))
            frames += struct.pack("<hh", v1, v2)
        w.writeframes(frames)


def install_sample_block(project: Path) -> None:
    crlf = "\r\n"
    block = (
        f"[SAMPLE]{crlf}"
        f"TYPE=FLEX{crlf}"
        f"SLOT=001{crlf}"
        f"PATH=../{SAMPLE_REL}{crlf}"
        f"TRIM_BARSx100=100{crlf}"
        f"LOOP_BARSx100=100{crlf}"
        f"BPMx24=2880{crlf}"
        f"TSMODE=0{crlf}"
        f"LOOPMODE=0{crlf}"
        f"GAIN=48{crlf}"
        f"TRIGQUANTIZATION=-1{crlf}"
        f"[/SAMPLE]{crlf}{crlf}"
    ).encode()
    for suffix in ("work", "strd"):
        path = project / f"project.{suffix}"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        pat = re.compile(
            b"\\[SAMPLE\\]\\r?\\nTYPE=FLEX\\r?\\nSLOT=001\\r?\\n.*?\\[/SAMPLE\\]\\r?\\n\\r?\\n",
            re.S,
        )
        raw = pat.sub(b"", raw)
        at = raw.find(b"[SAMPLE]")
        if at < 0:
            at = raw.find(b"[STATES]")
        path.write_bytes(raw[:at] + block + raw[at:])

    for suffix in ("work", "strd"):
        path = project / f"markers.{suffix}"
        if not path.is_file():
            continue
        data = bytearray(path.read_bytes())
        at = 0x16
        data[at : at + 784] = (
            struct.pack(">III", 0, SAMPLE_FRAMES, 0) + bytes(768) + bytes(4)
        )
        data[-2:] = (sum(data[0x10:-2]) & 0xFFFF).to_bytes(2, "big")
        path.write_bytes(bytes(data))


from hybrid_profile import decode_profiler_dump


def parse_ot_emu_log(log_text: str) -> dict:
    """Parse ColdFire full-frame cycle histogram, budget, and separate DSP core reports from `ot_emu`."""
    hist_m = re.search(
        r"cf frames\s*:\s*(\d+) frames sampled; mean (\d+) us\s+p50 (\d+)\s+p90 (\d+)\s+p99 (\d+)\s+p99\.9 (\d+)\s+MAX (\d+) us",
        log_text,
    )
    worst_m = re.search(
        r"worst frame #(\d+) \((\d+) cycles = (\d+) us\); frame period ([\d.]+) us",
        log_text,
    )
    steady_m = re.search(r"worst after frame 50: #(\d+) (\d+) us", log_text)
    over_m = re.search(r"frames over the [\d.]+ us period: (\d+)", log_text)
    budget_m = re.search(
        r"cf budget\s*:\s*(\d+) ColdFire cycles over the frames \((\d+) per frame of 16 samples = ([\d.]+) us at 264 MHz\)",
        log_text,
    )
    host_m = re.search(
        r"host port: (\d+) blocks / (\d+) words to the DSPs \((\d+) NON-ZERO\), (\d+) blocks / (\d+) words back \((\d+) NON-ZERO, (\d+) not in time\); (\d+) ticks a burst waited for the DSP to drain",
        log_text,
    )
    core_matches = re.findall(
        r"core (\d+): (\d+) frame commands \(vector 0x0c\), (\d+) DSP instructions \(([\d.]+)k/frame\), (\d+) tx words, (\d+) rx words",
        log_text,
    )
    cores = {}
    for c_id, cmds, instrs, k_per_f, tx_w, rx_w in core_matches:
        cmds_i = int(cmds)
        instrs_i = int(instrs)
        # Instructions are not elapsed DSP cycles; no busy-time conversion.
        mean_instr_per_frame = instrs_i / max(1, cmds_i)
        cores[f"core_{c_id}"] = {
            "frame_commands": cmds_i,
            "dsp_instructions": instrs_i,
            "mean_instructions_per_frame": round(mean_instr_per_frame, 1),
            "tx_words": int(tx_w),
            "rx_words": int(rx_w),
        }

    worst_cycles = int(worst_m.group(2)) if worst_m else 0
    worst_us_exact = worst_cycles * 1e6 / CF_CLOCK_HZ

    return {
        "cf_ack_interval": {
            "frames_sampled": int(hist_m.group(1)) if hist_m else 0,
            "mean_us": float(budget_m.group(3)) if budget_m else (float(hist_m.group(2)) if hist_m else 0.0),
            "p50_us": float(hist_m.group(3)) if hist_m else 0.0,
            "p90_us": float(hist_m.group(4)) if hist_m else 0.0,
            "p99_us": float(hist_m.group(5)) if hist_m else 0.0,
            "p99_9_us": float(hist_m.group(6)) if hist_m else 0.0,
            "max_us_rounded": float(hist_m.group(7)) if hist_m else 0.0,
            "max_cycles": worst_cycles,
            "max_us_exact": round(worst_us_exact, 3),
            "worst_frame_index": int(worst_m.group(1)) if worst_m else 0,
            "worst_after_frame_50_index": int(steady_m.group(1)) if steady_m else 0,
            "worst_after_frame_50_us": float(steady_m.group(2)) if steady_m else 0.0,
            "frames_over_362_8us_period": int(over_m.group(1)) if over_m else 0,
            "total_cf_cycles": int(budget_m.group(1)) if budget_m else 0,
            "mean_cf_cycles_per_frame": int(budget_m.group(2)) if budget_m else 0,
            "scope": "ACK-to-ACK CPU work including intervening tasks; not ISR latency",
            "headroom_to_362_81us_period_us": round(FRAME_PERIOD_US - worst_us_exact, 3),
            "headroom_to_290_25us_gate_us": round(ADVANCEMENT_MARGIN_US - worst_us_exact, 3),
        },
        "dsp_exchange_and_cores": {
            "blocks_to_dsps": int(host_m.group(1)) if host_m else 0,
            "words_to_dsps": int(host_m.group(2)) if host_m else 0,
            "nonzero_words_to_dsps": int(host_m.group(3)) if host_m else 0,
            "blocks_from_dsps": int(host_m.group(4)) if host_m else 0,
            "words_from_dsps": int(host_m.group(5)) if host_m else 0,
            "nonzero_words_from_dsps": int(host_m.group(6)) if host_m else 0,
            "words_not_in_time": int(host_m.group(7)) if host_m else 0,
            "cf_dsp_drain_wait_ticks": int(host_m.group(8)) if host_m else 0,
            "cores": cores,
        },
    }


def stage_integrated_fixture(
    project_src: Path,
    work_dir: Path,
    t2_key: str,
    t6_key: str,
    *,
    tone_path: Path,
    allow_family_transitions: bool = True,
    first_trig_delay: int = 0,
) -> Path:
    """Configure an 8-track integrated workload project:
    - T1 (track 0, DSP core B) and T5 (track 4, DSP core A): PERKY DSP synths
      (Complex/Fold1/Fold2/Simple) with dense steps, p-locks, LFOs, scenes.
    - T2 (track 1, CF inst 0) and T6 (track 5, CF inst 1): PERKY CF synths
      configured to `t2_key` and `t6_key`, with dense retriggers, six-control
      p-locks, long decay/sustain stress, LFOs, scenes, and optional family/mode
      transitions.
    - T3/T4/T7/T8 (tracks 2,3,6,7): stock FLEX sampler tracks playing the
      staged stereo 440/660 Hz sample with dense trigs.
    - Busy retained FX across all 8 tracks, including DARK REV on both DSP cores
      (T1 on Core B and T5 on Core A).
    """
    fixture = prepare(project_src, work_dir / "project")
    make_tone(tone_path)
    install_sample_block(fixture)

    t2_algo, t2_mode, t2_tune, t2_decay, t2_p1, t2_p2 = CF_SPEC[t2_key]
    t6_algo, t6_mode, t6_tune, t6_decay, t6_p1, t6_p2 = CF_SPEC[t6_key]

    fx1_assign = (
        "FILTER",
        "SPATIALIZER",
        "EQUALIZER",
        "DJ EQ",
        "PHASER",
        "FLANGER",
        "CHORUS",
        "COMB FILTER",
    )
    # Dark Reverb on both cores: T1 (Core B) and T5 (Core A)
    fx2_assign = (
        "DARK REV",    # T1 (Core B)
        "SPRING REV",  # T2 (Core B)
        "DELAY",       # T3 (Core B)
        "LO-FI",       # T4 (Core B)
        "DARK REV",    # T5 (Core A)
        "SPRING REV",  # T6 (Core A)
        "DELAY",       # T7 (Core A)
        "LO-FI",       # T8 (Core A)
    )

    steps = tuple(s for s in range(0, 64, 2) if s >= first_trig_delay) + tuple(
        s for s in (1, 5, 7, 11, 13, 19, 23, 29, 35, 41, 47, 53, 59) if s >= first_trig_delay
    )
    steps = tuple(sorted(set(steps)))

    for bank in fixture.glob("bank*.work"):
        def mutate(data: bytearray) -> None:
            for part in range(otp.NPARTS_ALL):
                file_base = otp.PART_BASE + part * otp.PART_STRIDE
                live_base = file_base + 9
                for track in range(8):
                    data[live_base + 0x22 + track] = 1  # underlying FLEX
                    if track in (0, 1, 4, 5):
                        data[file_base + otp.SLOT_OFF + track * 5 + otp.SLOT_KIND["flex"]] = (
                            RECORDER_BASE + track
                        )
                        data[live_base + 60 + 30 * track : live_base + 63 + 30 * track] = b"PK\x01"
                    else:
                        # Stock sampler tracks T3/T4/T7/T8 use FLEX slot 1
                        data[file_base + otp.SLOT_OFF + track * 5 + otp.SLOT_KIND["flex"]] = 0
                        data[live_base + 60 + 30 * track : live_base + 63 + 30 * track] = bytes(3)

                    if track in (0, 1, 4, 5):
                        if track == 0:
                            vals = (64, 108, 3, 72, 56, 0)  # T1 DSP Complex Drum
                        elif track == 4:
                            vals = (52, 108, 0, 84, 48, 1)  # T5 DSP Fold1 Drum
                        elif track == 1:
                            vals = (t2_tune, t2_decay, t2_algo, t2_p1, t2_p2, t2_mode)
                        else:
                            vals = (t6_tune, t6_decay, t6_algo, t6_p1, t6_p2, t6_mode)
                        for s_idx, v in enumerate(vals):
                            data[live_base + 0x2A + 30 * track + 6 + s_idx] = v

                    # Configure active LFO speeds/depths at the LFO page (`live_base + 0x11A + 24*track`)
                    # while preserving stock AMP (`page + 6 .. page + 12`: ATK=0, HOLD=127, REL=127, VOL=64, BAL=64).
                    page = live_base + 0x11A + 24 * track
                    data[page : page + 3] = bytes((32, 48, 24))   # LFO1/2/3 speeds
                    data[page + 3 : page + 6] = bytes((16, 12, 8))  # LFO1/2/3 depths

            for pattern in range(4):
                for track in range(8):
                    at = otp.trac_off(pattern, track)
                    data[at : at + 64] = bytes(64)
                    data[at + 0x59 : at + 0x59 + 64 * 32] = bytes([255]) * (64 * 32)
                    data[at + 0x899 : at + 0x919] = bytes(128)
                    data[at + 0x50 : at + 0x52] = bytes((64, 2))
                    for step in steps:
                        data[at + 7 - step // 8] |= 1 << (step % 8)
                        if track in (0, 4):
                            # Six-control p-locks + engine transitions on T1/T5 DSP
                            if step % 3 == 1:
                                dsp_algo = (step // 4 + (0 if track == 0 else 2)) % 4
                                dsp_mode = step % 3
                                locks = (
                                    24 + (step * 5) % 80,
                                    80 + (step * 3) % 47,
                                    dsp_algo,
                                    (step * 11) % 128,
                                    (step * 17) % 128,
                                    dsp_mode,
                                )
                                for s_idx, v in enumerate(locks):
                                    data[at + 0x59 + step * 32 + s_idx] = v
                        elif track in (1, 5):
                            base_a = t2_algo if track == 1 else t6_algo
                            base_m = t2_mode if track == 1 else t6_mode
                            # Exercise six-control p-locks, long decay/sustain, and mode/family locks.
                            # Keep each combination row on its designated (t2_algo, t6_algo) pair unless
                            # allow_family_transitions is explicitly enabled for transition testing.
                            if step % 4 == 2:
                                lock_a = ((base_a + 1) % 3) if (allow_family_transitions and step == 58) else base_a
                                lock_m = ((base_m + 1) % 3) if (allow_family_transitions and step == 46) else base_m
                                locks = (
                                    32 + (step * 7) % 64,
                                    96 + (step % 32),  # long decay/sustain stress (96..127)
                                    lock_a,
                                    (step * 13) % 128,
                                    (step * 19) % 128,
                                    lock_m,
                                )
                                for s_idx, v in enumerate(locks):
                                    data[at + 0x59 + step * 32 + s_idx] = v

        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)

    for track in range(1, 9):
        for slot, effect in [("fx1", fx1_assign[track - 1]), ("fx2", fx2_assign[track - 1])]:
            values = otp.module_defaults(registry.modules()[effect])
            otp.set_fx(fixture, slot, track, effect, page=values[:6], page2=values[6:12], guard=False)

    otp.set_tempo(fixture, 120)
    otp.set_pattern_scale(fixture, 1, 0, 64, "1X", guard=False)

    card = work_dir / "card.img"
    subprocess.run(
        [
            str(PY),
            str(ROOT / "tools/emu/ot_emu/stage_card.py"),
            str(fixture),
            "OCTABAM",
            "RIG",
            "--tree",
            str(work_dir / "tree"),
            "--out",
            str(card),
            "--audio",
            f"{tone_path}:{SAMPLE_REL}",
        ],
        cwd=ROOT,
        check=True,
    )
    shutil.rmtree(work_dir / "tree", ignore_errors=True)
    shutil.rmtree(fixture, ignore_errors=True)
    return card


def run_integrated_row(
    name: str,
    t2_key: str,
    t6_key: str,
    *,
    image_path: Path,
    syms: dict[str, int],
    project_src: Path,
    work_dir: Path,
    tone_path: Path,
    frames: int,
    verify_block_audio: bool = False,
    profiler_enable: int = 1,
    cf_arm: int = 1,
    allow_family_transitions: bool = False,
    first_trig_delay: int = 0,
    extra_steps: list[str] | None = None,
    cycle_clock: float = 1.0,
    card_out: Path | None = None,
    watch_pcs: list[int] | None = None,
) -> dict:
    """Run one integrated workload row in `ot_emu` and return bounded timing & audio stats."""
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    card = stage_integrated_fixture(
        project_src,
        work_dir,
        t2_key,
        t6_key,
        tone_path=tone_path,
        allow_family_transitions=allow_family_transitions,
        first_trig_delay=first_trig_delay,
    )

    prof_addr = syms["pk_hybrid_prof"]
    sizes = subprocess.check_output(['m68k-elf-nm', '-S', str(image_path.parent / 'platform/runtime.elf')], text=True)
    prof_size = next(int(line.split()[1], 16) for line in sizes.splitlines()
                     if len(line.split()) == 4 and line.split()[-1] == 'pk_hybrid_prof')
    prof_dump = work_dir / "prof.bin"
    log_path = work_dir / "port.log"

    # --poke-before-play accepts one byte per address (C integer syntax),
    # unlike --step poke's hex byte strings. Write all four big-endian bytes
    # and verify the effective switches below; a high-byte zero cannot turn
    # off a loaded uint32_t whose low byte is still one.
    pokes = [f"{syms[name] + i:#x}={value:#x}"
             for name, flag in (("pk_hybrid_profiler_enable", profiler_enable),
                                ("pk_hybrid_cf_arm", cf_arm))
             for i, value in enumerate(flag.to_bytes(4, 'big'))]

    cmd = [
        str(EMU),
        "--image",
        str(image_path),
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
        str(frames),
        "--dsp",
        "--dsp-dirty",
        "123",
        "--main-level",
        "64",
        "--cf-frame-hist",
        "--cf-frame-budget-us",
        "362.8",
        "--pit-clock-hz",
        str(int(PIT_CLOCK_HZ)),
        "--poke-before-play",
        ";".join(pokes),
        "--mem-dump",
        f"{prof_addr:#x},{prof_size}={prof_dump}",
    ]
    if watch_pcs:
        cmd.extend(['--watch-pc', ','.join(hex(a) for a in watch_pcs)])
    if cycle_clock > 0:
        cmd.extend(['--cf-cycles-clock', str(cycle_clock)])
    if card_out is not None:
        cmd.extend(['--card-out', str(card_out)])
    if extra_steps:
        for st in extra_steps:
            cmd.extend(["--step", st])

    with log_path.open("w") as f:
        f.write(" ".join(cmd) + "\n")
        f.flush()
        subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=1800)

    log_text = log_path.read_text(errors="replace")
    assert "FAULT:" not in log_text and "ILLEGAL" not in log_text, f"Fault in {name}: see {log_path}"
    assert f"PIT clock  : {int(PIT_CLOCK_HZ)} Hz" in log_text, 'PIT clock option not applied'
    assert "step       : unknown kind" not in log_text, f"Unexecuted workload action in {name}: see {log_path}"
    assert re.search(rf"frames run\s*:\s*{frames}\s+since transport start.*REACHED", log_text), (
        f"Did not reach {frames} frames in {name}: see {log_path}"
    )

    emu_metrics = parse_ot_emu_log(log_text)
    prof_metrics = decode_profiler_dump(prof_dump.read_bytes())
    if profiler_enable:
        assert prof_metrics['profiler_enabled'] is True
        assert prof_metrics['cf_armed'] == bool(cf_arm)
        if not cf_arm:
            assert prof_metrics['dtim3_ticks']['inst_calls'] == [0, 0]
    else:
        assert prof_metrics['frame_count'] == 0, 'profiler-disable poke did not take effect'

    # Optional short block-dump verification on the same card to confirm all 8 tracks
    # (T1/T5 DSP, T2/T6 CF, T3/T4/T7/T8 stock sampler) emit active audio & post-FX2 chain output
    audio_verification = None
    if verify_block_audio:
        b_dump = work_dir / "blocks.bin"
        b_log = work_dir / "blocks.log"
        b_cmd = [
            str(EMU),
            "--image",
            str(image_path),
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
            "2400",
            "--dsp",
            "--dsp-dirty",
            "123",
            "--main-level",
            "64",
            "--block-dump",
            str(b_dump),
        ]
        with b_log.open("w") as f:
            subprocess.run(b_cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=600)
        classes = bd.classes(bd.read(b_dump))
        track_stats = {}
        for tr in range(1, 9):
            rb = rl.readback_audio(classes, tr)
            sig = [v for v in rb if abs(v) > 64]
            assert len(sig) > 64, f"Row {name} track T{tr} post-FX2 chain output is silent!"
            rec_info = {"chain_samples": len(rb), "chain_significant": len(sig), "chain_peak": max(map(abs, rb))}
            if tr in (2, 3, 4, 6, 7, 8):
                src_a = rl.track_audio(classes, tr)
                src_sig = [v for v in src_a if abs(v) > 64]
                assert len(src_sig) > 64, f"Row {name} track T{tr} source record is silent!"
                rec_info["source_significant"] = len(src_sig)
                rec_info["source_peak"] = max(map(abs, src_a))
            track_stats[f"T{tr}"] = rec_info
        b_dump.unlink(missing_ok=True)
        audio_verification = track_stats

    card.unlink(missing_ok=True)

    return {
        "row": name,
        "t2": t2_key,
        "t6": t6_key,
        "frames": frames,
        "simulated_seconds": round(frames * 16.0 / SR, 2),
        "cycle_clock_factor": cycle_clock,
        "coldfire_clock_hz": CF_CLOCK_HZ,
        "pit_clock_hz": PIT_CLOCK_HZ,
        "profiler_enabled": bool(profiler_enable),
        "cf_armed": bool(cf_arm),
        "ot_emu": emu_metrics,
        "dtim3_profiler": prof_metrics,
        "audio_verification": audio_verification,
    }


def run_seq_drift_gate_hybrid(image_path: Path, project_src: Path, work_dir: Path) -> dict:
    """Verify hit-over-hit level flatness and pre-event preservation across split frames on T2 and T6."""
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    fixture = prepare(project_src, work_dir / "project")
    steps = (1, 7, 11)
    bars = 2
    for bank in fixture.glob("bank*.work"):
        def mutate(data: bytearray) -> None:
            for part in range(otp.NPARTS_ALL):
                file_base = otp.PART_BASE + part * otp.PART_STRIDE
                live_base = file_base + 9
                for t in range(8):
                    data[live_base + 0x22 + t] = 1
                    data[live_base + 60 + 30 * t : live_base + 63 + 30 * t] = bytes(3)
                for t, algo in ((1, 0), (5, 2)):  # T2 = WT V1, T6 = Resonant Snare
                    data[file_base + otp.SLOT_OFF + t * 5 + otp.SLOT_KIND["flex"]] = RECORDER_BASE + t
                    data[live_base + 60 + 30 * t : live_base + 63 + 30 * t] = b"PK\x01"
                    values = (64, 64, algo, 64, 64, 0)
                    for slot, value in enumerate(values):
                        data[live_base + 0x2A + 30 * t + 6 + slot] = value
            for t in (1, 5):
                at = otp.trac_off(0, t)
                data[at : at + 64] = bytes(64)
                data[at + 0x59 : at + 0x59 + 64 * 32] = bytes([255]) * (64 * 32)
                data[at + 0x899 : at + 0x919] = bytes(128)
                data[at + 0x50 : at + 0x52] = bytes((16, 2))
                for step in steps:
                    data[at + 7 - (step - 1) // 8] |= 1 << ((step - 1) % 8)
        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    otp.set_tempo(fixture, 120)
    otp.set_pattern_scale(fixture, 1, 0, 16, "1X", guard=False)

    card = work_dir / "card.img"
    subprocess.run(
        [
            str(PY),
            str(ROOT / "tools/emu/ot_emu/stage_card.py"),
            str(fixture),
            "OCTABAM",
            "RIG",
            "--tree",
            str(work_dir / "tree"),
            "--out",
            str(card),
        ],
        cwd=ROOT,
        check=True,
    )
    shutil.rmtree(work_dir / "tree", ignore_errors=True)
    shutil.rmtree(fixture, ignore_errors=True)

    frames = int(bars * 4 * SR / 16) + 400
    dump = work_dir / "blocks.bin"
    log = work_dir / "port.log"
    cmd = [
        str(EMU),
        "--image",
        str(image_path),
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
        str(frames),
        "--dsp",
        "--main-level",
        "64",
        "--block-dump",
        str(dump),
    ]
    with log.open("w") as f:
        subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=600)

    classes = bd.classes(bd.read(dump))
    results = {}
    for tr_zero, core, base_a, ping_a in (
        (1, 1, 0x80001C90, 0x80002710),
        (5, 0, 0x800021D0, 0x80002C50),
    ):
        pos = tr_zero % 4
        chain = [int(v) for v in rl.readback_audio(classes, tr_zero + 1)]
        groups = sorted(classes.get((">", 0, core, base_a), []) + classes.get((">", 0, core, ping_a), []))
        track_words = [rl.words(w)[pos * 84 : (pos + 1) * 84] for _, w in groups]
        splits = [tw[0] for tw in track_words]
        assert max(splits) > 0, f"Track {tr_zero+1} never split a frame"
        rec_pre = []
        for split, tw in zip(splits, track_words):
            if split <= 0:
                continue
            decoded = [int(v) for v in rl.record_audio(tw)]
            if len(decoded) == 16 and any(decoded):
                rec_pre.extend(decoded[:split])
        rec_blank = sum(1 for v in rec_pre if v == 0) / max(1, len(rec_pre))
        assert rec_blank <= 0.25, f"Track {tr_zero+1} pre-half blank ratio {rec_blank:.3f} > 0.25"

        step_s = 0.125 * SR
        bar_s = 16 * step_s
        hits = [b * bar_s + s * step_s for b in range(bars) for s in (0, 6, 10)]
        window = int(0.45 * SR)
        sub = int(0.005 * SR)
        levels = []
        for start in hits:
            a = int(start)
            seg = chain[a : a + window]
            best = 0.0
            for i in range(0, len(seg) - sub, sub):
                rms = (sum(v * v for v in seg[i : i + sub]) / sub) ** 0.5
                if rms > best:
                    best = rms
            levels.append(best)
        ratio = min(levels) / max(levels)
        assert ratio >= 0.90, f"Track {tr_zero+1} hit level ratio {ratio:.3f} < 0.90"
        results[f"T{tr_zero+1}"] = {
            "split_frames": sum(1 for s in splits if s > 0),
            "total_frames": len(splits),
            "max_split": max(splits),
            "pre_half_blank_ratio": round(rec_blank, 4),
            "hit_level_min_max_ratio": round(ratio, 4),
            "hit_levels": [round(x, 1) for x in levels],
        }

    card.unlink(missing_ok=True)
    dump.unlink(missing_ok=True)
    return {"status": "PASS", "tracks": results}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=ROOT / "out/perky/hybrid")
    ap.add_argument("--row-frames", type=int, default=165376, help="Frames per row (default 165,376 = 60.00 s)")
    ap.add_argument("--worst-frames", type=int, default=1653750, help="Frames for worst row (default 1,653,750 = 600.00 s)")
    ap.add_argument("--smoke", action="store_true", help="Run a short smoke test first")
    ap.add_argument('--jobs', type=int, default=1, help='Independent matrix processes; frame counts and gates are unchanged')
    args = ap.parse_args()

    work = args.work.resolve()
    probe_dir = work / "probe"
    image_path = probe_dir / "mainos_PKHYB2P.bin"
    elf_path = probe_dir / "platform/runtime.elf"
    syms = load_elf_symbols(elf_path)
    baseline_json = json.loads((ROOT / "modules/perky/hybrid/BASELINE.json").read_text())
    project_src = Path(baseline_json["project"]["root"])

    workload_dir = probe_dir / "workload"
    workload_dir.mkdir(parents=True, exist_ok=True)
    tone_path = workload_dir / "HYB_SAMPLER_440.wav"
    make_tone(tone_path)

    if args.smoke:
        print("[SMOKE] Running sequencer split-frame drift gate on T2/T6...")
        drift = run_seq_drift_gate_hybrid(image_path, project_src, workload_dir / "seq-drift")
        print("  PASS:", drift)
        print("[SMOKE] Running 1000-frame integrated row snare/snare with block-dump audio verification...")
        r = run_integrated_row(
            "smoke_snare_snare",
            "snare",
            "snare",
            image_path=image_path,
            syms=syms,
            project_src=project_src,
            work_dir=workload_dir / "smoke",
            tone_path=tone_path,
            frames=1000,
            verify_block_audio=True,
        )
        print("  PASS smoke row:", json.dumps(r["ot_emu"]["cf_ack_interval"], indent=2))
        print("  DTIM3 profiler:", json.dumps(r["dtim3_profiler"]["dtim3_us"], indent=2))
        return 0

    print("[1/5] Running sequencer split-frame drift gate on T2 and T6...")
    drift_res = run_seq_drift_gate_hybrid(image_path, project_src, workload_dir / "seq-drift")
    print("  PASS:", drift_res)

    # Each row has its own generated card, logs and profiler dump. Parallelize
    # only these independent processes; comparisons and worst-row selection
    # still consume every completed result in the original order.
    assert args.jobs >= 1
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=args.jobs)
    matrix = {}
    for group, rows in (('mandatory', MANDATORY_ROWS), ('extra', EXTRA_ROWS)):
        for index, (label, left, right) in enumerate(rows):
            matrix[label] = pool.submit(run_integrated_row, label, left, right,
                image_path=image_path, syms=syms, project_src=project_src,
                work_dir=workload_dir / (group+'_'+label.replace('/', '_')),
                tone_path=tone_path, frames=args.row_frames,
                verify_block_audio=(group == 'mandatory' or index == 0))

    mandatory_results = []
    for idx, (label, t2_k, t6_k) in enumerate(MANDATORY_ROWS, 1):
        slug = label.replace("/", "_")
        print(f"[2/5] Mandatory row {idx}/{len(MANDATORY_ROWS)}: {label} ({args.row_frames} frames = {args.row_frames*16/SR:.1f} s)...")
        res = matrix[label].result()
        mandatory_results.append(res)
        cf_isr = res["ot_emu"]["cf_ack_interval"]
        prof_us = res["dtim3_profiler"]["dtim3_us"]
        print(
            f"  -> {label}: CF ACK interval mean={cf_isr['mean_us']:.1f} us, p99={cf_isr['p99_us']:.0f} us, "
            f"MAX={cf_isr['max_us_exact']:.2f} us (over_362.8={cf_isr['frames_over_362_8us_period']}); "
            f"PERKY DTIM3 max={prof_us['max_perky_service_us']:.2f} us (mean={prof_us['mean_perky_service_us']:.2f} us)"
        )

    extra_results = []
    for idx, (label, t2_k, t6_k) in enumerate(EXTRA_ROWS, 1):
        slug = label.replace("/", "_")
        print(f"[3/5] Extra row {idx}/{len(EXTRA_ROWS)}: {label} ({args.row_frames} frames = {args.row_frames*16/SR:.1f} s)...")
        res = matrix[label].result()
        extra_results.append(res)
        cf_isr = res["ot_emu"]["cf_ack_interval"]
        prof_us = res["dtim3_profiler"]["dtim3_us"]
        print(
            f"  -> {label}: CF ACK interval mean={cf_isr['mean_us']:.1f} us, p99={cf_isr['p99_us']:.0f} us, "
            f"MAX={cf_isr['max_us_exact']:.2f} us; PERKY DTIM3 max={prof_us['max_perky_service_us']:.2f} us"
        )

    pool.shutdown()
    # Full ISR timer, not ACK interval, determines the worst service window.
    all_rows = mandatory_results + extra_results
    worst_row = max(
        all_rows,
        key=lambda r: (
            r["dtim3_profiler"]["dtim3_ticks"]["max_perky_service_ticks"],
        ),
    )
    w_label = worst_row["row"]
    w_t2 = worst_row["t2"]
    w_t6 = worst_row["t6"]

    print(
        f"[4/5] Running profiler-on/off and CF armed/disarmed comparisons on worst row {w_label} (27,563 frames = 10.0 s)..."
    )
    comp_frames = 27563
    comp_prof_on = run_integrated_row(
        f"{w_label}_prof_on_armed",
        w_t2,
        w_t6,
        image_path=image_path,
        syms=syms,
        project_src=project_src,
        work_dir=workload_dir / "comp_prof_on",
        tone_path=tone_path,
        frames=comp_frames,
        profiler_enable=1,
        cf_arm=1,
    )
    comp_prof_off = run_integrated_row(
        f"{w_label}_prof_off_armed",
        w_t2,
        w_t6,
        image_path=image_path,
        syms=syms,
        project_src=project_src,
        work_dir=workload_dir / "comp_prof_off",
        tone_path=tone_path,
        frames=comp_frames,
        profiler_enable=0,
        cf_arm=1,
    )
    comp_cf_disarmed = run_integrated_row(
        f"{w_label}_prof_on_disarmed",
        w_t2,
        w_t6,
        image_path=image_path,
        syms=syms,
        project_src=project_src,
        work_dir=workload_dir / "comp_cf_disarmed",
        tone_path=tone_path,
        frames=comp_frames,
        profiler_enable=1,
        cf_arm=0,
    )

    overhead_mean_cycles = (
        comp_prof_on["ot_emu"]["cf_ack_interval"]["mean_cf_cycles_per_frame"]
        - comp_prof_off["ot_emu"]["cf_ack_interval"]["mean_cf_cycles_per_frame"]
    )
    overhead_max_cycles = (
        comp_prof_on["ot_emu"]["cf_ack_interval"]["max_cycles"]
        - comp_prof_off["ot_emu"]["cf_ack_interval"]["max_cycles"]
    )
    cf_synthesis_mean_cycles = (
        comp_prof_on["ot_emu"]["cf_ack_interval"]["mean_cf_cycles_per_frame"]
        - comp_cf_disarmed["ot_emu"]["cf_ack_interval"]["mean_cf_cycles_per_frame"]
    )

    # Exercise live Part change + delayed first trigger + family/mode transitions
    part_step_spec = [
        "1000:poke:0x100b14cf=01;0x80000003=01",
        "2000:poke:0x100b14cf=00;0x80000003=00",
    ]
    part_handoff_run = run_integrated_row(
        f"{w_label}_live_part_handoff_delayed_trig_transitions",
        w_t2,
        w_t6,
        image_path=image_path,
        syms=syms,
        project_src=project_src,
        work_dir=workload_dir / "live_part_handoff",
        tone_path=tone_path,
        frames=4000,
        profiler_enable=1,
        cf_arm=1,
        allow_family_transitions=True,
        first_trig_delay=4,
        extra_steps=part_step_spec,
    )
    assert part_handoff_run["dtim3_profiler"]["handoff_generation"] >= 3, (
        f"Expected handoff_generation >= 3 across live Part switch, got {part_handoff_run['dtim3_profiler']['handoff_generation']}"
    )

    print(
        f"[5/5] Running 10-minute worst-case stress run on {w_label} ({args.worst_frames} frames = {args.worst_frames*16/SR:.1f} s)..."
    )
    ten_min_run = run_integrated_row(
        f"{w_label}_10min_stress",
        w_t2,
        w_t6,
        image_path=image_path,
        syms=syms,
        project_src=project_src,
        work_dir=workload_dir / "ten_min_worst",
        tone_path=tone_path,
        frames=args.worst_frames,
        verify_block_audio=False,
    )
    cf_10m = ten_min_run["ot_emu"]["cf_ack_interval"]
    prof_10m = ten_min_run["dtim3_profiler"]["dtim3_us"]
    print(
        f"  -> 10-min {w_label}: CF ACK interval mean={cf_10m['mean_us']:.1f} us, p99={cf_10m['p99_us']:.0f} us, "
        f"MAX={cf_10m['max_us_exact']:.2f} us (over_362.8={cf_10m['frames_over_362_8us_period']}); "
        f"PERKY DTIM3 max={prof_10m['max_perky_service_us']:.2f} us"
    )

    all_evaluated = all_rows + [ten_min_run, part_handoff_run]
    global_max_cycles = max(r["ot_emu"]["cf_ack_interval"]["max_cycles"] for r in all_evaluated)
    global_max_us = max(r["dtim3_profiler"]["dtim3_us"]["max_full_frame_us"] for r in all_evaluated)
    global_overruns = sum(
        r["dtim3_profiler"]["deadline_misses_100pct"] for r in all_evaluated
    )
    global_perky_max_us = max(
        r["dtim3_profiler"]["dtim3_us"]["max_perky_service_us"] for r in all_evaluated
    )

    timing_report = {
        "schema": "octabam.perky.hybrid.timing.v1",
        "status": "LOCAL_MODEL_WITHIN_BUDGET_HARDWARE_PENDING"
        if (global_overruns == 0 and global_max_us <= ADVANCEMENT_MARGIN_US)
        else "LOCAL_MODEL_OVER_MARGIN_REVIEW_REQUIRED",
        "hardware_feasibility": "UNVERIFIED",
        "clocks": {
            "coldfire_core_hz": int(CF_CLOCK_HZ),
            "pit_clock_hz": int(PIT_CLOCK_HZ),
            "dtim3_bus_hz": int(DTIM3_HZ),
            "dsp56303_core_hz": None,  # no clock/cycle completion calibration in this report
            "audio_sample_rate_hz": SR,
            "samples_per_frame": FRAME_SAMPLES,
            "frame_period_us": round(FRAME_PERIOD_US, 6),
            "proposed_advancement_margin_80pct_us": round(ADVANCEMENT_MARGIN_US, 6),
        },
        "summary": {
            "worst_discovered_row": w_label,
            "global_max_ack_interval_cycles": global_max_cycles,
            "scope_caveat": "ISR timer excludes entry save and post-stamp footer; not a hardware bound",
            "global_max_full_cf_frame_us": global_max_us,
            "global_max_full_cf_frame_pct_of_period": round(
                global_max_us / FRAME_PERIOD_US * 100.0, 2
            ),
            "global_headroom_to_period_us": round(FRAME_PERIOD_US - global_max_us, 3),
            "global_headroom_to_80pct_margin_us": round(ADVANCEMENT_MARGIN_US - global_max_us, 3),
            "global_within_80pct_margin": global_max_us <= ADVANCEMENT_MARGIN_US,
            "global_deadline_misses": global_overruns,
            "global_max_isr_timer_us": global_perky_max_us,
        },
        "profiler_and_arm_comparisons": {
            "row": w_label,
            "frames": comp_frames,
            "profiler_on_armed": comp_prof_on["ot_emu"]["cf_ack_interval"],
            "profiler_off_armed": comp_prof_off["ot_emu"]["cf_ack_interval"],
            "profiler_on_disarmed": comp_cf_disarmed["ot_emu"]["cf_ack_interval"],
            "ack_work_delta_mean_cf_cycles": overhead_mean_cycles,
            "ack_work_delta_mean_us": round(overhead_mean_cycles * 1e6 / CF_CLOCK_HZ, 3),
            "ack_work_delta_max_cf_cycles": overhead_max_cycles,
            "ack_work_delta_max_us": round(overhead_max_cycles * 1e6 / CF_CLOCK_HZ, 3),
            "cf_synthesis_delta_mean_cf_cycles": cf_synthesis_mean_cycles,
            "cf_synthesis_delta_mean_us": round(cf_synthesis_mean_cycles * 1e6 / CF_CLOCK_HZ, 3),
        },
        "sequencer_split_drift_gate": drift_res,
        "live_part_handoff_gate": {
            "row": w_label,
            "frames": 4000,
            "handoff_generation": part_handoff_run["dtim3_profiler"]["handoff_generation"],
            "cf_ack_interval": part_handoff_run["ot_emu"]["cf_ack_interval"],
            "dtim3_us": part_handoff_run["dtim3_profiler"]["dtim3_us"],
        },
        "mandatory_rows_60s": mandatory_results,
        "extra_rows_60s": extra_results,
        "worst_row_10min": ten_min_run,
    }
    (probe_dir / "TIMING.json").write_text(json.dumps(timing_report, indent=2) + "\n")
    print(f"TIMING REPORT WRITTEN: {probe_dir / 'TIMING.json'} ({timing_report['status']})")
    return 0 if global_overruns == 0 and global_max_us <= ADVANCEMENT_MARGIN_US else 1


if __name__ == "__main__":
    raise SystemExit(main())
