#!/usr/bin/env python3
"""Real-panel user-path gate for ColdFire PERKY Machines.

Unlike verify_perky_cf_userpath.py, this gate does NOT prewrite the PERKY
signature or recorder-buffer donor into the project. It starts T1 as ordinary
FLEX, drives the stock Octatrack panel path in ot_emu to select the custom
PERKY machine, then starts transport and requires non-zero DSP-bound source
PCM. This proves the actual machine-selection hook (pk_sig_write), its
sample-free recorder donor, and the renderer/scheduler handoff execute together
inside the whole-machine emulator.

The longer four-voice gate remains separate; this test exists specifically so a
fixture that manufactures an already-PERKY Part cannot hide a broken chooser or
machine-commit path.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]
import blockdump as bd  # noqa:E402
import ot_project as otp  # noqa:E402
import recloop as rl  # noqa:E402
from ab_fixture import prepare  # noqa:E402

EMU = ROOT / "out/emu/ot_emu"
PY = ROOT / ".venv/bin/python3"
PERKY_SIG = b"PK\x01"
RECORDER_BASE = 128
SIGNIFICANT = 64
MIN_SIGNIFICANT = 128
MIN_DISTINCT = 32


def fail(message: str) -> "NoReturn":
    raise SystemExit("PERKY CF panel user path: FAIL: " + message)


def key(code: int, gap: float = 0.6, hold: float = 0.6):
    return [(gap, f"key {code:#x} down"), (hold, f"key {code:#x} up")]


def fresh_flex_fixture(source: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    """T1 begins as plain FLEX with no PERKY signature/donor, but has a step-1 trig."""
    fixture = prepare(source, destination)
    for bank in fixture.glob("bank*.work"):
        def mutate(data: bytearray) -> None:
            for part in range(otp.NPARTS_ALL):
                file_base = otp.PART_BASE + part * otp.PART_STRIDE
                live_base = file_base + 9
                data[live_base + 0x22] = 1  # stock FLEX machine on T1
                data[file_base + otp.SLOT_OFF + otp.SLOT_KIND["flex"]] = 0
                data[live_base + 60:live_base + 63] = bytes(3)
            at = otp.trac_off(0, 0)
            data[at:at + 8] = (1).to_bytes(8, "big")

        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def write_script(path: pathlib.Path) -> None:
    # This is the already-measured stock panel path used by the Analog BD UI
    # gate: T1 -> SRC SETUP -> custom machine row -> YES. PERKY occupies the
    # same custom row in the final remix. Then close setup and press PLAY.
    events = key(0x10)
    events += [
        (0.6, "key 0x2d down"),
        (0.3, "key 0x22 down"),
        (0.3, "key 0x22 up"),
        (0.3, "key 0x2d up"),
    ]
    for _ in range(6):
        events += key(0x20, 0.25, 0.25)
    events += key(0x31)  # YES: commit PERKY
    events += key(0x32)  # leave SRC SETUP
    # PLAY is key-matrix row 0x25 bit 0 (KEYMAP.md "0x25.0 play"), i.e. live
    # code 0x28. 0x3f is row 0x27 bit 7 -- an encoder push, which never starts
    # the transport, so this gate could not have passed before.
    events += key(0x28)  # PLAY
    events += [(6.0, "quit")]

    elapsed = 0
    rows = []
    for delay, event in events:
        elapsed += round(delay * 1000)
        rows.append(f"{elapsed} {event}\n")
    path.write_text("".join(rows))


def require_audio(classes) -> None:
    audio = rl.track_audio(classes, 1)
    if not audio:
        fail("T1 produced no DSP-bound source record audio after panel selection")
    sig = [v for v in audio if abs(v) > SIGNIFICANT]
    if len(sig) < MIN_SIGNIFICANT:
        fail(f"T1 only produced {len(sig)} samples above {SIGNIFICANT}")
    distinct = len(set(sig))
    if distinct < MIN_DISTINCT:
        fail(f"T1 only produced {distinct} distinct significant samples")
    print(
        f"  PASS T1 panel-selected PERKY: {len(audio)} source samples, "
        f"{len(sig)} significant, {distinct} distinct, peak {max(map(abs, audio))}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--project", type=pathlib.Path, required=True)
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/cf-ui-userpath")
    args = ap.parse_args()

    image = args.image.expanduser().resolve()
    project = args.project.expanduser().resolve()
    work = args.work.expanduser().resolve()
    if not image.is_file():
        fail(f"missing built MAIN OS {image}")
    if not (project / "project.work").is_file():
        fail(f"{project} is not an Octatrack project")
    if not EMU.is_file():
        fail(f"missing {EMU}; run `make emu-cf`")
    if not PY.is_file():
        fail(f"missing {PY}; run `make emu-setup`")

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    fixture = fresh_flex_fixture(project, work / "project")
    card = work / "card.img"
    subprocess.run([
        str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"),
        str(fixture), "OCTABAM", "RIG",
        "--tree", str(work / "tree"), "--out", str(card),
    ], cwd=ROOT, check=True)

    script = work / "panel.script"
    write_script(script)
    dump = work / "blocks.bin"
    log = work / "port.log"
    part = work / "part.bin"
    shadow = work / "shadow.bin"
    spans = f"0x40170f60,6322={part};0x100a4ece,6322={shadow}"
    cmd = [
        str(EMU), "--image", str(image), "--card", str(card),
        "--set", "OCTABAM", "--project", "RIG", "--load-ms", "90000",
        "--mkii", "--dsp", "--dsp-dirty", "123", "--main-level", "64",
        "--block-dump", str(dump), "--mem-dump", spans,
        "--live-script", str(script),
    ]
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n")
        f.flush()
        result = subprocess.run(
            cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=600,
        )
    text = log.read_text(errors="replace")
    if result.returncode:
        fail(f"ot_emu exited {result.returncode}; see {log}")
    for bad in ("ILLEGAL", "BUS ERROR", "ADDRESS ERROR", "FATAL"):
        if bad in text.upper():
            fail(f"emulator reported {bad}; see {log}")
    if "LOAD PROJECT handled" not in text:
        fail(f"project load never completed; see {log}")
    if "ended on quit" not in text:
        fail(f"panel script did not complete cleanly; see {log}")
    if not dump.is_file() or dump.stat().st_size == 0:
        fail("emulator produced no DSP transport block dump")
    if not part.is_file() or not shadow.is_file():
        fail("emulator did not produce Part/SRAM evidence dumps")

    live = part.read_bytes()
    sram = shadow.read_bytes()
    if len(live) < 0x2cc or len(sram) < 0x2cc:
        fail("Part/SRAM evidence dump is too small")
    if live[0x22] != 1 or live[60:63] != PERKY_SIG:
        fail(f"live Part did not commit PERKY through panel path: type={live[0x22]} sig={live[60:63]!r}")
    if sram[0x22] != 1 or sram[60:63] != PERKY_SIG:
        fail(f"SRAM Part mirror did not persist PERKY: type={sram[0x22]} sig={sram[60:63]!r}")
    if live[0x2ca + 1] != RECORDER_BASE:
        fail(f"live T1 FLEX donor={live[0x2ca + 1]}, expected recorder object {RECORDER_BASE}")
    if sram[0x2ca + 1] != RECORDER_BASE:
        fail(f"SRAM T1 FLEX donor={sram[0x2ca + 1]}, expected recorder object {RECORDER_BASE}")

    require_audio(bd.classes(bd.read(dump)))
    print("PERKY CF REAL PANEL USER PATH: PASS")
    print("  stock panel selected PERKY from an ordinary FLEX T1")
    print("  live Part + SRAM mirror contain PK/1 and recorder-buffer donor R1")
    print("  PLAY/sequencer after that selection produced nonzero T1 DSP-bound PCM")
    print("  MKII panel path completed without illegal/bus/address/fatal errors")
    print(f"  evidence: {log} / {dump} / {part} / {shadow}")


if __name__ == "__main__":
    main()
