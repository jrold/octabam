#!/usr/bin/env python3
"""Generate exact OT-domain control fixtures for final ColdFire qualification.

The fixtures are derived from the recovered original v1.2.1 update/trigger laws
and from exact assets extracted from the SHA-pinned firmware image. They cover
all 128 OT positions for each of the four sound controls in every physical Mode,
plus a 1024-event four-track sequence where Algo/Mode/all four controls change.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky")]
import fold_control_update as fold  # noqa:E402
import karplus_control_state as karp  # noqa:E402
import noise_tone_control_update as nt  # noqa:E402
import perky_cf_assets  # noqa:E402
from extract_noise_tone_tables import find_m7, parse_container  # noqa:E402

# Resonant Drums' two 257-entry interpolation tables.
INTERP_A = (0x0803237C, 514)
INTERP_B = (0x08032178, 514)

FILENAMES = {
    "pk_asset_pitch": "pitch.bin",
    "pk_asset_chromatic": "chromatic.bin",
    "pk_asset_envelope1": "envelope1.bin",
    "pk_asset_envelope2": "envelope2.bin",
    "pk_asset_m1_wave": "m1.bin",
    "pk_asset_res_interp_a": "interp_a.bin",
    "pk_asset_res_interp_b": "interp_b.bin",
    "pk_asset_wave0": "w0.bin",
    "pk_asset_wave1": "w1.bin",
    "pk_asset_wave2": "w2.bin",
    "pk_asset_wave3": "w3.bin",
    "pk_asset_wt_base": "wt_base.bin",
    "pk_asset_wt_bank": "wt_bank.bin",
}


def write_assets(firmware: Path, out: Path) -> Path:
    assets = perky_cf_assets.extract(firmware)
    root = out / "assets"
    root.mkdir(parents=True, exist_ok=True)
    for symbol, blob in assets.items():
        (root / FILENAMES[symbol]).write_bytes(blob)
    segment = find_m7(parse_container(firmware.read_bytes())[1])
    (root / "interp_a.bin").write_bytes(segment.read(*INTERP_A))
    (root / "interp_b.bin").write_bytes(segment.read(*INTERP_B))
    return root


def write_control_fixtures(assets: Path, out: Path) -> tuple[int, int]:
    pitch = (assets / "pitch.bin").read_bytes()
    chrom = (assets / "chromatic.bin").read_bytes()

    fk = out / "fold_karp_control_fixtures.bin"
    total = 0
    with fk.open("wb") as f:
        f.write(b"PKCT")
        f.write(struct.pack("<I", 1))
        for engine in (0, 1, 2):
            for mode in range(3):
                for ctl in range(4):
                    for value in range(128):
                        vals = [64] * 4  # firmware order Tune,Decay,P1,P2
                        vals[ctl] = value
                        if engine == 0:
                            state = fold.fresh_fold1(mode)
                            c = fold.ControlState()
                            c.prepare(state, vals, mode, pitch, chrom, trig=True)
                        elif engine == 1:
                            state = fold.fresh_fold2(mode, object_address=0x20000000)
                            c = fold.ControlState()
                            c.prepare(
                                state, vals, mode, pitch, chrom, trig=True,
                                fold2=True, object_address=0x20000000,
                            )
                        else:
                            state = karp.fresh_state(mode)
                            c = karp.ControlState()
                            c.prepare(state, vals, mode, pitch, chrom, trig=True)
                        f.write(struct.pack("<BBBBI", engine, mode, ctl, value, len(state)))
                        f.write(state)
                        total += 1

    ntf = out / "nt_control_fixtures.bin"
    payload = bytearray()
    records = 0
    for mode in range(3):
        for ctl in range(4):
            for value in range(128):
                vals = [64] * 4
                vals[ctl] = value
                state = nt.fresh_state(mode)
                c = nt.ControlState()
                c.prepare(state, tuple(vals), mode, pitch, chrom, trig=True)
                payload += struct.pack("<BBBB", mode, ctl, value, 0) + state
                payload += struct.pack(
                    "<II",
                    0x12345678 ^ records,
                    0x9ABCDEF0 ^ ((records * 0x9E3779B9) & 0xFFFFFFFF),
                )
                records += 1
    ntf.write_bytes(b"NTC1" + struct.pack("<I", records) + payload)
    return total, records


class SequenceTrack:
    def __init__(self) -> None:
        self.states: dict[int, bytearray] = {}
        self.controls: dict[int, object] = {}

    def prepare(self, algo: int, mode: int, src: tuple[int, int, int, int],
                track: int, pitch: bytes, chrom: bytes) -> bytearray:
        # SRC is Decay,Tune,P1,P2; recovered firmware order is Tune,Decay,P1,P2.
        raw = (src[1], src[0], src[2], src[3])
        if algo == 0:
            if algo not in self.states:
                self.states[algo] = fold.fresh_fold1(mode)
                self.controls[algo] = fold.ControlState()
            self.controls[algo].prepare(self.states[algo], raw, mode, pitch, chrom, trig=True)
            return self.states[algo]
        if algo == 1:
            if algo not in self.states:
                self.states[algo] = fold.fresh_fold2(
                    mode, object_address=0x20000000 + track * 0x10000
                )
                self.controls[algo] = fold.ControlState()
            self.controls[algo].prepare(
                self.states[algo], raw, mode, pitch, chrom, trig=True,
                fold2=True, object_address=0x20000000 + track * 0x10000,
            )
            return self.states[algo]
        if algo == 2:
            if algo not in self.states:
                self.states[algo] = karp.fresh_state(mode)
                self.controls[algo] = karp.ControlState()
            self.controls[algo].prepare(self.states[algo], raw, mode, pitch, chrom, trig=True)
            return self.states[algo]
        # Noise/Tone maintains independent state for physical M1 and shared M2/M3.
        if 3 not in self.states:
            self.states[3] = nt.fresh_state(0)
            self.controls[3] = nt.ControlState()
            self.states[4] = nt.fresh_state(1)
            self.controls[4] = nt.ControlState()
        key = 3 if mode == 0 else 4
        self.controls[key].prepare(self.states[key], raw, mode, pitch, chrom, trig=True)
        return self.states[key]


def write_sequence(assets: Path, out: Path, count: int = 1024) -> Path:
    pitch = (assets / "pitch.bin").read_bytes()
    chrom = (assets / "chromatic.bin").read_bytes()
    tracks = [SequenceTrack() for _ in range(4)]
    path = out / "perky4_sequence.bin"
    with path.open("wb") as h:
        h.write(b"P4SQ")
        h.write(struct.pack("<I", count))
        for ev in range(count):
            track = ev & 3
            step = ev >> 2
            algo = (step + track * 3) % 4
            mode = (step * 2 + track) % 3
            src = (
                (step * 17 + track * 11) % 128,
                (step * 29 + track * 7) % 128,
                (step * 43 + track * 5) % 128,
                (step * 61 + track * 3) % 128,
            )
            state = tracks[track].prepare(algo, mode, src, track, pitch, chrom)
            h.write(struct.pack("<BBBBBBBBI", track, algo, mode, 1, *src, len(state)))
            h.write(state)
    return path


def generate(firmware: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    assets = write_assets(firmware, out)
    fk, nt_count = write_control_fixtures(assets, out)
    seq = write_sequence(assets, out)
    return {
        "fold_karp_records": fk,
        "noise_tone_records": nt_count,
        "assets": assets,
        "fixture_dir": out,
        "sequence": seq,
        "sequence_records": 1024,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("firmware", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/perky/cf-final-fixtures"))
    args = ap.parse_args()
    r = generate(args.firmware, args.out)
    print(
        "PERKY CF fixtures: PASS "
        f"(Fold/Fold2/Karplus={r['fold_karp_records']}; "
        f"NoiseTone={r['noise_tone_records']}; sequence={r['sequence_records']})"
    )


if __name__ == "__main__":
    main()
