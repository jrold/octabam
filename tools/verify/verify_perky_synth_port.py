#!/usr/bin/env python3
"""Exercise the complete synthetic PERKY Noise/Tone canary on both DSP cores.

This is intentionally separate from verify_perky_probe_port.py. The impulse
probe proves transport; this gate proves the table-loaded complete synth image
produces a sustained multi-sample source through the stock AMP/FX continuation.

Requires:
  * OT_PROJECT=<stock project fixture>
  * out/mainos_perky_synth.bin, normally built with
      python3 tools/perky/build_synth_canary.py

No hardware is flashed by this script.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]

import ot_project as otp  # noqa:E402
import blockdump as bd  # noqa:E402
import recloop as rl  # noqa:E402
from ab_fixture import prepare  # noqa:E402

ENGINE = int(os.environ.get("PERKY_TEST_ENGINE", "10"))
assert ENGINE in (0, 2, 10), "only qualified engine candidates can enter this gate"
OUT = ROOT / f"out/perky/synth-port-engine-{ENGINE}"
TRACKS = (1, 5)
BLOCKED_TRACKS = (2, 3, 4, 6, 7, 8)
DEFAULT_IMAGE = ROOT / "out/mainos_perky_synth.bin"
SIGNIFICANT = 100
MIN_SIGNIFICANT_SAMPLES = 16
MIN_DISTINCT_VALUES = 5


def fail(msg: str) -> None:
    raise AssertionError(f"PERKY synth port: {msg}")


def signed_records(classes, core: int):
    addrs = {
        1: (0x80001C90, 0x80002710),
        0: (0x800021D0, 0x80002C50),
    }[core]
    records = sorted(sum((classes.get((">", 0, core, addr), []) for addr in addrs), []))
    return [words for _, words in records
            if len(words) >= 4 and words[0] == 0x504B and words[2] == 0x5931]


def configure_fixture(project: str, *, engine: int = ENGINE, name: str = "project") -> Path:
    fixture = prepare(project, OUT / name)
    for bank in fixture.glob("bank*.work"):
        def mutate(data):
            for part in range(8):
                base = otp.PART_BASE + part * otp.PART_STRIDE + 9
                for track in range(8):
                    data[base + 0x22 + track] = 1  # FLEX transport donor
                    data[base + 60 + 30 * track:base + 63 + 30 * track] = b"PK\x01"
                    defaults = (64, 64, 64, 64, 0, 0, 0, 0, 0, 0, 0, engine) if track != 4 else (127, 127, 127, 0, 0, 0, 2, 0, 0, 0, 0, engine)
                    for slot, value in enumerate(defaults):
                        off = (0x2a if slot < 6 else 0x1da) + 30 * track + 6 + slot % 6
                        data[base + off] = value
                    data[base + track] = 0         # FX1 NONE
                    data[base + 8 + track] = 0     # FX2 NONE
            for track in range(8):
                at = otp.trac_off(0, track)
                data[at:at + 8] = (1).to_bytes(8, "big")  # one trig at step 0

        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def main() -> None:
    project = os.environ.get("OT_PROJECT")
    if not project:
        print("[SKIP] PERKY synth port: set OT_PROJECT to a stock project fixture")
        return

    image_src = Path(os.environ.get("PERKY_SYNTH_IMAGE", DEFAULT_IMAGE))
    if not image_src.exists():
        fail(
            f"missing {image_src}; build it first with "
            "`python3 tools/perky/build_synth_canary.py`"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    fixture = configure_fixture(project)
    card = OUT / "card.img"
    subprocess.run([
        sys.executable,
        str(ROOT / "tools/emu/ot_emu/stage_card.py"),
        str(fixture),
        "OCTABAM",
        "RIG",
        "--tree",
        str(OUT / "tree"),
        "--out",
        str(card),
    ], check=True, cwd=ROOT)

    image = OUT / "image.bin"
    shutil.copy2(image_src, image)
    dump = OUT / "blocks.bin"
    basewav = OUT / "audio"
    log_path = OUT / "port.log"

    cmd = [
        os.environ.get("PERKY_EMU", str(ROOT / "out/emu/ot_emu")),
        "--image", str(image),
        "--card", str(card),
        "--set", "OCTABAM",
        "--project", "RIG",
        "--load-ms", "90000",
        "--sequencer",
        "--internal-clock",
        "--bank", "0",
        "--frames", "32000",
        "--dsp",
        "--dsp-dirty", "123",
        "--main-level", "64",
        "--audio-out", str(basewav),
        "--block-dump", str(dump),
    ]

    with log_path.open("w") as log:
        log.write(" ".join(cmd) + "\n")
        log.flush()
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=600,
                       stdout=log, stderr=subprocess.STDOUT)

    # Same signed-source continuation with an unsupported engine produces exact
    # zero source PCM. Ordinary FLEX may skip AMP entirely on its first frames,
    # so it cannot provide a matching dirty-AMP startup control for this seam.
    # The DSP dispatcher rejects 99 and still resumes the original AMP/FX code.
    silent_fixture = configure_fixture(project, engine=99, name='silent-project')
    silent_card = OUT / 'silent-card.img'
    subprocess.run([sys.executable, str(ROOT / 'tools/emu/ot_emu/stage_card.py'),
                    str(silent_fixture), 'OCTABAM', 'RIG', '--tree',
                    str(OUT / 'silent-tree'), '--out', str(silent_card)], check=True, cwd=ROOT)
    baseline_dump = OUT / 'stock-dirty.bin'
    baseline_cmd = list(cmd)
    baseline_cmd[baseline_cmd.index('--card') + 1] = str(silent_card)
    baseline_cmd[baseline_cmd.index('--frames') + 1] = '2600'
    baseline_cmd[baseline_cmd.index('--block-dump') + 1] = str(baseline_dump)
    audio_at = baseline_cmd.index('--audio-out')
    del baseline_cmd[audio_at:audio_at + 2]
    with (OUT / 'stock-dirty.log').open('w') as log:
        subprocess.run(baseline_cmd, cwd=ROOT, check=True, timeout=600,
                       stdout=log, stderr=subprocess.STDOUT)
    verify_outputs(log_path, dump, baseline_dump)


def verify_outputs(log_path, dump, baseline_dump):
    log = log_path.read_text()
    baseline = bd.classes(bd.read(baseline_dump))
    if "ILLEGAL" in log:
        fail("emulator hit ILLEGAL")
    if not re.search(r"frames run\s*:\s*32000", log):
        fail("emulator did not complete all 32000 frames")

    classes = bd.classes(bd.read(dump))
    summaries = []
    for track, core in ((1, 1), (5, 0)):
        packets = signed_records(classes, core)
        if not packets:
            fail(f"T{track}/core {core}: no PK/Y1 transport records")
        if not any((packet[3] & 0xFFFF) == 1 for packet in packets):
            fail(f"T{track}/core {core}: PK/Y1 records never carried a trig")

        assert any(len(p) >= 20 and p[19] == ENGINE for p in packets), "production engine record missing"
        if ENGINE == 2:
            assert any(any(v > 127 for v in p[8:16]) for p in packets if len(p) >= 20), "prepared 16-bit record byte transport missing"

        left = rl.readback_audio(classes, track)
        right = rl.readback_audio(classes, track, True)
        if not left or not right:
            fail(f"T{track}/core {core}: no post-chain readback")
        # Stock AMP/DC-filter state has dirty-memory startup tails and a
        # small deterministic DC floor. Measure it with the SAME stock card.
        bl = rl.readback_audio(baseline, track)
        br = rl.readback_audio(baseline, track, True)
        from statistics import median
        bias = int(median(a - b for a, b in zip(bl[-1024:], br[-1024:])))
        error = max(abs(a - b - bias) for a, b in zip(left[4096:], right[4096:]))
        if error > 2:
            fail(f"T{track}/core {core}: L/R residual {error} exceeds measured stock bias {bias} + 2 LSB rounding")

        significant = [sample for sample in left[4096:] if abs(sample) > SIGNIFICANT]
        if len(significant) < MIN_SIGNIFICANT_SAMPLES:
            fail(
                f"T{track}/core {core}: only {len(significant)} samples exceed "
                f"{SIGNIFICANT}; looks like silence/impulse, not the synth"
            )
        distinct = len(set(significant))
        if distinct < MIN_DISTINCT_VALUES:
            fail(
                f"T{track}/core {core}: only {distinct} distinct significant "
                "values; source does not look synthesized"
            )
        peak = max(map(abs, left))
        summaries.append((track, core, len(significant), distinct, peak))
        print(
            f"PASS T{track}/core {core}: {len(significant)} significant samples, "
            f"{distinct} distinct values, peak {peak}"
        )

    # Every audio track carries PERKY in this fixture. The admission guard
    # must keep the other six silent instead of overrunning either core.
    for track in BLOCKED_TRACKS:
        for right_channel in (False, True):
            audio = rl.readback_audio(classes, track, right_channel)
            stock_audio = rl.readback_audio(baseline, track, right_channel)
            assert audio and audio[:len(stock_audio)] == stock_audio, f'T{track}: blocked voice differs from stock silence'
            assert max(map(abs, audio[4096:])) <= max(map(abs, stock_audio[4096:])) + 2
    live_events = re.findall(r'frame\s+(\d+) track [04] byte 0x10', log)
    assert any(int(frame) > 1000 for frame in live_events), 'transport never reached a later trig'
    if len(summaries) != 2:
        fail("did not qualify both DSP cores")
    print("PASS PERKY synth canary: both DSP cores, 32000 frames with dirty memory, "
          "later trigs, varying stereo-matched post-chain audio, six excess voices silent")


if __name__ == "__main__":
    main()
