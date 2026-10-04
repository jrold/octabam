#!/usr/bin/env python3
"""Fabricate deterministic PERKY Noise/Tone development fixtures.

These fixtures are SYNTHETIC. They are intentionally shaped like the real
Noise/Tone assets/captures so the Octabam port can exercise its packers,
render primitives and control-analysis tooling without a PĒRKONS firmware
image. They must never be presented as measured firmware data.

Outputs:

  <out>/tables/
      envelope1.bin
      envelope2.bin
      wave_10000000.bin .. wave_10000600.bin
      manifest.json
      state.bin

  <out>/control.jsonl

The table geometry exactly matches the validated native renderer:
  * 2 x 2048 little-endian u16 envelope curves
  * 4 x 256 little-endian s16 waveform tables
  * 0x120-byte prepared-state-shaped blob with wave pointers at the four
    offsets consumed by extract_noise_tone_tables.py

The control JSONL uses the same record shape consumed by
perky_control_analyze.py but declares synthetic=true in the header. The state
mutations are deterministic stand-ins that exercise ownership, smoothing,
trigger and pairwise-analysis paths; they are not the real PĒRKONS update()
curves.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct

STATE_BYTES = 0x120
WRAPPER_BYTES = 0x40
CONTROL_BYTES = 0x10
WAVE_SAMPLES = 256
ENVELOPE_SAMPLES = 2048
WAVE_POINTER_OFFSETS = (0x38, 0x3C, 0xD0, 0xD4)
WAVE_ADDRESSES = (0x10000000, 0x10000200, 0x10000400, 0x10000600)
CONTROL_ANCHORS = (0, 1, 512, 1024, 1536, 2047, 2048, 2049,
                   2560, 3072, 3584, 4094, 4095)
VELOCITY_ANCHORS = (1, 64, 127, 192, 255)
NOTE_ANCHORS = (24, 36, 45, 48, 60, 72, 96)
MODES = (0, 2)


def clamp_u16(v: int) -> int:
    return max(0, min(0xFFFF, int(v)))


def pack_u16(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}H", *(v & 0xFFFF for v in values))


def pack_s16(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}h", *(max(-32768, min(32767, v)) for v in values))


def envelope_linear() -> list[int]:
    return [round(i * 65535 / (ENVELOPE_SAMPLES - 1)) for i in range(ENVELOPE_SAMPLES)]


def envelope_ease() -> list[int]:
    # Smooth monotonic S-curve with intentionally small local deltas. This is
    # useful for testing the realtime block-delta storage planner.
    out = []
    for i in range(ENVELOPE_SAMPLES):
        x = i / (ENVELOPE_SAMPLES - 1)
        y = x * x * (3.0 - 2.0 * x)
        out.append(clamp_u16(round(y * 65535.0)))
    return out


def waves() -> list[list[int]]:
    sine = [round(math.sin(2.0 * math.pi * i / WAVE_SAMPLES) * 30000.0)
            for i in range(WAVE_SAMPLES)]
    saw = [round((-1.0 + 2.0 * i / WAVE_SAMPLES) * 30000.0)
           for i in range(WAVE_SAMPLES)]
    tri = []
    for i in range(WAVE_SAMPLES):
        x = i / WAVE_SAMPLES
        y = 4.0 * abs(x - math.floor(x + 0.5)) - 1.0
        tri.append(round(y * 30000.0))
    square = [28000 if i < WAVE_SAMPLES // 2 else -28000
              for i in range(WAVE_SAMPLES)]
    return [sine, saw, tri, square]


def emit_tables(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    envs = [envelope_linear(), envelope_ease()]
    files = []
    for idx, values in enumerate(envs, 1):
        name = f"envelope{idx}.bin"
        blob = pack_u16(values)
        (root / name).write_bytes(blob)
        files.append({"file": name, "address": f"synthetic:env{idx}", "bytes": len(blob)})

    for address, values in zip(WAVE_ADDRESSES, waves()):
        name = f"wave_{address:08x}.bin"
        blob = pack_s16(values)
        (root / name).write_bytes(blob)
        files.append({"file": name, "address": f"0x{address:08x}", "bytes": len(blob)})

    state = bytearray(STATE_BYTES)
    for off, address in zip(WAVE_POINTER_OFFSETS, WAVE_ADDRESSES):
        struct.pack_into("<I", state, off, address)
    (root / "state.bin").write_bytes(state)

    manifest = {
        "schema": "perky-noise-tone-synthetic-tables-v1",
        "synthetic": True,
        "source_image": None,
        "product": "SYNTHETIC -- NOT PĒRKONS DATA",
        "state_file": "state.bin",
        "wave_addresses": [f"0x{x:08x}" for x in WAVE_ADDRESSES],
        "files": files,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def set_u16(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", buf, off, value & 0xFFFF)


def set_u32(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", buf, off, value & 0xFFFFFFFF)


def synthetic_state(mode: int, controls: tuple[int, int, int, int], iteration: int) -> bytearray:
    """Deterministic state with realistic field ownership, not real curves."""
    state = bytearray(STATE_BYTES)
    p0, p1, p2, p3 = controls
    t = max(0, min(16, iteration))

    # Preserve the four synthetic wave pointers in the same slots the native
    # renderer consumes, including current/next pairs for both oscillators.
    for off, address in zip(WAVE_POINTER_OFFSETS, WAVE_ADDRESSES):
        set_u32(state, off, address)

    # p0: pitch -> both oscillator increments, with one-pole-ish movement over
    # 16 update passes. p1: envelope times. p2: filter/noise texture. p3: mix.
    pitch_target = 0x1000 + p0 * 0x180
    pitch = (0x1000 * (16 - t) + pitch_target * t) // 16
    set_u32(state, 0x34, pitch)
    set_u32(state, 0xCC, pitch + (0x80 if mode == 2 else 0))

    attack = 1 + p1 // 16
    decay = 1 + (4095 - p1) // 8
    set_u16(state, 0x74 + 0x20, attack)
    set_u16(state, 0x74 + 0x22, decay)
    state[0x74 + 1] = 1 if mode == 0 else 2

    set_u16(state, 0x60 + 2, 1 + p2 // 128)
    set_u16(state, 0x9C + 0x0C, 0x0200 + p2 // 4)
    set_u16(state, 0x9C + 0x0E, 0x1000 + p2 * 8)

    mix_target = p3 << 8
    mix = (0x80000 * (16 - t) + mix_target * t) // 16
    set_u32(state, 0xF8, mix)

    # A small explicit pairwise term so the analyzer's cross-term path is
    # exercised. This byte is outside the live renderer fields on purpose.
    state[0x11F] = ((p0 >> 8) ^ (p3 >> 8) ^ (mode << 5)) & 0xFF
    return state


def synthetic_wrapper(mode: int, velocity: int, note: int, triggered: bool = False) -> bytearray:
    wrapper = bytearray(WRAPPER_BYTES)
    wrapper[4] = 0  # synthetic internal algorithm id for Noise/Tone
    wrapper[5] = mode & 0xFF
    wrapper[6] = velocity & 0xFF
    wrapper[7] = note & 0xFF
    if triggered:
        wrapper[0x10] = 1
    return wrapper


def emit_record(fh, *, phase: str, mode: int, controls: tuple[int, int, int, int],
                iteration: int, velocity: int, note: int, state: bytearray,
                wrapper: bytearray, sweep: str, sweep_parameter: int,
                sweep_value: int) -> None:
    control_ram = struct.pack("<4I", *controls)
    rec = {
        "type": "snapshot",
        "phase": phase,
        "mode": mode,
        "controls": list(controls),
        "iteration": iteration,
        "velocity": velocity,
        "note": note,
        "sweep": sweep,
        "sweep_parameter": sweep_parameter,
        "sweep_value": sweep_value,
        "state": bytes(state).hex(),
        "wrapper": bytes(wrapper).hex(),
        "control_ram": control_ram.hex(),
        "synthetic": True,
    }
    fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def emit_controls(path: Path, pairwise: bool = True) -> None:
    with path.open("w", encoding="utf-8") as fh:
        header = {
            "type": "header",
            "schema": "perkybits-control-v1",
            "synthetic": True,
            "warning": "FABRICATED DEVELOPMENT FIXTURE -- NOT PĒRKONS MEASUREMENT",
            "state_bytes": STATE_BYTES,
            "slot": 4,
            "panel_algorithm": 1,
            "internal_algorithm": 0,
            "shared_modes": list(MODES),
        }
        fh.write(json.dumps(header, separators=(",", ":")) + "\n")

        for mode in MODES:
            for parameter in range(4):
                for value in CONTROL_ANCHORS:
                    controls = [2048, 2048, 2048, 2048]
                    controls[parameter] = value
                    c = tuple(controls)
                    for iteration in range(17):
                        emit_record(
                            fh, phase="target-written" if iteration == 0 else "update",
                            mode=mode, controls=c, iteration=iteration,
                            velocity=255, note=45,
                            state=synthetic_state(mode, c, iteration),
                            wrapper=synthetic_wrapper(mode, 255, 45),
                            sweep="control", sweep_parameter=parameter,
                            sweep_value=value)

            base = (2048, 2048, 2048, 2048)
            for velocity in VELOCITY_ANCHORS:
                before = synthetic_state(mode, base, 16)
                after = bytearray(before)
                after[6] = velocity
                after[0x74 + 7] = 1
                emit_record(fh, phase="pre-trigger", mode=mode, controls=base,
                            iteration=16, velocity=velocity, note=45,
                            state=before, wrapper=synthetic_wrapper(mode, velocity, 45),
                            sweep="velocity", sweep_parameter=-1, sweep_value=velocity)
                emit_record(fh, phase="post-trigger", mode=mode, controls=base,
                            iteration=17, velocity=velocity, note=45,
                            state=after, wrapper=synthetic_wrapper(mode, velocity, 45, True),
                            sweep="velocity", sweep_parameter=-1, sweep_value=velocity)

            for note in NOTE_ANCHORS:
                before = synthetic_state(mode, base, 16)
                after = bytearray(before)
                set_u32(after, 0x34, 0x1000 + note * 0x800)
                set_u32(after, 0xCC, 0x1000 + note * 0x800 + (0x80 if mode == 2 else 0))
                emit_record(fh, phase="pre-trigger", mode=mode, controls=base,
                            iteration=16, velocity=255, note=note,
                            state=before, wrapper=synthetic_wrapper(mode, 255, note),
                            sweep="note", sweep_parameter=-1, sweep_value=note)
                emit_record(fh, phase="post-trigger", mode=mode, controls=base,
                            iteration=17, velocity=255, note=note,
                            state=after, wrapper=synthetic_wrapper(mode, 255, note, True),
                            sweep="note", sweep_parameter=-1, sweep_value=note)

            if pairwise:
                anchors = (0, 2048, 4095)
                for a in range(4):
                    for b in range(a + 1, 4):
                        for av in anchors:
                            for bv in anchors:
                                controls = [2048, 2048, 2048, 2048]
                                controls[a] = av
                                controls[b] = bv
                                c = tuple(controls)
                                emit_record(
                                    fh, phase="settled", mode=mode, controls=c,
                                    iteration=16, velocity=255, note=45,
                                    state=synthetic_state(mode, c, 16),
                                    wrapper=synthetic_wrapper(mode, 255, 45),
                                    sweep="pairwise", sweep_parameter=a * 10 + b,
                                    sweep_value=av * 4096 + bv)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("out/perky/synthetic"))
    ap.add_argument("--no-pairwise", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    emit_tables(args.out / "tables")
    emit_controls(args.out / "control.jsonl", pairwise=not args.no_pairwise)
    print(f"wrote synthetic PERKY fixtures under {args.out}")
    print("WARNING: synthetic development data; not measured PĒRKONS firmware output")


if __name__ == "__main__":
    main()
