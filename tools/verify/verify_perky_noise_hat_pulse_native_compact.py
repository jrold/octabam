#!/usr/bin/env python3
"""Compile/run the local native-layout vs 59-word Pulse Stack PCM differential."""
from __future__ import annotations

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'tools/verify/noise_hat_pulse_native_compact.cpp'
OUT = ROOT / 'out/perky/noise-hat-pulse-native-compact'
BIN = OUT / 'noise_hat_pulse_native_compact'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    compile_result = subprocess.run(
        ['c++', '-std=c++20', '-O2', str(SRC), '-o', str(BIN)],
        capture_output=True,
        text=True,
    )
    if compile_result.returncode:
        raise SystemExit(
            'Pulse Stack native/compact compile failed:\n'
            + compile_result.stdout[-2000:]
            + compile_result.stderr[-4000:]
        )

    result = subprocess.run([str(BIN)], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(
            'Pulse Stack native/compact PCM differential failed:\n'
            + result.stdout[-2000:]
            + result.stderr[-4000:]
        )
    print(result.stdout.strip())


if __name__ == '__main__':
    main()
