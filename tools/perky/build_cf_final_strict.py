#!/usr/bin/env python3
"""Strict local PERKY release entry point.

Runs the normal final builder, but extends its whole-machine release gate with
verify_perky_cf_ui_userpath.py before any flashable card/MIDI wrapper is
created. The existing long four-voice sequencer/FLEX gate still runs unchanged;
this additional gate starts from plain FLEX and selects PERKY through the real
MKII panel path so pk_sig_write + recorder-donor scheduling cannot be bypassed
by a pre-seeded fixture.

No GitHub Actions/CI are involved. This file is the hardware-release entry point
for PERKY Machines until the panel-path gate is folded into the base builder.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/perky"))
import build_cf_final as base  # noqa:E402

UI_GATE = ROOT / "tools/verify/verify_perky_cf_ui_userpath.py"
UI_GATE_GIT_BLOB = "62551b5f7887d75d02c4725ae4a75579ac72aeeb"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = b"blob " + str(len(data)).encode() + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def require_ui_gate_identity() -> None:
    if not UI_GATE.is_file():
        raise SystemExit(f"build-perky-cf-strict: missing {UI_GATE}")
    got = git_blob_sha(UI_GATE)
    if got != UI_GATE_GIT_BLOB:
        raise SystemExit(
            "build-perky-cf-strict: real-panel gate source drift: "
            f"git:{got} != git:{UI_GATE_GIT_BLOB}"
        )
    print(f"PERKY real-panel gate identity: PASS (git:{got})")


def arg_after(cmd, option: str) -> str:
    values = list(map(str, cmd))
    try:
        return values[values.index(option) + 1]
    except (ValueError, IndexError):
        raise SystemExit(f"build-perky-cf-strict: base gate omitted required {option}")


def main() -> None:
    require_ui_gate_identity()
    original_run = base.run
    panel_gate_seen = False

    def strict_run(cmd) -> None:
        nonlocal panel_gate_seen
        original_run(cmd)
        values = list(map(str, cmd))
        if any(v.endswith("tools/verify/verify_perky_cf_userpath.py") for v in values):
            image = arg_after(values, "--image")
            project = arg_after(values, "--project")
            work = Path(arg_after(values, "--work"))
            ui_work = work.parent / "ui-userpath"
            print("=== PERKY CF STRICT: real MKII panel machine-selection + audio gate ===")
            original_run([
                sys.executable, UI_GATE,
                "--image", image,
                "--project", project,
                "--work", ui_work,
            ])
            panel_gate_seen = True

    # The base builder does not reach wrapper creation until after its existing
    # four-voice emulator gate and stock-DSP identity test. Intercepting run()
    # here places the real-panel test directly after that emulator gate and
    # therefore before wrap_flashable().
    base.run = strict_run
    original_wrap = base.wrapper.wrap_flashable

    def guarded_wrap(mainos, version):
        if not panel_gate_seen:
            raise SystemExit(
                "build-perky-cf-strict: refusing flashable wrapper; "
                "real-panel emulator gate did not execute"
            )
        return original_wrap(mainos, version)

    base.wrapper.wrap_flashable = guarded_wrap
    base.main()
    if not panel_gate_seen:
        raise SystemExit("build-perky-cf-strict: real-panel gate was never reached")
    print("PERKY CF STRICT RELEASE: PASS")
    print("  PCM/native PerkyBits gate : PASS (base builder)")
    print("  four-voice ot_emu gate    : PASS (base builder)")
    print("  real-panel ot_emu gate    : PASS")
    print("  flashable wrappers         : emitted only after all gates")


if __name__ == "__main__":
    main()
